"""Stage 1.6B runtime resolution: plausibility, not installation."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.evidence.contracts import Confidence
from kultrun.execution.contracts import (
    ExecutorAvailability,
    ExecutorCapabilityProfile,
    FeatureSupport,
)
from kultrun.host.contracts import (
    Accelerator,
    AcceleratorVendor,
    Architecture,
    HostCapabilities,
)
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.runtime.contracts import (
    CompatibilityClass,
    ResolutionReasonCode,
    RuntimePolicy,
    RuntimeResolverMode,
    RuntimeSupportTier,
)
from kultrun.runtime.resolve import RuntimeResolver, fingerprint_candidate_id, resolve
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named
from tests.test_contracts import host_capabilities

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _native(
    host: HostCapabilities,
    *,
    availability: ExecutorAvailability = ExecutorAvailability.AVAILABLE,
    accelerator: FeatureSupport = FeatureSupport.SUPPORTED,
) -> ExecutorCapabilityProfile:
    process = (
        FeatureSupport.SUPPORTED
        if availability is ExecutorAvailability.AVAILABLE
        else FeatureSupport.UNSUPPORTED
    )
    return ExecutorCapabilityProfile(
        executor=Name("native-process"),
        executor_type=Name("process"),
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        availability=availability,
        process_execution=process,
        structured_argv=process,
        environment_variables=process,
        working_directory=process,
        filesystem_access="host_native",
        networking="host_native",
        port_binding=process,
        accelerator_exposure=accelerator,
        bounded_stdout=process,
        bounded_stderr=process,
        lifecycle_observation=process,
        graceful_termination=process,
        forced_termination=process,
        isolation=FeatureSupport.UNSUPPORTED,
        accelerator_exposure_mode="host_process_inheritance",
        confidence=Confidence.HIGH,
    )


def _container(
    host: HostCapabilities,
    *,
    availability: ExecutorAvailability = ExecutorAvailability.AVAILABLE,
    accelerator: FeatureSupport = FeatureSupport.UNKNOWN,
) -> ExecutorCapabilityProfile:
    support = (
        FeatureSupport.SUPPORTED
        if availability is ExecutorAvailability.AVAILABLE
        else FeatureSupport.UNSUPPORTED
    )
    return ExecutorCapabilityProfile(
        executor=Name("container-docker"),
        executor_type=Name("container"),
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        availability=availability,
        process_execution=support,
        structured_argv=support,
        environment_variables=support,
        working_directory=support,
        filesystem_access="mapped",
        networking="host_namespace",
        port_binding=support,
        accelerator_exposure=accelerator,
        bounded_stdout=support,
        bounded_stderr=support,
        lifecycle_observation=support,
        graceful_termination=support,
        forced_termination=support,
        isolation=FeatureSupport.SUPPORTED,
        accelerator_exposure_mode="not_implemented",
        confidence=(
            Confidence.HIGH
            if availability is ExecutorAvailability.AVAILABLE
            else Confidence.LOW
        ),
    )


def _linux_cpu(host: HostCapabilities) -> HostCapabilities:
    return replace(host, accelerators=())


def _macos(host: HostCapabilities) -> HostCapabilities:
    environment = replace(
        host.operating_environment,
        os_name="darwin",
        architecture=Architecture.ARM64,
    )
    apple = Accelerator(
        index=0,
        vendor=AcceleratorVendor.APPLE,
        model_name="Apple Silicon",
        memory_total_bytes=NOT_PROVIDED,
        driver_version=NOT_PROVIDED,
        unified_memory=True,
    )
    return replace(host, operating_environment=environment, accelerators=(apple,))


def test_case_a_linux_nvidia_native_is_compatible_when_vllm_present() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (
            _native(host),
            _container(host, availability=ExecutorAvailability.UNAVAILABLE),
        ),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    native = next(
        item for item in result.candidates if item.executor.value == "native-process"
    )
    assert native.compatibility is CompatibilityClass.COMPATIBLE
    assert native.support_tier is RuntimeSupportTier.PRODUCT
    assert is_resolved(result.preferred_candidate_id)
    assert result.preferred_candidate_id == native.candidate_id.value


def test_case_b_macos_apple_silicon_is_unsupported() -> None:
    host = _macos(host_capabilities())
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert result.candidates == ()
    assert result.unsupported
    codes = {code for item in result.unsupported for code in item.reason_codes}
    assert ResolutionReasonCode.HOST_OS_UNSUPPORTED in codes
    assert not is_resolved(result.preferred_candidate_id)


def test_case_c_unavailable_container_executor_is_unsupported() -> None:
    host = host_capabilities()
    descriptor = replace(
        VllmRuntimeSupport().support(),
        compatible_executor_types=(Name("container-docker"),),
    )
    result = resolve(
        host,
        (
            _native(host),
            _container(host, availability=ExecutorAvailability.UNAVAILABLE),
        ),
        (descriptor,),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert result.candidates == ()
    assert any(
        ResolutionReasonCode.EXECUTOR_UNAVAILABLE in item.reason_codes
        for item in result.unsupported
    )


def test_case_d_unknown_accelerator_exposure_is_not_compatible() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_container(host, accelerator=FeatureSupport.UNKNOWN),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert result.candidates
    item = result.candidates[0]
    assert item.compatibility is CompatibilityClass.CONDITIONAL
    assert ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN in item.reason_codes


def test_case_e_explicit_incompatible_runtime_does_not_fallback() -> None:
    host = _macos(host_capabilities())
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(), ReferenceServingRuntime().support()),
        RuntimePolicy(mode=RuntimeResolverMode.EXPLICIT, requested_runtime="vllm"),
        components={"vllm": "present"},
    )
    names = {item.runtime.value for item in result.unsupported}
    assert names == {"vllm"}
    assert result.candidates == ()
    assert not is_resolved(result.preferred_candidate_id)


def test_case_f_normal_auto_excludes_reference_serving() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(), ReferenceServingRuntime().support()),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert "reference-serving" in result.excluded_runtimes
    assert all(item.runtime.value != "reference-serving" for item in result.candidates)
    assert all(item.runtime.value != "reference-serving" for item in result.unsupported)


def test_case_g_test_policy_opts_in_reference() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_native(host),),
        (ReferenceServingRuntime().support(),),
        RuntimePolicy(allow_test_only=True),
    )
    assert any(item.runtime.value == "reference-serving" for item in result.candidates)


def test_case_h_two_compatible_candidates_are_ranked_deterministically() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_native(host), _container(host, accelerator=FeatureSupport.SUPPORTED)),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert [item.executor.value for item in result.candidates] == [
        "native-process",
        "container-docker",
    ]
    assert [item.rank for item in result.candidates] == [0, 1]


def test_case_i_same_inputs_yield_the_same_ids_and_order() -> None:
    host = host_capabilities()
    policy = RuntimePolicy()
    executors = (_native(host), _container(host))
    descriptors = (VllmRuntimeSupport().support(),)
    first = resolve(
        host, executors, descriptors, policy, components={"vllm": "present"}
    )
    second = resolve(
        host, executors, descriptors, policy, components={"vllm": "present"}
    )
    assert [item.candidate_id for item in first.candidates] == [
        item.candidate_id for item in second.candidates
    ]
    assert [item.executor.value for item in first.candidates] == [
        item.executor.value for item in second.candidates
    ]


def test_missing_component_is_conditional_not_compatible() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    item = result.candidates[0]
    assert item.compatibility is CompatibilityClass.CONDITIONAL
    assert ResolutionReasonCode.REQUIRED_COMPONENT_MISSING in item.reason_codes
    assert not is_resolved(result.preferred_candidate_id)


def test_unknown_host_architecture_is_unresolved() -> None:
    host = host_capabilities()
    host = replace(
        host,
        operating_environment=replace(
            host.operating_environment, architecture=Architecture.UNKNOWN
        ),
    )
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    assert result.unresolved
    assert result.unresolved[0].compatibility is CompatibilityClass.UNRESOLVED


def test_explicit_unknown_runtime_does_not_choose_reference() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(), ReferenceServingRuntime().support()),
        RuntimePolicy(mode=RuntimeResolverMode.EXPLICIT, requested_runtime="llama.cpp"),
    )
    assert result.candidates == ()
    assert all(item.runtime.value != "reference-serving" for item in result.unsupported)
    assert any("llama.cpp" in note for note in result.notes)


def test_candidate_has_no_docker_fields() -> None:
    from kultrun.runtime.contracts import RuntimeCandidate

    names = {field.name for field in fields(RuntimeCandidate)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    assert "image" not in names
    assert "docker_network" not in names


def test_candidate_identity_is_fingerprint_derived() -> None:
    first = fingerprint_candidate_id(
        runtime="vllm",
        version="unspecified",
        executor="native-process",
        host_id="host_aaaaaaaaaaaaaaaa",
        host_fingerprint="abc",
    )
    second = fingerprint_candidate_id(
        runtime="vllm",
        version="unspecified",
        executor="native-process",
        host_id="host_aaaaaaaaaaaaaaaa",
        host_fingerprint="abc",
    )
    assert first == second
    assert first.value.startswith("rcand_")


def test_runtime_resolver_class_delegates_to_resolve() -> None:
    host = host_capabilities()
    executors = (_native(host),)
    descriptors = (VllmRuntimeSupport().support(),)
    policy = RuntimePolicy()
    components = {"vllm": "present"}
    function = resolve(host, executors, descriptors, policy, components=components)
    named = RuntimeResolver().resolve(
        host, executors, descriptors, policy, components=components
    )
    assert function.preferred_candidate_id == named.preferred_candidate_id
    assert [item.candidate_id for item in function.candidates] == [
        item.candidate_id for item in named.candidates
    ]


def test_vllm_adapter_does_not_launch_or_import_vllm() -> None:
    adapter = VllmRuntimeSupport()
    with pytest.raises(ValidationError, match="exact interpreter"):
        adapter.launch_spec()
    source = (SOURCE / "kultrun" / "adapters" / "runtime" / "vllm.py").read_text(
        encoding="utf-8"
    )
    assert "import vllm" not in source
    assert "from vllm" not in source


def test_resolver_module_does_not_import_forbidden_domains() -> None:
    path = SOURCE / "kultrun" / "runtime" / "resolve.py"
    leaks = _imports_named(
        path,
        "kultrun.execution",
        "kultrun.resource",
        "kultrun.model",
        "kultrun.planning",
        "kultrun.inference",
        "kultrun.adapters",
    )
    assert leaks == []


def test_api_candidates_are_read_only(tmp_path: Path) -> None:
    from kultrun.adapters.host import fixtures
    from kultrun.api.contracts import ApiRequest, Method
    from kultrun.main import build, config_schema

    platform = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
    )
    response = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/candidates")
    )
    assert response.status == 200
    payload = response.body["payload"]
    assert isinstance(payload, dict)
    assert payload["mutations"] is False
    assert payload["install"] is False
    assert payload["verify"] is False
    resolution = payload["resolution"]
    assert isinstance(resolution, dict)
    names = {
        item["runtime"]
        for group in ("candidates", "unsupported", "unresolved")
        for item in resolution.get(group, [])
    }
    assert "reference-serving" not in names
    explicit = platform.router.handle(
        ApiRequest(
            method=Method.GET,
            path="/v1/runtimes/candidates",
            query={"runtime": "vllm"},
        )
    )
    assert explicit.status == 200
    body = explicit.body["payload"]
    assert isinstance(body, dict)
    assert body["policy"]["mode"] == "explicit"
    assert body["policy"]["requested_runtime"] == "vllm"


def test_console_candidates_panel_has_no_verify_or_launch() -> None:
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "Runtime candidates" in html
    assert "Start Runtime" not in html
    assert "Launch Model" not in html
    candidates = html.split("candidates-panel", 1)[1].split("<section", 1)[0]
    assert "Verify" not in candidates
    assert "/runtimes/candidates" in script
    assert "Recommended Runtime" not in script
    assert "Select Model" not in script
