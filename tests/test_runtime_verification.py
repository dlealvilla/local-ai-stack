"""Stage 1.6D runtime verification: installed is not verified."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.adapters.verification.fixture import (
    SCENARIO_BACKEND_UNAVAILABLE,
    SCENARIO_GPU_MISSING,
    SCENARIO_IMPORT_FAILURE,
    SCENARIO_INVALID_EVIDENCE,
    SCENARIO_OPERATION_FAILED,
    SCENARIO_PACKAGE_MISSING,
    SCENARIO_TIMEOUT,
    SCENARIO_VERSION_MISMATCH,
    FixtureProbeRunner,
    FixtureRuntimeVerifier,
)
from kultrun.adapters.verification.vllm_native import VllmNativeVerifier
from kultrun.api.contracts import ApiRequest, Method
from kultrun.execution.contracts import ExecutorAvailability
from kultrun.host.contracts import AcceleratorVendor, HostCapabilities, MemoryFacts
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, config_schema
from kultrun.runtime.basis import (
    build_verification_basis,
    effective_status,
    fingerprint_profile_id,
)
from kultrun.runtime.contracts import (
    InstallationStatus,
    RuntimeCapabilityProfile,
    RuntimePolicy,
    RuntimeSupportDescriptor,
    RuntimeVerificationBasis,
    VerificationReasonCode,
    VerificationStatus,
)
from kultrun.runtime.lock import ProvisioningLock, VerificationLock
from kultrun.runtime.pins import VLLM_VERSION
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.verify import VerificationService
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named
from tests.test_contracts import host_capabilities
from tests.test_runtime_provisioning import _candidate
from tests.test_runtime_resolution import _native

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _services(
    tmp_path: Path,
    scenario: str = "healthy",
    *,
    store: FileStore | None = None,
) -> tuple[ProvisioningService, VerificationService, FixtureProbeRunner]:
    records = store or FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    state = tmp_path / "state"
    provisioning = ProvisioningService(
        records,
        clock,
        FixtureRuntimeProvisioner(),
        state,
        ProvisioningLock(state),
    )
    runner = FixtureProbeRunner(scenario)
    verification = VerificationService(
        records,
        clock,
        FixtureRuntimeVerifier(scenario),
        runner,
        state,
        VerificationLock(state),
    )
    return provisioning, verification, runner


def _install(
    tmp_path: Path,
    host: HostCapabilities | None = None,
    scenario: str = "healthy",
):
    host = host or host_capabilities()
    native = _native(host)
    provisioning, verification, runner = _services(tmp_path, scenario)
    candidate, _ = _candidate(host, (native,))
    plan = provisioning.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installation = provisioning.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    return installation, verification, runner, host, native, provisioning


def test_profile_schema_has_no_model_or_ranking_fields() -> None:
    names = {item.name for item in fields(RuntimeCapabilityProfile)}
    forbidden = {
        "model_id",
        "model",
        "artifact_id",
        "rank",
        "score",
        "recommended_runtime",
        "selected_runtime",
        "throughput",
        "ttft",
        "deployment_plan_id",
    }
    assert names.isdisjoint(forbidden)
    assert "installation_id" in names
    assert "verification_basis_fingerprint" in names
    kinds = {
        RuntimeCapabilityProfile.kind,
        RuntimeSupportDescriptor.kind,
        RuntimeVerificationBasis.kind,
    }
    assert kinds == {
        "runtime.capability_profile",
        "runtime.support_descriptor",
        "runtime.verification_basis",
    }


def test_profile_identity_is_stable_per_installation(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(tmp_path)
    first = verification.verify(installation.installation_id, host, (native,))
    second = verification.verify(installation.installation_id, host, (native,))
    assert first.profile_id == fingerprint_profile_id(
        installation.installation_id.value
    )
    assert first.profile_id == second.profile_id
    assert runner.run_count == 1
    assert first.attempt_count == 1
    assert second.attempt_count == 1


def test_basis_excludes_transient_capacity() -> None:
    host = host_capabilities()
    native = _native(host)
    python = "/state/runtimes/vllm/0.28.0/rinst_x/venv/bin/python"
    installation = _fake_install(host, python)
    basis = build_verification_basis(installation, host, (native,))
    ram = replace(
        host,
        memory=MemoryFacts(
            total_bytes=host.memory.total_bytes,
            available_bytes=1,
            unified_with_accelerator=False,
        ),
    )
    ram_basis = build_verification_basis(installation, ram, (native,))
    assert basis.fingerprint == ram_basis.fingerprint
    more_free = replace(
        host,
        mounts=(replace(host.mounts[0], free_bytes=1),),
    )
    assert (
        basis.fingerprint
        == build_verification_basis(installation, more_free, (native,)).fingerprint
    )
    cores = replace(host, cpu=replace(host.cpu, logical_cores=8))
    assert (
        basis.fingerprint
        == build_verification_basis(installation, cores, (native,)).fingerprint
    )


def test_driver_and_accelerator_and_runtime_change_stale_basis() -> None:
    host = host_capabilities()
    native = _native(host)
    installation = _fake_install(host, "/tmp/python")
    original = build_verification_basis(installation, host, (native,))
    driver = replace(
        host,
        accelerators=(replace(host.accelerators[0], driver_version="999.0"),),
    )
    assert (
        original.fingerprint
        != build_verification_basis(installation, driver, (native,)).fingerprint
    )
    gpu = replace(
        host,
        accelerators=(replace(host.accelerators[0], model_name="RTX A6000"),),
    )
    assert (
        original.fingerprint
        != build_verification_basis(installation, gpu, (native,)).fingerprint
    )
    swapped = replace(installation, runtime_version="0.27.0")
    assert (
        original.fingerprint
        != build_verification_basis(swapped, host, (native,)).fingerprint
    )
    assert (
        effective_status(
            VerificationStatus.VERIFIED,
            original.fingerprint,
            build_verification_basis(installation, driver, (native,)).fingerprint,
        )
        is VerificationStatus.STALE
    )


def _fake_install(host: HostCapabilities, python: str):
    from kultrun.kernel.ids import Name
    from kultrun.runtime.contracts import (
        RuntimeCandidateId,
        RuntimeInstallation,
        RuntimeInstallationId,
        RuntimeProvisioningPlanId,
    )

    return RuntimeInstallation(
        installation_id=RuntimeInstallationId.parse("rinst_0123456789abcdef"),
        plan_id=RuntimeProvisioningPlanId.parse("rplan_0123456789abcdef"),
        candidate_id=RuntimeCandidateId.parse("rcand_0123456789abcdef"),
        runtime=Name("vllm"),
        runtime_family=Name("vllm"),
        runtime_provider=Name("vllm"),
        runtime_version=VLLM_VERSION,
        executor=Name("native-process"),
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        status=InstallationStatus.INSTALLED,
        installation_root="runtimes/vllm/0.28.0/rinst_0123456789abcdef",
        installer="pip",
        package_source="pypi",
        created_at=now_utc(),
        python_executable=python,
        python_version="3.12",
    )


def test_case_a_healthy_nvidia_fixture_verified(tmp_path: Path) -> None:
    installation, verification, runner, host, native, provisioning = _install(tmp_path)
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.VERIFIED
    assert profile.runtime.value == "vllm"
    assert profile.runtime_version == VLLM_VERSION
    assert is_resolved(profile.runtime_package_version)
    assert profile.attempt_count == 1
    assert runner.run_count == 1
    current = provisioning.get_installation(installation.installation_id)
    assert current.status is InstallationStatus.INSTALLED


def test_case_b_package_missing_failed(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_PACKAGE_MISSING
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.RUNTIME_PACKAGE_MISSING in profile.reason_codes
    assert runner.run_count == 0


def test_case_c_version_mismatch_failed(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_VERSION_MISMATCH
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.RUNTIME_VERSION_MISMATCH in profile.reason_codes


def test_case_d_runtime_import_failure(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_IMPORT_FAILURE
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.RUNTIME_IMPORT_FAILED in profile.reason_codes


def test_case_e_executor_unavailable(tmp_path: Path) -> None:
    installation, verification, runner, host, _, _ = _install(tmp_path)
    unavailable = _native(host, availability=ExecutorAvailability.UNAVAILABLE)
    profile = verification.verify(installation.installation_id, host, (unavailable,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.EXECUTOR_UNAVAILABLE in profile.reason_codes
    assert runner.run_count == 0
    assert (
        verification.profile_for(installation.installation_id, host, (unavailable,))
        is not None
    )


def test_case_f_backend_unavailable(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_BACKEND_UNAVAILABLE
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert (
        VerificationReasonCode.BACKEND_ACCELERATOR_UNAVAILABLE
        in profile.reason_codes
    )


def test_case_g_gpu_missing(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_GPU_MISSING
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.ACCELERATOR_NOT_VISIBLE in profile.reason_codes


def test_case_h_accelerator_operation_failed(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_OPERATION_FAILED
    )
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.FAILED
    assert VerificationReasonCode.ACCELERATOR_OPERATION_FAILED in profile.reason_codes


def test_timeout_and_invalid_evidence_failed(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_TIMEOUT
    )
    timed_out = verification.verify(installation.installation_id, host, (native,))
    assert timed_out.status is VerificationStatus.FAILED
    assert VerificationReasonCode.PROBE_TIMEOUT in timed_out.reason_codes
    other = tmp_path / "invalid"
    other.mkdir()
    installation, verification, _, host, native, _ = _install(
        other, scenario=SCENARIO_INVALID_EVIDENCE
    )
    invalid = verification.verify(installation.installation_id, host, (native,))
    assert invalid.status is VerificationStatus.FAILED
    assert VerificationReasonCode.PROBE_OUTPUT_INVALID in invalid.reason_codes


def test_case_i_driver_change_stales_verified(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(tmp_path)
    profile = verification.verify(installation.installation_id, host, (native,))
    assert profile.status is VerificationStatus.VERIFIED
    changed = replace(
        host,
        accelerators=(replace(host.accelerators[0], driver_version="999.99.99"),),
    )
    presented = verification.profile_for(
        installation.installation_id, changed, (_native(changed),)
    )
    assert presented is not None
    assert presented.status is VerificationStatus.STALE
    assert runner.run_count == 1


def test_case_j_gpu_identity_change_stales_verified(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(tmp_path)
    verification.verify(installation.installation_id, host, (native,))
    changed = replace(
        host,
        accelerators=(
            replace(
                host.accelerators[0],
                vendor=AcceleratorVendor.NVIDIA,
                model_name="RTX A6000",
            ),
        ),
    )
    presented = verification.profile_for(
        installation.installation_id, changed, (_native(changed),)
    )
    assert presented is not None
    assert presented.status is VerificationStatus.STALE


def test_case_k_free_vram_capacity_does_not_stale(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(tmp_path)
    verification.verify(installation.installation_id, host, (native,))
    changed = replace(host, cpu=replace(host.cpu, logical_cores=4))
    presented = verification.profile_for(
        installation.installation_id, changed, (_native(changed),)
    )
    assert presented is not None
    assert presented.status is VerificationStatus.VERIFIED
    assert runner.run_count == 1


def test_case_l_free_ram_does_not_stale(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(tmp_path)
    verification.verify(installation.installation_id, host, (native,))
    changed = replace(
        host,
        memory=MemoryFacts(
            total_bytes=host.memory.total_bytes,
            available_bytes=1,
            unified_with_accelerator=False,
        ),
    )
    presented = verification.profile_for(
        installation.installation_id, changed, (_native(changed),)
    )
    assert presented is not None
    assert presented.status is VerificationStatus.VERIFIED


def test_case_m_restart_reloads_profile(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(tmp_path)
    original = verification.verify(installation.installation_id, host, (native,))
    restored = VerificationService(
        FileStore(tmp_path / "records"),
        FixedClock(now_utc()),
        FixtureRuntimeVerifier(),
        FixtureProbeRunner(),
        tmp_path / "state",
        VerificationLock(tmp_path / "state"),
    )
    loaded = restored.profile_for(installation.installation_id, host, (native,))
    assert loaded is not None
    assert loaded.profile_id == original.profile_id
    assert loaded.status is VerificationStatus.VERIFIED


def test_case_n_repeated_fresh_verify_does_not_reprobe(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(tmp_path)
    first = verification.verify(installation.installation_id, host, (native,))
    second = verification.verify(installation.installation_id, host, (native,))
    assert first.profile_id == second.profile_id
    assert runner.run_count == 1
    assert second.attempt_count == first.attempt_count


def test_case_o_failed_then_corrected_verifies(tmp_path: Path) -> None:
    installation, verification, _, host, native, _ = _install(
        tmp_path, scenario=SCENARIO_IMPORT_FAILURE
    )
    failed = verification.verify(installation.installation_id, host, (native,))
    assert failed.status is VerificationStatus.FAILED
    healthy = VerificationService(
        FileStore(tmp_path / "records"),
        FixedClock(now_utc()),
        FixtureRuntimeVerifier(),
        FixtureProbeRunner(),
        tmp_path / "state",
        VerificationLock(tmp_path / "state"),
    )
    passed = healthy.verify(installation.installation_id, host, (native,))
    assert passed.status is VerificationStatus.VERIFIED
    assert passed.profile_id == failed.profile_id
    assert passed.attempt_count == failed.attempt_count + 1


def test_get_does_not_run_probe(tmp_path: Path) -> None:
    installation, verification, runner, host, native, _ = _install(tmp_path)
    verification.verify(installation.installation_id, host, (native,))
    verification.profiles(host, (native,))
    verification.profile_for(installation.installation_id, host, (native,))
    assert runner.run_count == 1


def test_failed_verify_does_not_mutate_installation(tmp_path: Path) -> None:
    installation, verification, _, host, native, provisioning = _install(
        tmp_path, scenario=SCENARIO_IMPORT_FAILURE
    )
    verification.verify(installation.installation_id, host, (native,))
    current = provisioning.get_installation(installation.installation_id)
    assert current.status is InstallationStatus.INSTALLED


def test_architecture_non_edges() -> None:
    for relative in (
        "kultrun/runtime/verify.py",
        "kultrun/runtime/basis.py",
        "kultrun/adapters/verification/fixture.py",
        "kultrun/adapters/verification/vllm_native.py",
    ):
        leaks = _imports_named(
            SOURCE / relative,
            "kultrun.model",
            "kultrun.planning",
            "kultrun.resource",
            "kultrun.inference",
            "subprocess",
        )
        assert leaks == []
    native = (
        SOURCE / "kultrun" / "adapters" / "verification" / "vllm_native.py"
    ).read_text(encoding="utf-8")
    assert "shell=True" not in native
    assert "vllm serve" not in native
    runner = (SOURCE / "kultrun" / "platform" / "probe_run.py").read_text(
        encoding="utf-8"
    )
    assert "executions.start" in runner
    assert "subprocess" not in runner
    assert "Popen" not in runner
    names = {item.name for item in fields(RuntimeCapabilityProfile)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    assert "model_id" not in names


def test_vllm_native_probe_is_structured_argv() -> None:
    from kultrun.kernel.ids import Name
    from kultrun.runtime.contracts import (
        RuntimeCandidateId,
        RuntimeInstallation,
        RuntimeInstallationId,
        RuntimeProvisioningPlanId,
    )

    host = host_capabilities()
    installation = RuntimeInstallation(
        installation_id=RuntimeInstallationId.parse("rinst_0123456789abcdef"),
        plan_id=RuntimeProvisioningPlanId.parse("rplan_0123456789abcdef"),
        candidate_id=RuntimeCandidateId.parse("rcand_0123456789abcdef"),
        runtime=Name("vllm"),
        runtime_family=Name("vllm"),
        runtime_provider=Name("vllm"),
        runtime_version=VLLM_VERSION,
        executor=Name("native-process"),
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        status=InstallationStatus.INSTALLED,
        installation_root="runtimes/vllm/0.28.0/rinst_0123456789abcdef",
        installer="pip",
        package_source="pypi",
        created_at=now_utc(),
        python_executable="/tmp/venv/bin/python",
        python_version="3.12",
    )
    spec = VllmNativeVerifier().probe_spec(installation)
    assert spec.arguments[0] == "-c"
    assert "import vllm" in spec.arguments[1]
    assert "torch.zeros" in spec.arguments[1]
    assert all(not item.startswith("sh") for item in spec.arguments)


def test_api_get_does_not_verify_without_profile(tmp_path: Path) -> None:
    from kultrun.adapters.host import fixtures

    platform = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
        runtime_verifier="fixture",
    )
    missing = platform.router.handle(
        ApiRequest(
            method=Method.GET,
            path="/v1/runtimes/capability-profile",
            query={"installation_id": "rinst_0123456789abcdef"},
        )
    )
    assert missing.status == 404
    listed = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/capability-profiles")
    )
    assert listed.status == 200
    payload = listed.body["payload"]
    assert isinstance(payload, dict)
    assert payload["mutations"] is False
    assert payload["verify_on_get"] is False
