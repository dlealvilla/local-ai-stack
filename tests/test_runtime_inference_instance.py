"""Stage 1.6K — plan-driven InferenceInstance. Consumes; does not serve."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from kultrun.adapters.runtime.vllm import VllmRuntimeSupport
from kultrun.api.contracts import Method
from kultrun.inference.contracts import InferenceInstance, InstanceId, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.errors import ConflictError, PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.main import main
from kultrun.model.contracts import ArtifactId
from kultrun.resource.contracts import ReservationId
from kultrun.runtime.catalogue import RuntimeCatalogue
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_inference_instance import SMALL, _Stack
from tests.test_runtime_deployment_plan import _call, _product, _realize
from tests.test_runtime_deployment_prepare import _count_admit, _current_plan

SOURCE = Path(__file__).resolve().parent.parent / "src"


def _prepare(platform) -> dict[str, object]:
    _current_plan(platform)
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert prepared.status == 200
    payload = prepared.body["payload"]
    assert payload["plan_status"] == "current"
    assert payload["admission"]["verdict"] == "admitted"
    return payload


def _other_feasible(platform, recommended: str) -> str:
    """A different feasible model. Prefer the smallest so leftover grants still fit."""
    selection = _call(platform, "/models/selection").body["payload"]
    requirements = _call(platform, "/models/requirements").body["payload"]
    vram = {
        row["logical_name"]: row["required_vram_bytes"]
        for row in requirements["assessments"]
        if isinstance(row.get("required_vram_bytes"), int)
    }
    others = [
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != recommended
    ]
    others.sort(key=lambda name: vram.get(name, 1 << 62))
    return others[0]


def _create(platform, **query: str):
    return _call(platform, "/inference/instances", Method.POST, **query)


def test_matching_triple_creates_from_plan(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    counted = _count_admit(platform)
    created = _create(platform, reservation_id=prepared["admission"]["reservation_id"])
    assert created.status == 200
    body = created.body["payload"]
    assert body["observed_state"] == "created"
    assert body["plan_id"] == plan["plan_id"]
    assert body["plan_basis"] == plan["plan_basis"]
    assert body["configuration_current"] is True
    assert body["plan_status"] == "current"
    assert body["model_id"] == plan["model_id"]
    assert body["logical_name"] == plan["selected_model"]
    assert body["artifact_id"] == prepared["artifact_id"]
    assert body["reservation_id"] == prepared["admission"]["reservation_id"]
    assert body["runtime"] == plan["runtime"] == "vllm"
    assert body["executor"] == plan["executor"]
    settings = plan["settings"]
    assert body["placement"] == settings["placement"]
    assert body["accelerator_index"] == settings["accelerator_index"]
    if settings["context_tokens"] is not None:
        assert body["context_length_tokens"] == settings["context_tokens"]
    assert counted["count"] == 0
    stored = platform.instances.get(InstanceId.parse(body["instance_id"]))
    assert stored is not None
    assert stored.observed_state is ObservedState.CREATED
    assert stored.model_id.value == plan["model_id"]


def test_stale_and_unavailable_create_refused(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    unread = _create(platform)
    assert unread.status == 412
    assert unread.body["error"]["context"]["reason"] == "plan_unavailable"
    _realize(platform)
    created = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    other = _other_feasible(platform, created["selected_model"])
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    stale = _create(platform)
    assert stale.status == 412
    assert stale.body["error"]["context"]["reason"] == "plan_stale"
    assert platform.instances.list() == ()


def test_mismatch_matrix_refused(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    first_plan = _current_plan(platform)
    first = _prepare(platform)
    first_reservation = first["admission"]["reservation_id"]
    first_artifact = first["artifact_id"]
    other = _other_feasible(platform, first_plan["selected_model"])
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    second_plan = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert second_plan["selected_model"] == other
    second = _call(platform, "/deployments/plan/prepare", Method.POST).body["payload"]
    second_reservation = second["admission"]["reservation_id"]
    second_artifact = second["artifact_id"]
    assert first_artifact != second_artifact
    assert first_reservation != second_reservation

    wrong_artifact = _create(
        platform,
        reservation_id=second_reservation,
        artifact_id=first_artifact,
    )
    assert wrong_artifact.status == 412
    assert wrong_artifact.body["error"]["context"]["reason"] in {
        "artifact_plan_mismatch",
        "reservation_artifact_mismatch",
    }

    wrong_reservation = _create(platform, reservation_id=first_reservation)
    assert wrong_reservation.status == 412
    assert wrong_reservation.body["error"]["context"]["reason"] in {
        "artifact_plan_mismatch",
        "reservation_plan_mismatch",
        "reservation_request_mismatch",
    }

    cross = _create(
        platform,
        reservation_id=first_reservation,
        artifact_id=second_artifact,
    )
    assert cross.status == 412

    released = _call(
        platform,
        "/resources/reservations",
        Method.DELETE,
        reservation_id=second_reservation,
    )
    assert released.status == 200
    inactive = _create(platform, reservation_id=second_reservation)
    assert inactive.status == 412
    assert inactive.body["error"]["context"]["reason"] == "reservation_not_active"
    assert platform.instances.list() == ()


def test_same_model_plan_basis_mismatch_refused(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    reservation_id = prepared["admission"]["reservation_id"]
    _call(
        platform,
        "/models/selection",
        Method.POST,
        mode="manual",
        model=plan["selected_model"],
    )
    refreshed = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert refreshed["status"] == "current"
    assert refreshed["selected_model"] == plan["selected_model"]
    assert refreshed["plan_basis"] != plan["plan_basis"]
    refused = _create(platform, reservation_id=reservation_id)
    assert refused.status == 412
    assert refused.body["error"]["context"]["reason"] in {
        "reservation_plan_mismatch",
        "reservation_request_mismatch",
        "plan_stale",
    }
    assert platform.instances.list() == ()


def test_legacy_artifact_reservation_is_not_instance_authority(
    tmp_path: Path,
) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    other = _other_feasible(platform, plan["selected_model"])
    stored = _call(platform, "/models/acquire", Method.POST, candidate=other)
    assert stored.status == 200
    leftover = _call(
        platform,
        "/resources/reservations",
        Method.POST,
        artifact_id=stored.body["payload"]["artifact_id"],
    )
    assert leftover.status == 200
    legacy = leftover.body["payload"]["reservation"]["reservation_id"]
    refused = _create(platform, reservation_id=legacy)
    assert refused.status == 412
    assert refused.body["error"]["context"]["reason"] in {
        "artifact_plan_mismatch",
        "reservation_plan_mismatch",
        "reservation_request_mismatch",
        "plan_stale",
    }
    assert platform.instances.list() == ()


def test_manual_model_and_plan_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = _product(tmp_path)
    auto = _current_plan(platform)
    other = _other_feasible(platform, auto["selected_model"])
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    plan = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert plan["selected_model"] == other
    assert plan["selected_model"] != auto["selected_model"]
    import kultrun.planning.service as planning_mod
    import kultrun.platform.admission as admission_mod

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("instance create must not reconstruct from helpers")

    monkeypatch.setattr(admission_mod, "plan_for_entry", boom)
    monkeypatch.setattr(planning_mod, "plan_for_entry", boom)
    monkeypatch.setattr(planning_mod, "plan_from", boom)
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert prepared.status == 200
    created = _create(
        platform, reservation_id=prepared.body["payload"]["admission"]["reservation_id"]
    )
    assert created.status == 200
    body = created.body["payload"]
    assert body["logical_name"] == other
    assert body["model_id"] == plan["model_id"]
    assert body["runtime"] == plan["runtime"]
    assert body["executor"] == plan["executor"]
    assert auto["selected_model"] not in {body["logical_name"], body["model_id"]}


def test_vllm_start_does_not_substitute_reference(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    prepared = _prepare(platform)
    created = _create(platform, reservation_id=prepared["admission"]["reservation_id"])
    body = created.body["payload"]
    started = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=body["instance_id"],
    )
    assert started.status == 200
    payload = started.body["payload"]
    assert payload["runtime"] == "vllm"
    assert payload["observed_state"] == "failed"
    stored = platform.instances.get(InstanceId.parse(body["instance_id"]))
    assert stored is not None
    assert stored.observed_state is ObservedState.FAILED
    assert stored.runtime.value == "vllm"


def test_stale_before_start_keeps_created(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    created = _create(platform, reservation_id=prepared["admission"]["reservation_id"])
    body = created.body["payload"]
    other = _other_feasible(platform, plan["selected_model"])
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    listing = _call(platform, "/inference/instances").body["payload"]
    listed = listing["instances"][0]
    assert listed["observed_state"] == "created"
    assert listed["configuration_current"] is False
    assert listed["plan_status"] == "stale"
    started = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=body["instance_id"],
    )
    assert started.status == 412
    assert started.body["error"]["context"]["reason"] == "plan_stale"
    stored = platform.instances.get(InstanceId.parse(body["instance_id"]))
    assert stored is not None
    assert stored.observed_state is ObservedState.CREATED
    assert platform.executions.list() == ()


def test_reference_lifecycle_stale_while_running_and_restart(
    tmp_path: Path,
) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    artifact = platform.inventory.get(ArtifactId.parse(prepared["artifact_id"]))
    reservation = platform.resources.get(
        ReservationId.parse(prepared["admission"]["reservation_id"])
    )
    assert artifact is not None
    assert reservation is not None
    instance = platform.instances.create(
        artifact,
        reservation,
        runtime=Name("reference-serving"),
        executor=Name("native-process"),
        plan_id=plan["plan_id"],
        plan_basis=plan["plan_basis"],
    )
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    running = platform.instances.start(
        instance.instance_id, ledger_health=platform.resources.summary(envelope).health
    )
    assert running.observed_state is ObservedState.RUNNING
    other = _other_feasible(platform, plan["selected_model"])
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    view = platform.deployment_instance.view(
        platform.instances.observe(instance.instance_id), host
    )
    assert view.instance.observed_state is ObservedState.RUNNING
    assert view.configuration_current is False
    assert view.plan_status == "stale"
    assert platform.executions.list() != ()
    stopped = platform.deployment_instance.stop(instance.instance_id, host)
    assert stopped.instance.observed_state is ObservedState.STOPPED
    refused = _call(
        platform,
        "/inference/instances/start",
        Method.POST,
        instance_id=instance.instance_id.value,
    )
    assert refused.status == 412
    assert refused.body["error"]["context"]["reason"] == "plan_stale"
    assert (
        platform.instances.observe(instance.instance_id).observed_state
        is ObservedState.STOPPED
    )


def test_reference_restart_while_plan_current(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    artifact = platform.inventory.get(ArtifactId.parse(prepared["artifact_id"]))
    reservation = platform.resources.get(
        ReservationId.parse(prepared["admission"]["reservation_id"])
    )
    assert artifact is not None
    assert reservation is not None
    instance = platform.instances.create(
        artifact,
        reservation,
        runtime=Name("reference-serving"),
        executor=Name("native-process"),
        plan_id=plan["plan_id"],
        plan_basis=plan["plan_basis"],
    )
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    health = platform.resources.summary(envelope).health
    platform.instances.start(instance.instance_id, ledger_health=health)
    platform.instances.stop(instance.instance_id)
    restarted = platform.instances.start(instance.instance_id, ledger_health=health)
    assert restarted.observed_state is ObservedState.RUNNING
    view = platform.deployment_instance.view(restarted, host)
    assert view.configuration_current is True
    platform.instances.stop(instance.instance_id)


def test_release_protection_and_one_live_instance(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    prepared = _prepare(platform)
    artifact = platform.inventory.get(ArtifactId.parse(prepared["artifact_id"]))
    reservation = platform.resources.get(
        ReservationId.parse(prepared["admission"]["reservation_id"])
    )
    assert artifact is not None
    assert reservation is not None
    first = platform.instances.create(
        artifact,
        reservation,
        runtime=Name("reference-serving"),
        plan_id=plan["plan_id"],
        plan_basis=plan["plan_basis"],
    )
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    platform.instances.start(
        first.instance_id, ledger_health=platform.resources.summary(envelope).health
    )
    blocked = _call(
        platform,
        "/resources/reservations",
        Method.DELETE,
        reservation_id=reservation.reservation_id.value,
    )
    assert blocked.status == 409
    assert blocked.body["error"]["context"]["reason"] == "reservation_in_use"
    with pytest.raises(ConflictError, match="live instance"):
        platform.instances.create(
            artifact,
            reservation,
            runtime=Name("reference-serving"),
        )
    platform.instances.stop(first.instance_id)
    released = _call(
        platform,
        "/resources/reservations",
        Method.DELETE,
        reservation_id=reservation.reservation_id.value,
    )
    assert released.status == 200


def test_isolated_launch_path_guards(tmp_path: Path) -> None:
    stack = _Stack(tmp_path)
    stack.runtimes = RuntimeCatalogue(
        (stack.runtimes.get(Name("reference-serving")), VllmRuntimeSupport())
    )
    stack.instances = InstanceService(
        stack.store,
        stack.clock,
        stack.inventory,
        stack.resources,
        stack.executions,
        stack.runtimes,
        startup_timeout=1.2,
        live_executor="native-process",
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    vllm = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    with pytest.raises(PreconditionFailedError, match="cannot launch") as launched:
        stack.instances.start(vllm.instance_id, ledger_health=stack.health())
    assert launched.value.context["reason"] == "runtime_launch_unsupported"
    assert (
        stack.instances.observe(vllm.instance_id).observed_state
        is ObservedState.CREATED
    )
    missing = stack.instances.create(
        artifact, reservation, runtime=Name("missing-runtime")
    )
    with pytest.raises(PreconditionFailedError, match="not available") as absent:
        stack.instances.start(missing.instance_id, ledger_health=stack.health())
    assert absent.value.context["reason"] == "runtime_unavailable"
    foreign = stack.instances.create(
        artifact,
        reservation,
        runtime=Name("reference-serving"),
        executor=Name("container-docker"),
    )
    with pytest.raises(PreconditionFailedError, match="executor") as executor:
        stack.instances.start(foreign.instance_id, ledger_health=stack.health())
    assert executor.value.context["reason"] == "executor_unavailable"


def test_cli_and_console_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("KULTRUN_FIXTURE", "linux-x86_64-nvidia-blackwell-rtxpro4500")
    monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
    platform = _product(tmp_path)
    prepared = _prepare(platform)
    reservation_id = prepared["admission"]["reservation_id"]
    assert main(["instances", "create", reservation_id]) == 0
    printed = capsys.readouterr().out
    assert "Plan:" in printed
    assert "Model:" in printed
    assert "Artifact:" in printed
    assert "Reservation:" in printed
    assert "Runtime:" in printed
    assert "Executor:" in printed
    assert "Instance:" in printed
    assert "CREATED" in printed
    assert "Configuration: CURRENT" in printed
    assert main(["instances"]) == 0
    listed = capsys.readouterr().out
    assert "configuration CURRENT" in listed
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Create instance" in script
    assert "configuration" in script
    assert "chat" not in script
    assert "/inference/instances/infer" in script
    assert "native vLLM" in html


def test_architecture_guards() -> None:
    names = {item.name for item in fields(InferenceInstance)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    tree = SOURCE / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in tree.rglob("*.py"))
    assert "class InferenceInstanceV2" not in text
    assert "class PlanInferenceInstance" not in text
    assert "class RuntimeInstanceV2" not in text
    instance = (SOURCE / "kultrun" / "platform" / "deployment_instance.py").read_text(
        encoding="utf-8"
    )
    assert "plan_for_entry" not in instance
    assert "plan_from" not in instance
    assert "rank_feasible" not in instance
    assert "ResourceManager.admit" not in instance
    assert ".admit(" not in instance
    assert "acquire(" not in instance
    service = (SOURCE / "kultrun" / "inference" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "plan_for_entry" not in service
    assert "plan_from" not in service
    assert "DeploymentPlan" not in service
    routes = (SOURCE / "kultrun" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "deployment_instance.create" in routes
    assert "instances.create(artifact, reservation)" not in routes
    assert (
        _imports_named(
            SOURCE / "kultrun" / "inference" / "service.py",
            "kultrun.planning",
            "kultrun.platform",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "platform" / "deployment_instance.py",
            "kultrun.planning.service",
            "kultrun.planning.evaluate",
        )
        == []
    )
    offenders = [
        edge.describe()
        for edge in scan(SOURCE)
        if edge.source_package == "inference"
        and edge.target_package in {"planning", "platform"}
    ]
    assert offenders == []
