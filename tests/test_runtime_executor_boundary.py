"""Stage 1.5C — Runtime / Executor I/O and composition boundaries."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.adapters.execution.recording import RecordingExecutor
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.execution.contracts import FeatureSupport
from kultrun.inference.service import InstanceService
from kultrun.kernel.unresolved import is_resolved
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.contracts import RuntimeLaunchRequest
from tests.architecture import seam_import_leaks
from tests.test_contracts import host_capabilities

SOURCE = Path(__file__).resolve().parent.parent / "src"


def test_native_capability_profile_is_truthful() -> None:
    host = host_capabilities()
    profile = NativeProcessExecutor().capabilities(host)
    assert profile.executor.value == "native-process"
    assert profile.filesystem_access == "host_native"
    assert profile.networking == "host_native"
    assert profile.port_binding is FeatureSupport.SUPPORTED
    assert profile.accelerator_exposure_mode == "host_process_inheritance"
    assert profile.isolation is FeatureSupport.UNSUPPORTED
    assert any("container_isolation" in item for item in profile.limitations)
    assert any(item.startswith("os=") for item in profile.evidence)


def test_inference_composes_runtime_and_executor_identities() -> None:
    hints = InstanceService.start.__annotations__
    assert "subprocess" not in str(hints)
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "kultrun"
        / "inference"
        / "service.py"
    ).read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "Popen" not in source
    assert "inspect_readiness" in source
    assert "urllib" not in source


def test_seams_have_no_cycles_or_implementation_imports() -> None:
    assert seam_import_leaks(SOURCE) == []


def test_alternate_executor_consumes_the_same_generic_spec() -> None:
    runtime = ReferenceServingRuntime()
    launch = runtime.launch_spec(
        RuntimeLaunchRequest(instance_id="inst_boundary", mode="healthy")
    )
    spec = executor_spec_from(launch)
    native = NativeProcessExecutor()
    recording = RecordingExecutor()
    host = host_capabilities()
    recorded = recording.start(host.host_id, spec)
    assert recorded.executor.value == "recording"
    assert not is_resolved(recorded.pid)
    assert is_resolved(recorded.external_identity)
    assert spec.executable == launch.executable
    assert spec.arguments == launch.arguments
    assert spec.environment == launch.environment
    assert spec.network_bindings == launch.network_bindings
    assert native.identity.value != recording.identity.value
