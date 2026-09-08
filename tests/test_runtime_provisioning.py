"""Stage 1.6C runtime provisioning: install is not verify."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.provisioning.fixture import FixtureRuntimeProvisioner
from kultrun.adapters.provisioning.vllm_native import (
    CommandResult,
    VllmNativeProvisioner,
)
from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.api.contracts import ApiRequest, Method
from kultrun.execution.contracts import ExecutorAvailability, ExecutorCapabilityProfile
from kultrun.host.contracts import Architecture, HostCapabilities
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import ConflictError, PreconditionFailedError
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, config_schema
from kultrun.runtime.contracts import (
    CompatibilityClass,
    InstallationStatus,
    RuntimeCandidate,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeResolution,
)
from kultrun.runtime.lock import ProvisioningLock
from kultrun.runtime.pins import VLLM_VERSION
from kultrun.runtime.plan import is_provisionable
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.resolve import resolve
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named
from tests.test_contracts import host_capabilities
from tests.test_runtime_resolution import _container, _macos, _native

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _service(
    tmp_path: Path,
    provisioner: FixtureRuntimeProvisioner | None = None,
) -> ProvisioningService:
    store = FileStore(tmp_path / "records")
    return ProvisioningService(
        store,
        FixedClock(now_utc()),
        provisioner or FixtureRuntimeProvisioner(),
        tmp_path / "state",
        ProvisioningLock(tmp_path / "state"),
    )


def _candidate(
    host: HostCapabilities,
    executors: Sequence[ExecutorCapabilityProfile],
    *,
    components: dict[str, str] | None = None,
) -> tuple[RuntimeCandidate, RuntimeResolution]:
    result = resolve(
        host,
        executors,
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components=components or {"vllm": "missing"},
    )
    native = next(
        item
        for item in (*result.candidates, *result.unsupported, *result.unresolved)
        if item.executor.value == "native-process"
    )
    return native, result


def test_case_a_unsupported_candidate_has_no_plan(tmp_path: Path) -> None:
    host = _macos(host_capabilities())
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (_native(host),), components={"vllm": "present"})
    assert candidate.compatibility is CompatibilityClass.UNSUPPORTED
    with pytest.raises(PreconditionFailedError, match="unsupported"):
        service.create_plan(
            candidate.candidate_id.value,
            host,
            (_native(host),),
            (VllmRuntimeSupport().support(),),
            RuntimePolicy(),
            components={"vllm": "present"},
        )


def test_case_b_unresolved_candidate_has_no_plan(tmp_path: Path) -> None:
    host = host_capabilities()
    host = replace(
        host,
        operating_environment=replace(
            host.operating_environment,
            architecture=Architecture.UNKNOWN,
        ),
    )
    service = _service(tmp_path)
    candidate, result = _candidate(host, (_native(host),))
    assert result.unresolved
    with pytest.raises(PreconditionFailedError, match="unresolved"):
        service.create_plan(
            candidate.candidate_id.value,
            host,
            (_native(host),),
            (VllmRuntimeSupport().support(),),
            RuntimePolicy(),
            components={"vllm": "missing"},
        )


def test_case_c_missing_runtime_package_is_provisionable(tmp_path: Path) -> None:
    host = host_capabilities()
    candidate, _ = _candidate(host, (_native(host),))
    assert candidate.compatibility is CompatibilityClass.CONDITIONAL
    assert is_provisionable(candidate)
    plan = _service(tmp_path).create_plan(
        candidate.candidate_id.value,
        host,
        (_native(host),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    assert plan.runtime_version == VLLM_VERSION
    assert plan.python_version == "3.12"
    assert "model" not in {item.name for item in fields(type(plan))}


def test_case_d_stale_executor_rejects_provision(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    unavailable = _native(host, availability=ExecutorAvailability.UNAVAILABLE)
    with pytest.raises(PreconditionFailedError, match="no longer available"):
        service.provision(
            plan.plan_id,
            host,
            (unavailable,),
            (VllmRuntimeSupport().support(),),
            components={"vllm": "missing"},
        )


def test_case_e_host_fingerprint_change_rejects_plan(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    changed = replace(host, fingerprint="deadbeefdeadbeefdeadbeefdeadbeef")
    with pytest.raises(PreconditionFailedError, match="fingerprint"):
        service.provision(
            plan.plan_id,
            changed,
            (_native(changed),),
            (VllmRuntimeSupport().support(),),
            components={"vllm": "missing"},
        )


def test_case_f_missing_python_is_prerequisite_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Required(FixtureRuntimeProvisioner):
        @property
        def requires_host_python(self) -> bool:
            return True

    monkeypatch.setattr("kultrun.runtime.provision.locate_python", lambda: None)
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path, Required())
    candidate, _ = _candidate(host, (native,))
    with pytest.raises(PreconditionFailedError, match=r"python 3\.12"):
        service.create_plan(
            candidate.candidate_id.value,
            host,
            (native,),
            (VllmRuntimeSupport().support(),),
            RuntimePolicy(),
            components={"vllm": "missing"},
        )


def test_case_g_installer_failure_is_not_promoted(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path, FixtureRuntimeProvisioner(fail=True))
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert installed.status is InstallationStatus.FAILED
    final = tmp_path / "state" / plan.installation_root
    assert not final.exists()


def test_case_h_partial_staging_is_cleaned(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path, FixtureRuntimeProvisioner(fail=True))
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    staging_root = tmp_path / "state" / "runtimes" / ".staging"
    leftovers = list(staging_root.glob(f"{installed.installation_id.value}-*"))
    assert leftovers == []
    assert installed.status is not InstallationStatus.INSTALLED


def test_case_i_successful_plan_is_idempotent(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    provisioner = FixtureRuntimeProvisioner()
    service = _service(tmp_path, provisioner)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    first = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    second = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert first.status is InstallationStatus.INSTALLED
    assert second.installation_id == first.installation_id
    assert provisioner.install_calls == 1


def test_case_j_installing_conflicts(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    first = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    installing = replace(first, status=InstallationStatus.INSTALLING)
    service._store.put(installing.installation_id.value, installing)
    with pytest.raises(ConflictError, match="already provisioning"):
        service.provision(
            plan.plan_id,
            host,
            (native,),
            (VllmRuntimeSupport().support(),),
            components={"vllm": "missing"},
        )


def test_case_k_explicit_retry_increments_attempt(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    failing = FixtureRuntimeProvisioner(fail=True)
    service = _service(tmp_path, failing)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    failed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert failed.status is InstallationStatus.FAILED
    assert failed.attempt_count == 1
    service._provisioner = FixtureRuntimeProvisioner()
    retried = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
        retry=True,
    )
    assert retried.status is InstallationStatus.INSTALLED
    assert retried.attempt_count == 2
    assert retried.installation_id == failed.installation_id


def test_case_l_wrong_metadata_version_fails(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(
        tmp_path, FixtureRuntimeProvisioner(installed_version="0.27.0")
    )
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert installed.status is InstallationStatus.FAILED
    assert installed.last_failure_code == "version_mismatch"


def test_case_m_installed_is_not_verified(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    assert installed.status is InstallationStatus.INSTALLED
    names = {item.name for item in fields(RuntimeInstallation)}
    assert "verified" not in names
    assert "capabilities" not in names
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    final = tmp_path / "state" / installed.installation_root
    assert final.is_dir()
    assert (final / "manifest" / "installer-report.json").is_file()
    assert is_resolved(installed.provenance_manifest_sha256)
    assert is_resolved(installed.python_executable)
    python = Path(str(installed.python_executable))
    assert python.is_file()
    assert python.is_relative_to(final)
    assert ".staging" not in str(python)


def test_plan_identity_is_stable(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    first = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    second = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    assert first.plan_id == second.plan_id
    assert first.plan_fingerprint == second.plan_fingerprint


def test_restart_reloads_installation(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    first = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = first.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = first.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    reloaded = _service(tmp_path).get_installation(installed.installation_id)
    assert reloaded.status is InstallationStatus.INSTALLED
    assert reloaded.installation_id == installed.installation_id


def test_interrupted_installing_reconciles_to_failed(tmp_path: Path) -> None:
    host = host_capabilities()
    native = _native(host)
    service = _service(tmp_path)
    candidate, _ = _candidate(host, (native,))
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "missing"},
    )
    interrupted = replace(installed, status=InstallationStatus.INSTALLING)
    service._store.put(interrupted.installation_id.value, interrupted)
    service.reconcile()
    failed = service.get_installation(installed.installation_id)
    assert failed.status is InstallationStatus.FAILED
    assert failed.last_failure_code == "interrupted"


def test_plan_and_installation_have_no_model_or_docker_fields() -> None:
    from kultrun.runtime.contracts import RuntimeProvisioningPlan

    for contract_type in (RuntimeProvisioningPlan, RuntimeInstallation):
        names = {item.name for item in fields(contract_type)}
        assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
        assert "model_id" not in names
        assert "logical_name" not in names
        assert "verified" not in names
        assert "capabilities" not in names


def test_container_candidate_is_not_provisionable() -> None:
    host = host_capabilities()
    result = resolve(
        host,
        (_container(host),),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    item = result.candidates[0]
    assert item.executor.value == "container-docker"
    assert not is_provisionable(item)


def test_vllm_native_argv_is_exact_and_unshellled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []

    class Runner:
        def run(
            self,
            argv: Sequence[str],
            *,
            cwd: Path | None = None,
            timeout: float | None = None,
        ) -> CommandResult:
            del cwd, timeout
            recorded = tuple(str(item) for item in argv)
            calls.append(recorded)
            if "-m" in recorded and "venv" in recorded:
                root = Path(recorded[-1])
                (root / "bin").mkdir(parents=True)
                (root / "bin" / "python").write_text("", encoding="utf-8")
                return CommandResult(0, "", "")
            if "install" in recorded:
                report = Path(recorded[recorded.index("--report") + 1])
                report.write_text('{"version": "1"}\n', encoding="utf-8")
                return CommandResult(0, "", "")
            if "-c" in recorded:
                return CommandResult(0, f"{VLLM_VERSION}\n", "")
            if "--version" in recorded:
                return CommandResult(0, "pip 24.0\n", "")
            return CommandResult(0, "", "")

    host = host_capabilities()
    native = _native(host)
    service = ProvisioningService(
        FileStore(tmp_path / "records"),
        FixedClock(now_utc()),
        VllmNativeProvisioner(Runner()),
        tmp_path / "state",
        ProvisioningLock(tmp_path / "state"),
    )
    monkeypatch.setattr(
        "kultrun.runtime.provision.locate_python",
        lambda requirement="3.12": "/usr/bin/python3.12",
    )
    candidate, _ = _candidate(host, (native,), components={"vllm": "present"})
    plan = service.create_plan(
        candidate.candidate_id.value,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        RuntimePolicy(),
        components={"vllm": "present"},
    )
    installed = service.provision(
        plan.plan_id,
        host,
        (native,),
        (VllmRuntimeSupport().support(),),
        components={"vllm": "present"},
    )
    assert installed.status is InstallationStatus.INSTALLED
    joined = [" ".join(call) for call in calls]
    assert any("-m venv" in item for item in joined)
    assert any(f"vllm=={VLLM_VERSION}" in item for item in joined)
    assert any("--report" in item for item in joined)
    assert all("shell" not in item for item in joined)
    assert all("--user" not in call for call in calls)


def test_provisioning_modules_do_not_import_forbidden_domains() -> None:
    for relative in (
        "kultrun/runtime/plan.py",
        "kultrun/runtime/provision.py",
        "kultrun/adapters/provisioning/fixture.py",
        "kultrun/adapters/provisioning/vllm_native.py",
    ):
        leaks = _imports_named(
            SOURCE / relative,
            "kultrun.model",
            "kultrun.planning",
            "kultrun.resource",
            "kultrun.inference",
        )
        assert leaks == []
    native = (
        SOURCE / "kultrun" / "adapters" / "provisioning" / "vllm_native.py"
    ).read_text(encoding="utf-8")
    assert "import vllm" not in native
    assert "from vllm" not in native
    assert "shell=True" not in native
    assert "shell=False" in native


def test_api_plan_and_provision_and_reads(tmp_path: Path) -> None:
    from kultrun.adapters.host import fixtures

    platform = build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
    )
    candidates = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/candidates")
    )
    assert candidates.status == 200
    payload = candidates.body["payload"]
    assert isinstance(payload, dict)
    assert payload["mutations"] is False
    resolution = payload["resolution"]
    assert isinstance(resolution, dict)
    native = next(
        item
        for item in resolution["candidates"]
        if item["executor"] == "native-process" and item["runtime"] == "vllm"
    )
    created = platform.router.handle(
        ApiRequest(
            method=Method.POST,
            path="/v1/runtimes/provisioning-plans",
            query={"candidate_id": native["candidate_id"]},
        )
    )
    assert created.status == 200
    plan = created.body["payload"]
    assert isinstance(plan, dict)
    assert plan["runtime_version"] == VLLM_VERSION
    provisioned = platform.router.handle(
        ApiRequest(
            method=Method.POST,
            path="/v1/runtimes/provision",
            query={"plan_id": plan["plan_id"]},
        )
    )
    assert provisioned.status == 200
    installation = provisioned.body["payload"]
    assert isinstance(installation, dict)
    assert installation["status"] == "installed"
    listed = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/installations")
    )
    assert listed.status == 200
    body = listed.body["payload"]
    assert isinstance(body, dict)
    assert body["verify_on_get"] is False
    plans = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/provisioning-plans")
    )
    assert plans.status == 200
    missing = platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/verify")
    )
    assert missing.status == 400
    verified = platform.router.handle(
        ApiRequest(
            method=Method.POST,
            path="/v1/runtimes/verify",
            query={"installation_id": installation["installation_id"]},
        )
    )
    assert verified.status == 200
    profile = verified.body["payload"]
    assert isinstance(profile, dict)
    assert profile["status"] == "verified"
    listed_again = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/runtimes/capability-profiles")
    )
    assert listed_again.status == 200
    listed_body = listed_again.body["payload"]
    assert isinstance(listed_body, dict)
    assert listed_body["verify_on_get"] is False
    assert listed_body["mutations"] is False


def test_console_has_plan_provision_and_verify() -> None:
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "Create plan" in script
    assert "Provision" in script
    assert "/runtimes/provisioning-plans" in script
    assert "post('/runtimes/verify" in script
    assert "Launch Model" not in html
    assert "Launch Model" not in script
    assert "Recommended Runtime" not in script
    assert "Select Model" not in script
    assert "textContent = 'Start vLLM'" not in script
    panel = html.split("candidates-panel", 1)[1].split("<section", 1)[0]
    assert "Verify" not in panel
    assert "provenance" in script or "verification" in script
