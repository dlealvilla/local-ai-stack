"""Stage 1.6F runtime-aware eligible model view. Compatibility, not capacity."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

from kultrun.adapters.host import fixtures
from kultrun.adapters.model_source.candidates import acceptance_candidate
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.runtime.vllm import VllmModelCompatibility, VllmRuntimeSupport
from kultrun.adapters.verification.fixture import (
    SCENARIO_IMPORT_FAILURE,
    FixtureProbeRunner,
    FixtureRuntimeVerifier,
)
from kultrun.api.contracts import ApiRequest, Method
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.ids import Name
from kultrun.main import build, config_schema
from kultrun.planning.contracts import CompatibilityVerdict
from kultrun.platform.eligibility import catalog_facts, runtime_compatibility
from kultrun.runtime.contracts import (
    EligibilityReasonCode,
    EligibleModelView,
    EligibleViewStatus,
    RuntimeEligibilityStatus,
    RuntimeEligibleModelCandidate,
    RuntimePolicy,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
    VerificationStatus,
)
from kultrun.runtime.eligibility import (
    ModelEligibilityFacts,
    ModelEligibilityService,
    declared_compatibility,
)
from kultrun.runtime.lock import ProvisioningLock, SelectionLock, VerificationLock
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.verify import VerificationService
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named
from tests.test_contracts import host_capabilities
from tests.test_runtime_resolution import _native

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _services(
    tmp_path: Path,
    scenario: str = "healthy",
) -> tuple[ModelEligibilityService, FoundationSelectionService]:
    records = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    provisioning = ProvisioningService(
        records,
        clock,
        FixtureRuntimeProvisioner(),
        state,
        ProvisioningLock(state),
    )
    verification = VerificationService(
        records,
        clock,
        FixtureRuntimeVerifier(scenario),
        FixtureProbeRunner(scenario),
        state,
        VerificationLock(state),
    )
    foundation = FoundationSelectionService(
        records,
        clock,
        provisioning,
        verification,
        SelectionLock(state),
    )
    eligibility = ModelEligibilityService(
        clock,
        foundation,
        provisioning,
        verification,
        interpreters=(VllmModelCompatibility(),),
    )
    return eligibility, foundation


def _alt_descriptor() -> RuntimeSupportDescriptor:
    return RuntimeSupportDescriptor(
        runtime=Name("alt-native"),
        display_name="Alternate native family",
        support_tier=RuntimeSupportTier.TEST_ONLY,
        production_candidate=False,
        compatible_executor_types=(Name("native-process"),),
        supported_os_families=("linux",),
        supported_architectures=("x86_64",),
        supported_accelerator_families=("nvidia",),
        required_features=(
            "process_execution",
            "structured_argv",
            "environment_variables",
        ),
        required_components=(Name("vllm"),),
        preferred_version="0.0.1",
    )


def _facts() -> tuple[ModelEligibilityFacts, ...]:
    return (
        ModelEligibilityFacts(
            model_id="model_awq",
            logical_name="qwen2.5-7b-instruct-awq",
            architecture="qwen2",
            family="qwen2.5",
            quantization="awq",
            supported_runtimes=("vllm",),
        ),
        ModelEligibilityFacts(
            model_id="model_q4",
            logical_name="tinyllama-1.1b-chat-q4",
            architecture="llama",
            family="tinyllama",
            quantization="q4_k",
            supported_runtimes=("llama.cpp", "vllm"),
        ),
        ModelEligibilityFacts(
            model_id="model_tiny",
            logical_name="hf-acceptance-tiny",
            architecture="gpt2",
            family="gpt2",
            quantization="fp32",
            supported_runtimes=(),
        ),
    )


def _verified(
    tmp_path: Path,
    *,
    scenario: str = "healthy",
    descriptors: tuple[RuntimeSupportDescriptor, ...] | None = None,
    policy: RuntimePolicy | None = None,
) -> tuple[
    ModelEligibilityService,
    FoundationSelectionService,
    object,
    object,
    tuple[RuntimeSupportDescriptor, ...],
]:
    host = host_capabilities()
    native = _native(host)
    descriptors = descriptors or (VllmRuntimeSupport().support(),)
    eligibility, foundation = _services(tmp_path, scenario)
    args = (host, (native,), descriptors)
    kwargs = {"components": {"vllm": "missing"}}
    if policy is not None:
        foundation.select_auto(*args, policy, **kwargs)
        foundation.realize_selected(*args, policy, **kwargs)
        foundation.verify_selected(*args, policy, **kwargs)
    else:
        foundation.select_auto(*args, **kwargs)
        foundation.realize_selected(*args, **kwargs)
        foundation.verify_selected(*args, **kwargs)
    return eligibility, foundation, host, native, descriptors


def test_schema_has_no_parallel_version_objects() -> None:
    names = {item.name for item in fields(EligibleModelView)}
    forbidden = {
        "score",
        "vram",
        "ram",
        "reservation",
        "deployment_foundation",
        "environment_provider",
    }
    assert names.isdisjoint(forbidden)
    assert EligibleModelView.kind == "runtime.eligible_model_view"
    assert RuntimeEligibleModelCandidate.kind == "runtime.eligible_model_candidate"
    assert "ELIGIBLE" in RuntimeEligibilityStatus.__members__
    assert "CURRENT" in EligibleViewStatus.__members__


def test_unknown_is_not_eligible() -> None:
    descriptor = VllmRuntimeSupport().support()
    decision = declared_compatibility(
        ModelEligibilityFacts(
            model_id="x",
            logical_name="incomplete",
            supported_runtimes=(),
        ),
        descriptor,
    )
    assert decision.status is RuntimeEligibilityStatus.UNRESOLVED
    assert (
        EligibilityReasonCode.REQUIRED_MODEL_METADATA_MISSING in decision.reason_codes
    )


def test_vllm_awq_is_eligible_and_gguf_is_blocked() -> None:
    descriptor = VllmRuntimeSupport().support()
    facts = _facts()
    eligible = declared_compatibility(facts[0], descriptor)
    blocked = VllmModelCompatibility().evaluate(facts[1], descriptor, _fake_profile())
    unresolved = declared_compatibility(facts[2], descriptor)
    assert eligible.status is RuntimeEligibilityStatus.ELIGIBLE
    assert blocked.status is RuntimeEligibilityStatus.BLOCKED
    assert EligibilityReasonCode.UNSUPPORTED_QUANTIZATION in blocked.reason_codes
    assert unresolved.status is RuntimeEligibilityStatus.UNRESOLVED


def _fake_profile():  # type: ignore[no-untyped-def]
    from kultrun.host.contracts import HostId
    from kultrun.kernel.clock import now_utc
    from kultrun.runtime.basis import fingerprint_profile_id
    from kultrun.runtime.contracts import (
        RuntimeCandidateId,
        RuntimeCapabilityProfile,
        RuntimeInstallationId,
        RuntimeProvisioningPlanId,
    )

    installation_id = RuntimeInstallationId.parse("rinst_" + "a" * 16)
    return RuntimeCapabilityProfile(
        profile_id=fingerprint_profile_id(installation_id.value),
        installation_id=installation_id,
        plan_id=RuntimeProvisioningPlanId.parse("rplan_" + "a" * 16),
        candidate_id=RuntimeCandidateId.parse("rcand_" + "a" * 16),
        runtime=Name("vllm"),
        runtime_family=Name("vllm"),
        runtime_provider=Name("vllm"),
        runtime_version="0.28.0",
        executor=Name("native-process"),
        executor_type="process",
        host_id=HostId.generate(),
        status=VerificationStatus.VERIFIED,
        verification_basis_fingerprint="test",
        verifier_provider=Name("fixture"),
        verifier_schema="1",
        created_at=now_utc(),
        last_attempted_at=now_utc(),
    )


def test_unavailable_without_verified_foundation(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    eligibility, _ = _services(tmp_path)
    view = eligibility.evaluate(
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        _facts(),
        components={"vllm": "missing"},
    )
    assert view.status is EligibleViewStatus.UNAVAILABLE
    assert view.candidates == ()
    assert EligibilityReasonCode.SELECTED_FOUNDATION_MISSING in view.reason_codes or (
        EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED in view.reason_codes
    )


def test_current_view_has_eligible_blocked_unresolved(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    view = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert view.status is EligibleViewStatus.CURRENT
    by_name = {item.logical_name: item for item in view.candidates}
    assert (
        by_name["qwen2.5-7b-instruct-awq"].status is RuntimeEligibilityStatus.ELIGIBLE
    )
    assert by_name["tinyllama-1.1b-chat-q4"].status is RuntimeEligibilityStatus.BLOCKED
    assert by_name["hf-acceptance-tiny"].status is RuntimeEligibilityStatus.UNRESOLVED
    assert view.eligible_count == 1
    assert view.blocked_count == 1
    assert view.unresolved_count == 1


def test_evaluation_is_deterministic(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    first = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    second = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert first.view_id == second.view_id
    assert [item.status for item in first.candidates] == [
        item.status for item in second.candidates
    ]


def test_manual_selected_foundation_is_honored(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    descriptors = (VllmRuntimeSupport().support(), _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    eligibility, foundation = _services(tmp_path)
    viewed = foundation.view(
        host, (native,), descriptors, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    foundation.select_manual(
        other.candidate_id,
        host,
        (native,),
        descriptors,
        policy,
        components={"vllm": "missing"},
    )
    stored = foundation.stored(host)
    assert stored is not None
    assert stored.selected_candidate_id == other.candidate_id
    assert stored.recommended_candidate_id != other.candidate_id
    view = eligibility.evaluate(
        host,
        (native,),
        descriptors,
        _facts(),
        policy,
        components={"vllm": "missing"},
    )
    assert view.selected_candidate_id == other.candidate_id
    assert view.recommended_candidate_id != other.candidate_id


def test_foundation_change_is_not_current(tmp_path: Path) -> None:
    eligibility, foundation, host, native, descriptors = _verified(tmp_path)
    current = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert current.status is EligibleViewStatus.CURRENT
    widened = (*descriptors, _alt_descriptor())
    policy = RuntimePolicy(allow_test_only=True)
    viewed = foundation.view(
        host, (native,), widened, policy, components={"vllm": "missing"}
    )
    other = next(
        item for item in viewed.candidates if item.role == "other_provisionable"
    )
    foundation.select_manual(
        other.candidate_id,
        host,
        (native,),
        widened,
        policy,
        components={"vllm": "missing"},
    )
    changed = eligibility.evaluate(
        host,
        (native,),
        widened,
        _facts(),
        policy,
        components={"vllm": "missing"},
    )
    assert changed.status is not EligibleViewStatus.CURRENT
    assert changed.selected_candidate_id == other.candidate_id


def test_stale_profile_makes_view_stale(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    current = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert current.status is EligibleViewStatus.CURRENT
    accelerator = replace(host.accelerators[0], driver_version="changed-driver")
    shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
    stale = eligibility.evaluate(
        shifted, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert stale.status is EligibleViewStatus.STALE
    assert EligibilityReasonCode.RUNTIME_CAPABILITY_STALE in stale.reason_codes


def test_failed_profile_is_unavailable(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(
        tmp_path, scenario=SCENARIO_IMPORT_FAILURE
    )
    view = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert view.status is EligibleViewStatus.UNAVAILABLE
    assert EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED in view.reason_codes


def test_missing_profile_is_unavailable(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    eligibility, foundation = _services(tmp_path)
    descriptors = (VllmRuntimeSupport().support(),)
    foundation.select_auto(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    foundation.realize_selected(
        host, (native,), descriptors, components={"vllm": "missing"}
    )
    view = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert view.status is EligibleViewStatus.UNAVAILABLE
    assert EligibilityReasonCode.RUNTIME_CAPABILITY_UNVERIFIED in view.reason_codes


def test_wrong_profile_installation_is_rejected() -> None:
    from kultrun.host.contracts import HostId
    from kultrun.runtime.contracts import (
        FoundationSelection,
        FoundationSelectionId,
        FoundationSelectionMode,
        InstallationStatus,
        RuntimeCandidateId,
        RuntimeInstallation,
        RuntimeInstallationId,
        RuntimeProvisioningPlanId,
    )
    from kultrun.runtime.eligibility import _view_status

    host_id = HostId.generate()
    selected = "rcand_" + "b" * 16
    now = now_utc()
    selection = FoundationSelection(
        selection_id=FoundationSelectionId.parse("fsel_" + "a" * 16),
        host_id=host_id,
        selection_mode=FoundationSelectionMode.AUTO,
        created_at=now,
        selected_at=now,
        selected_candidate_id=selected,
        recommended_candidate_id=selected,
    )
    installation = RuntimeInstallation(
        installation_id=RuntimeInstallationId.parse("rinst_" + "a" * 16),
        plan_id=RuntimeProvisioningPlanId.parse("rplan_" + "a" * 16),
        candidate_id=RuntimeCandidateId.parse(selected),
        runtime=Name("vllm"),
        runtime_family=Name("vllm"),
        runtime_provider=Name("vllm"),
        runtime_version="0.28.0",
        executor=Name("native-process"),
        host_id=host_id,
        host_fingerprint="fp",
        status=InstallationStatus.INSTALLED,
        installation_root="runtimes/vllm",
        installer="pip",
        package_source="pypi",
        created_at=now,
    )
    profile = replace(
        _fake_profile(),
        candidate_id=RuntimeCandidateId.parse("rcand_" + "c" * 16),
        installation_id=installation.installation_id,
        host_id=host_id,
    )
    status, codes = _view_status(selection, installation, profile)
    assert status is EligibleViewStatus.UNAVAILABLE
    assert EligibilityReasonCode.PROFILE_INSTALLATION_MISMATCH in codes


def test_same_model_differs_by_foundation() -> None:
    descriptor = VllmRuntimeSupport().support()
    alt = _alt_descriptor()
    model = _facts()[0]
    vllm = declared_compatibility(model, descriptor)
    other = declared_compatibility(model, alt)
    assert vllm.status is RuntimeEligibilityStatus.ELIGIBLE
    assert other.status is RuntimeEligibilityStatus.BLOCKED
    assert EligibilityReasonCode.UNSUPPORTED_RUNTIME in other.reason_codes


def test_metadata_is_not_mutated(tmp_path: Path) -> None:
    extra = acceptance_candidate()
    before = extra.metadata
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    eligibility.evaluate(
        host,
        (native,),
        descriptors,
        catalog_facts(_catalogue()),
        components={"vllm": "missing"},
    )
    assert extra.metadata is before
    assert extra.metadata.supported_runtimes == ()


def _catalogue():  # type: ignore[no-untyped-def]
    from kultrun.adapters.model_source.huggingface import HuggingFaceSource
    from kultrun.model.catalogue import ModelCatalogue

    return ModelCatalogue(HuggingFaceSource(), extras=(acceptance_candidate(),))


def test_resource_inputs_are_irrelevant() -> None:
    text = (SOURCE / "kultrun" / "runtime" / "eligibility.py").read_text(
        encoding="utf-8"
    )
    assert "safe_vram" not in text
    assert "ResourceReservation" not in text
    assert "CapacityEnvelope" not in text


def test_architecture_non_edges() -> None:
    leaks = _imports_named(
        SOURCE / "kultrun" / "runtime" / "eligibility.py",
        "kultrun.model",
        "kultrun.planning",
        "kultrun.resource",
        "kultrun.inference",
        "kultrun.execution",
        "subprocess",
    )
    assert leaks == []
    names = {item.name for item in fields(EligibleModelView)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    text = (SOURCE / "kultrun" / "runtime" / "eligibility.py").read_text(
        encoding="utf-8"
    )
    assert "DeploymentFoundation" not in text
    assert "CompatibilityFramework" not in text
    assert "ModelMetadataV2" not in text


def test_planning_tokens_use_eligible_view(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    view = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    mapping = runtime_compatibility(
        view, [item.model_id for item in _facts()]
    )
    assert mapping["model_awq"] is CompatibilityVerdict.COMPATIBLE
    assert mapping["model_q4"] is CompatibilityVerdict.UNSUPPORTED
    assert mapping["model_tiny"] is CompatibilityVerdict.UNRESOLVED
    stale = replace(view, status=EligibleViewStatus.STALE)
    unresolved = runtime_compatibility(stale, ["model_awq"])
    assert unresolved["model_awq"] is CompatibilityVerdict.UNRESOLVED


def test_api_cli_and_console_surfaces(tmp_path: Path) -> None:
    platform = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
        runtime_verifier="fixture",
    )
    empty = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/eligible")
    )
    assert empty.status == 200
    payload = empty.body["payload"]
    assert isinstance(payload, dict)
    assert payload["mutations"] is False
    assert payload["acquire"] is False
    assert payload["capacity"] is False
    assert payload["status"] == "unavailable"
    platform.router.handle(
        ApiRequest(
            method=Method.POST,
            path="/v1/runtimes/foundation/select",
            query={"mode": "auto"},
        )
    )
    platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/realize")
    )
    verified = platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/verify")
    )
    assert verified.status == 200
    eligible = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/eligible")
    )
    assert eligible.status == 200
    body = eligible.body["payload"]
    assert isinstance(body, dict)
    assert body["status"] == "current"
    assert body["authoritative"] is True
    assert body["eligible_count"] >= 1
    assert body["blocked_count"] >= 1
    assert body["unresolved_count"] >= 1
    selection = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/selection")
    )
    assert selection.status == 200
    select_body = selection.body["payload"]
    assert isinstance(select_body, dict)
    assert select_body["runtime_eligibility_status"] == "current"
    assert select_body["runtime_eligibility_authoritative"] is True
    restarted = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
        runtime_verifier="fixture",
    )
    again = restarted.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/eligible")
    )
    assert again.status == 200
    restored = again.body["payload"]
    assert isinstance(restored, dict)
    assert restored["status"] == "current"
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "/models/eligible" in script
    assert "Eligible models" in html
    assert "Select Model" not in script
    assert "declared runtimes" in script


def test_capacity_change_does_not_change_eligibility(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    first = eligibility.evaluate(
        host, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    rammy = replace(
        host, memory=replace(host.memory, total_bytes=host.memory.total_bytes * 2)
    )
    second = eligibility.evaluate(
        rammy, (native,), descriptors, _facts(), components={"vllm": "missing"}
    )
    assert [item.status for item in first.candidates] == [
        item.status for item in second.candidates
    ]
