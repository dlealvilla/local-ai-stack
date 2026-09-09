"""Stage 1.6H — ModelSelector consumes feasible candidates; bounded AUTO|MANUAL."""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path

import pytest

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.host import fixtures
from kultrun.adapters.model_source.candidates import (
    acceptance_candidate,
    packaged_candidates,
)
from kultrun.adapters.model_source.huggingface import HuggingFaceSource
from kultrun.adapters.persistence.file_store import FileStore
from kultrun.api.contracts import ApiRequest, Method
from kultrun.capacity.envelope import CapacityService
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.main import build, config_schema, main
from kultrun.model.catalogue import ModelCatalogue
from kultrun.planning.contracts import (
    FeasibleModelCandidate,
    ModelSelection,
    ModelSelectionMode,
    ModelSelectionStatus,
    SelectionPolicy,
)
from kultrun.planning.service import SelectionService
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.model_selection import ModelSelectionLock, ModelSelectionService
from kultrun.platform.requirement import (
    assess_catalog,
    feasible_candidates,
    recommend_from_view,
)
from kultrun.runtime.contracts import EligibleViewStatus, RuntimePolicy
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_runtime_model_eligibility import _verified

SOURCE = Path(__file__).resolve().parent.parent / "src"
GIB = 1024**3
SMALL = "qwen2.5-0.5b-instruct-awq"
SEVEN = "qwen2.5-7b-instruct-awq"
LARGE = "qwen2.5-72b-instruct-awq"
BLOCKED = "tinyllama-1.1b-chat-q4"
UNRESOLVED = "kultrun-hf-acceptance-tiny"


def _catalog() -> ModelCatalogue:
    return ModelCatalogue(HuggingFaceSource(), extras=(acceptance_candidate(),))


def _named(models: ModelCatalogue, logical: str):
    entry = models.acquirable(logical)
    assert entry is not None
    return entry


