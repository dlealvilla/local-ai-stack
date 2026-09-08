"""Plan-driven InferenceInstance create. Consumes; does not replan.

Composition-owned. Inference still owns lifecycle. Planning still owns
the DeploymentPlan. This service only binds a CURRENT plan to a matching
artifact and ACTIVE reservation. It does not select a model, estimate
capacity, admit resources, or launch a product runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from kultrun.host.contracts import HostCapabilities
from kultrun.inference.contracts import InferenceInstance, InstanceId
from kultrun.inference.service import InstanceService
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, is_resolved
from kultrun.model.contracts import ArtifactId, ArtifactState, ModelArtifact
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import DeploymentPlan, DeploymentPlanStatus
from kultrun.platform.admission import (
    artifact_matches_plan,
    fingerprint_plan_request_id,
)
from kultrun.platform.deployment_plan import DeploymentPlanOverview
from kultrun.platform.deployment_prepare import require_current_plan
from kultrun.resource.contracts import (
    LedgerHealth,
    ReservationId,
    ReservationState,
    ResourceReservation,
)
from kultrun.resource.manager import ResourceManager


@dataclass(frozen=True, slots=True)
class InstanceView:
    """Instance plus derived plan currentness. Currentness is not a lifecycle state."""

    instance: InferenceInstance
    plan_status: str | None

    @property
    def configuration_current(self) -> bool | None:
        if self.plan_status is None:
            return None
        return self.plan_status == DeploymentPlanStatus.CURRENT.value

    def payload(self) -> dict[str, object]:
        item = self.instance
        return {
            "instance": item,
            "instance_id": item.instance_id.value,
            "observed_state": item.observed_state.value,
            "desired_state": item.desired_state.value,
            "lifecycle_state": item.lifecycle_state.value,
            "health": item.health.value,
            "plan_id": _token(item.plan_id),
            "plan_basis": _token(item.plan_basis),
            "plan_status": self.plan_status,
            "configuration_current": self.configuration_current,
            "model_id": item.model_id.value,
            "logical_name": _token(item.logical_name),
            "model_revision": _token(item.model_revision),
            "quantization": _token(item.quantization),
            "artifact_id": (
                item.artifact_id.value if item.artifact_id is not None else None
            ),
            "reservation_id": (
                item.reservation_id.value if item.reservation_id is not None else None
            ),
            "runtime": item.runtime.value,
            "runtime_version": _token(item.runtime_version),
            "executor": item.executor.value,
            "placement": _token(item.placement),
            "accelerator_index": item.accelerator_index,
            "context_length_tokens": (
                item.context_length_tokens
                if is_resolved(item.context_length_tokens)
                else None
            ),
            "endpoint": item.endpoint,
            "ready": item.ready if is_resolved(item.ready) else None,
            "pid": item.pid if is_resolved(item.pid) else None,
            "execution_id": (
                item.execution_id.value if item.execution_id is not None else None
            ),
            "created_at": item.created_at,
            "started_at": item.started_at,
            "stopped_at": item.stopped_at,
            "failure_reason": (
                item.failure_reason if is_resolved(item.failure_reason) else None
            ),
        }


class DeploymentInstanceService:
    """CURRENT plan + matching artifact + ACTIVE reservation → InferenceInstance."""

    def __init__(
        self,
        overview: Callable[[HostCapabilities], DeploymentPlanOverview],
        inventory: ModelInventory,
        resources: ResourceManager,
        instances: InstanceService,
    ) -> None:
        self._overview = overview
        self._inventory = inventory
        self._resources = resources
        self._instances = instances

    def create(
        self,
        host: HostCapabilities,
        reservation_id: ReservationId | None = None,
        artifact_id: ArtifactId | None = None,
        plan_id: str | None = None,
    ) -> InstanceView:
        """Persist CREATED. Does not start, select, admit, or acquire."""
        overview = self._overview(host)
        plan = require_current_plan(overview)
        if plan_id and _token(plan.plan_id) != plan_id:
            raise PreconditionFailedError(
                "supplied plan id is not the current deployment plan",
                reason="plan_id_mismatch",
                plan_id=plan_id,
            )
        artifact, reservation = self._resolve_triple(
            host, plan, reservation_id, artifact_id
        )
        require_matching_triple(plan, artifact, reservation, host)
        runtime = _required_name(plan.runtime, "runtime", "plan_runtime_unresolved")
        executor = _required_name(
            plan.executor_kind, "executor", "plan_executor_unresolved"
        )
        instance = self._instances.create(
            artifact,
            reservation,
            runtime=runtime,
            executor=executor,
            plan_id=plan.plan_id,
            plan_basis=plan.plan_basis,
            runtime_version=plan.runtime_version,
            placement=plan.placement.value,
            accelerator_index=plan.accelerator_index,
            context_tokens=(
                plan.context_tokens
                if is_resolved(plan.context_tokens)
                else NOT_MEASURED
            ),
        )
        return self.view(instance, host)

    def start(
        self,
        instance_id: InstanceId,
        host: HostCapabilities,
        *,
        ledger_health: LedgerHealth,
        serving_mode: str = "healthy",
    ) -> InstanceView:
        instance = self._require_instance(instance_id)
        self._require_start_currentness(instance, host)
        started = self._instances.start(
            instance_id, ledger_health=ledger_health, serving_mode=serving_mode
        )
        return self.view(started, host)

    def stop(self, instance_id: InstanceId, host: HostCapabilities) -> InstanceView:
        return self.view(self._instances.stop(instance_id), host)

    def get(self, instance_id: InstanceId, host: HostCapabilities) -> InstanceView:
        return self.view(self._require_instance(instance_id), host)

    def list(self, host: HostCapabilities) -> tuple[InstanceView, ...]:
        return tuple(self.view(item, host) for item in self._instances.list())

    def view(self, instance: InferenceInstance, host: HostCapabilities) -> InstanceView:
        return InstanceView(instance, self.plan_status_of(instance, host))

    def plan_status_of(
        self, instance: InferenceInstance, host: HostCapabilities
    ) -> str | None:
        """Lifecycle is unchanged. This only answers whether bound intent is current."""
        if not is_resolved(instance.plan_id):
            return None
        overview = self._overview(host)
        if overview.plan is None or overview.status is DeploymentPlanStatus.UNAVAILABLE:
            return DeploymentPlanStatus.UNAVAILABLE.value
        if overview.status is DeploymentPlanStatus.STALE:
            return DeploymentPlanStatus.STALE.value
        if is_resolved(instance.plan_basis) and (
            instance.plan_basis != overview.plan.plan_basis
        ):
            return DeploymentPlanStatus.STALE.value
        if instance.plan_id != overview.plan.plan_id:
            return DeploymentPlanStatus.STALE.value
        return overview.status.value

    def _require_start_currentness(
        self, instance: InferenceInstance, host: HostCapabilities
    ) -> None:
        if not is_resolved(instance.plan_id):
            return
        status = self.plan_status_of(instance, host)
        if status == DeploymentPlanStatus.UNAVAILABLE.value:
            raise PreconditionFailedError(
                "bound deployment plan is unavailable",
                reason="plan_unavailable",
                instance_id=instance.instance_id.value,
            )
        if status != DeploymentPlanStatus.CURRENT.value:
            raise PreconditionFailedError(
                "bound deployment plan is stale; create a new instance",
                reason="plan_stale",
                instance_id=instance.instance_id.value,
                plan_status=status,
            )
        overview = self._overview(host)
        plan = require_current_plan(overview)
        if instance.artifact_id is None or instance.reservation_id is None:
            raise PreconditionFailedError(
                "instance is missing artifact or reservation",
                instance_id=instance.instance_id.value,
            )
        artifact = self._inventory.get(instance.artifact_id)
        reservation = self._resources.get(instance.reservation_id)
        if artifact is None or artifact.state is not ArtifactState.STORED:
            raise PreconditionFailedError(
                "bound artifact is missing or not STORED",
                reason="artifact_missing",
                instance_id=instance.instance_id.value,
            )
        if reservation is None or reservation.state is not ReservationState.ACTIVE:
            raise PreconditionFailedError(
                "bound reservation is not ACTIVE",
                reason="reservation_not_active",
                instance_id=instance.instance_id.value,
            )
        require_matching_triple(plan, artifact, reservation, host)
        if _token(plan.runtime) and instance.runtime.value != plan.runtime:
            raise PreconditionFailedError(
                "instance runtime no longer matches the bound plan",
                reason="instance_runtime_mismatch",
                instance_id=instance.instance_id.value,
            )
        if _token(plan.executor_kind) and instance.executor.value != plan.executor_kind:
            raise PreconditionFailedError(
                "instance executor no longer matches the bound plan",
                reason="instance_executor_mismatch",
                instance_id=instance.instance_id.value,
            )

    def _resolve_triple(
        self,
        host: HostCapabilities,
        plan: DeploymentPlan,
        reservation_id: ReservationId | None,
        artifact_id: ArtifactId | None,
    ) -> tuple[ModelArtifact, ResourceReservation]:
        reservation = self._load_reservation(host, plan, reservation_id)
        if reservation.artifact_id is None:
            raise PreconditionFailedError(
                "reservation has no artifact",
                reason="reservation_artifact_mismatch",
                reservation_id=reservation.reservation_id.value,
            )
        wanted = artifact_id or reservation.artifact_id
        artifact = self._inventory.get(wanted)
        if artifact is None:
            raise NotFoundError(
                "no such model artifact",
                artifact_id=wanted.value,
            )
        return artifact, reservation

    def _load_reservation(
        self,
        host: HostCapabilities,
        plan: DeploymentPlan,
        reservation_id: ReservationId | None,
    ) -> ResourceReservation:
        if reservation_id is not None:
            found = self._resources.get(reservation_id)
            if found is None:
                raise NotFoundError(
                    "no such reservation", reservation_id=reservation_id.value
                )
            return found
        matches = [
            item
            for item in self._resources.reservations()
            if item.state is ReservationState.ACTIVE
            and item.host_id == host.host_id
            and is_resolved(item.plan_fingerprint)
            and item.plan_fingerprint == plan.plan_basis
        ]
        if len(matches) != 1:
            raise ValidationError(
                "a reservation id is required when the current plan is not unique",
                parameter="reservation_id",
                matches=len(matches),
            )
        return matches[0]

    def _require_instance(self, instance_id: InstanceId) -> InferenceInstance:
        found = self._instances.get(instance_id)
        if found is None:
            raise NotFoundError(
                "no such inference instance", instance_id=instance_id.value
            )
        return found


def require_matching_triple(
    plan: DeploymentPlan,
    artifact: ModelArtifact,
    reservation: ResourceReservation,
    host: HostCapabilities,
) -> None:
    """Fail before persist when plan, artifact, and reservation disagree."""
    if artifact.state is not ArtifactState.STORED:
        raise PreconditionFailedError(
            "artifact is not STORED",
            reason="artifact_missing",
            artifact_id=artifact.artifact_id.value,
        )
    if artifact.model_id != plan.model_id or not artifact_matches_plan(artifact, plan):
        raise PreconditionFailedError(
            "artifact does not match the current deployment plan",
            reason="artifact_plan_mismatch",
            artifact_id=artifact.artifact_id.value,
            model_id=plan.model_id.value,
        )
    if reservation.state is not ReservationState.ACTIVE:
        raise PreconditionFailedError(
            "reservation is not ACTIVE",
            reason="reservation_not_active",
            reservation_id=reservation.reservation_id.value,
        )
    if reservation.host_id != host.host_id:
        raise PreconditionFailedError(
            "reservation host does not match the live host",
            reason="reservation_host_mismatch",
            reservation_id=reservation.reservation_id.value,
        )
    if is_resolved(plan.host_id) and plan.host_id != host.host_id.value:
        raise PreconditionFailedError(
            "plan host does not match the live host",
            reason="plan_host_mismatch",
            plan_host=plan.host_id,
        )
    if reservation.artifact_id != artifact.artifact_id:
        raise PreconditionFailedError(
            "reservation does not match the artifact",
            reason="reservation_artifact_mismatch",
            reservation_id=reservation.reservation_id.value,
            artifact_id=artifact.artifact_id.value,
        )
    if (
        not is_resolved(reservation.plan_fingerprint)
        or reservation.plan_fingerprint != plan.plan_basis
    ):
        raise PreconditionFailedError(
            "reservation does not match the current deployment plan",
            reason="reservation_plan_mismatch",
            reservation_id=reservation.reservation_id.value,
        )
    if reservation.request_id is None or not is_resolved(plan.plan_basis):
        raise PreconditionFailedError(
            "reservation is missing plan-driven request identity",
            reason="reservation_request_mismatch",
            reservation_id=reservation.reservation_id.value,
        )
    expected = fingerprint_plan_request_id(
        str(plan.plan_basis), artifact.artifact_id.value
    )
    if reservation.request_id != expected:
        raise PreconditionFailedError(
            "reservation request does not match the current plan and artifact",
            reason="reservation_request_mismatch",
            reservation_id=reservation.reservation_id.value,
        )


def _required_name(value: object, what: str, reason: str) -> Name:
    token = _token(value)
    if token is None:
        raise PreconditionFailedError(
            f"deployment plan has no {what}",
            reason=reason,
        )
    return Name(token)


def _token(value: object) -> str | None:
    if not is_resolved(value) or value is None:
        return None
    text = value.value if hasattr(value, "value") else value
    if isinstance(text, str) and text.strip():
        return text
    return None

