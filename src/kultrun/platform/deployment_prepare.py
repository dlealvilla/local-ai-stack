"""Plan-driven acquisition and resource admission. Stops before InferenceInstance.

Composition-owned. Acquisition still owns download/verify. ResourceManager
still owns live admission. This service consumes a CURRENT DeploymentPlan.
On a footprint/storage rejection it may invoke the bounded storage-replan
seam once, then consume the new CURRENT plan. It does not launch.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.acquisition import AcquisitionService
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    AcquisitionId,
    AcquisitionReceipt,
    ArtifactId,
    ArtifactState,
    ModelAcquisitionRequest,
    ModelArtifact,
    ModelCatalogEntry,
)
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import DeploymentPlan, DeploymentPlanStatus
from kultrun.platform.admission import AdmissionService, artifact_matches_plan
from kultrun.platform.deployment_plan import DeploymentPlanOverview
from kultrun.platform.storage_acquire import StorageAwareAcquisition
from kultrun.platform.storage_replan import (
    ReplanOutcome,
    ReplanStage,
    StorageReplanService,
)
from kultrun.resource.contracts import (
    AdmissionDecision,
    AdmissionVerdict,
    ResourceRequest,
)
from kultrun.storage.contracts import StorageSanityEvidence
from kultrun.storage.reduction import (
    is_footprint_retryable,
    is_manual_capacity_required,
)


@dataclass(frozen=True, slots=True)
class PlanAcquisitionResult:
    """Acquire/reuse outcome for a CURRENT plan. Not a reservation."""

    plan: DeploymentPlan
    plan_status: DeploymentPlanStatus
    artifact: ModelArtifact
    receipt: AcquisitionReceipt

    def payload(self) -> dict[str, object]:
        return {
            "plan_id": _token(self.plan.plan_id),
            "plan_basis": _token(self.plan.plan_basis),
            "plan_status": self.plan_status.value,
            "model_id": self.plan.model_id.value,
            "selected_model": self.plan.logical_name.value,
            "source_ref": self.plan.source_ref,
            "source_revision": _token(self.plan.source_revision),
            "quantization": _token(self.plan.quantization),
            "artifact": self.artifact,
            "artifact_id": self.artifact.artifact_id.value,
            "receipt": self.receipt,
            "acquisition": {
                "outcome": self.receipt.outcome,
                "reused": self.receipt.reused,
                "artifact_id": self.artifact.artifact_id.value,
            },
            "admit": False,
            "launch": False,
            "instance": False,
        }


@dataclass(frozen=True, slots=True)
class PreparedDeployment:
    """Non-persisted acquire+admit result. Not an InferenceInstance."""

    plan: DeploymentPlan
    plan_status: DeploymentPlanStatus
    artifact: ModelArtifact
    receipt: AcquisitionReceipt | None
    request: ResourceRequest | None
    decision: AdmissionDecision | None

    def payload(self) -> dict[str, object]:
        reservation = self.decision.reservation if self.decision is not None else None
        reused = self.receipt.reused if self.receipt is not None else True
        outcome = (
            self.receipt.outcome
            if self.receipt is not None
            else ("reused" if reused else "stored")
        )
        return {
            "plan_id": _token(self.plan.plan_id),
            "plan_basis": _token(self.plan.plan_basis),
            "plan_status": self.plan_status.value,
            "model_id": self.plan.model_id.value,
            "selected_model": self.plan.logical_name.value,
            "source_ref": self.plan.source_ref,
            "source_revision": _token(self.plan.source_revision),
            "quantization": _token(self.plan.quantization),
            "artifact": self.artifact,
            "artifact_id": self.artifact.artifact_id.value,
            "receipt": self.receipt,
            "request": self.request,
            "decision": self.decision,
            "reservation": reservation,
            "acquisition": {
                "outcome": outcome,
                "reused": reused,
                "artifact_id": self.artifact.artifact_id.value,
            },
            "admission": _admission_payload(self.decision),
            "launch": False,
            "instance": False,
        }


class DeploymentPreparationService:
    """CURRENT plan → artifact → ResourceRequest → ResourceManager. Stop."""

    def __init__(
        self,
        overview: Callable[[HostCapabilities], DeploymentPlanOverview],
        models: ModelCatalogue,
        acquisition: AcquisitionService,
        inventory: ModelInventory,
        admission: AdmissionService,
        capacity: CapacityService,
        stored_sanity: Callable[[HostCapabilities], dict[str, StorageSanityEvidence]],
        clock: Clock,
        storage_acquire: StorageAwareAcquisition | None = None,
        replan: StorageReplanService | None = None,
    ) -> None:
        self._overview = overview
        self._models = models
        self._acquisition = acquisition
        self._inventory = inventory
        self._admission = admission
        self._capacity = capacity
        self._stored_sanity = stored_sanity
        self._clock = clock
        self._storage_acquire = storage_acquire
        self._replan = replan

    def acquire(
        self, host: HostCapabilities, *, _replanned: bool = False
    ) -> PlanAcquisitionResult:
        """Ensure the CURRENT plan's exact artifact exists. Does not admit."""
        try:
            return self._acquire_once(host)
        except PreconditionFailedError as error:
            if _replanned or not self._maybe_replan(host, error=error):
                raise
            return self.acquire(host, _replanned=True)

    def _acquire_once(self, host: HostCapabilities) -> PlanAcquisitionResult:
        overview = self._overview(host)
        plan = require_current_plan(overview)
        entry = catalog_entry_for_plan(self._models, plan)
        existing = find_plan_artifact(self._inventory, plan)
        if existing is not None:
            receipt = _reused_receipt(existing, self._clock)
            return PlanAcquisitionResult(
                plan=plan,
                plan_status=overview.status,
                artifact=existing,
                receipt=receipt,
            )
        envelope = self._capacity.compute(host, self._stored_sanity(host))
        if self._storage_acquire is not None:
            receipt = self._storage_acquire.acquire(
                acquisition_request_for_plan(plan, entry),
                host,
                self._stored_sanity(host),
            )
        else:
            receipt = self._acquisition.acquire(
                acquisition_request_for_plan(plan, entry),
                envelope,
                host.host_id,
            )
        artifact = self._inventory.get(receipt.artifact_id)
        if (
            artifact is None
            or receipt.state is not ArtifactState.STORED
            or artifact.state is not ArtifactState.STORED
        ):
            reason = (
                str(receipt.failure_reason)
                if is_resolved(receipt.failure_reason)
                else "acquisition_failed"
            )
            raise PreconditionFailedError(
                "plan acquisition did not produce a stored artifact",
                reason=reason,
                artifact_id=receipt.artifact_id.value,
            )
        if not artifact_matches_plan(artifact, plan):
            raise PreconditionFailedError(
                "acquired artifact does not match the current deployment plan",
                reason="artifact_plan_mismatch",
                artifact_id=artifact.artifact_id.value,
            )
        return PlanAcquisitionResult(
            plan=plan,
            plan_status=overview.status,
            artifact=artifact,
            receipt=receipt,
        )

    def admit(
        self,
        host: HostCapabilities,
        artifact_id: ArtifactId | None = None,
        *,
        _replanned: bool = False,
    ) -> PreparedDeployment:
        """Admit the CURRENT plan against a matching stored artifact."""
        prepared = self._admit_once(host, artifact_id)
        _raise_if_manual_capacity(prepared.decision)
        if _replanned or not self._rejected_storage(prepared.decision):
            return prepared
        code = (
            str(prepared.decision.reason_code) if prepared.decision is not None else ""
        )
        if self._maybe_replan(host, code=code, plan=prepared.plan):
            return self.admit(host, artifact_id, _replanned=True)
        return prepared

    def _admit_once(
        self,
        host: HostCapabilities,
        artifact_id: ArtifactId | None,
    ) -> PreparedDeployment:
        overview = self._overview(host)
        plan = require_current_plan(overview)
        artifact = self._artifact_for_admit(plan, artifact_id)
        request, decision = self._admission.reserve_for_plan(
            plan, artifact, host, self._stored_sanity(host)
        )
        return PreparedDeployment(
            plan=plan,
            plan_status=overview.status,
            artifact=artifact,
            receipt=None,
            request=request,
            decision=decision,
        )

    def prepare(
        self, host: HostCapabilities, *, _replanned: bool = False
    ) -> PreparedDeployment:
        """Acquire/reuse then admit. Does not create an InferenceInstance."""
        try:
            acquired = self._acquire_once(host)
        except PreconditionFailedError as error:
            if _replanned or not self._maybe_replan(host, error=error):
                raise
            return self.prepare(host, _replanned=True)
        overview = self._overview(host)
        plan = require_current_plan(overview)
        if not artifact_matches_plan(acquired.artifact, plan):
            raise PreconditionFailedError(
                "acquired artifact does not match the current deployment plan",
                reason="artifact_plan_mismatch",
                artifact_id=acquired.artifact.artifact_id.value,
            )
        request, decision = self._admission.reserve_for_plan(
            plan, acquired.artifact, host, self._stored_sanity(host)
        )
        prepared = PreparedDeployment(
            plan=plan,
            plan_status=overview.status,
            artifact=acquired.artifact,
            receipt=acquired.receipt,
            request=request,
            decision=decision,
        )
        _raise_if_manual_capacity(decision)
        if _replanned or not self._rejected_storage(decision):
            return prepared
        code = str(decision.reason_code)
        if self._maybe_replan(host, code=code, plan=plan):
            return self.prepare(host, _replanned=True)
        return prepared

    def _rejected_storage(self, decision: AdmissionDecision | None) -> bool:
        if decision is None or decision.verdict is AdmissionVerdict.ADMITTED:
            return False
        code = decision.reason_code
        return isinstance(code, str) and is_footprint_retryable(code)

    def _maybe_replan(
        self,
        host: HostCapabilities,
        *,
        error: PreconditionFailedError | None = None,
        code: str | None = None,
        plan: DeploymentPlan | None = None,
    ) -> bool:
        if self._replan is None:
            return False
        if error is not None:
            code = str(error.context.get("reason") or "")
        if isinstance(code, str) and is_manual_capacity_required(code):
            raise PreconditionFailedError(
                "automatic storage capacity is unresolved; "
                "administrator capacity may be supplied as last resort",
                reason="manual_capacity_required",
            )
        if not isinstance(code, str) or not is_footprint_retryable(code):
            return False
        if plan is None:
            stored = self._overview(host).plan
            plan = stored
        identity = plan.model_id.value if plan is not None else "unselected"
        footprint = _plan_footprint(plan)
        if footprint <= 0:
            return False
        report = self._replan.handle(
            host,
            failure_code=code,
            original_identity=identity,
            original_footprint=footprint,
            stage=ReplanStage.MODEL,
        )
        if report.outcome is ReplanOutcome.SUCCEEDED:
            return True
        if report.outcome is ReplanOutcome.MANUAL_BLOCKED:
            raise PreconditionFailedError(report.message, reason=report.outcome.value)
        if report.outcome is ReplanOutcome.LOW_SPACE:
            raise PreconditionFailedError(report.message, reason="storage_low_space")
        if report.outcome is ReplanOutcome.TERMINAL:
            raise PreconditionFailedError(report.message, reason=report.outcome.value)
        if report.outcome is ReplanOutcome.MANUAL_CAPACITY_REQUIRED:
            raise PreconditionFailedError(report.message, reason=report.outcome.value)
        return False

    def _artifact_for_admit(
        self, plan: DeploymentPlan, artifact_id: ArtifactId | None
    ) -> ModelArtifact:
        if artifact_id is not None:
            artifact = self._inventory.get(artifact_id)
            if artifact is None:
                raise NotFoundError(
                    "no such model artifact", artifact_id=artifact_id.value
                )
            if not artifact_matches_plan(artifact, plan):
                raise PreconditionFailedError(
                    "artifact does not match the current deployment plan",
                    reason="artifact_plan_mismatch",
                    artifact_id=artifact.artifact_id.value,
                    model_id=plan.model_id.value,
                )
            return artifact
        found = find_plan_artifact(self._inventory, plan, require_revision=False)
        if found is None:
            raise PreconditionFailedError(
                "no stored artifact matches the current deployment plan",
                reason="artifact_missing",
                model_id=plan.model_id.value,
            )
        return found


