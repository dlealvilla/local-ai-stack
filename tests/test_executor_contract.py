"""Reusable executor contract: native and recording share one input/output."""

from __future__ import annotations

import contextlib
import sys
import time

import pytest

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.execution.recording import RecordingExecutor
from kultrun.execution.contracts import (
    ExecutionState,
    ExecutorAvailability,
    ExecutorSpec,
    FeatureSupport,
)
from kultrun.kernel.unresolved import is_resolved
from tests.test_contracts import host_capabilities


def _spec(**overrides: object) -> ExecutorSpec:
    payload: dict[str, object] = {
        "executable": sys.executable,
        "arguments": ("-c", "print('kultrun-executor-contract')"),
    }
    payload.update(overrides)
    return ExecutorSpec(**payload)  # type: ignore[arg-type]


@pytest.fixture(params=["native", "recording"])
def executor(request: pytest.FixtureRequest) -> object:
    if request.param == "native":
        return NativeProcessExecutor()
    return RecordingExecutor()


def test_capability_profile_uses_the_current_host(executor: object) -> None:
    host = host_capabilities()
    profile = executor.capabilities(host)  # type: ignore[attr-defined]
    assert profile.host_id == host.host_id
    assert profile.host_fingerprint == host.fingerprint
    assert profile.availability is ExecutorAvailability.AVAILABLE
    assert profile.structured_argv is FeatureSupport.SUPPORTED
    assert profile.process_execution is FeatureSupport.SUPPORTED
    assert profile.isolation is FeatureSupport.UNSUPPORTED
    assert "docker" not in profile.executor.value
    assert profile.executor_type.value in {"process", "recording"}


def test_unknown_capability_is_not_unsupported() -> None:
    host = host_capabilities()
    profile = RecordingExecutor().capabilities(host)
    assert profile.accelerator_exposure is FeatureSupport.UNKNOWN
    assert profile.accelerator_exposure is not FeatureSupport.UNSUPPORTED
    assert profile.accelerator_exposure is not FeatureSupport.SUPPORTED


def test_start_observe_stop_use_generic_identity(executor: object) -> None:
    host = host_capabilities()
    handle = executor.start(host.host_id, _spec())  # type: ignore[attr-defined]
    try:
        assert handle.execution_id.value.startswith("exec_")
        assert handle.executor.value in {"native-process", "recording"}
        observed = executor.observe(handle)  # type: ignore[attr-defined]
        assert observed.execution_id == handle.execution_id
        if handle.executor.value == "recording":
            assert not is_resolved(observed.pid)
            assert is_resolved(observed.external_identity)
        stopped = executor.stop(observed)  # type: ignore[attr-defined]
        again = executor.stop(stopped)  # type: ignore[attr-defined]
        assert again.observed_state in {
            ExecutionState.EXITED,
            ExecutionState.FAILED,
        }
    finally:
        if handle.executor.value == "native-process":
            with contextlib.suppress(Exception):
                executor.stop(handle)  # type: ignore[attr-defined]


def test_native_captures_bounded_stdout() -> None:
    executor = NativeProcessExecutor()
    host = host_capabilities()
    handle = executor.start(
        host.host_id,
        _spec(
            arguments=("-c", "print('x' * 4000)"),
            output_limit_bytes=64,
        ),
    )
    deadline = time.monotonic() + 5
    current = handle
    while time.monotonic() < deadline:
        current = executor.observe(current)
        if current.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}:
            break
        time.sleep(0.05)
    assert current.output_truncated is True
    assert len(current.stdout.encode("utf-8")) <= 64
    assert is_resolved(current.pid) or current.observed_state is ExecutionState.EXITED


def test_recording_handle_does_not_require_a_pid() -> None:
    executor = RecordingExecutor()
    host = host_capabilities()
    spec = _spec(network_bindings=("tcp:127.0.0.1:0",))
    handle = executor.start(host.host_id, spec)
    assert spec in executor.accepted
    assert not is_resolved(handle.pid)
    assert handle.external_identity == "recording:1"
    assert handle.network_bindings == ("tcp:127.0.0.1:0",)
    assert handle.observed_state is ExecutionState.RUNNING