def _ready(tmp_path: Path):
    models = _catalog()
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    view = eligibility.evaluate(
        host,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    envelope = CapacityService().compute(host, {})
    return host, models, view, envelope


def _service(tmp_path: Path, models: ModelCatalogue) -> ModelSelectionService:
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


def _names(items: tuple[FeasibleModelCandidate, ...]) -> set[str]:
    return {item.logical_name for item in items}


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


def test_eligible_feasible_enters_set(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    names = _names(feasible_candidates(_rows(models, view, envelope)))
    assert SMALL in names
    assert SEVEN in names


def test_eligible_infeasible_does_not_enter(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    names = _names(feasible_candidates(_rows(models, view, envelope)))
    assert LARGE not in names


def test_blocked_does_not_enter(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    names = _names(feasible_candidates(_rows(models, view, envelope)))
    assert BLOCKED not in names


def test_unresolved_does_not_enter(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    names = _names(feasible_candidates(_rows(models, view, envelope)))
    assert UNRESOLVED not in names


def test_stale_capacity_does_not_enter(tmp_path: Path) -> None:
    host, models, view, _ = _ready(tmp_path)
    poor = CapacityService().compute(
        replace(
            host,
            accelerators=(
                replace(host.accelerators[0], memory_total_bytes=2 * GIB),
            ),
        ),
        {},
    )
    names = _names(feasible_candidates(_rows(models, view, poor)))
    assert SEVEN not in names
    assert LARGE not in names


def test_stale_requirement_does_not_enter(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    models = _catalog()
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
    envelope = CapacityService().compute(host, {})
    names = _names(feasible_candidates(_rows(models, stale, envelope)))
    assert names == set()


def test_deterministic_recommendation(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    left = recommend_from_view(
        SelectionService(KultrunRequirementEstimator(), FixedClock(now_utc())),
        envelope,
        rows,
    )
    right = recommend_from_view(
        SelectionService(KultrunRequirementEstimator(), FixedClock(now_utc())),
        envelope,
        rows,
    )
    assert left.primary is not None
    assert right.primary is not None
    assert left.primary.model_id == right.primary.model_id
    assert left.outcome == right.outcome


def test_ranking_sees_only_feasible_candidates(tmp_path: Path) -> None:
    _, models, view, envelope = _ready(tmp_path)
    rows = _rows(models, view, envelope)
    recommendation = recommend_from_view(
        SelectionService(KultrunRequirementEstimator(), FixedClock(now_utc())),
        envelope,
        rows,
    )
    names = {item.logical_name.value for item in recommendation.evaluations}
    assert BLOCKED not in names
    assert LARGE not in names
    assert UNRESOLVED not in names
    assert SMALL in names or SEVEN in names


def test_auto_selected_equals_recommendation(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    overview = service.select_auto(host, view, envelope, _rows(models, view, envelope))
    assert overview.selection.selection_mode is ModelSelectionMode.AUTO
    assert overview.status is ModelSelectionStatus.CURRENT
    assert (
        overview.selection.selected_model_id == overview.selection.recommended_model_id
    )


def test_manual_valid_alternative_preserves_recommendation(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    auto = service.select_auto(host, view, envelope, rows)
    recommended = auto.selection.recommended_logical_name
    other = next(
        item.logical_name for item in auto.feasible if item.logical_name != recommended
    )
    manual = service.select_manual(other, host, view, envelope, rows)
    assert manual.selection.selection_mode is ModelSelectionMode.MANUAL
    assert manual.selection.selected_logical_name == other
    assert manual.selection.recommended_logical_name == recommended
    assert recommended != other


def test_invalid_manual_blocked_refused(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    with pytest.raises(PreconditionFailedError) as raised:
        service.select_manual(BLOCKED, host, view, envelope, rows)
    assert raised.value.context["reason"] == "model_not_eligible"


def test_invalid_manual_infeasible_refused(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    with pytest.raises(PreconditionFailedError) as raised:
        service.select_manual(LARGE, host, view, envelope, rows)
    assert raised.value.context["reason"] == "model_infeasible"


def test_invalid_manual_unresolved_refused(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    with pytest.raises(PreconditionFailedError) as raised:
        service.select_manual(UNRESOLVED, host, view, envelope, rows)
    assert raised.value.context["reason"] == "model_requirement_unresolved"


def test_return_to_auto(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    auto = service.select_auto(host, view, envelope, rows)
    recommended = auto.selection.recommended_logical_name
    other = next(
        item.logical_name for item in auto.feasible if item.logical_name != recommended
    )
    service.select_manual(other, host, view, envelope, rows)
    back = service.select_auto(host, view, envelope, rows)
    assert back.selection.selection_mode is ModelSelectionMode.AUTO
    assert back.selection.selected_logical_name == recommended


def test_capacity_change_invalidates_manual_without_fallback(
    tmp_path: Path,
) -> None:
    host, models, view, envelope = _ready(tmp_path)
    service = _service(tmp_path, models)
    rows = _rows(models, view, envelope)
    service.select_manual(SEVEN, host, view, envelope, rows)
    tiny = replace(host.accelerators[0], memory_total_bytes=2 * GIB)
    poor = CapacityService().compute(replace(host, accelerators=(tiny,)), {})
    later = service.view(host, view, poor, _rows(models, view, poor))
    assert later.status is ModelSelectionStatus.INVALID
    assert later.selection.selection_mode is ModelSelectionMode.MANUAL
    assert later.selection.selected_logical_name == SEVEN
    assert SEVEN not in _names(later.feasible)


def test_foundation_change_invalidates_selection(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors = _verified(tmp_path)
    models = _catalog()
    view = eligibility.evaluate(
        host,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    envelope = CapacityService().compute(host, {})
    service = _service(tmp_path, models)
    service.select_auto(host, view, envelope, _rows(models, view, envelope))
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
    later = service.view(host, stale, envelope, _rows(models, stale, envelope))
    assert later.status is ModelSelectionStatus.STALE


def test_catalog_metadata_unchanged(tmp_path: Path) -> None:
    host, models, view, envelope = _ready(tmp_path)
    before = packaged_candidates()[0].metadata
    service = _service(tmp_path, models)
    service.select_auto(host, view, envelope, _rows(models, view, envelope))
    after = packaged_candidates()[0].metadata
    assert after == before


def test_no_force_mode_surface() -> None:
    text = (SOURCE / "kultrun" / "platform" / "model_selection.py").read_text(
        encoding="utf-8"
    )
    assert "force=true" not in text
    assert "allow_infeasible" not in text
    assert "allow_unsupported" not in text
    assert "ignore_capacity" not in text


def test_product_auto_manual_and_refusal(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    listed = _call(platform, "/models/selection")
    assert listed.status == 200
    payload = listed.body["payload"]
    assert isinstance(payload, dict)
    assert payload["plan_authoritative"] is False
    assert payload["status"] == "current"
    feasible = [item["logical_name"] for item in payload["feasible"]]
    assert SMALL in feasible
    assert SEVEN in feasible
    assert LARGE not in feasible
    assert BLOCKED not in feasible
    recommended = payload["recommended"]
    other = next(name for name in feasible if name != recommended)
    chosen = _call(
        platform,
        "/models/selection",
        Method.POST,
        mode="manual",
        model=other,
    )
    assert chosen.status == 200
    body = chosen.body["payload"]
    assert isinstance(body, dict)
    assert body["selection_mode"] == "manual"
    assert body["selected"] == other
    assert body["recommended"] == recommended
    blocked = _call(
        platform,
        "/models/selection",
        Method.POST,
        mode="manual",
        model=BLOCKED,
    )
    assert blocked.status == 412
    error = blocked.body["error"]
    assert isinstance(error, dict)
    context = error["context"]
    assert isinstance(context, dict)
    assert context["reason"] == "model_not_eligible"
    infeasible = _call(
        platform,
        "/models/selection",
        Method.POST,
        mode="manual",
        model=LARGE,
    )
    assert infeasible.status == 412
    unresolved = _call(
        platform,
        "/models/selection",
        Method.POST,
        mode="manual",
        model=UNRESOLVED,
    )
    assert unresolved.status == 412
    auto = _call(platform, "/models/selection", Method.POST, mode="auto")
    assert auto.status == 200
    restored = auto.body["payload"]
    assert isinstance(restored, dict)
    assert restored["selection_mode"] == "auto"
    assert restored["selected"] == recommended


def test_restart_reloads_manual_selection(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    first = _call(platform, "/models/selection").body["payload"]
    assert isinstance(first, dict)
    recommended = first["recommended"]
    other = next(
        item["logical_name"]
        for item in first["feasible"]
        if item["logical_name"] != recommended
    )
    _call(platform, "/models/selection", Method.POST, mode="manual", model=other)
    restarted = _product(tmp_path)
    again = _call(restarted, "/models/selection").body["payload"]
    assert isinstance(again, dict)
    assert again["selection_mode"] == "manual"
    assert again["selected"] == other
    assert again["recommended"] == recommended


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
    assert main(["models", "selection"]) == 0
    printed = capsys.readouterr().out
    assert "mode auto" in printed
    assert "recommended" in printed
    assert "feasible" in printed
    other = next(
        item["logical_name"]
        for item in _call(platform, "/models/selection").body["payload"]["feasible"]
        if item["logical_name"]
        != _call(platform, "/models/selection").body["payload"]["recommended"]
    )
    assert main(["models", "select", other]) == 0
    selected = capsys.readouterr().out
    assert "manual" in selected
    assert other in selected
    assert main(["models", "select", "--auto"]) == 0
    assert "auto" in capsys.readouterr().out
    assert main(["models", "select", BLOCKED]) == 1
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    assert "Use AUTO" in script
    assert "Choose" in script
    assert "/models/selection" in script
    assert "Select Model" not in script
    assert "Model selection" in html
    assert "Available Models" in html
    assert html.index("Available Models") < html.index("Model selection")


def test_architecture_guards() -> None:
    names = {item.name for item in fields(ModelSelection)}
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    tree = SOURCE / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in tree.rglob("*.py"))
    assert "class ModelSelectorV2" not in text
    assert "class NewSelectionService" not in text
    assert "class SelectionFramework" not in text
    assert "class GenericSelection" not in text
    assert "class SelectedDeploymentCandidate" not in text
    assert "class AvailableModelsV2" not in text
    assert "class GenericConstraintEngine" not in text
    routes = (SOURCE / "kultrun" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "plane.selection.recommend" not in routes
    assert "rank_feasible" in (
        SOURCE / "kultrun" / "planning" / "service.py"
    ).read_text(encoding="utf-8")
    assert (
        _imports_named(
            SOURCE / "kultrun" / "planning" / "service.py",
            "kultrun.runtime",
            "kultrun.resource",
            "kultrun.inference",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "planning" / "contracts.py",
            "kultrun.runtime",
            "kultrun.resource",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "resource" / "manager.py",
            "kultrun.planning",
            "kultrun.runtime",
            "kultrun.platform",
        )
        == []
    )
    offenders = [
        edge.describe()
        for edge in scan(SOURCE)
        if edge.source_package == "planning" and edge.target_package == "runtime"
    ]
    assert offenders == []