def _plan_footprint(plan: DeploymentPlan | None) -> int:
    if plan is None:
        return 0
    value = plan.expected_storage_bytes
    return value if isinstance(value, int) and value > 0 else 0


def _raise_if_manual_capacity(decision: AdmissionDecision | None) -> None:
    if decision is None:
        return
    code = decision.reason_code
    if isinstance(code, str) and is_manual_capacity_required(code):
        raise PreconditionFailedError(
            "automatic storage capacity is unresolved; "
            "administrator capacity may be supplied as last resort",
            reason="manual_capacity_required",
        )


def require_current_plan(overview: DeploymentPlanOverview) -> DeploymentPlan:
    """Refuse STALE and UNAVAILABLE. Does not refresh the plan."""
    if overview.status is DeploymentPlanStatus.STALE:
        raise PreconditionFailedError(
            "deployment plan is stale; refresh before execution",
            reason="plan_stale",
            status=overview.status.value,
        )
    if overview.status is DeploymentPlanStatus.UNAVAILABLE or overview.plan is None:
        raise PreconditionFailedError(
            "no current deployment plan",
            reason="plan_unavailable",
            status=overview.status.value,
        )
    if overview.status is not DeploymentPlanStatus.CURRENT:
        raise PreconditionFailedError(
            "deployment plan is not current",
            reason="plan_not_current",
            status=overview.status.value,
        )
    return overview.plan


