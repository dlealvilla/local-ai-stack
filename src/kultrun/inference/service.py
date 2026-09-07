"""InferenceInstance lifecycle. Composes runtime and executor; does not exec."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from kultrun.execution.contracts import (
    DeviceRequest,
    ExecutionId,
    ExecutionOwnership,
    ExecutionState,
    ExecutorHandle,
    ExecutorSpec,
)
from kultrun.execution.service import ExecutionService
from kultrun.inference.contracts import (
    DesiredState,
    HealthState,
    InferenceEndpoint,
    InferenceInstance,
    InstanceId,
    LifecycleState,
    ObservedState,
)
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_MEASURED, is_resolved
from kultrun.model.contracts import ArtifactState, ModelArtifact
from kultrun.model.inventory import ModelInventory
from kultrun.resource.contracts import (
    LedgerHealth,
    ReservationId,
    ReservationState,
    ResourceReservation,
)
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeLaunchSpec

SERVING_RUNTIME = Name("reference-serving")
STARTUP_TIMEOUT_SECONDS = 5.0
_LIVE = frozenset(
    {ObservedState.STARTING, ObservedState.RUNNING, ObservedState.STOPPING}
)
_BLOCKS_RELEASE = _LIVE | frozenset({ObservedState.UNKNOWN})
_LIFECYCLE = {
    ObservedState.CREATED: LifecycleState.PENDING,
    ObservedState.STARTING: LifecycleState.STARTING,
    ObservedState.RUNNING: LifecycleState.RUNNING,
    ObservedState.STOPPING: LifecycleState.STOPPING,
    ObservedState.STOPPED: LifecycleState.STOPPED,
    ObservedState.FAILED: LifecycleState.FAILED,
    ObservedState.UNKNOWN: LifecycleState.UNKNOWN,
}


class InstanceService:
    """Create, start, observe, stop. Plural. No scheduler."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        inventory: ModelInventory,
        resources: ResourceManager,
        executions: ExecutionService,
        runtimes: RuntimeCatalogue,
        startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._clock = clock
        self._inventory = inventory
        self._resources = resources
        self._executions = executions
        self._runtimes = runtimes
        self._startup_timeout = startup_timeout

    def list(self) -> tuple[InferenceInstance, ...]:
        return tuple(
            self.observe(item.instance_id)
            for item in self._store.records(InferenceInstance)
        )

    def get(self, instance_id: InstanceId) -> InferenceInstance | None:
        found = self._store.get(InferenceInstance, instance_id.value)
        if found is None:
            return None
        return self.observe(found.instance_id)

    def blocks_release(self, reservation_id: ReservationId) -> bool:
        """True when a live instance still uses this reservation."""
        for item in self._store.records(InferenceInstance):
            if item.reservation_id != reservation_id:
                continue
            current = self.observe(item.instance_id)
            if current.observed_state in _BLOCKS_RELEASE:
                return True
        return False

    def live_for_reservation(
        self, reservation_id: ReservationId
    ) -> InferenceInstance | None:
        for item in self.list():
            if (
                item.reservation_id == reservation_id
                and item.observed_state in _BLOCKS_RELEASE
            ):
                return item
        return None

    def create(
        self,
        artifact: ModelArtifact,
        reservation: ResourceReservation,
        runtime: Name | None = None,
        executor: Name | None = None,
    ) -> InferenceInstance:
        self._require_create(artifact, reservation)
        now = self._clock.now()
        chosen = runtime or SERVING_RUNTIME
        instance = InferenceInstance(
            instance_id=InstanceId.generate(),
            host_id=reservation.host_id,
            model_id=artifact.model_id,
            runtime=chosen,
            executor=executor or Name("native-process"),
            lifecycle_state=LifecycleState.PENDING,
            health=HealthState.UNKNOWN,
            configuration_version=1,
            model_revision=artifact.revision,
            reservation_id=reservation.reservation_id,
            artifact_id=artifact.artifact_id,
            desired_state=DesiredState.STOPPED,
            observed_state=ObservedState.CREATED,
            created_at=now,
            last_observed_at=now,
            logical_name=artifact.logical_name,
            quantization=artifact.quantization,
            serving_runtime=chosen.value,
        )
        self._store.put(instance.instance_id.value, instance)
        return instance

    def start(
        self,
        instance_id: InstanceId,
        *,
        ledger_health: LedgerHealth,
        serving_mode: str = "healthy",
    ) -> InferenceInstance:
        instance = self._require(instance_id)
        if instance.observed_state is ObservedState.RUNNING:
            return instance
        if instance.observed_state is ObservedState.STARTING:
            return instance
        if instance.observed_state is ObservedState.STOPPING:
            raise PreconditionFailedError("instance is stopping")
        if instance.observed_state is ObservedState.UNKNOWN:
            raise PreconditionFailedError(
                "instance process identity is unverified; resolve it before start"
            )
        self._require_start(instance, ledger_health)
        now = self._clock.now()
        instance = self._write(
            instance,
            desired_state=DesiredState.RUNNING,
            observed_state=ObservedState.STARTING,
            lifecycle_state=LifecycleState.STARTING,
            health=HealthState.UNKNOWN,
            last_observed_at=now,
            failure_reason=NOT_MEASURED,
        )
        request = RuntimeLaunchRequest(
            instance_id=instance.instance_id.value,
            mode=serving_mode,
            artifact_id=(
                instance.artifact_id.value if instance.artifact_id is not None else ""
            ),
        )
        launch = self._runtimes.launch(instance.runtime, request)
        handle = self._executions.start(instance.host_id, _spec_from(launch))
        instance = self._write(instance, execution_id=handle.execution_id)
        if handle.observed_state is ExecutionState.FAILED:
            return self._fail(instance, handle.detail or "executor failed to start")
        ready = self._wait_ready(instance, handle.execution_id)
        if ready is None:
            self._safe_stop(handle.execution_id)
            refreshed = self._executions.observe(handle.execution_id)
            reason = "readiness was not achieved before startup timeout"
            if is_resolved(refreshed.exit_code):
                reason = f"process exited before ready ({refreshed.exit_code})"
            return self._fail(instance, reason, refreshed)
        host, port = ready
        now = self._clock.now()
        return self._write(
            instance,
            observed_state=ObservedState.RUNNING,
            lifecycle_state=LifecycleState.RUNNING,
            health=HealthState.HEALTHY,
            reachable=True,
            ready=True,
            endpoint=InferenceEndpoint(scheme="http", address=host, port=port),
            pid=self._pid_of(handle.execution_id),
            started_at=now,
            last_observed_at=now,
            stopped_at=None,
        )

    def stop(self, instance_id: InstanceId) -> InferenceInstance:
        instance = self._require(instance_id)
        owned = self._owned_live(instance.execution_id)
        if (
            instance.observed_state
            in {
                ObservedState.STOPPED,
                ObservedState.CREATED,
            }
            and not owned
        ):
            return self._write(
                instance,
                desired_state=DesiredState.STOPPED,
                observed_state=ObservedState.STOPPED,
                lifecycle_state=LifecycleState.STOPPED,
            )
        if instance.observed_state is ObservedState.UNKNOWN and not owned:
            return self._write(
                instance,
                desired_state=DesiredState.STOPPED,
                failure_reason="process identity unverified; not signalled",
            )
        instance = self._write(
            instance,
            desired_state=DesiredState.STOPPED,
            observed_state=ObservedState.STOPPING,
            lifecycle_state=LifecycleState.STOPPING,
            last_observed_at=self._clock.now(),
        )
        if instance.execution_id is not None:
            handle = self._safe_stop(instance.execution_id)
        else:
            handle = None
        now = self._clock.now()
        return self._write(
            instance,
            observed_state=ObservedState.STOPPED,
            lifecycle_state=LifecycleState.STOPPED,
            health=HealthState.UNKNOWN,
            reachable=False,
            ready=False,
            pid=NOT_MEASURED,
            stopped_at=now,
            last_observed_at=now,
            exit_code=handle.exit_code if handle is not None else NOT_MEASURED,
        )

    def observe(self, instance_id: InstanceId) -> InferenceInstance:
        recorded = self._store.get(InferenceInstance, instance_id.value)
        if recorded is None:
            raise NotFoundError(
                "no such inference instance", instance_id=instance_id.value
            )
        return self._reconcile_one(recorded)

    def reconcile(self) -> str:
        unknown = 0
        for recorded in self._store.records(InferenceInstance):
            current = self._reconcile_one(recorded)
            if current.observed_state is ObservedState.UNKNOWN:
                unknown += 1
        if unknown:
            return f"{unknown} instance(s) left UNKNOWN"
        return "instances reconciled"

    def _reconcile_one(self, instance: InferenceInstance) -> InferenceInstance:
        if instance.execution_id is None:
            return instance
        try:
            handle = self._executions.observe(instance.execution_id)
        except NotFoundError:
            if instance.observed_state in _LIVE:
                return self._write(
                    instance,
                    observed_state=ObservedState.UNKNOWN,
                    lifecycle_state=LifecycleState.UNKNOWN,
                    health=HealthState.UNKNOWN,
                    ready=NOT_MEASURED,
                    last_observed_at=self._clock.now(),
                    failure_reason="execution record missing after restart",
                )
            return instance
        if handle.ownership is ExecutionOwnership.UNVERIFIED:
            return self._write(
                instance,
                observed_state=ObservedState.UNKNOWN,
                lifecycle_state=LifecycleState.UNKNOWN,
                health=HealthState.UNKNOWN,
                ready=NOT_MEASURED,
                pid=NOT_MEASURED,
                last_observed_at=self._clock.now(),
                failure_reason="process identity cannot be proven after restart",
            )
        if handle.ownership is ExecutionOwnership.ABSENT or handle.observed_state in {
            ExecutionState.EXITED,
            ExecutionState.FAILED,
        }:
            if (
                instance.desired_state is DesiredState.RUNNING
                and instance.observed_state
                in {ObservedState.RUNNING, ObservedState.STARTING}
            ):
                return self._fail(
                    instance,
                    handle.detail or "process exited unexpectedly",
                    handle,
                )
            if instance.observed_state in _LIVE:
                return self._write(
                    instance,
                    observed_state=ObservedState.STOPPED,
                    lifecycle_state=LifecycleState.STOPPED,
                    ready=False,
                    reachable=False,
                    pid=NOT_MEASURED,
                    last_observed_at=self._clock.now(),
                    exit_code=handle.exit_code,
                )
        if (
            instance.observed_state is ObservedState.RUNNING
            and handle.ownership is ExecutionOwnership.OWNED
            and handle.observed_state is ExecutionState.RUNNING
            and instance.endpoint is not None
        ):
            verdict = self._runtimes.inspect_readiness(
                instance.runtime,
                stdout=handle.stdout,
                stderr=handle.stderr,
                execution_alive=True,
                bound_address=instance.endpoint.address,
                bound_port=instance.endpoint.port,
            )
            ready = verdict.ready
            return self._write(
                instance,
                health=HealthState.HEALTHY if ready else HealthState.UNHEALTHY,
                ready=ready,
                reachable=ready,
                pid=handle.pid,
                last_observed_at=self._clock.now(),
            )
        return instance

    def _require_create(
        self, artifact: ModelArtifact, reservation: ResourceReservation
    ) -> None:
        if artifact.state is not ArtifactState.STORED:
            raise PreconditionFailedError(
                "artifact is not STORED", artifact_id=artifact.artifact_id.value
            )
        if reservation.state is not ReservationState.ACTIVE:
            raise PreconditionFailedError(
                "reservation is not ACTIVE",
                reservation_id=reservation.reservation_id.value,
            )
        if reservation.artifact_id != artifact.artifact_id:
            raise ValidationError(
                "reservation does not match artifact",
                artifact_id=artifact.artifact_id.value,
                reservation_id=reservation.reservation_id.value,
            )
        if self.live_for_reservation(reservation.reservation_id) is not None:
            raise ConflictError(
                "reservation already backs a live instance",
                reason="reservation_in_use",
                reservation_id=reservation.reservation_id.value,
            )

    def _require_start(
        self, instance: InferenceInstance, ledger_health: LedgerHealth
    ) -> None:
        if instance.artifact_id is None or instance.reservation_id is None:
            raise PreconditionFailedError("instance is missing artifact or reservation")
        artifact = self._inventory.get(instance.artifact_id)
        if artifact is None or artifact.state is not ArtifactState.STORED:
            raise PreconditionFailedError("artifact is not STORED")
        reservation = self._resources.get(instance.reservation_id)
        if reservation is None or reservation.state is not ReservationState.ACTIVE:
            raise PreconditionFailedError("reservation is not ACTIVE")
        if reservation.artifact_id != instance.artifact_id:
            raise ValidationError("reservation no longer matches this instance")
        if ledger_health is LedgerHealth.UNRESOLVED:
            raise PreconditionFailedError("current SAFE capacity is unresolved")
        if ledger_health is LedgerHealth.OVERCOMMITTED:
            raise PreconditionFailedError(
                "ledger is OVERCOMMITTED; new start is refused"
            )
        if instance.execution_id is not None:
            handle = self._executions.observe(instance.execution_id)
            if (
                handle.ownership is ExecutionOwnership.OWNED
                and handle.observed_state
                in {ExecutionState.RUNNING, ExecutionState.STARTING}
            ):
                raise ConflictError("instance already has a live process")

    def _wait_ready(
        self, instance: InferenceInstance, execution_id: ExecutionId
    ) -> tuple[str, int] | None:
        deadline = time.monotonic() + self._startup_timeout
        while time.monotonic() < deadline:
            handle = self._executions.observe(execution_id)
            alive = handle.observed_state is ExecutionState.RUNNING
            verdict = self._runtimes.inspect_readiness(
                instance.runtime,
                stdout=handle.stdout,
                stderr=handle.stderr,
                execution_alive=alive,
            )
            if (
                verdict.ready
                and is_resolved(verdict.address)
                and is_resolved(verdict.port)
            ):
                return str(verdict.address), int(verdict.port)
            if handle.observed_state in {
                ExecutionState.EXITED,
                ExecutionState.FAILED,
            }:
                return None
            time.sleep(0.05)
        return None

    def _fail(
        self,
        instance: InferenceInstance,
        reason: str,
        handle: object | None = None,
    ) -> InferenceInstance:
        exit_code = NOT_MEASURED
        if handle is not None and hasattr(handle, "exit_code"):
            exit_code = handle.exit_code
        return self._write(
            instance,
            desired_state=instance.desired_state,
            observed_state=ObservedState.FAILED,
            lifecycle_state=LifecycleState.FAILED,
            health=HealthState.UNHEALTHY,
            ready=False,
            reachable=False,
            failure_reason=reason,
            exit_code=exit_code,
            last_observed_at=self._clock.now(),
            stopped_at=self._clock.now(),
        )

    def _safe_stop(self, execution_id: ExecutionId) -> ExecutorHandle | None:
        try:
            return self._executions.stop(execution_id)
        except NotFoundError:
            return None

    def _owned_live(self, execution_id: ExecutionId | None) -> bool:
        if execution_id is None:
            return False
        try:
            handle = self._executions.observe(execution_id)
        except NotFoundError:
            return False
        return (
            handle.ownership is ExecutionOwnership.OWNED
            and handle.observed_state
            in {ExecutionState.RUNNING, ExecutionState.STARTING}
        )

    def _pid_of(self, execution_id: ExecutionId) -> object:
        handle = self._executions.observe(execution_id)
        return handle.pid

    def _require(self, instance_id: InstanceId) -> InferenceInstance:
        found = self._store.get(InferenceInstance, instance_id.value)
        if found is None:
            raise NotFoundError(
                "no such inference instance", instance_id=instance_id.value
            )
        return found

    def _write(self, instance: InferenceInstance, **changes: Any) -> InferenceInstance:
        updated = replace(instance, **changes)
        self._store.put(updated.instance_id.value, updated)
        return updated


def _spec_from(launch: RuntimeLaunchSpec) -> ExecutorSpec:
    """Copy a recipe into executor language. Inference does not import platform."""
    return ExecutorSpec(
        executable=launch.executable,
        arguments=launch.arguments,
        environment=launch.environment,
        working_directory=launch.working_directory,
        output_limit_bytes=launch.output_limit_bytes,
        grace_period_seconds=launch.grace_period_seconds,
        device_requests=tuple(
            DeviceRequest(index=index) for index in launch.device_indexes
        ),
        filesystem_mappings=launch.filesystem_mappings,
        network_bindings=launch.network_bindings,
    )
