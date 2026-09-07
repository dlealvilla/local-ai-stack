"""Container realization of the generic Executor port.

Docker-specific argv stays in the ContainerEngine adapter. This class maps
engine state onto ExecutorHandle.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace

from kultrun.evidence.contracts import Confidence
from kultrun.execution.contracts import (
    ContainerExecutionConfig,
    ContainerNetworkMode,
    ExecutionHealth,
    ExecutionId,
    ExecutionOwnership,
    ExecutionState,
    ExecutorAvailability,
    ExecutorCapabilityProfile,
    ExecutorHandle,
    ExecutorSpec,
    FeatureSupport,
)
from kultrun.execution.engine import ContainerInspection
from kultrun.execution.ports import ContainerEngine
from kultrun.execution.resolve import container_command, host_pythonpath_entries
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, is_resolved

IDENTITY = Name("container-docker")


@dataclass
class _Live:
    spec: ExecutorSpec
    container_id: str
    config: ContainerExecutionConfig


class ContainerExecutor:
    """Generic Executor backed by a ContainerEngine."""

    def __init__(
        self,
        engine: ContainerEngine,
        config: ContainerExecutionConfig,
        clock: Clock | None = None,
    ) -> None:
        self._engine = engine
        self._config = config
        self._clock = clock or SystemClock()
        self._live: dict[str, _Live] = {}
        self._lock = threading.Lock()

    @property
    def identity(self) -> Name:
        return IDENTITY

    def capabilities(self, host: HostCapabilities) -> ExecutorCapabilityProfile:
        probe = self._engine.probe()
        available = probe.availability is ExecutorAvailability.AVAILABLE
        support = (
            FeatureSupport.SUPPORTED if available else FeatureSupport.UNSUPPORTED
        )
        host_net = self._config.network_mode is ContainerNetworkMode.HOST
        return ExecutorCapabilityProfile(
            executor=self.identity,
            executor_type=Name("container"),
            host_id=host.host_id,
            host_fingerprint=host.fingerprint,
            availability=(
                ExecutorAvailability.AVAILABLE
                if available
                else ExecutorAvailability.UNAVAILABLE
            ),
            process_execution=support,
            structured_argv=FeatureSupport.SUPPORTED,
            environment_variables=FeatureSupport.SUPPORTED,
            working_directory=FeatureSupport.SUPPORTED,
            filesystem_access="mapped",
            networking="host_namespace" if host_net else "bridge",
            port_binding=(
                FeatureSupport.SUPPORTED if host_net else FeatureSupport.UNSUPPORTED
            ),
            accelerator_exposure=FeatureSupport.UNKNOWN,
            bounded_stdout=FeatureSupport.SUPPORTED,
            bounded_stderr=FeatureSupport.SUPPORTED,
            lifecycle_observation=support,
            graceful_termination=support,
            forced_termination=support,
            isolation=FeatureSupport.SUPPORTED,
            reason=(
                NOT_PROVIDED
                if available
                else (
                    probe.reason
                    if is_resolved(probe.reason)
                    else "engine unavailable"
                )
            ),
            accelerator_exposure_mode="not_implemented",
            limitations=_limitations(host_net=host_net),
            evidence=(
                f"engine={self._engine.identity.value}",
                f"provider={self.identity.value}",
                *(probe.evidence or ()),
            ),
            confidence=Confidence.HIGH if available else Confidence.LOW,
        )

    def start(self, host_id: HostId, spec: ExecutorSpec) -> ExecutorHandle:
        now = self._clock.now()
        execution_id = ExecutionId.generate()
        try:
            command = (container_command(spec.executable), *spec.arguments)
        except ValidationError as error:
            return _failed(
                execution_id,
                host_id,
                spec,
                now,
                detail=error.message,
            )
        environment = host_pythonpath_entries(spec.environment)
        name = _safe_name(self._config.name_prefix, execution_id.value)
        labels = (
            self._config.managed_label,
            f"kultrun.execution_id={execution_id.value}",
        )
        created = self._engine.create(
            name=name,
            config=self._config,
            command=command,
            environment=environment,
            labels=labels,
        )
        if not created.ok or created.container_id is None:
            return _failed(
                execution_id,
                host_id,
                spec,
                now,
                detail=created.detail or "container create failed",
                external=created.container_id,
            )
        container_id = created.container_id
        started = self._engine.start(container_id)
        if not started.ok:
            self._cleanup(container_id)
            return _failed(
                execution_id,
                host_id,
                spec,
                now,
                detail=started.detail or "container start failed",
                external=container_id,
            )
        with self._lock:
            self._live[execution_id.value] = _Live(
                spec=spec, container_id=container_id, config=self._config
            )
        handle = ExecutorHandle(
            execution_id=execution_id,
            host_id=host_id,
            executor=self.identity,
            desired_state=ExecutionState.RUNNING,
            observed_state=ExecutionState.RUNNING,
            health=ExecutionHealth.UNKNOWN,
            ownership=ExecutionOwnership.OWNED,
            created_at=now,
            executable=command[0],
            arguments=spec.arguments,
            started_at=now,
            external_identity=container_id,
            network_bindings=spec.network_bindings,
        )
        return self.observe(handle)

    def observe(self, handle: ExecutorHandle) -> ExecutorHandle:
        with self._lock:
            live = self._live.get(handle.execution_id.value)
        if live is None:
            return _unclaimed(self._engine, handle)
        inspection = self._engine.inspect(live.container_id)
        logs = self._engine.logs(
            live.container_id, limit_bytes=live.spec.output_limit_bytes
        )
        if inspection is None:
            with self._lock:
                self._live.pop(handle.execution_id.value, None)
            return replace(
                handle,
                observed_state=ExecutionState.EXITED,
                ownership=ExecutionOwnership.ABSENT,
                pid=NOT_MEASURED,
                stdout=logs.stdout,
                stderr=logs.stderr,
                output_truncated=logs.truncated,
                detail=handle.detail or "container is no longer owned",
            )
        state, exit_code = _map_state(inspection)
        if state in {ExecutionState.EXITED, ExecutionState.FAILED}:
            with self._lock:
                self._live.pop(handle.execution_id.value, None)
        return replace(
            handle,
            observed_state=state,
            ownership=(
                ExecutionOwnership.OWNED
                if state is ExecutionState.RUNNING
                else ExecutionOwnership.ABSENT
            ),
            pid=NOT_MEASURED,
            exit_code=exit_code if exit_code is not None else handle.exit_code,
            stdout=logs.stdout,
            stderr=logs.stderr,
            output_truncated=logs.truncated,
            external_identity=live.container_id,
            exited_at=(
                handle.exited_at or self._clock.now()
                if state in {ExecutionState.EXITED, ExecutionState.FAILED}
                else handle.exited_at
            ),
        )

    def stop(self, handle: ExecutorHandle) -> ExecutorHandle:
        with self._lock:
            live = self._live.get(handle.execution_id.value)
        if live is None:
            observed = self.observe(handle)
            if observed.observed_state in {
                ExecutionState.EXITED,
                ExecutionState.FAILED,
            }:
                return observed
            return observed
        stopping = replace(
            handle,
            desired_state=ExecutionState.STOPPING,
            observed_state=ExecutionState.STOPPING,
        )
        self._engine.stop(
            live.container_id,
            grace_period_seconds=live.spec.grace_period_seconds,
        )
        inspection = self._engine.inspect(live.container_id)
        if inspection is not None and inspection.running:
            self._engine.kill(live.container_id)
        stopped = self.observe(stopping)
        if live.config.remove_on_stop:
            self._engine.remove(live.container_id)
        return stopped

    def _cleanup(self, container_id: str) -> None:
        if self._config.remove_on_stop:
            self._engine.remove(container_id)


def build(
    engine: ContainerEngine,
    config: ContainerExecutionConfig,
    clock: Clock | None = None,
) -> ContainerExecutor:
    return ContainerExecutor(engine, config, clock)


def _limitations(*, host_net: bool) -> tuple[str, ...]:
    items = [
        "accelerator_exposure unknown; GPU device attachment is not implemented",
        "single container engine: docker CLI",
        "no image marketplace",
        "no kubernetes",
    ]
    if host_net:
        items.append("host_network is linux-only v0; bridge publish is deferred")
    return tuple(items)


def _safe_name(prefix: str, execution_id: str) -> str:
    token = execution_id.replace("_", "-")
    return f"{prefix}{token}"


def _map_state(
    inspection: ContainerInspection,
) -> tuple[ExecutionState, int | None]:
    status = inspection.status.lower()
    if inspection.running or status in {"running", "paused"}:
        return ExecutionState.RUNNING, None
    if status in {"created", "restarting"}:
        return ExecutionState.STARTING, inspection.exit_code
    if status in {"removing"}:
        return ExecutionState.STOPPING, inspection.exit_code
    code = inspection.exit_code
    if code in (None, 0):
        return ExecutionState.EXITED, 0 if code == 0 else code
    return ExecutionState.FAILED, code


def _failed(
    execution_id: ExecutionId,
    host_id: HostId,
    spec: ExecutorSpec,
    now: object,
    *,
    detail: str,
    external: str | None = None,
) -> ExecutorHandle:
    return ExecutorHandle(
        execution_id=execution_id,
        host_id=host_id,
        executor=IDENTITY,
        desired_state=ExecutionState.RUNNING,
        observed_state=ExecutionState.FAILED,
        health=ExecutionHealth.UNKNOWN,
        ownership=ExecutionOwnership.ABSENT,
        created_at=now,  # type: ignore[arg-type]
        executable=spec.executable,
        arguments=spec.arguments,
        exited_at=now,  # type: ignore[arg-type]
        detail=detail,
        external_identity=external if external is not None else NOT_MEASURED,
        network_bindings=spec.network_bindings,
    )


def _unclaimed(engine: ContainerEngine, handle: ExecutorHandle) -> ExecutorHandle:
    if handle.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}:
        return replace(handle, ownership=ExecutionOwnership.ABSENT, pid=NOT_MEASURED)
    if is_resolved(handle.external_identity):
        inspection = engine.inspect(str(handle.external_identity))
        if inspection is not None and inspection.running:
            return replace(
                handle,
                ownership=ExecutionOwnership.UNVERIFIED,
                observed_state=ExecutionState.RUNNING,
                health=ExecutionHealth.UNKNOWN,
                pid=NOT_MEASURED,
                detail=(
                    "container exists but this control plane did not "
                    "start it in this process"
                ),
            )
    return replace(
        handle,
        ownership=ExecutionOwnership.ABSENT,
        observed_state=ExecutionState.EXITED,
        pid=NOT_MEASURED,
        detail=handle.detail or "container is no longer owned by this control plane",
    )