def catalog_entry_for_plan(
    models: ModelCatalogue, plan: DeploymentPlan
) -> ModelCatalogEntry:
    """Resolve the catalog row that matches plan identity. Not a recommendation."""
    entry = models.for_model(plan.model_id)
    if entry is None:
        entry = models.acquirable(plan.logical_name.value)
    if entry is None:
        raise NotFoundError(
            "selected model is not in the catalog",
            model_id=plan.model_id.value,
        )
    if entry.metadata.model_id != plan.model_id:
        raise PreconditionFailedError(
            "catalog identity does not match the deployment plan",
            reason="plan_catalog_mismatch",
            model_id=plan.model_id.value,
        )
    if entry.metadata.source_ref != plan.source_ref:
        raise PreconditionFailedError(
            "catalog source does not match the deployment plan",
            reason="plan_source_mismatch",
            source_ref=plan.source_ref,
        )
    return entry


def acquisition_request_for_plan(
    plan: DeploymentPlan, entry: ModelCatalogEntry
) -> ModelAcquisitionRequest:
    """Build an acquisition request from plan identity. Catalog supplies source Name."""
    meta = entry.metadata
    req = entry.requirement
    revision = (
        plan.source_revision
        if is_resolved(plan.source_revision)
        else meta.source_revision
    )
    quantization = (
        plan.quantization if is_resolved(plan.quantization) else meta.quantization
    )
    return ModelAcquisitionRequest(
        request_id=AcquisitionId.generate(),
        model_id=plan.model_id,
        logical_name=plan.logical_name,
        source=meta.source,
        source_ref=plan.source_ref,
        requested_revision=revision,
        artifact_format=NOT_PROVIDED,
        quantization=quantization,
        expected_storage_bytes=req.storage_bytes,
        expected_peak_bytes=req.peak_additional_bytes,
        license_id=meta.license_id,
    )


