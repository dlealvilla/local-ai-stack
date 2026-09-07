"""Stage 1.3 — runtime recipes and native process execution.

The runtime writes a structured launch spec. The executor starts it. Neither
imports the other; composition copies the recipe. No LLM, no shell string,
no capacity policy.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.host import fixtures
from kultrun.adapters.persistence.file_store import build as build_store
from kultrun.adapters.runtime import reference_workload
from kultrun.adapters.runtime.reference import ReferenceProcessRuntime
from kultrun.api.contracts import ApiRequest, Method
from kultrun.execution.contracts import (
    ExecutionOwnership,
    ExecutionState,
    ExecutorHandle,
    ExecutorSpec,
)
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostId
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import (
    EvidenceMode,
    Platform,
    build,
    config_schema,
    start_reference_workload,
)
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchSpec, RuntimeProfile

WORKLOAD = Path(reference_workload.__file__).resolve()
HOST = HostId.generate()
MARKER = "kultrun-reference-workload"


def _spec(*args: str, **overrides: object) -> ExecutorSpec:
    payload: dict[str, object] = {
        "executable": sys.executable,
        "arguments": (str(WORKLOAD), *args),
    }
    payload.update(overrides)
    return ExecutorSpec(**payload)  # type: ignore[arg-type]


def _wait(
    service: ExecutionService, handle: ExecutorHandle, *, timeout: float = 5.0
) -> ExecutorHandle:
    deadline = time.monotonic() + timeout
    current = handle
    while time.monotonic() < deadline:
        current = service.observe(current.execution_id)
        if current.observed_state in (
            ExecutionState.EXITED,
            ExecutionState.FAILED,
        ):
            return current
        time.sleep(0.05)
    return current


def _wait_output(
    service: ExecutionService,
    handle: ExecutorHandle,
    text: str,
    *,
    timeout: float = 5.0,
) -> ExecutorHandle:
    deadline = time.monotonic() + timeout
    current = handle
    while time.monotonic() < deadline:
        current = service.observe(current.execution_id)
        if text in current.stdout or text in current.stderr:
            return current
        if current.observed_state in (ExecutionState.EXITED, ExecutionState.FAILED):
            return current
        time.sleep(0.05)
    return current


@pytest.fixture
def service(tmp_path: Path) -> ExecutionService:
    return ExecutionService(NativeProcessExecutor(), build_store(tmp_path))


@pytest.fixture
def platform(tmp_path: Path) -> Iterator[Platform]:
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "state")}}
    )
    assembled = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
    try:
        yield assembled
    finally:
        assembled.executions.stop_all_running()


class TestLaunchSpecValidation:
    def test_an_empty_executable_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeLaunchSpec(
                runtime=Name("reference-process"),
                profile=Name("reference-process"),
                executable="  ",
                arguments=(),
            )

    def test_a_shell_executable_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="sh -c"):
            RuntimeLaunchSpec(
                runtime=Name("reference-process"),
                profile=Name("reference-process"),
                executable="/bin/sh",
                arguments=("-c", "echo hi"),
            )

    def test_a_nul_in_an_argument_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeLaunchSpec(
                runtime=Name("reference-process"),
                profile=Name("reference-process"),
                executable=sys.executable,
                arguments=("ok", "bad\0"),
            )

    def test_a_non_positive_grace_period_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeLaunchSpec(
                runtime=Name("reference-process"),
                profile=Name("reference-process"),
                executable=sys.executable,
                arguments=(),
                grace_period_seconds=0,
            )


class TestExecutorSpecRejectsAShell:
    def test_sh_is_not_an_executable(self) -> None:
        with pytest.raises(ValidationError, match="sh -c"):
            ExecutorSpec(executable="sh", arguments=("-c", "echo hi"))

    def test_bash_is_not_an_executable(self) -> None:
        with pytest.raises(ValidationError):
            ExecutorSpec(executable="/bin/bash", arguments=())

    def test_environment_names_must_be_identifiers(self) -> None:
        with pytest.raises(ValidationError):
            ExecutorSpec(
                executable=sys.executable,
                arguments=(),
                environment=("1BAD=x",),
            )

    def test_native_executor_source_never_sets_shell_true(self) -> None:
        from kultrun.adapters.execution import native_process

        source = Path(native_process.__file__).read_text(encoding="utf-8")
        assert "shell=True" not in source
        assert "shell = True" not in source


class TestCompositionCopiesTheRecipe:
    def test_the_reference_adapter_does_not_start_a_process(self) -> None:
        launch = ReferenceProcessRuntime(hold=False).launch_spec()
        assert launch.executable == "python"
        assert "-m" in launch.arguments
        assert "--once" in launch.arguments
        assert "vllm" not in launch.executable.lower()

    def test_composition_copies_fields_without_policy(self) -> None:
        launch = RuntimeLaunchSpec(
            runtime=Name("reference-process"),
            profile=Name("reference-process"),
            executable=sys.executable,
            arguments=("--once",),
            environment=("KULTRUN_TEST_MARKER=copied",),
            output_limit_bytes=512,
            grace_period_seconds=1.5,
            device_indexes=(0,),
        )
        spec = executor_spec_from(launch)
        assert spec.executable == launch.executable
        assert spec.arguments == launch.arguments
        assert spec.environment == launch.environment
        assert spec.output_limit_bytes == 512
        assert spec.grace_period_seconds == 1.5
        assert spec.device_requests[0].index == 0
        assert spec.filesystem_mappings == launch.filesystem_mappings
        assert spec.network_bindings == launch.network_bindings

    def test_a_profile_is_not_a_running_process(self) -> None:
        profile = ReferenceProcessRuntime().profile()
        assert isinstance(profile, RuntimeProfile)
        assert profile.runtime.value == "reference-process"
        assert profile.executor_kind.value == "native-process"


class TestNativeProcessLifecycle:
    def test_stdout_is_visible_while_the_process_is_still_running(
        self, service: ExecutionService
    ) -> None:
        handle = service.start(HOST, _spec("--hold"))
        try:
            running = _wait_output(service, handle, f"{MARKER}:start")
            assert running.observed_state is ExecutionState.RUNNING
            assert is_resolved(running.pid)
            assert f"{MARKER}:start" in running.stdout
        finally:
            service.stop_all_running()

    def test_a_process_starts_and_exits_zero(self, service: ExecutionService) -> None:
        handle = service.start(HOST, _spec("--once"))
        assert is_resolved(handle.pid)
        finished = _wait(service, handle)
        assert finished.observed_state is ExecutionState.EXITED
        assert finished.exit_code == 0
        assert f"{MARKER}:start" in finished.stdout
        assert f"{MARKER}:done" in finished.stdout

    def test_a_non_zero_exit_is_failed(self, service: ExecutionService) -> None:
        handle = service.start(HOST, _spec("--fail"))
        finished = _wait(service, handle)
        assert finished.observed_state is ExecutionState.FAILED
        assert finished.exit_code == 2
        assert f"{MARKER}:fail" in finished.stdout

    def test_environment_is_passed_through(self, service: ExecutionService) -> None:
        handle = service.start(
            HOST,
            _spec(
                "--once",
                environment=("KULTRUN_TEST_MARKER=alpha",),
            ),
        )
        finished = _wait(service, handle)
        assert f"{MARKER}:env:alpha" in finished.stdout

    def test_stdout_is_bounded(self, service: ExecutionService) -> None:
        handle = service.start(
            HOST,
            _spec("--once", "--bytes", "8000", output_limit_bytes=200),
        )
        finished = _wait(service, handle)
        assert finished.output_truncated is True
        assert len(finished.stdout.encode("utf-8")) <= 200

    def test_stderr_is_captured_and_bounded(self, service: ExecutionService) -> None:
        handle = service.start(
            HOST,
            _spec("--once", "--stderr", "--bytes", "1", output_limit_bytes=64),
        )
        finished = _wait(service, handle)
        assert f"{MARKER}:stderr" in finished.stderr

    def test_graceful_stop_lets_the_child_exit_zero(
        self, service: ExecutionService
    ) -> None:
        handle = service.start(HOST, _spec("--hold", grace_period_seconds=2.0))
        try:
            running = _wait_output(service, handle, f"{MARKER}:start")
            assert running.observed_state is ExecutionState.RUNNING
            assert f"{MARKER}:start" in running.stdout
            stopped = service.stop(running.execution_id)
            finished = _wait(service, stopped)
            assert finished.observed_state is ExecutionState.EXITED
            assert finished.exit_code == 0
            assert f"{MARKER}:stopped" in finished.stdout
            assert finished.desired_state is ExecutionState.STOPPING
        finally:
            service.stop_all_running()

    def test_forced_termination_follows_a_bounded_grace(
        self, service: ExecutionService
    ) -> None:
        handle = service.start(
            HOST,
            _spec("--hold", "--ignore-term", grace_period_seconds=0.2),
        )
        try:
            running = _wait_output(service, handle, f"{MARKER}:start")
            assert running.observed_state is ExecutionState.RUNNING
            assert f"{MARKER}:start" in running.stdout
            stopped = service.stop(running.execution_id)
            finished = _wait(service, stopped)
            assert finished.observed_state is ExecutionState.FAILED
            assert finished.exit_code == -signal.SIGKILL
        finally:
            service.stop_all_running()

    def test_two_executions_are_a_collection(self, service: ExecutionService) -> None:
        first = service.start(HOST, _spec("--hold"))
        second = service.start(HOST, _spec("--hold"))
        try:
            listed = service.list()
            ids = {item.execution_id.value for item in listed}
            assert first.execution_id.value in ids
            assert second.execution_id.value in ids
            assert len(ids) >= 2
        finally:
            service.stop_all_running()

    def test_a_restart_does_not_claim_or_signal_a_stranger_pid(
        self, tmp_path: Path
    ) -> None:
        store = build_store(tmp_path)
        live = NativeProcessExecutor()
        owned = ExecutionService(live, store)
        handle = owned.start(HOST, _spec("--hold"))
        try:
            running = _wait_output(owned, handle, f"{MARKER}:start")
            assert running.observed_state is ExecutionState.RUNNING
            assert f"{MARKER}:start" in running.stdout
            assert is_resolved(running.pid)
            pid = running.pid

            other = ExecutionService(NativeProcessExecutor(), store)
            observed = other.observe(running.execution_id)
            assert observed.ownership is ExecutionOwnership.UNVERIFIED
            other.stop(running.execution_id)
            os.kill(pid, 0)
        finally:
            live.stop(handle)


class TestArchitectureBoundaries:
    def test_execution_does_not_import_runtime_or_capacity(self) -> None:
        from tests.architecture import scan

        edges = scan(Path(__file__).resolve().parent.parent / "src")
        forbidden = {
            (edge.source_package, edge.target_package)
            for edge in edges
            if edge.source_package == "execution"
            and edge.target_package in {"runtime", "capacity"}
        }
        assert forbidden == set()

    def test_runtime_does_not_import_execution_or_capacity(self) -> None:
        from tests.architecture import scan

        edges = scan(Path(__file__).resolve().parent.parent / "src")
        forbidden = {
            (edge.source_package, edge.target_package)
            for edge in edges
            if edge.source_package == "runtime"
            and edge.target_package in {"execution", "capacity"}
        }
        assert forbidden == set()

    def test_the_native_adapter_does_not_import_runtime(self) -> None:
        from tests.architecture import scan

        edges = [
            edge
            for edge in scan(Path(__file__).resolve().parent.parent / "src")
            if edge.source_module.startswith("kultrun.adapters.execution")
            and edge.target_package == "runtime"
        ]
        assert edges == []


class TestPlatformApiAndConsole:
    def test_runtime_surface_is_plural_and_honest(self, platform: Platform) -> None:
        payload = _call(platform, "/runtime")
        assert _obj(payload["executor"])["identity"] == "native-process"
        assert _obj(payload["controls"])["arbitrary_command"] is False
        assert _obj(payload["process_evidence"])["kind"] == "live_local_process"
        assert payload["host_evidence_mode"] == EvidenceMode.FIXTURE_REPLAY.value
        assert payload["executions"] == []
        assert "execution" not in payload
        profiles = _items(payload["profiles"])
        assert any(_obj(item)["runtime"] == "reference-process" for item in profiles)

    def test_mode_keeps_host_and_process_evidence_apart(
        self, platform: Platform
    ) -> None:
        mode = _call(platform, "/mode")
        assert mode["evidence_mode"] == EvidenceMode.FIXTURE_REPLAY.value
        assert mode["physical_host_connected"] is False
        assert mode["process_evidence_kind"] == "live_local_process"
        assert mode["host_evidence_kind"] == "fixture_replay"
        assert mode["storage_evidence_kind"] == "replayed_test_evidence"

    def test_start_and_stop_the_reference_workload(self, platform: Platform) -> None:
        started = start_reference_workload(platform, hold=True)
        running = _wait_output(platform.executions, started, f"{MARKER}:start")
        assert running.observed_state is ExecutionState.RUNNING
        assert f"{MARKER}:start" in running.stdout
        listed = _items(_call(platform, "/runtime")["executions"])
        first = _obj(listed[0])
        assert first["execution_id"] == started.execution_id.value
        assert first["observed_state"] == "running"
        assert isinstance(first["pid"], int)
        assert f"{MARKER}:start" in str(first.get("stdout") or "")

        response = platform.router.handle(
            ApiRequest(method=Method.POST, path="/v1/runtime/execution/stop")
        )
        assert response.status == 200
        finished = platform.executions.observe(started.execution_id)
        assert finished.observed_state in (
            ExecutionState.EXITED,
            ExecutionState.FAILED,
            ExecutionState.STOPPING,
        )

    def test_an_arbitrary_command_is_rejected(self, platform: Platform) -> None:
        response = platform.router.handle(
            ApiRequest(
                method=Method.POST,
                path="/v1/runtime/execution",
                query={"executable": "/bin/echo", "command": "echo hi"},
            )
        )
        assert response.status == 400
        error = _obj(response.body["error"])
        assert "arbitrary" in str(error["message"])

    def test_start_is_unreachable_by_get(self, platform: Platform) -> None:
        response = platform.router.handle(
            ApiRequest(method=Method.GET, path="/v1/runtime/execution")
        )
        assert response.status in (404, 405)

    def test_get_runtime_does_not_start_a_process(self, platform: Platform) -> None:
        _call(platform, "/runtime")
        _call(platform, "/runtime")
        assert platform.executions.list() == ()

    def test_once_completes_through_composition(self, platform: Platform) -> None:
        handle = start_reference_workload(platform, hold=False)
        finished = _wait(platform.executions, handle)
        assert finished.observed_state is ExecutionState.EXITED
        assert finished.exit_code == 0


def _call(platform: Platform, path: str) -> dict[str, object]:
    response = platform.router.handle(
        ApiRequest(method=Method.GET, path=f"/v1{path}", query={})
    )
    assert response.status == 200, response.body
    payload = response.body["payload"]
    assert isinstance(payload, dict)
    return payload


def _obj(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def _items(value: object) -> list[object]:
    assert isinstance(value, list)
    return value
