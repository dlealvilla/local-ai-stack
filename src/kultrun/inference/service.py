"""InferenceInstance lifecycle. Composes runtime and executor; does not exec."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
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
    DEFAULT_INFERENCE_TIMEOUT_SECONDS,
    DEFAULT_OUTPUT_TOKENS,
    DesiredState,
    HealthState,
    InferenceEndpoint,
    InferenceInstance,
    InferenceRequest,
    InferenceRequestId,
    InferenceResponse,
    InstanceId,
    LifecycleState,
    ObservedState,
)
from kultrun.inference.endpoint import LOOPBACK
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe, is_resolved
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
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeSupportTier,
)

SERVING_RUNTIME = Name("reference-serving")
PRODUCT_VLLM = Name("vllm")
STARTUP_TIMEOUT_SECONDS = 5.0
_LIVE = frozenset(
    {ObservedState.STARTING, ObservedState.RUNNING, ObservedState.STOPPING}
)
_BLOCKS_RELEASE = _LIVE | frozenset({ObservedState.UNKNOWN})
_LAUNCHABLE_TIERS = frozenset(
    {RuntimeSupportTier.REFERENCE, RuntimeSupportTier.TEST_ONLY}
)


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
        live_executor: str | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._inventory = inventory
        self._resources = resources
        self._executions = executions
        self._runtimes = runtimes
        self._startup_timeout = startup_timeout
        self._live_executor = live_executor

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
        *,
        plan_id: Maybe[str] = NOT_PROVIDED,
        plan_basis: Maybe[str] = NOT_PROVIDED,
        runtime_version: Maybe[str] = NOT_PROVIDED,
        placement: Maybe[str] = NOT_PROVIDED,
        accelerator_index: int | None = None,
        context_tokens: Maybe[int] = NOT_MEASURED,
    ) -> InferenceInstance:
        """Bind an artifact and reservation. Isolated tests may omit plan fields.

        Product create always supplies plan provenance and explicit runtime
        and executor names. A missing runtime is reference-serving only when
        there is no plan identity, so a plan-driven call cannot silently
        reconstruct a test harness.
        """
        self._require_create(artifact, reservation)
        if is_resolved(plan_id) and runtime is None:
            raise ValidationError(
                "plan-driven create requires an explicit runtime",
                plan_id=plan_id,
            )
        now = self._clock.now()
        chosen = runtime or SERVING_RUNTIME
        chosen_executor = executor or Name("native-process")
        instance = InferenceInstance(
            instance_id=InstanceId.generate(),
            host_id=reservation.host_id,
            model_id=artifact.model_id,
            runtime=chosen,
            executor=chosen_executor,
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
            serving_runtime=(
                chosen.value if chosen == SERVING_RUNTIME else NOT_MEASURED
            ),
            plan_id=plan_id,
            plan_basis=plan_basis,
            runtime_version=runtime_version,
            placement=placement,
            accelerator_index=accelerator_index,
            context_length_tokens=context_tokens,
        )
        self._store.put(instance.instance_id.value, instance)
        return instance

    def start(
        self,
        instance_id: InstanceId,
        *,
        ledger_health: LedgerHealth,
        serving_mode: str = "healthy",
        launch_request: RuntimeLaunchRequest | None = None,
        startup_timeout: float | None = None,
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
        request = launch_request or RuntimeLaunchRequest(
            instance_id=instance.instance_id.value,
            mode=serving_mode,
            artifact_id=(
                instance.artifact_id.value if instance.artifact_id is not None else ""
            ),
        )
        self._require_launch_path(instance, request)
        timeout = self._startup_timeout if startup_timeout is None else startup_timeout
        now = self._clock.now()
        endpoint = None
        if is_resolved(request.bind_port) and is_resolved(request.bind_address):
            endpoint = InferenceEndpoint(
                scheme="http",
                address=str(request.bind_address),
                port=int(request.bind_port),
            )
        instance = self._write(
            instance,
            desired_state=DesiredState.RUNNING,
            observed_state=ObservedState.STARTING,
            lifecycle_state=LifecycleState.STARTING,
            health=HealthState.UNKNOWN,
            last_observed_at=now,
            failure_reason=NOT_MEASURED,
            ready=False,
            reachable=False,
            endpoint=endpoint,
        )
        try:
            launch = self._runtimes.launch(instance.runtime, request)
            handle = self._executions.start(instance.host_id, _spec_from(launch))
        except (ValidationError, PreconditionFailedError) as error:
            return self._fail(
                instance,
                f"process did not start: {error.message}",
                reason_code="process_did_not_start",
            )
        instance = self._write(instance, execution_id=handle.execution_id)
        if handle.observed_state is ExecutionState.FAILED:
            return self._fail(
                instance,
                f"process did not start: {handle.detail or 'executor failed to start'}",
                handle,
                reason_code="process_did_not_start",
            )
        expected = (
            str(request.served_model)
            if is_resolved(request.served_model)
            else served_model_identity(instance)
        )
        outcome = self._wait_ready(
            instance,
            handle.execution_id,
            timeout=timeout,
            bound_address=endpoint.address if endpoint is not None else None,
            bound_port=endpoint.port if endpoint is not None else None,
            expected_served_model=(
                expected if instance.runtime == PRODUCT_VLLM else None
            ),
        )
        if outcome.kind != "ready":
            self._safe_stop(handle.execution_id)
            refreshed = self._executions.observe(handle.execution_id)
            return self._fail(
                instance,
                outcome.message,
                refreshed,
                reason_code=outcome.reason,
            )
        now = self._clock.now()
        host, port = outcome.host, outcome.port
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
            failure_reason=NOT_MEASURED,
        )

    def infer(
        self,
        instance_id: InstanceId,
        request: InferenceRequest,
        *,
        configuration_current: Maybe[bool] = NOT_MEASURED,
    ) -> InferenceResponse:
        instance = self.observe(instance_id)
        if instance.observed_state is ObservedState.FAILED:
            raise PreconditionFailedError(
                "instance is not running",
                reason="instance_not_running",
                observed_state=instance.observed_state.value,
            )
        if instance.observed_state is not ObservedState.RUNNING:
            reason = (
                "instance_not_ready"
                if instance.observed_state is ObservedState.STARTING
                else "instance_not_running"
            )
            raise PreconditionFailedError(
                "instance is not running",
                reason=reason,
                observed_state=instance.observed_state.value,
            )
        if not (is_resolved(instance.ready) and instance.ready is True):
            raise PreconditionFailedError(
                "instance is not ready",
                reason="instance_not_ready",
            )
        if instance.reservation_id is None:
            raise PreconditionFailedError(
                "reservation is not ACTIVE",
                reason="reservation_not_active",
            )
        reservation = self._resources.get(instance.reservation_id)
        if reservation is None or reservation.state is not ReservationState.ACTIVE:
            raise PreconditionFailedError(
                "reservation is not ACTIVE",
                reason="reservation_not_active",
            )
        if instance.execution_id is None:
            raise PreconditionFailedError(
                "runtime process is not running",
                reason="runtime_process_exited",
            )
        handle = self._executions.observe(instance.execution_id)
        if (
            handle.ownership is not ExecutionOwnership.OWNED
            or handle.observed_state is not ExecutionState.RUNNING
        ):
            failed = self._fail(
                instance,
                handle.detail or "process exited unexpectedly",
                handle,
                reason_code="runtime_process_exited",
            )
            raise PreconditionFailedError(
                "runtime process exited",
                reason="runtime_process_exited",
                instance_id=failed.instance_id.value,
            )
        if instance.endpoint is None:
            raise PreconditionFailedError(
                "instance is not ready",
                reason="instance_not_ready",
            )
        adapter = self._runtimes.get(instance.runtime)
        complete = getattr(adapter, "complete", None)
        if complete is None:
            raise PreconditionFailedError(
                "selected runtime does not support inference",
                reason="inference_unsupported",
                runtime=instance.runtime.value,
            )
        served = served_model_identity(instance)
        request_id = InferenceRequestId.generate()
        started = time.monotonic()
        completion = complete(
            address=instance.endpoint.address,
            port=instance.endpoint.port,
            served_model=served,
            prompt=request.prompt,
            max_output_tokens=request.max_output_tokens,
            temperature=request.temperature,
            timeout_seconds=request.timeout_seconds,
        )
        latency_ms = max(0, int((time.monotonic() - started) * 1000))
        return InferenceResponse(
            request_id=request_id,
            instance_id=instance.instance_id,
            model_id=instance.model_id,
            served_model=served,
            generated_text=completion.text,
            runtime=instance.runtime,
            latency_ms=latency_ms,
            finish_reason=(
                completion.finish_reason if completion.finish_reason else NOT_PROVIDED
            ),
            input_tokens=(
                completion.input_tokens
                if completion.input_tokens is not None
                else NOT_MEASURED
            ),
            output_tokens=(
                completion.output_tokens
                if completion.output_tokens is not None
                else NOT_MEASURED
            ),
            runtime_version=instance.runtime_version,
            executor=instance.executor.value,
            configuration_current=configuration_current,
        )

    def occupied_ports(self) -> set[int]:
        ports: set[int] = set()
        for item in self._store.records(InferenceInstance):
            current = item
            if current.observed_state in _LIVE and current.endpoint is not None:
                ports.add(current.endpoint.port)
        return ports

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
                expected_served_model=served_model_identity(instance),
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

    def _require_launch_path(
        self, instance: InferenceInstance, request: RuntimeLaunchRequest
    ) -> None:
        """Refuse missing runtimes. Product vLLM needs a complete request."""
        if (
            self._live_executor is not None
            and instance.executor.value != self._live_executor
        ):
            raise PreconditionFailedError(
                "selected executor is not available",
                reason="executor_unavailable",
                required=instance.executor.value,
                available=self._live_executor,
            )
        try:
            adapter = self._runtimes.get(instance.runtime)
        except NotFoundError as error:
            raise PreconditionFailedError(
                "selected runtime is not available",
                reason="runtime_unavailable",
                runtime=instance.runtime.value,
            ) from error
        tier = adapter.support().support_tier
        if tier in _LAUNCHABLE_TIERS:
            return
        if (
            tier is RuntimeSupportTier.PRODUCT
            and instance.runtime == PRODUCT_VLLM
            and instance.executor.value == "native-process"
            and _vllm_request_complete(request)
        ):
            return
        raise PreconditionFailedError(
            "selected runtime cannot launch this instance yet",
            reason="runtime_launch_unsupported",
            runtime=instance.runtime.value,
        )

    def _wait_ready(
        self,
        instance: InferenceInstance,
        execution_id: ExecutionId,
        *,
        timeout: float,
        bound_address: str | None,
        bound_port: int | None,
        expected_served_model: str | None,
    ) -> _ReadyOutcome:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            handle = self._executions.observe(execution_id)
            alive = handle.observed_state is ExecutionState.RUNNING
            verdict = self._runtimes.inspect_readiness(
                instance.runtime,
                stdout=handle.stdout,
                stderr=handle.stderr,
                execution_alive=alive,
                bound_address=bound_address,
                bound_port=bound_port,
                expected_served_model=expected_served_model,
            )
            if (
                is_resolved(verdict.reason)
                and str(verdict.reason) == "runtime_model_mismatch"
            ):
                return _ReadyOutcome(
                    kind="mismatch",
                    reason="runtime_model_mismatch",
                    message="runtime reported a different served model than planned",
                )
            if (
                verdict.ready
                and is_resolved(verdict.address)
                and is_resolved(verdict.port)
            ):
                return _ReadyOutcome(
                    kind="ready",
                    host=str(verdict.address),
                    port=int(verdict.port),
                )
            if handle.observed_state in {
                ExecutionState.EXITED,
                ExecutionState.FAILED,
            }:
                code = handle.exit_code if is_resolved(handle.exit_code) else "unknown"
                evidence = _bounded_log(handle.stderr or handle.stdout)
                message = f"process exited before ready ({code})"
                if evidence:
                    message = f"{message}: {evidence}"
                return _ReadyOutcome(
                    kind="exited",
                    reason="runtime_process_exited",
                    message=message,
                )
            time.sleep(0.05)
        evidence = ""
        try:
            handle = self._executions.observe(execution_id)
            evidence = _bounded_log(handle.stderr or handle.stdout)
        except NotFoundError:
            evidence = ""
        message = "runtime_readiness_timeout"
        if evidence:
            message = f"{message}: {evidence}"
        return _ReadyOutcome(
            kind="timeout",
            reason="runtime_readiness_timeout",
            message=message,
        )

    def _fail(
        self,
        instance: InferenceInstance,
        reason: str,
        handle: object | None = None,
        *,
        reason_code: str | None = None,
    ) -> InferenceInstance:
        del reason_code
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


@dataclass(frozen=True, slots=True)
class _ReadyOutcome:
    kind: str
    reason: str = ""
    message: str = ""
    host: str = LOOPBACK
    port: int = 0


def served_model_identity(instance: InferenceInstance) -> str:
    """Deterministic served-model name from plan identity. Not a filesystem path."""
    if is_resolved(instance.logical_name):
        token = str(instance.logical_name).strip()
        if token:
            return token
    return instance.model_id.value


def _vllm_request_complete(request: RuntimeLaunchRequest) -> bool:
    return (
        is_resolved(request.interpreter)
        and is_resolved(request.model_path)
        and is_resolved(request.served_model)
        and is_resolved(request.bind_port)
        and bool(str(request.interpreter).strip())
        and bool(str(request.model_path).strip())
    )


def _bounded_log(text: str, *, limit: int = 800) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


_INFER_QUERY_KEYS = frozenset(
    {
        "instance_id",
        "prompt",
        "max_output_tokens",
        "temperature",
        "timeout_seconds",
    }
)
_INFER_REFUSED_KEYS = frozenset(
    {
        "model",
        "model_id",
        "served_model",
        "url",
        "path",
        "executable",
        "host",
        "port",
        "runtime",
        "argv",
        "command",
        "flags",
        "quantization",
        "trust_remote_code",
    }
)


def parse_inference_request(query: Mapping[str, str]) -> InferenceRequest:
    """Build a generic request from query fields. Callers cannot choose the model."""
    refused = sorted(set(query) & _INFER_REFUSED_KEYS)
    if refused:
        raise ValidationError(
            "inference callers may not choose model, runtime, path, or flags",
            refused=refused,
        )
    extra = sorted(key for key in query if key not in _INFER_QUERY_KEYS)
    if extra:
        raise ValidationError(
            "unsupported inference parameter",
            refused=extra,
        )
    return InferenceRequest(
        prompt=query.get("prompt", ""),
        max_output_tokens=_optional_int(
            query.get("max_output_tokens"), DEFAULT_OUTPUT_TOKENS
        ),
        temperature=_optional_float(query.get("temperature"), 0.0),
        timeout_seconds=_optional_float(
            query.get("timeout_seconds"), DEFAULT_INFERENCE_TIMEOUT_SECONDS
        ),
    )


def _optional_int(raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValidationError(
            "max_output_tokens must be an integer",
            parameter="max_output_tokens",
        ) from error


def _optional_float(raw: str | None, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise ValidationError("numeric inference field is malformed") from error
