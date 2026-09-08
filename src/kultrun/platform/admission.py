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
from kultrun.kernel.errors import ConflictError, NotFoundError, ValidationError
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
from kultrun.storage.contracts import StorageSanityEvidence


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
        envelope = self._capacity.compute(host, sanity)
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
    """Build a request from server-side evidence. No caller amounts."""
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
    plan = plan_for_entry(
        selection,
        entry,
        envelope,
        verdict,
        runtime=runtime,
        runtime_version=runtime_version,
    )
    capacity = deployment_capacity(envelope)
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
