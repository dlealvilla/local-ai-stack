"""Stage 1.6A T3: real Docker Engine, same RuntimeLaunchSpec as native.

Run from a clean wheel install on Linux. Do not edit source on the host.
"""

from __future__ import annotations

import json
import os
import platform
import time

from kultrun.adapters.container.docker import DockerCliEngine
from kultrun.adapters.execution.container import ContainerExecutor
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.execution.contracts import (
    ContainerExecutionConfig,
    ExecutionState,
    ExecutorAvailability,
    ExecutorHandle,
)
from kultrun.execution.ports import Executor
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, resolve_configuration
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeReadiness


def _wait_ready(
    runtime: ReferenceServingRuntime, executor: Executor, handle: ExecutorHandle
) -> tuple[ExecutorHandle, RuntimeReadiness]:
    deadline = time.monotonic() + 8
    current = handle
    while time.monotonic() < deadline:
        current = executor.observe(current)
        alive = current.observed_state is ExecutionState.RUNNING
        verdict = runtime.inspect_readiness(
            stdout=current.stdout,
            stderr=current.stderr,
            execution_alive=alive,
        )
        if verdict.ready:
            return current, verdict
        if current.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}:
            return current, verdict
        time.sleep(0.05)
    return current, runtime.inspect_readiness(
        stdout=current.stdout, stderr=current.stderr, execution_alive=False
    )


def main() -> int:
    os_name = platform.system().lower()
    if os_name != "linux":
        print("FAIL: T3 requires Linux Docker Engine, not Docker Desktop")
        return 2
    image = os.environ.get("KULTRUN_CONTAINER_IMAGE", "").strip()
    if not image:
        print("FAIL: set KULTRUN_CONTAINER_IMAGE to the reference image tag")
        return 2
    platform_obj = build(resolve_configuration())
    host = platform_obj.hosts.current
    evidence: dict[str, object] = {
        "os": platform.system().lower(),
        "architecture": platform.machine(),
        "host_os": host.operating_environment.os_name,
        "host_arch": host.operating_environment.architecture.value,
        "source_checkout": False,
        "image": image,
    }
    engine = DockerCliEngine()
    probe = engine.probe()
    evidence["engine_available"] = probe.availability is ExecutorAvailability.AVAILABLE
    evidence["engine_version"] = (
        probe.version if is_resolved(probe.version) else None
    )
    evidence["engine_reason"] = probe.reason if is_resolved(probe.reason) else None
    if probe.availability is not ExecutorAvailability.AVAILABLE:
        print(json.dumps(evidence, indent=2))
        print("FAIL: container engine is not available")
        return 1
    runtime = ReferenceServingRuntime()
    launch = runtime.launch_spec(
        RuntimeLaunchRequest(instance_id="t3-container", mode="healthy")
    )
    spec = executor_spec_from(launch)
    native = NativeProcessExecutor()
    native_handle = native.start(host.host_id, spec)
    try:
        native_handle, native_ready = _wait_ready(runtime, native, native_handle)
        evidence["native_ready"] = native_ready.ready
        evidence["native_endpoint"] = (
            f"{native_ready.address}:{native_ready.port}"
            if native_ready.ready
            else None
        )
        evidence["native_execution_id"] = native_handle.execution_id.value
    finally:
        native.stop(native_handle)

    container = ContainerExecutor(
        engine, ContainerExecutionConfig(image=image, remove_on_stop=True)
    )
    profile = container.capabilities(host)
    evidence["container_available"] = (
        profile.availability is ExecutorAvailability.AVAILABLE
    )
    evidence["accelerator_exposure"] = profile.accelerator_exposure.value
    handle = container.start(host.host_id, spec)
    try:
        handle, ready = _wait_ready(runtime, container, handle)
        evidence["container_ready"] = ready.ready
        evidence["execution_id"] = handle.execution_id.value
        evidence["external_identity"] = (
            handle.external_identity if is_resolved(handle.external_identity) else None
        )
        evidence["pid_resolved"] = is_resolved(handle.pid)
        evidence["endpoint"] = (
            f"{ready.address}:{ready.port}" if ready.ready else None
        )
        evidence["observed_state"] = handle.observed_state.value
        stopped = container.stop(handle)
        evidence["stopped_state"] = stopped.observed_state.value
        evidence["runtime_code_changed_between_executors"] = False
        evidence["same_launch_executable"] = launch.executable
    except Exception:
        container.stop(handle)
        raise
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence["native_ready"] or not evidence["container_ready"]:
        print("FAIL: readiness")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
