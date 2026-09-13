"""Stage 1.6J — plan-driven acquisition and resource admission."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.api.contracts import Method
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import main
from kultrun.model.acquisition import request_from_entry
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
    ModelId,
)
from kultrun.planning.contracts import DeploymentPlan
from kultrun.platform.admission import request_from_plan
from kultrun.platform.deployment_prepare import find_plan_artifact
from kultrun.resource.contracts import RequestId, ResourceRequest, WorkloadType
from kultrun.storage.topology import mount_for_path
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_runtime_deployment_plan import _call, _product, _realize

SOURCE = Path(__file__).resolve().parent.parent / "src"
GIB = 1024**3


class _Inventory:
    def __init__(self, items: tuple[ModelArtifact, ...]) -> None:
        self._items = items

    def artifacts(self, *, include_deleted: bool = False) -> tuple[ModelArtifact, ...]:
        del include_deleted
        return self._items


def test_unresolved_plan_revision_reuses_stored_artifact() -> None:
    model_id = ModelId.generate()
    stored = ModelArtifact(
        artifact_id=ArtifactId.generate(),
        model_id=model_id,
        revision="abc123",
        source_ref="org/probe",
        quantization="awq",
        state=ArtifactState.STORED,
    )
    plan = DeploymentPlan(
        model_id=model_id,
        logical_name=Name("probe"),
        source_ref="org/probe",
        quantization="awq",
        runtime="vllm",
        executor_kind="native-process",
        placement=MemoryPlacement.DISCRETE_GPU,
        expected_ram_bytes=GIB,
        expected_vram_bytes=8 * GIB,
        expected_unified_bytes=NOT_PROVIDED,
        expected_storage_bytes=GIB,
        expected_utilization=0.4,
        estimator_provider="test",
        policy_version="test",
        rationale=("fixture",),
        source_revision=NOT_PROVIDED,
    )
    found = find_plan_artifact(_Inventory((stored,)), plan, require_revision=False)
    assert found is not None
    assert found.artifact_id == stored.artifact_id
    assert find_plan_artifact(_Inventory((stored,)), plan) is None
    wrong = replace(plan, source_revision="other-revision")
    assert find_plan_artifact(_Inventory((stored,)), wrong) is None
    matching = replace(plan, source_revision="abc123")
    assert find_plan_artifact(_Inventory((stored,)), matching) is not None
    remote = replace(stored, state=ArtifactState.REMOTE)
    assert (
        find_plan_artifact(_Inventory((remote,)), plan, require_revision=False) is None
    )


def _current_plan(platform):
    _realize(platform)
    response = _call(platform, "/deployments/plan", Method.POST)
    assert response.status == 200
    payload = response.body["payload"]
    assert payload["status"] == "current"
    return payload


def _count_admit(platform) -> dict[str, int]:
    """Count inference admissions only.

    Model acquisition and runtime provisioning also call ResourceManager.
    Those reservations are released before the plan-driven inference admit.
    """
    original = platform.resources.admit
    state = {"count": 0}

    def wrapped(*args: object, **kwargs: object) -> object:
        request = args[0] if args else kwargs.get("request")
        workload = getattr(request, "workload_type", None)
        if workload not in {
            WorkloadType.RUNTIME_PROVISIONING,
            WorkloadType.MODEL_ACQUISITION,
        }:
            state["count"] += 1
        return original(*args, **kwargs)

    platform.resources.admit = wrapped  # type: ignore[method-assign]
    return state


def test_current_plan_acquire_reuses_and_does_not_admit(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    counted = _count_admit(platform)
    first = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert first.status == 200
    body = first.body["payload"]
    assert body["plan_status"] == "current"
    assert body["selected_model"] == plan["selected_model"]
    assert body["acquisition"]["reused"] is False
    assert body["admit"] is False
    assert body["launch"] is False
    assert body["instance"] is False
    artifact_id = body["artifact_id"]
    assert counted["count"] == 0
    assert platform.resources.reservations() == ()
    assert platform.instances.list() == ()
    second = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert second.status == 200
    reused = second.body["payload"]
    assert reused["acquisition"]["reused"] is True
    assert reused["artifact_id"] == artifact_id
    stored = [
        item
        for item in platform.inventory.artifacts()
        if item.artifact_id.value == artifact_id
    ]
    assert len(stored) == 1
    assert counted["count"] == 0
    assert platform.resources.reservations() == ()


def test_unavailable_acquire_refused_until_a_plan_can_be_drafted(
    tmp_path: Path,
) -> None:
    platform = _product(tmp_path)
    unread = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert unread.status == 412
    error = unread.body["error"]
    assert error["code"] == "precondition_failed"
    assert error["context"]["reason"] == "plan_unavailable"
    assert platform.inventory.artifacts() == ()
    assert platform.resources.reservations() == ()


def test_acquire_refreshes_stale_plan_after_model_change(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    created = _current_plan(platform)
    recommended = created["selected_model"]
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != recommended
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    viewed = _call(platform, "/deployments/plan").body["payload"]
    assert viewed["status"] == "stale"
    assert viewed["mutations"] is False
    assert viewed["selected_model"] == recommended
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert acquired.status == 200
    payload = acquired.body["payload"]
    assert payload["selected_model"] == other
    later = _call(platform, "/deployments/plan").body["payload"]
    assert later["status"] == "current"
    assert later["selected_model"] == other
    artifact = platform.inventory.get(ArtifactId.parse(payload["artifact_id"]))
    assert artifact is not None
    name = artifact.logical_name if is_resolved(artifact.logical_name) else ""
    assert name == other


def test_prepare_computes_fresh_plan_without_explicit_refresh(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    selected = _call(platform, "/models/selection", Method.POST, mode="auto")
    assert selected.status == 200
    viewed = _call(platform, "/deployments/plan").body["payload"]
    assert viewed["status"] == "unavailable"
    assert viewed["mutations"] is False
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert prepared.status == 200
    payload = prepared.body["payload"]
    assert payload["plan_status"] == "current"
    assert payload["admission"]["verdict"] == "admitted"
    later = _call(platform, "/deployments/plan").body["payload"]
    assert later["status"] == "current"
    assert later["selected_model"] == payload["selected_model"]
    assert later["mutations"] is False


def test_wrong_revision_and_quantization_not_reused(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    entry = platform.models.acquirable(plan["selected_model"])
    assert entry is not None
    wrong_revision = replace(request_from_entry(entry), requested_revision="other-rev")
    platform.acquisition.acquire(
        wrong_revision,
        envelope,
        host.host_id,
        destination_mount=mount_for_path(platform.plane.state_root / "models", host),
    )
    base = request_from_entry(entry)
    wrong_quant = replace(
        base,
        requested_revision="fixture-rev-quant",
        quantization="fp16",
    )
    platform.acquisition.acquire(
        wrong_quant,
        envelope,
        host.host_id,
        destination_mount=mount_for_path(platform.plane.state_root / "models", host),
    )
    counted = _count_admit(platform)
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert acquired.status == 200
    payload = acquired.body["payload"]
    artifact = platform.inventory.get(ArtifactId.parse(payload["artifact_id"]))
    assert artifact is not None
    assert artifact.revision != "other-rev"
    assert artifact.revision != "fixture-rev-quant"
    if is_resolved(artifact.quantization) and plan["quantization"]:
        assert artifact.quantization == plan["quantization"]
    assert payload["acquisition"]["reused"] is False
    assert counted["count"] == 0
    identities = {
        (item.revision, item.quantization)
        for item in platform.inventory.artifacts()
        if item.model_id == artifact.model_id
    }
    assert len(identities) >= 2


def test_manual_selected_model_not_recommendation(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    auto = _current_plan(platform)
    recommended = auto["selected_model"]
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != recommended
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    refreshed = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert refreshed["selected_model"] == other
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert acquired.status == 200
    payload = acquired.body["payload"]
    assert payload["selected_model"] == other
    assert payload["selected_model"] != recommended
    artifact = platform.inventory.get(ArtifactId.parse(payload["artifact_id"]))
    assert artifact is not None
    name = artifact.logical_name if is_resolved(artifact.logical_name) else ""
    assert name == other


def test_store_only_independent_of_plan(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != plan["selected_model"]
    )
    counted = _count_admit(platform)
    stored = _call(platform, "/models/acquire", Method.POST, candidate=other)
    assert stored.status == 200
    receipt = stored.body["payload"]
    assert receipt["reused"] is False
    assert counted["count"] == 0
    later = _call(platform, "/deployments/plan").body["payload"]
    assert later["status"] == "current"
    assert later["selected_model"] == plan["selected_model"]
    assert later["plan_id"] == plan["plan_id"]
    assert platform.resources.reservations() == ()
    names = {
        item.logical_name
        for item in platform.inventory.artifacts()
        if is_resolved(item.logical_name)
    }
    assert other in names


def test_plan_derived_request_and_prepare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    import kultrun.platform.admission as admission_mod

    def boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("plan_for_entry must not supply plan-driven amounts")

    monkeypatch.setattr(admission_mod, "plan_for_entry", boom)
    counted = _count_admit(platform)
    prepared = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert prepared.status == 200
    payload = prepared.body["payload"]
    assert payload["plan_status"] == "current"
    assert payload["acquisition"]["reused"] is False
    assert payload["admission"]["verdict"] == "admitted"
    assert payload["admission"]["reservation_id"]
    assert payload["launch"] is False
    assert payload["instance"] is False
    request = payload["request"]
    spec = plan["resource_request"]
    assert request["ram_bytes"] == spec["ram_bytes"]
    assert request["accelerator_bytes"] == spec["accelerator_bytes"]
    assert request["artifact_id"] == payload["artifact_id"]
    assert request["plan_fingerprint"] == plan["plan_basis"]
    assert spec["artifact_id"] is None
    assert spec["submitted"] is False
    assert counted["count"] == 1
    assert len(platform.resources.reservations()) == 1
    assert platform.instances.list() == ()
    again = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert again.status == 200
    second = again.body["payload"]
    assert second["acquisition"]["reused"] is True
    assert second["artifact_id"] == payload["artifact_id"]
    assert second["admission"]["verdict"] == "admitted"
    assert second["admission"]["reused"] is True
    assert (
        second["admission"]["reservation_id"] == payload["admission"]["reservation_id"]
    )
    assert len(platform.resources.reservations()) == 1
    assert platform.instances.list() == ()


def test_stale_between_acquire_and_admit(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert acquired.status == 200
    artifact_id = acquired.body["payload"]["artifact_id"]
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != plan["selected_model"]
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    viewed = _call(platform, "/deployments/plan").body["payload"]
    assert viewed["status"] == "stale"
    counted = _count_admit(platform)
    refused = _call(platform, "/deployments/plan/admit", Method.POST)
    assert refused.status == 412
    assert refused.body["error"]["context"]["reason"] == "artifact_missing"
    assert counted["count"] == 0
    assert platform.resources.reservations() == ()
    assert platform.inventory.get(ArtifactId.parse(artifact_id)) is not None
    assert platform.instances.list() == ()
    later = _call(platform, "/deployments/plan").body["payload"]
    assert later["status"] == "current"
    assert later["selected_model"] == other


def test_mismatched_artifact_refused_before_manager(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != plan["selected_model"]
    )
    stored = _call(platform, "/models/acquire", Method.POST, candidate=other)
    other_id = stored.body["payload"]["artifact_id"]
    counted = _count_admit(platform)
    refused = _call(
        platform,
        "/deployments/plan/admit",
        Method.POST,
        artifact_id=other_id,
    )
    assert refused.status == 412
    assert refused.body["error"]["context"]["reason"] == "artifact_plan_mismatch"
    assert counted["count"] == 0
    assert platform.resources.reservations() == ()


def test_admission_failure_no_fallback(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    plan = _current_plan(platform)
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    assert acquired.status == 200
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != plan["selected_model"]
    )
    stored = _call(platform, "/models/acquire", Method.POST, candidate=other)
    other_id = stored.body["payload"]["artifact_id"]
    artifact = platform.inventory.get(ArtifactId.parse(other_id))
    assert artifact is not None
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    summary = platform.resources.summary(envelope)
    available = summary.accelerators[0].available_bytes
    assert isinstance(available, int)
    assert available > 0
    competing = ResourceRequest(
        request_id=RequestId.generate(),
        host_id=envelope.host_id,
        artifact_id=artifact.artifact_id,
        model_id=artifact.model_id,
        plan_fingerprint="contention",
        placement=MemoryPlacement.DISCRETE_GPU,
        ram_bytes=1 * GIB,
        accelerator_bytes=available,
        unified_bytes=NOT_PROVIDED,
        accelerator_index=0,
        incremental_storage_bytes=NOT_PROVIDED,
        workload_type=WorkloadType.INFERENCE,
    )
    decision = platform.resources.admit(competing, envelope, artifact)
    assert decision.verdict.value == "admitted"
    viewed = _call(platform, "/deployments/plan").body["payload"]
    assert viewed["status"] == "stale"
    assert viewed["mutations"] is False
    admitted = _call(platform, "/deployments/plan/admit", Method.POST)
    later = _call(platform, "/deployments/plan").body["payload"]
    assert later["selected_model"] == plan["selected_model"]
    assert later["runtime"] == plan["runtime"]
    assert later["mutations"] is False
    if admitted.status == 412:
        assert admitted.body["error"]["context"]["reason"] == "plan_stale"
        assert later["status"] == "stale"
    else:
        assert admitted.status == 200
        payload = admitted.body["payload"]
        assert payload["admission"]["verdict"] == "rejected"
        assert payload["admission"]["reason_code"] == "insufficient_safe_accelerator"
        assert later["status"] == "current"
    assert platform.instances.list() == ()
    plan_reservations = [
        item
        for item in platform.resources.reservations()
        if is_resolved(item.logical_name)
        and item.logical_name == plan["selected_model"]
    ]
    assert plan_reservations == []


def test_small_large_small_and_full_chain(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _current_plan(platform)
    selection = _call(platform, "/models/selection").body["payload"]
    requirements = _call(platform, "/models/requirements").body["payload"]
    feasible = {item["logical_name"] for item in selection["feasible"]}
    sized = [
        row
        for row in requirements["assessments"]
        if row["logical_name"] in feasible
        and isinstance(row["required_vram_bytes"], int)
    ]
    sized.sort(key=lambda row: row["required_vram_bytes"])
    assert len(sized) >= 2
    small = sized[0]["logical_name"]
    large = sized[-1]["logical_name"]
    _call(platform, "/models/selection", Method.POST, mode="manual", model=small)
    small_plan = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert small_plan["selected_model"] == small
    first = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert first.status == 200
    first_body = first.body["payload"]
    assert first_body["admission"]["verdict"] == "admitted"
    small_ram = first_body["request"]["ram_bytes"]
    _call(
        platform,
        "/resources/reservations",
        Method.DELETE,
        reservation_id=first_body["admission"]["reservation_id"],
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=large)
    large_plan = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert large_plan["selected_model"] == large
    second = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert second.status == 200
    second_body = second.body["payload"]
    assert second_body["admission"]["verdict"] == "admitted"
    assert (
        second_body["request"]["ram_bytes"]
        == large_plan["resource_request"]["ram_bytes"]
    )
    _call(
        platform,
        "/resources/reservations",
        Method.DELETE,
        reservation_id=second_body["admission"]["reservation_id"],
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=small)
    again_plan = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert again_plan["selected_model"] == small
    third = _call(platform, "/deployments/plan/prepare", Method.POST)
    assert third.status == 200
    third_body = third.body["payload"]
    assert third_body["admission"]["verdict"] == "admitted"
    assert third_body["request"]["ram_bytes"] == small_ram
    assert platform.instances.list() == ()


def test_request_from_plan_is_deterministic(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _current_plan(platform)
    acquired = _call(platform, "/deployments/plan/acquire", Method.POST)
    artifact = platform.inventory.get(
        ArtifactId.parse(acquired.body["payload"]["artifact_id"])
    )
    assert artifact is not None
    stored = platform.deployment_plan.stored(platform.hosts.current)
    assert stored is not None
    envelope = platform.capacity.compute(platform.hosts.current, {})
    first = request_from_plan(stored, artifact, envelope)
    second = request_from_plan(stored, artifact, envelope)
    assert first.request_id == second.request_id
    assert first.ram_bytes == stored.expected_ram_bytes
    assert first.artifact_id == artifact.artifact_id
    assert first.plan_fingerprint == stored.plan_basis


def test_cli_and_console_prepare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = _product(tmp_path)
    _current_plan(platform)
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
    monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
    monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
    assert main(["deployments", "prepare"]) == 0
    printed = capsys.readouterr().out
    assert "Plan: CURRENT" in printed
    assert "Artifact:" in printed
    assert "Admission: ADMITTED" in printed
    assert "Reservation ID:" in printed
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Prepare deployment" in script
    assert "/deployments/plan/prepare" in script
    assert "Select Model" not in script
    assert "Start Model" not in script
    assert "Deployment plan" in html


def test_architecture_guards() -> None:
    names = {item.name for item in fields(DeploymentPlan)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    tree = SOURCE / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in tree.rglob("*.py"))
    assert "class PlanAcquisitionServiceV2" not in text
    assert "class PlanResourceRequestV2" not in text
    assert "class DeploymentController" not in text
    prepare = (SOURCE / "kultrun" / "platform" / "deployment_prepare.py").read_text(
        encoding="utf-8"
    )
    assert "rank_feasible" not in prepare
    assert "plan_for_entry" not in prepare
    assert "plan_from" not in prepare
    assert "InstanceService" not in prepare
    assert "ModelSelectionService" not in prepare
    assert (
        _imports_named(
            SOURCE / "kultrun" / "platform" / "deployment_prepare.py",
            "kultrun.resource.manager",
            "kultrun.inference",
            "kultrun.planning.service",
            "kultrun.planning.evaluate",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "resource" / "manager.py",
            "kultrun.planning",
            "kultrun.platform",
            "kultrun.runtime",
            "kultrun.inference",
        )
        == []
    )
    offenders = [
        edge.describe()
        for edge in scan(SOURCE)
        if edge.source_package == "resource" and edge.target_package == "planning"
    ]
    assert offenders == []
