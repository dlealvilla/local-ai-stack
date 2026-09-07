"""Runtime adapter contract: declared support, launch neutrality, readiness."""

from __future__ import annotations

from dataclasses import fields

from kultrun.adapters.execution.recording import RecordingExecutor
from kultrun.adapters.runtime.reference import ReferenceProcessRuntime
from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.kernel.ids import Name
from kultrun.platform.launch import executor_spec_from
from kultrun.runtime.catalogue import RuntimeCatalogue
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeSupportTier,
)
from kultrun.runtime.ports import InferenceRuntime
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS
from tests.test_contracts import host_capabilities


def test_reference_serving_is_test_only() -> None:
    descriptor = ReferenceServingRuntime().support()
    assert descriptor.runtime.value == "reference-serving"
    assert descriptor.support_tier is RuntimeSupportTier.TEST_ONLY
    assert descriptor.production_candidate is False
    assert descriptor.supported_os_families
    assert Name("native-process") in descriptor.compatible_executor_types
    assert Name("container-docker") in descriptor.compatible_executor_types
    assert "installed" not in descriptor.limitations
    assert "verified" not in " ".join(descriptor.limitations).lower()


def test_reference_process_is_test_only() -> None:
    descriptor = ReferenceProcessRuntime().support()
    assert descriptor.support_tier is RuntimeSupportTier.TEST_ONLY
    assert descriptor.production_candidate is False


def test_catalogue_excludes_harness_runtimes_from_product_identities() -> None:
    catalogue = RuntimeCatalogue(
        (ReferenceProcessRuntime(), ReferenceServingRuntime())
    )
    assert catalogue.product_identities() == ()
    names = {item.runtime.value for item in catalogue.descriptors()}
    assert names == {"reference-process", "reference-serving"}


def test_launch_spec_is_executor_neutral() -> None:
    launch = ReferenceServingRuntime().launch_spec(
        RuntimeLaunchRequest(instance_id="inst_test", mode="healthy")
    )
    names = {field.name for field in fields(RuntimeLaunchSpec)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    assert "docker_image" not in names
    assert launch.arguments == ("-m", "kultrun.adapters.runtime.serving_workload")
    assert launch.executable == "python"
    assert not any(entry.startswith("PYTHONPATH=") for entry in launch.environment)
    assert all("=" in entry for entry in launch.environment)
    assert "vllm" not in launch.executable.lower()
    for banned in BANNED_IMPLEMENTATION_FIELDS:
        assert not hasattr(launch, banned)


def test_launch_translation_is_deterministic() -> None:
    runtime = ReferenceServingRuntime()
    request = RuntimeLaunchRequest(instance_id="inst_a", mode="healthy")
    first = runtime.launch_spec(request)
    second = runtime.launch_spec(request)
    assert first == second


def test_the_same_spec_is_accepted_by_the_recording_executor() -> None:
    runtime = ReferenceServingRuntime()
    launch = runtime.launch_spec(
        RuntimeLaunchRequest(instance_id="inst_alt", mode="healthy")
    )
    spec = executor_spec_from(launch)
    handle = RecordingExecutor().start(host_capabilities().host_id, spec)
    assert handle.executor.value == "recording"
    assert not handle.execution_id.value.startswith("pid")
    assert handle.executable == launch.executable
    assert handle.arguments == launch.arguments


def test_readiness_is_runtime_owned_and_does_not_require_a_live_process() -> None:
    runtime: InferenceRuntime = ReferenceServingRuntime()
    dead = runtime.inspect_readiness(
        stdout="", stderr="", execution_alive=False
    )
    assert dead.ready is False
    unpublished = runtime.inspect_readiness(
        stdout="still starting", stderr="", execution_alive=True
    )
    assert unpublished.ready is False


def test_reference_process_readiness_follows_liveness() -> None:
    runtime = ReferenceProcessRuntime()
    assert runtime.inspect_readiness(
        stdout="", stderr="", execution_alive=True
    ).ready
    assert not runtime.inspect_readiness(
        stdout="", stderr="", execution_alive=False
    ).ready
