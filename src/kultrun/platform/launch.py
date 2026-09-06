"""Compose a runtime recipe into an executor spec.

`execution` and `runtime` must not import each other. This module sits in
`platform` so the copy is an explicit composition step, not a hidden edge.
"""

from __future__ import annotations

from kultrun.execution.contracts import DeviceRequest, ExecutorSpec
from kultrun.runtime.contracts import RuntimeLaunchSpec


def executor_spec_from(launch: RuntimeLaunchSpec) -> ExecutorSpec:
    """Copy a recipe into the executor's language. Field-for-field, no policy."""
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
    )
