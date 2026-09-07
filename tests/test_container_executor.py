"""ContainerExecutor against a fake engine, plus the same RuntimeLaunchSpec."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.container.recording import RecordingContainerEngine
from kultrun.adapters.execution.container import ContainerExecutor
from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.runtime.serving import PYTHON_COMPONENT, ReferenceServingRuntime
from kultrun.execution.contracts import (
    ContainerExecutionConfig,
    EngineFailureKind,
    ExecutionState,
    ExecutorAvailability,
    ExecutorSpec,
    FeatureSupport,
    PullPolicy,
)
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.unresolved import is_resolved
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchRequest, RuntimeLaunchSpec
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, seam_import_leaks
from tests.test_contracts import host_capabilities

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _config(**overrides: object) -> ContainerExecutionConfig:
    payload: dict[str, object] = {"image": "kultrun-reference-serving:stage-16a"}
    payload.update(overrides)
    return ContainerExecutionConfig(**payload)  # type: ignore[arg-type]


def _executor(
    engine: RecordingContainerEngine | None = None,
    config: ContainerExecutionConfig | None = None,
) -> tuple[ContainerExecutor, RecordingContainerEngine]:
    fake = engine or RecordingContainerEngine()
    return ContainerExecutor(fake, config or _config()), fake


def _spec(**overrides: object) -> ExecutorSpec:
    payload: dict[str, object] = {
        "executable": PYTHON_COMPONENT,
        "arguments": ("-m", "kultrun.adapters.runtime.serving_workload"),
    }
    payload.update(overrides)
    return ExecutorSpec(**payload)  # type: ignore[arg-type]


def test_container_config_rejects_shell_metacharacters_in_the_image() -> None:
    try:
        _config(image="python:3.12; rm -rf /")
    except ValidationError:
        return
    raise AssertionError("unsafe image was accepted")


def test_container_config_name_prefix_must_be_kultrun_owned() -> None:
    try:
        _config(name_prefix="other-")
    except ValidationError:
        return
    raise AssertionError("foreign prefix was accepted")


def test_capability_profile_is_truthful_when_the_engine_is_down() -> None:
    engine = RecordingContainerEngine(
        probe_available=False,
        probe_failure=EngineFailureKind.DAEMON_UNAVAILABLE,
    )
    executor, _ = _executor(engine)
    profile = executor.capabilities(host_capabilities())
    assert profile.executor.value == "container-docker"
    assert profile.executor_type.value == "container"
    assert profile.availability is ExecutorAvailability.UNAVAILABLE
    assert profile.isolation is FeatureSupport.SUPPORTED
    assert profile.accelerator_exposure is FeatureSupport.UNKNOWN
    assert profile.structured_argv is FeatureSupport.SUPPORTED
    assert "docker_image" not in profile.limitations
    assert any("linux-only" in item for item in profile.limitations)


def test_capability_profile_is_available_when_the_engine_answers() -> None:
    executor, _ = _executor()
    profile = executor.capabilities(host_capabilities())
    assert profile.availability is ExecutorAvailability.AVAILABLE
    assert profile.filesystem_access == "mapped"
    assert profile.networking == "host_namespace"
    assert profile.port_binding is FeatureSupport.SUPPORTED
    assert profile.accelerator_exposure is not FeatureSupport.SUPPORTED


def test_generic_execution_id_and_optional_pid() -> None:
    executor, engine = _executor()
    handle = executor.start(host_capabilities().host_id, _spec())
    assert handle.execution_id.value.startswith("exec_")
    assert handle.executor.value == "container-docker"
    assert not is_resolved(handle.pid)
    assert is_resolved(handle.external_identity)
    assert str(handle.external_identity).startswith("ctr")
    assert handle.observed_state is ExecutionState.RUNNING
    stopped = executor.stop(handle)
    assert stopped.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}
    assert ("remove", str(handle.external_identity)) in engine.calls


def test_stop_of_an_already_stopped_container_is_idempotent() -> None:
    executor, _ = _executor()
    handle = executor.start(host_capabilities().host_id, _spec())
    first = executor.stop(handle)
    again = executor.stop(first)
    assert again.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}


def test_forced_stop_uses_kill_when_graceful_stop_does_not_exit() -> None:
    class Sticky(RecordingContainerEngine):
        def stop(self, container_id: str, *, grace_period_seconds: float) -> None:
            del grace_period_seconds
            self.calls.append(("stop", container_id))

    engine = Sticky()
    executor, _ = _executor(engine)
    handle = executor.start(host_capabilities().host_id, _spec())
    stopped = executor.stop(handle)
    assert ("kill", str(handle.external_identity)) in engine.calls
    assert stopped.observed_state in {ExecutionState.EXITED, ExecutionState.FAILED}


def test_image_missing_is_normalized() -> None:
    missing = ContainerExecutor(
        RecordingContainerEngine(),
        _config(image="missing.example/none:latest"),
    )
    failed = missing.start(host_capabilities().host_id, _spec())
    assert failed.observed_state is ExecutionState.FAILED
    assert failed.detail == "container image is not present"


def test_invalid_image_is_normalized() -> None:
    executor = ContainerExecutor(
        RecordingContainerEngine(),
        _config(image="invalid:latest"),
    )
    failed = executor.start(host_capabilities().host_id, _spec())
    assert failed.observed_state is ExecutionState.FAILED
    assert failed.detail == "container image reference is invalid"


def test_command_unavailable_inside_the_image() -> None:
    executor, _ = _executor()
    failed = executor.start(
        host_capabilities().host_id,
        ExecutorSpec(executable="missing-command", arguments=()),
    )
    assert failed.observed_state is ExecutionState.FAILED
    assert failed.exit_code == 127


def test_immediate_exit_is_failed_or_exited() -> None:
    executor, _ = _executor()
    handle = executor.start(
        host_capabilities().host_id,
        ExecutorSpec(
            executable=PYTHON_COMPONENT,
            arguments=("exit-immediately",),
        ),
    )
    assert handle.observed_state in {ExecutionState.FAILED, ExecutionState.EXITED}


def test_engine_unavailable_on_create() -> None:
    engine = RecordingContainerEngine(fail_create=EngineFailureKind.DAEMON_UNAVAILABLE)
    executor, _ = _executor(engine)
    failed = executor.start(host_capabilities().host_id, _spec())
    assert failed.observed_state is ExecutionState.FAILED
    assert "daemon" in (failed.detail or "")


def test_cleanup_only_removes_the_id_it_created() -> None:
    engine = RecordingContainerEngine()
    executor, _ = _executor(engine)
    handle = executor.start(host_capabilities().host_id, _spec())
    owned = str(handle.external_identity)
    executor.stop(handle)
    removed = [item[1] for item in engine.calls if item[0] == "remove"]
    assert removed == [owned]


def test_runtime_launch_spec_has_no_docker_fields() -> None:
    launch = ReferenceServingRuntime().launch_spec(
        RuntimeLaunchRequest(instance_id="inst_portability", mode="healthy")
    )
    names = set(RuntimeLaunchSpec.__dataclass_fields__)
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    assert launch.executable == PYTHON_COMPONENT
    assert "/" not in launch.executable
    assert not any(entry.startswith("PYTHONPATH=") for entry in launch.environment)
    assert not any("docker" in field for field in names)


def test_same_runtime_spec_feeds_native_and_container() -> None:
    runtime = ReferenceServingRuntime()
    launch = runtime.launch_spec(
        RuntimeLaunchRequest(instance_id="inst_same", mode="healthy")
    )
    spec = executor_spec_from(launch)
    host = host_capabilities()
    native = NativeProcessExecutor()
    container, engine = _executor()
    recorded = container.start(host.host_id, spec)
    try:
        assert spec.executable == launch.executable == PYTHON_COMPONENT
        assert spec.arguments == launch.arguments
        assert recorded.executor.value == "container-docker"
        assert not is_resolved(recorded.pid)
        assert engine.boxes[str(recorded.external_identity)].command[0] == "python"
        assert "PYTHONPATH" not in {
            entry.split("=", 1)[0]
            for entry in engine.boxes[str(recorded.external_identity)].environment
        }
        native_handle = native.start(host.host_id, spec)
        try:
            assert native_handle.executor.value == "native-process"
            assert native_handle.arguments == recorded.arguments
        finally:
            native.stop(native_handle)
    finally:
        container.stop(recorded)


def test_runtime_adapter_does_not_branch_on_executor() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "kultrun"
        / "adapters"
        / "runtime"
        / "serving.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()
    assert "sys.executable" not in source
    assert "if executor" not in lowered
    assert "docker_image" not in lowered
    assert "import docker" not in lowered
    assert "from docker" not in lowered
    assert seam_import_leaks(SOURCE) == []


def test_pull_policy_default_is_never() -> None:
    assert _config().pull_policy is PullPolicy.NEVER
