"""Run a RuntimeVerificationProbe through the wired Executor.

Runtime owns the recipe. Execution owns process launch. This composition
helper copies one into the other and waits with a timeout.
"""

from __future__ import annotations

import time

from kultrun.execution.contracts import ExecutionState, ExecutorSpec
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostId
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import RuntimeVerificationProbe
from kultrun.runtime.ports import ProbeExecutionResult

_POLL_SECONDS = 0.05


class ExecutorProbeRunner:
    """One-shot verification execution. Not a runtime interpreter."""

    def __init__(self, executions: ExecutionService) -> None:
        self._executions = executions

    def run(
        self,
        spec: RuntimeVerificationProbe,
        *,
        host_id: HostId,
    ) -> ProbeExecutionResult:
        handle = self._executions.start(host_id, _executor_spec(spec))
        deadline = time.monotonic() + spec.timeout_seconds
        current = handle
        while current.observed_state in (
            ExecutionState.PENDING,
            ExecutionState.STARTING,
            ExecutionState.RUNNING,
            ExecutionState.STOPPING,
        ):
            if time.monotonic() > deadline:
                stopped = self._executions.stop(current.execution_id)
                return ProbeExecutionResult(
                    timed_out=True,
                    exit_code=_exit(stopped.exit_code),
                    stdout=stopped.stdout,
                    stderr=stopped.stderr,
                    truncated=stopped.output_truncated,
                    executed=True,
                )
            time.sleep(_POLL_SECONDS)
            current = self._executions.observe(current.execution_id)
        return ProbeExecutionResult(
            timed_out=False,
            exit_code=_exit(current.exit_code),
            stdout=current.stdout,
            stderr=current.stderr,
            truncated=current.output_truncated,
            executed=True,
        )


def _executor_spec(probe: RuntimeVerificationProbe) -> ExecutorSpec:
    return ExecutorSpec(
        executable=probe.executable,
        arguments=probe.arguments,
        environment=probe.environment,
        output_limit_bytes=probe.output_limit_bytes,
        grace_period_seconds=5.0,
    )


def _exit(value: object) -> int | None:
    if is_resolved(value) and isinstance(value, int):
        return value
    return None
