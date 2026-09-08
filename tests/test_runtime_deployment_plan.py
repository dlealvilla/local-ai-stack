"""Stage 1.6I — authoritative DeploymentPlan. Decision, not execution."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.host import fixtures
from kultrun.adapters.model_source.candidates import acceptance_candidate
from kultrun.adapters.model_source.huggingface import HuggingFaceSource
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.api.contracts import ApiRequest, Method
from kultrun.capacity.envelope import CapacityService
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, config_schema, main
from kultrun.model.catalogue import ModelCatalogue
from kultrun.planning.contracts import (
    DeploymentPlan,
    DeploymentPlanStatus,
    ModelSelectionMode,
    ModelSelectionStatus,
    SelectionPolicy,
)
from kultrun.planning.service import SelectionService, plan_from
from kultrun.platform.deployment_plan import (
    DeploymentPlanLock,
    DeploymentPlanningService,
    plan_basis,
)
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.model_selection import ModelSelectionLock, ModelSelectionService
from kultrun.platform.requirement import assess_catalog
from kultrun.runtime.contracts import (
    EligibleViewStatus,
    FoundationSelectionId,
    RuntimePolicy,
)
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_runtime_model_eligibility import _verified

SOURCE = Path(__file__).resolve().parent.parent / "src"
GIB = 1024**3


def _catalog() -> ModelCatalogue:
    return ModelCatalogue(HuggingFaceSource(), extras=(acceptance_candidate(),))


def _ready(tmp_path: Path):
    models = _catalog()
    eligibility, foundation, host, native, descriptors = _verified(tmp_path)
    view = eligibility.evaluate(
        host,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    envelope = CapacityService().compute(host, {})
    return host, models, view, envelope, foundation, eligibility, native, descriptors


def _selection(tmp_path: Path, models: ModelCatalogue) -> ModelSelectionService:
    return ModelSelectionService(
        FileStore(tmp_path / "records"),
        FixedClock(now_utc()),
        SelectionService(KultrunRequirementEstimator(), FixedClock(now_utc())),
        models,
        ModelSelectionLock(tmp_path / "locks"),
    )


def _rows(models, view, envelope):
    return assess_catalog(
        view, models, envelope, KultrunRequirementEstimator(), SelectionPolicy()
    )


def _plans(tmp_path: Path) -> DeploymentPlanningService:
    return DeploymentPlanningService(
        FileStore(tmp_path / "records"),
        FixedClock(now_utc()),
        DeploymentPlanLock(tmp_path / "locks"),
        "native-process",
        SelectionPolicy().policy_version,
    )


def _product(tmp_path: Path):
    return build(
        config_schema().load({"platform": {"state_root": str(tmp_path / "state")}}),
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
        runtime_provisioner="fixture",
        runtime_verifier="fixture",
    )


def _realize(platform) -> None:
    assert (
        platform.router.handle(
            ApiRequest(
                method=Method.POST,
                path="/v1/runtimes/foundation/select",
                query={"mode": "auto"},
            )
        ).status
        == 200
    )
    assert (
        platform.router.handle(
            ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/realize")
        ).status
        == 200
    )
    assert (
        platform.router.handle(
            ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/verify")
        ).status
        == 200
    )


def _call(platform, path: str, method: Method = Method.GET, **query: str):
    return platform.router.handle(
        ApiRequest(method=method, path=f"/v1{path}", query=query)
    )


def _chain(tmp_path: Path):
    host, models, view, envelope, foundation, *_rest = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    selection = _selection(tmp_path, models).select_auto(host, view, envelope, rows)
    stored = foundation.stored(host)
    assert stored is not None
    return host, view, envelope, rows, selection, stored, _plans(tmp_path)


def test_current_plan_from_verified_selection(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    overview = service.refresh(host, view, envelope, rows, selection, stored)
    assert overview.status is DeploymentPlanStatus.CURRENT
    assert overview.plan is not None
    assert is_resolved(overview.plan.plan_id)
    assert overview.plan.logical_name.value == selection.selection.selected_logical_name
    assert overview.plan.capacity_verdict == "feasible"
    payload = overview.payload()
    assert payload["authoritative"] is True
    request = payload["resource_request"]
    assert isinstance(request, dict)
    assert request["submitted"] is False
    assert request["artifact_id"] is None
    assert payload["acquire"] is False
    assert payload["admit"] is False
    assert payload["launch"] is False


def test_manual_uses_selected_not_recommendation(tmp_path: Path) -> None:
    host, models, view, envelope, foundation, *_rest = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    selector = _selection(tmp_path, models)
    auto = selector.select_auto(host, view, envelope, rows)
    recommended = auto.selection.recommended_logical_name
    other = next(
        item.logical_name for item in auto.feasible if item.logical_name != recommended
    )
    manual = selector.select_manual(other, host, view, envelope, rows)
    overview = _plans(tmp_path).refresh(
        host, view, envelope, rows, manual, foundation.stored(host)
    )
    assert overview.status is DeploymentPlanStatus.CURRENT
    assert overview.plan is not None
    assert overview.plan.logical_name.value == other
    assert overview.plan.model_selection_mode == ModelSelectionMode.MANUAL.value
    assert overview.plan.recommended_model_id == auto.selection.recommended_model_id


def test_auto_uses_recommendation(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    overview = service.refresh(host, view, envelope, rows, selection, stored)
    assert overview.plan is not None
    assert (
        overview.plan.logical_name.value == selection.selection.recommended_logical_name
    )
    assert overview.plan.model_selection_mode == ModelSelectionMode.AUTO.value


def test_invalid_selection_is_unavailable(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    service.refresh(host, view, envelope, rows, selection, stored)
    broken = replace(selection, status=ModelSelectionStatus.INVALID)
    later = service.view(host, view, envelope, rows, broken, stored)
    assert later.status is not DeploymentPlanStatus.CURRENT
    refreshed = service.refresh(host, view, envelope, rows, broken, stored)
    assert refreshed.status is not DeploymentPlanStatus.CURRENT


def test_stale_runtime_makes_plan_stale(tmp_path: Path) -> None:
    host, models, view, envelope, foundation, eligibility, native, descriptors = _ready(
        tmp_path
    )
    rows = _rows(models, view, envelope)
    selection = _selection(tmp_path, models).select_auto(host, view, envelope, rows)
    service = _plans(tmp_path)
    stored = foundation.stored(host)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    assert first.status is DeploymentPlanStatus.CURRENT
    accelerator = replace(host.accelerators[0], driver_version="changed-driver")
    shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
    stale = eligibility.evaluate(
        shifted,
        (native,),
        descriptors,
        catalog_facts(models),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    assert stale.status is EligibleViewStatus.STALE
    later = service.view(
        host, stale, envelope, _rows(models, stale, envelope), selection, stored
    )
    assert later.status is DeploymentPlanStatus.STALE
    assert later.plan is not None
    assert first.plan is not None
    assert later.plan.plan_id == first.plan.plan_id


def test_foundation_change_makes_plan_stale(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    other = replace(stored, selection_id=FoundationSelectionId("fsel_" + "ab" * 8))
    later = service.view(host, view, envelope, rows, selection, other)
    assert later.status is DeploymentPlanStatus.STALE
    assert later.plan is not None
    assert later.current_basis != later.plan.plan_basis
    assert first.plan is not None


def test_selected_model_change_makes_plan_stale(tmp_path: Path) -> None:
    host, models, view, envelope, foundation, *_rest = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    selector = _selection(tmp_path, models)
    auto = selector.select_auto(host, view, envelope, rows)
    stored = foundation.stored(host)
    service = _plans(tmp_path)
    first = service.refresh(host, view, envelope, rows, auto, stored)
    recommended = auto.selection.recommended_logical_name
    other = next(
        item.logical_name for item in auto.feasible if item.logical_name != recommended
    )
    manual = selector.select_manual(other, host, view, envelope, rows)
    later = service.view(host, view, envelope, rows, manual, stored)
    assert later.status is DeploymentPlanStatus.STALE
    assert later.plan is not None
    assert later.plan.logical_name.value == auto.selection.selected_logical_name
    refreshed = service.refresh(host, view, envelope, rows, manual, stored)
    assert refreshed.status is DeploymentPlanStatus.CURRENT
    assert refreshed.plan is not None
    assert refreshed.plan.logical_name.value == other
    assert first.plan is not None
    assert refreshed.plan.generation == first.plan.generation + 1


def test_requirement_basis_change_makes_plan_stale(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    selected = selection.selection.selected_model_id
    shifted = tuple(
        replace(item, basis="changed-requirement")
        if item.model_id == selected
        else item
        for item in rows
    )
    later = service.view(host, view, envelope, shifted, selection, stored)
    assert later.status is DeploymentPlanStatus.STALE
    assert first.plan is not None


def test_capacity_basis_change_makes_plan_stale(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    shifted = replace(envelope, host_fingerprint="changed-capacity")
    later = service.view(host, view, shifted, rows, selection, stored)
    assert later.status is DeploymentPlanStatus.STALE
    assert first.plan is not None


def test_infeasible_selected_model_has_no_current_plan(tmp_path: Path) -> None:
    host, models, view, envelope, foundation, *_rest = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    selector = _selection(tmp_path, models)
    auto = selector.select_auto(host, view, envelope, rows)
    recommended = auto.selection.recommended_logical_name
    other = next(
        item.logical_name for item in auto.feasible if item.logical_name != recommended
    )
    manual = selector.select_manual(other, host, view, envelope, rows)
    stored = foundation.stored(host)
    service = _plans(tmp_path)
    first = service.refresh(host, view, envelope, rows, manual, stored)
    assert first.status is DeploymentPlanStatus.CURRENT
    tiny = replace(host.accelerators[0], memory_total_bytes=2 * GIB)
    poor = CapacityService().compute(replace(host, accelerators=(tiny,)), {})
    later_rows = _rows(models, view, poor)
    later_selection = selector.view(host, view, poor, later_rows)
    later = service.refresh(host, view, poor, later_rows, later_selection, stored)
    assert later.status is not DeploymentPlanStatus.CURRENT
    if later.plan is not None:
        assert later.plan.logical_name.value == other


def test_revision_change_makes_plan_stale(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    changed = replace(
        selection,
        selection=replace(
            selection.selection, selected_source_revision="rev-changed-0001"
        ),
    )
    later = service.view(host, view, envelope, rows, changed, stored)
    assert later.status is DeploymentPlanStatus.STALE
    assert first.plan is not None


def test_same_basis_is_deterministic(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    first = service.refresh(host, view, envelope, rows, selection, stored)
    second = service.refresh(host, view, envelope, rows, selection, stored)
    assert first.plan is not None
    assert second.plan is not None
    assert first.plan.plan_basis == second.plan.plan_basis
    assert first.plan.plan_id == second.plan.plan_id
    selected = next(
        item for item in rows if item.model_id == selection.selection.selected_model_id
    )
    assert (
        plan_basis(
            view,
            envelope,
            selection,
            selected,
            foundation_selection_id=stored.selection_id.value,
            executor_identity="native-process",
            policy_version=SelectionPolicy().policy_version,
        )
        == first.plan.plan_basis
    )


def test_view_does_not_persist(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    empty = service.view(host, view, envelope, rows, selection, stored)
    assert empty.status is DeploymentPlanStatus.UNAVAILABLE
    assert empty.plan is None
    assert empty.refreshable is True
    still = service.view(host, view, envelope, rows, selection, stored)
    assert still.plan is None
    assert service.stored(host) is None


def test_get_does_not_mutate_product(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    first = _call(platform, "/deployments/plan")
    assert first.status == 200
    payload = first.body["payload"]
    assert payload["status"] == "unavailable"
    assert payload["mutations"] is False
    second = _call(platform, "/deployments/plan")
    assert second.body["payload"]["status"] == "unavailable"
    assert platform.inventory.artifacts() == ()
    assert platform.resources.reservations() == ()
    assert platform.instances.list() == ()


def test_refresh_performs_no_execution(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    created = _call(platform, "/deployments/plan", Method.POST)
    assert created.status == 200
    payload = created.body["payload"]
    assert payload["status"] == "current"
    assert payload["mutations"] is True
    assert payload["acquire"] is False
    assert payload["admit"] is False
    assert payload["launch"] is False
    request = payload["resource_request"]
    assert isinstance(request, dict)
    assert request["submitted"] is False
    assert platform.inventory.artifacts() == ()
    assert platform.resources.reservations() == ()
    assert platform.instances.list() == ()


def test_product_auto_and_manual_and_restart(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    auto = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert auto["status"] == "current"
    assert auto["model_selection_mode"] == "auto"
    recommended = auto["selected_model"]
    selection = _call(platform, "/models/selection").body["payload"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != recommended
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    stale = _call(platform, "/deployments/plan").body["payload"]
    assert stale["status"] == "stale"
    assert stale["selected_model"] == recommended
    refreshed = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert refreshed["status"] == "current"
    assert refreshed["selected_model"] == other
    assert refreshed["model_selection_mode"] == "manual"
    later_selection = _call(platform, "/models/selection").body["payload"]
    assert later_selection["recommended"] == recommended
    assert later_selection["plan_authoritative"] is False
    restarted = _product(tmp_path)
    again = _call(restarted, "/deployments/plan").body["payload"]
    assert again["status"] == "current"
    assert again["selected_model"] == other
    assert again["plan_id"] == refreshed["plan_id"]


def test_product_capacity_and_auto_transition(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    selection = _call(platform, "/models/selection").body["payload"]
    recommended = selection["recommended"]
    other = next(
        item["logical_name"]
        for item in selection["feasible"]
        if item["logical_name"] != recommended
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    first = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert first["selected_model"] == other
    _call(platform, "/models/selection", Method.POST, mode="auto")
    stale = _call(platform, "/deployments/plan").body["payload"]
    assert stale["status"] == "stale"
    restored = _call(platform, "/deployments/plan", Method.POST).body["payload"]
    assert restored["status"] == "current"
    assert restored["selected_model"] == recommended
    assert restored["model_selection_mode"] == "auto"


def test_plan_from_is_not_authoritative(tmp_path: Path) -> None:
    host, view, envelope, rows, selection, stored, service = _chain(tmp_path)
    overview = service.refresh(host, view, envelope, rows, selection, stored)
    projected = plan_from(selection.recommendation)
    assert projected is not None
    assert not is_resolved(projected.plan_id)
    assert overview.plan is not None
    assert is_resolved(overview.plan.plan_id)
    platform = _product(tmp_path)
    _realize(platform)
    payload = _call(platform, "/models/selection").body["payload"]
    assert payload["plan_authoritative"] is False
    assert payload["deployment_plan_route"] == "/v1/deployments/plan"


def test_cli_and_console_surfaces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
    monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
    assert main(["deployments", "plan"]) == 0
    unread = capsys.readouterr().out
    assert "UNAVAILABLE" in unread
    assert main(["deployments", "plan", "--refresh"]) == 0
    printed = capsys.readouterr().out
    assert "CURRENT" in printed
    assert "Runtime:" in printed
    assert "Model:" in printed
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Refresh plan" in script
    assert "/deployments/plan" in script
    assert "Deployment plan" in html
    assert "Select Model" not in script


def test_architecture_guards() -> None:
    names = {item.name for item in fields(DeploymentPlan)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    tree = SOURCE / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in tree.rglob("*.py"))
    assert "class DeploymentPlanV2" not in text
    assert "class ExecutionPlan" not in text
    assert "class ServingPlan" not in text
    assert "class GenericPlanFramework" not in text
    assert "class PlannerFramework" not in text
    service = (SOURCE / "kultrun" / "platform" / "deployment_plan.py").read_text(
        encoding="utf-8"
    )
    assert "rank_feasible" not in service
    assert "SelectionService" not in service
    assert "ModelEligibilityService" not in service
    assert "AcquisitionService" not in service
    assert "InstanceService" not in service
    assert (
        _imports_named(
            SOURCE / "kultrun" / "platform" / "deployment_plan.py",
            "kultrun.resource",
            "kultrun.inference",
            "kultrun.model.acquisition",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "planning" / "service.py",
            "kultrun.runtime",
            "kultrun.resource",
            "kultrun.inference",
        )
        == []
    )
    offenders = [
        edge.describe()
        for edge in scan(SOURCE)
        if edge.source_package == "planning" and edge.target_package == "runtime"
    ]
    assert offenders == []
    routes = (SOURCE / "kultrun" / "api" / "routes.py").read_text(encoding="utf-8")
    plan_block = routes.split("def deployments_plan")[1].split(
        "def models_requirements"
    )[0]
    assert "plane.resources." not in plan_block
    assert "plane.instances." not in plan_block
    assert "plane.acquisition." not in plan_block
