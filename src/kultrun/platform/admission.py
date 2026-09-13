"""Translate a STORED artifact and a plan into a ResourceRequest, then admit.

Lives in platform so planning ⟂ resource stays structural.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping

from kultrun.audit.contracts import (
    AuditDecision,
    AuditEvent,
    AuditId,
    AuditOutcome,
)
from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.identity.contracts import SubjectId
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
)
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import CompatibilityVerdict, DeploymentPlan
from kultrun.planning.evaluate import deployment_capacity
from kultrun.planning.service import SelectionService, plan_for_entry
from kultrun.resource.contracts import (
    AdmissionDecision,
    RequestId,
    ReservationId,
    ResourceRequest,
    ResourceReservation,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.storage.contracts import StorageCapacityEvidence, StorageSanityEvidence


class AdmissionService:
    """Server-side derivation and admission. Clients do not set RAM/VRAM."""

    def __init__(
        self,
        manager: ResourceManager,
        inventory: ModelInventory,
        models: ModelCatalogue,
        selection: SelectionService,
        capacity: CapacityService,
        store: Store,
        clock: Clock,
        actor_id: SubjectId,
        reservation_in_use: Callable[[ReservationId], bool] | None = None,
        stored_storage: (
            Callable[[HostCapabilities], dict[str, StorageCapacityEvidence]] | None
        ) = None,
    ) -> None:
        self._manager = manager
        self._inventory = inventory
        self._models = models
        self._selection = selection
        self._capacity = capacity
        self._store = store
        self._clock = clock
        self._actor_id = actor_id
        self._reservation_in_use = reservation_in_use or (lambda _: False)

        def _empty_storage(
            _host: HostCapabilities,
        ) -> dict[str, StorageCapacityEvidence]:
            return {}

        self._stored_storage = stored_storage or _empty_storage

    @property
    def manager(self) -> ResourceManager:
        return self._manager

    def reserve(
        self,
        artifact_id: ArtifactId,
        host: HostCapabilities,
        sanity: dict[str, StorageSanityEvidence],
        runtime_compatibility: Mapping[str, CompatibilityVerdict],
        *,
        runtime: str,
        runtime_version: Maybe[str] = NOT_PROVIDED,
        request_id: RequestId | None = None,
    ) -> AdmissionDecision:
        artifact = self._inventory.get(artifact_id)
        if artifact is None:
            raise NotFoundError("no such model artifact", artifact_id=artifact_id.value)
        envelope = self._capacity.compute(host, sanity, self._stored_storage(host))
        request = request_from_artifact(
            artifact,
            envelope,
            self._models,
            self._selection,
            runtime_compatibility,
            runtime=runtime,
            runtime_version=runtime_version,
            request_id=request_id,
        )
        decision = self._manager.admit(request, envelope, artifact)
        self._audit(
            "resource.reserve",
            artifact_id.value,
            decision.verdict.value,
            decision.reasons[0] if decision.reasons else None,
            allowed=decision.verdict.value == "admitted",
        )
        return decision

    def reserve_for_plan(
        self,
        plan: DeploymentPlan,
        artifact: ModelArtifact,
        host: HostCapabilities,
        sanity: dict[str, StorageSanityEvidence],
    ) -> tuple[ResourceRequest, AdmissionDecision]:
        """Admit plan resource intent bound to a matching artifact.

        Amounts come from the authoritative DeploymentPlan, not plan_for_entry.
        ResourceManager remains the live physical decision.
        """
        if not artifact_matches_plan(artifact, plan):
            raise PreconditionFailedError(
                "artifact does not match the current deployment plan",
                reason="artifact_plan_mismatch",
                artifact_id=artifact.artifact_id.value,
                model_id=plan.model_id.value,
            )
        envelope = self._capacity.compute(host, sanity, self._stored_storage(host))
        request = request_from_plan(plan, artifact, envelope)
        decision = self._manager.admit(request, envelope, artifact)
        self._audit(
            "resource.reserve",
            artifact.artifact_id.value,
            decision.verdict.value,
            decision.reasons[0] if decision.reasons else None,
            allowed=decision.verdict.value == "admitted",
        )
        return request, decision

    def release(self, reservation_id: ReservationId) -> ResourceReservation:
        if self._reservation_in_use(reservation_id):
            raise ConflictError(
                "reservation is in use by a live instance",
                reason="reservation_in_use",
                reservation_id=reservation_id.value,
            )
        released = self._manager.release(reservation_id)
        self._audit(
            "resource.release",
            reservation_id.value,
            "released",
            "reservation released",
            allowed=True,
        )
        return released

    def _audit(
        self,
        action: str,
        target_id: str,
        outcome: str,
        reason: str | None,
        *,
        allowed: bool,
    ) -> None:
        event = AuditEvent(
            audit_id=AuditId.generate(),
            occurred_at=self._clock.now(),
            actor_id=self._actor_id,
            action=Name(action),
            target_kind=Name("resource.reservation"),
            target_id=target_id,
            decision=AuditDecision.ALLOWED if allowed else AuditDecision.DENIED,
            outcome=AuditOutcome.SUCCEEDED if allowed else AuditOutcome.NOT_ATTEMPTED,
            reason=reason,
        )
        del outcome
        self._store.put(event.audit_id.value, event)


def artifact_matches_plan(artifact: ModelArtifact, plan: DeploymentPlan) -> bool:
    """Exact plan identity. Same display name with a wrong revision is not a match."""
    if artifact.model_id != plan.model_id:
        return False
    if is_resolved(artifact.source_ref) and artifact.source_ref != plan.source_ref:
        return False
    if is_resolved(plan.source_revision) and (
        not is_resolved(artifact.revision) or artifact.revision != plan.source_revision
    ):
        return False
    return not (
        is_resolved(plan.quantization)
        and _opt(artifact.quantization) != _opt(plan.quantization)
    )


def request_from_plan(
    plan: DeploymentPlan,
    artifact: ModelArtifact,
    envelope: CapacityEnvelope,
    *,
    request_id: RequestId | None = None,
) -> ResourceRequest:
    """Bind plan resource intent to a stored artifact. Does not re-estimate."""
    if not is_resolved(plan.plan_basis):
        raise ValidationError("deployment plan has no basis")
    if is_resolved(plan.host_id) and plan.host_id != envelope.host_id.value:
        raise PreconditionFailedError(
            "plan host does not match live host",
            reason="plan_host_mismatch",
            plan_host=plan.host_id,
            live_host=envelope.host_id.value,
        )
    ident = request_id or fingerprint_plan_request_id(
        str(plan.plan_basis), artifact.artifact_id.value
    )
    placement = plan.placement
    return ResourceRequest(
        request_id=ident,
        host_id=envelope.host_id,
        artifact_id=artifact.artifact_id,
        model_id=plan.model_id,
        plan_fingerprint=str(plan.plan_basis),
        placement=placement,
        ram_bytes=plan.expected_ram_bytes,
        accelerator_bytes=(
            plan.expected_vram_bytes
            if placement is MemoryPlacement.DISCRETE_GPU
            else NOT_PROVIDED
        ),
        unified_bytes=(
            plan.expected_unified_bytes
            if placement is MemoryPlacement.UNIFIED_MEMORY
            else NOT_PROVIDED
        ),
        logical_name=plan.logical_name.value,
        runtime=plan.runtime,
        accelerator_index=plan.accelerator_index,
        incremental_storage_bytes=NOT_PROVIDED,
        estimator_provider=plan.estimator_provider,
        plan_version=plan.policy_version,
        model_revision=artifact.revision,
        quantization=plan.quantization,
        context_tokens=plan.context_tokens,
        capacity_policy_version=envelope.policy_version,
        host_fingerprint=envelope.host_fingerprint,
        workload_type=WorkloadType.INFERENCE,
        storage_pool_mount=(
            plan.storage_pool_mount
            if is_resolved(plan.storage_pool_mount)
            else (
                artifact.storage_mount
                if is_resolved(artifact.storage_mount)
                else NOT_PROVIDED
            )
        ),
    )


def fingerprint_plan_request_id(plan_basis: str, artifact_id: str) -> RequestId:
    """Deterministic request identity for one plan basis + artifact pair."""
    digest = hashlib.sha256(
        f"resource.request.plan@1|{plan_basis}|{artifact_id}".encode()
    ).hexdigest()
    return RequestId(f"rreq_{digest[:16]}")


def _opt(value: object) -> str:
    if not is_resolved(value) or value is None:
        return ""
    return str(value)


def request_from_artifact(
    artifact: ModelArtifact,
    envelope: CapacityEnvelope,
    models: ModelCatalogue,
    selection: SelectionService,
    runtime_compatibility: Mapping[str, CompatibilityVerdict],
    *,
    runtime: str,
    runtime_version: Maybe[str] = NOT_PROVIDED,
    request_id: RequestId | None = None,
) -> ResourceRequest:
    """Legacy artifact-id reservation path. Not plan-driven admission.

    Amounts still come from ``plan_for_entry`` for the residual artifact-id
    reservation API (``POST /resources/reservations?artifact_id=``). That path
    is not InferenceInstance authority and is not normal deployment execution.
    Normal deployment uses ``request_from_plan``.
    """
    if artifact.state is not ArtifactState.STORED:
        # Still build a request so ResourceManager can reject with the typed reason.
        pass
    entry = None
    if is_resolved(artifact.logical_name):
        entry = models.acquirable(str(artifact.logical_name))
    if entry is None:
        entry = models.for_model(artifact.model_id)
    if entry is None:
        raise ValidationError(
            "no catalog evidence for this artifact",
            artifact_id=artifact.artifact_id.value,
        )
    ident = entry.metadata.model_id.value
    verdict = runtime_compatibility.get(ident, CompatibilityVerdict.UNRESOLVED)
    mount = artifact.storage_mount if isinstance(artifact.storage_mount, str) else None
    plan = plan_for_entry(
        selection,
        entry,
        envelope,
        verdict,
        runtime=runtime,
        runtime_version=runtime_version,
        storage_mount=mount,
    )
    capacity = deployment_capacity(envelope, storage_mount=mount)
    fingerprint = _plan_fingerprint(artifact, plan, capacity.accelerator_index)
    incremental = NOT_PROVIDED
    return ResourceRequest(
        request_id=request_id or RequestId.generate(),
        host_id=envelope.host_id,
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        plan_fingerprint=fingerprint,
        placement=plan.placement,
        ram_bytes=plan.expected_ram_bytes,
        accelerator_bytes=(
            plan.expected_vram_bytes
            if plan.placement is MemoryPlacement.DISCRETE_GPU
            else NOT_PROVIDED
        ),
        unified_bytes=(
            plan.expected_unified_bytes
            if plan.placement is MemoryPlacement.UNIFIED_MEMORY
            else NOT_PROVIDED
        ),
        logical_name=plan.logical_name.value,
        runtime=plan.runtime,
        accelerator_index=capacity.accelerator_index,
        incremental_storage_bytes=incremental,
        estimator_provider=plan.estimator_provider,
        plan_version=plan.policy_version,
        model_revision=artifact.revision,
        quantization=plan.quantization,
        context_tokens=entry.requirement.assumed_context_tokens,
        capacity_policy_version=envelope.policy_version,
        host_fingerprint=envelope.host_fingerprint,
        workload_type=WorkloadType.INFERENCE,
        storage_pool_mount=mount if mount is not None else NOT_PROVIDED,
    )


def _plan_fingerprint(
    artifact: ModelArtifact, plan: DeploymentPlan, index: int | None
) -> str:
    revision = artifact.revision if is_resolved(artifact.revision) else ""
    quant = getattr(plan, "quantization", "")
    runtime = getattr(plan, "runtime", "")
    placement = plan.placement
    estimator = getattr(plan, "estimator_provider", "")
    version = getattr(plan, "policy_version", "")
    raw = "|".join(
        [
            artifact.artifact_id.value,
            artifact.model_id.value,
            str(revision),
            str(quant if is_resolved(quant) else ""),
            str(runtime if is_resolved(runtime) else ""),
            placement.value,
            str(index if index is not None else ""),
            str(estimator),
            str(version),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
