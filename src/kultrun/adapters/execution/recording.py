"""Deterministic executor fixture. Consumes the generic spec. Does not exec.

This is not a ContainerExecutor and not a production adapter. It exists so
the RuntimeLaunchSpec / InferenceInstance composition can be proven without
NativeProcessExecutor internals, Popen, or a PID.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from kultrun.evidence.contracts import Confidence
from kultrun.execution.contracts import (
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
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED

IDENTITY = Name("recording")


@dataclass
class _Recorded:
    spec: ExecutorSpec
    handle: ExecutorHandle


class RecordingExecutor:
    """Accepts RuntimeLaunchSpec-derived specs and returns generic handles."""

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._records: dict[str, _Recorded] = {}
        self.accepted: list[ExecutorSpec] = []

    @property
    def identity(self) -> Name:
        return IDENTITY

    def capabilities(self, host: HostCapabilities) -> ExecutorCapabilityProfile:
        return ExecutorCapabilityProfile(
            executor=self.identity,
            executor_type=Name("recording"),
            host_id=host.host_id,
            host_fingerprint=host.fingerprint,
            availability=ExecutorAvailability.AVAILABLE,
            process_execution=FeatureSupport.SUPPORTED,
            structured_argv=FeatureSupport.SUPPORTED,
            environment_variables=FeatureSupport.SUPPORTED,
            working_directory=FeatureSupport.SUPPORTED,
            filesystem_access="host_native",
            networking="host_native",
            port_binding=FeatureSupport.SUPPORTED,
            accelerator_exposure=FeatureSupport.UNKNOWN,
            bounded_stdout=FeatureSupport.SUPPORTED,
            bounded_stderr=FeatureSupport.SUPPORTED,
            lifecycle_observation=FeatureSupport.SUPPORTED,
            graceful_termination=FeatureSupport.SUPPORTED,
            forced_termination=FeatureSupport.SUPPORTED,
            isolation=FeatureSupport.UNSUPPORTED,
            reason=NOT_PROVIDED,
            accelerator_exposure_mode=NOT_PROVIDED,
            limitations=(
                "TEST_ONLY fixture",
                "does not start a real process",
                "not a ContainerExecutor",
            ),
            evidence=("recording-executor-fixture",),
            confidence=Confidence.HIGH,
        )

    def start(self, host_id: HostId, spec: ExecutorSpec) -> ExecutorHandle:
        self.accepted.append(spec)
        now = self._clock.now()
        token = f"recording:{len(self.accepted)}"
        handle = ExecutorHandle(
            execution_id=ExecutionId.generate(),
            host_id=host_id,
            executor=self.identity,
            desired_state=ExecutionState.RUNNING,
            observed_state=ExecutionState.RUNNING,
            health=ExecutionHealth.UNKNOWN,
            ownership=ExecutionOwnership.OWNED,
            created_at=now,
            executable=spec.executable,
            arguments=spec.arguments,
            started_at=now,
            stdout="recording:started\n",
            external_identity=token,
            network_bindings=spec.network_bindings,
        )
        self._records[handle.execution_id.value] = _Recorded(spec=spec, handle=handle)
        return handle

    def observe(self, handle: ExecutorHandle) -> ExecutorHandle:
        recorded = self._records.get(handle.execution_id.value)
        if recorded is None:
            return replace(
                handle,
                ownership=ExecutionOwnership.ABSENT,
                observed_state=ExecutionState.EXITED,
                pid=NOT_MEASURED,
                detail=handle.detail or "recording has no such execution",
            )
        return recorded.handle

    def stop(self, handle: ExecutorHandle) -> ExecutorHandle:
        recorded = self._records.get(handle.execution_id.value)
        if recorded is None:
            raise NotFoundError(
                "no such recorded execution", execution_id=handle.execution_id.value
            )
        if recorded.handle.observed_state in {
            ExecutionState.EXITED,
            ExecutionState.FAILED,
        }:
            return recorded.handle
        now = self._clock.now()
        stopped = replace(
            recorded.handle,
            desired_state=ExecutionState.EXITED,
            observed_state=ExecutionState.EXITED,
            ownership=ExecutionOwnership.ABSENT,
            exited_at=now,
            exit_code=0,
            stdout=recorded.handle.stdout + "recording:stopped\n",
        )
        recorded.handle = stopped
        return stopped


def build(clock: Clock | None = None) -> RecordingExecutor:
    return RecordingExecutor(clock)