def find_plan_artifact(
    inventory: ModelInventory,
    plan: DeploymentPlan,
    *,
    require_revision: bool = True,
) -> ModelArtifact | None:
    """Exact stored match for plan identity. Wrong revision is not a match."""
    if require_revision and not is_resolved(plan.source_revision):
        return None
    for artifact in inventory.artifacts():
        if artifact.state is not ArtifactState.STORED:
            continue
        if artifact_matches_plan(artifact, plan):
            return artifact
    return None


def _reused_receipt(artifact: ModelArtifact, clock: Clock) -> AcquisitionReceipt:
    return AcquisitionReceipt(
        request_id=AcquisitionId.generate(),
        artifact_id=artifact.artifact_id,
        outcome="reused",
        state=artifact.state,
        verification_state=artifact.verification_state,
        reused=True,
        acquired_at=clock.now(),
        resolved_revision=artifact.revision,
        stored_bytes=artifact.installed_bytes,
        file_count=artifact.file_count,
        serving=False,
    )


def _admission_payload(decision: AdmissionDecision | None) -> dict[str, object] | None:
    if decision is None:
        return None
    reservation = decision.reservation
    return {
        "verdict": decision.verdict.value,
        "reason_code": (
            decision.reason_code if is_resolved(decision.reason_code) else None
        ),
        "reasons": list(decision.reasons),
        "reused": decision.reused,
        "reservation_id": (
            reservation.reservation_id.value if reservation is not None else None
        ),
        "serving": False,
    }


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
