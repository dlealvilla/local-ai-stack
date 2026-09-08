"""Stage 1.6G — ModelRequirement and Capacity consume eligible models."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace
from pathlib import Path

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.host import fixtures
from kultrun.adapters.model_source.candidates import (
    acceptance_candidate,
    packaged_candidates,
)
from kultrun.adapters.model_source.huggingface import HuggingFaceSource
from kultrun.api.contracts import ApiRequest, Method
from kultrun.capacity.envelope import CapacityService
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import build, config_schema, main
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.planning.contracts import CompatibilityVerdict, SelectionPolicy
from kultrun.planning.evaluate import evaluate, not_assessed
from kultrun.planning.service import SelectionService, estimation_request
from kultrun.platform.eligibility import catalog_facts
from kultrun.platform.requirement import (
    RequirementStatus,
    assess_catalog,
    assess_entry,
    capacity_verdict,
    recommend_from_view,
)
from kultrun.runtime.contracts import (
    EligibleViewStatus,
    RuntimeEligibilityStatus,
    RuntimePolicy,
)
from tests.architecture import BANNED_IMPLEMENTATION_FIELDS, _imports_named, scan
from tests.test_runtime_model_eligibility import _alt_descriptor, _verified

SOURCE = Path(__file__).resolve().parent.parent / "src"
GIB = 1024**3
SMALL = "qwen2.5-0.5b-instruct-awq"
LARGE = "qwen2.5-72b-instruct-awq"
SEVEN = "qwen2.5-7b-instruct-awq"
BLOCKED = "tinyllama-1.1b-chat-q4"
UNRESOLVED = "kultrun-hf-acceptance-tiny"


class RecordingEstimator:
    """Captures estimator requests. Does not shop or invent fit."""

    def __init__(self, inner: ModelRequirementEstimator) -> None:
        self._inner = inner
        self.requests: list[ModelEstimationRequest] = []

    @property
    def identity(self) -> Name:
        return self._inner.identity

    @property
    def version(self) -> str:
        return self._inner.version

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        self.requests.append(request)
        return self._inner.estimate(request)


class UnknownVramEstimator:
    """Load-bearing VRAM unknown. Capacity must not become feasible."""

    def __init__(self, inner: ModelRequirementEstimator) -> None:
        self._inner = inner

    @property
    def identity(self) -> Name:
        return self._inner.identity

    @property
    def version(self) -> str:
        return self._inner.version

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        requirement = self._inner.estimate(request)
        return replace(requirement, estimated_vram_bytes=NOT_PROVIDED)


def _catalog() -> ModelCatalogue:
    return ModelCatalogue(HuggingFaceSource(), extras=(acceptance_candidate(),))


def _named(models: ModelCatalogue, logical: str) -> ModelCatalogEntry:
    entry = models.acquirable(logical)
    assert entry is not None
    return entry


def _ready(tmp_path: Path, *, scenario: str = "healthy"):
    models = _catalog()
    eligibility, foundation, host, native, descriptors = _verified(
        tmp_path, scenario=scenario
    )
    view = eligibility.evaluate(
        host,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    envelope = CapacityService().compute(host, {})
    return eligibility, foundation, host, native, descriptors, models, view, envelope


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
    verified = platform.router.handle(
        ApiRequest(method=Method.POST, path="/v1/runtimes/foundation/verify")
    )
    assert verified.status == 200


def _rows_by_name(rows):
    return {item.logical_name: item for item in rows}


def _assess(view, entry, envelope, estimator=None):
    return assess_entry(
        view,
        entry,
        envelope,
        estimator or KultrunRequirementEstimator(),
        SelectionPolicy(),
    )


def test_eligible_verified_produces_requirement(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    assert view.status is EligibleViewStatus.CURRENT
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    row = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        recorder,
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.READY
    assert row.eligibility_status == RuntimeEligibilityStatus.ELIGIBLE.value
    assert row.requirement is not None
    assert is_resolved(row.requirement.estimated_vram_bytes)
    assert recorder.requests[0].runtime == view.runtime
    assert row.requirement.assumed_runtime == view.runtime
    assert row.basis is not None
    assert row.capacity_assessed is True


def test_blocked_refuses_normal_requirement(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    row = assess_entry(
        view,
        _named(models, BLOCKED),
        envelope,
        recorder,
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.REFUSED
    assert row.eligibility_status == RuntimeEligibilityStatus.BLOCKED.value
    assert row.requirement is None
    assert row.capacity_assessed is False
    assert row.capacity_verdict == "not_assessed"
    assert recorder.requests == []


def test_unresolved_is_not_ready(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    row = assess_entry(
        view,
        _named(models, UNRESOLVED),
        envelope,
        recorder,
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.UNRESOLVED
    assert row.capacity_verdict == "not_assessed"
    assert row.capacity_verdict != "feasible"
    assert recorder.requests == []


def test_runtime_identity_is_selected_profile_not_catalog(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    entry = _named(models, SMALL)
    assert entry.metadata.supported_runtimes
    other = "sglang"
    assert other != entry.metadata.supported_runtimes[0]
    shifted = replace(view, runtime=other, runtime_version="9.9.9")
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    row = assess_entry(shifted, entry, envelope, recorder, SelectionPolicy())
    assert recorder.requests[0].runtime == other
    assert recorder.requests[0].runtime_version == "9.9.9"
    assert row.requirement is not None
    assert row.requirement.assumed_runtime == other
    assert row.requirement.supported_runtimes == (other,)


def test_manual_foundation_runtime_is_honored(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    assert view.status is EligibleViewStatus.CURRENT
    recommended = view.runtime
    manual = replace(
        view,
        runtime="alt-native",
        runtime_version="0.0.1",
        selection_mode="manual",
    )
    assert recommended != "alt-native"
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    row = assess_entry(
        manual,
        _named(models, SMALL),
        envelope,
        recorder,
        SelectionPolicy(),
    )
    assert recorder.requests[0].runtime == "alt-native"
    assert row.requirement is not None
    assert row.requirement.assumed_runtime == "alt-native"
    assert row.selection_mode == "manual"


def test_requirement_provenance_includes_runtime_basis(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    row = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert row.requirement is not None
    assert row.runtime == view.runtime
    assert row.runtime_version == view.runtime_version
    assert row.profile_id == view.profile_id
    assert row.view_id == view.view_id.value
    assert row.requirement.requirement_basis == row.basis
    assert row.requirement.estimator_provider == "kultrun"


def test_different_runtime_changes_estimator_request(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    entry = _named(models, SMALL)
    first = RecordingEstimator(KultrunRequirementEstimator())
    second = RecordingEstimator(KultrunRequirementEstimator())
    assess_entry(view, entry, envelope, first, SelectionPolicy())
    assess_entry(
        replace(view, runtime="alt-native"),
        entry,
        envelope,
        second,
        SelectionPolicy(),
    )
    assert first.requests[0].runtime != second.requests[0].runtime


def test_stale_profile_is_not_authoritative(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors, models, view, envelope = _ready(tmp_path)
    ready = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert ready.requirement_status is RequirementStatus.READY
    accelerator = replace(host.accelerators[0], driver_version="changed-driver")
    shifted = replace(host, accelerators=(accelerator, *host.accelerators[1:]))
    stale = eligibility.evaluate(
        shifted,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    assert stale.status is EligibleViewStatus.STALE
    row = assess_entry(
        stale,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.STALE
    assert row.capacity_assessed is False
    assert row.capacity_verdict == "not_assessed"


def test_failed_profile_is_not_authoritative(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path, scenario="import_failure")
    assert view.status is EligibleViewStatus.UNAVAILABLE
    row = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.UNAVAILABLE
    assert row.capacity_assessed is False


def test_unknown_load_bearing_is_unresolved_capacity(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    row = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        UnknownVramEstimator(KultrunRequirementEstimator()),
        SelectionPolicy(),
    )
    assert row.requirement_status is RequirementStatus.READY
    assert row.capacity_verdict == "unresolved"
    assert row.capacity_verdict != "feasible"


def test_requirement_versus_safe_capacity(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    estimator = KultrunRequirementEstimator()
    policy = SelectionPolicy()
    small = assess_entry(view, _named(models, SMALL), envelope, estimator, policy)
    large = assess_entry(view, _named(models, LARGE), envelope, estimator, policy)
    assert small.capacity_verdict == "feasible"
    assert large.capacity_verdict == "infeasible"
    assert small.eligibility_status == large.eligibility_status == "eligible"


def test_free_vram_does_not_change_eligibility(tmp_path: Path) -> None:
    eligibility, _, host, native, descriptors, models, view, envelope = _ready(tmp_path)
    tiny = replace(host.accelerators[0], memory_total_bytes=2 * GIB)
    poor_host = replace(host, accelerators=(tiny,))
    poor = CapacityService().compute(poor_host, {})
    same = eligibility.evaluate(
        poor_host,
        (native,),
        descriptors,
        catalog_facts(models),
        components={"vllm": "missing"},
    )
    assert [item.status for item in view.candidates] == [
        item.status for item in same.candidates
    ]
    estimator = KultrunRequirementEstimator()
    rich = _assess(view, _named(models, SEVEN), envelope, estimator)
    tight = _assess(view, _named(models, SEVEN), poor, estimator)
    assert rich.eligibility_status == tight.eligibility_status == "eligible"
    assert rich.capacity_verdict == "feasible"
    assert tight.capacity_verdict == "infeasible"


def test_catalog_metadata_is_not_mutated(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    entry = _named(models, SMALL)
    before = entry.metadata
    assess_entry(
        view,
        entry,
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    after = _named(models, SMALL).metadata
    assert after == before
    assert after.supported_runtimes == before.supported_runtimes


def test_generic_requirement_has_no_runtime_flags(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    row = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert row.requirement is not None
    for item in fields(row.requirement):
        value = getattr(row.requirement, item.name)
        if isinstance(value, str):
            assert not value.startswith("--")
            assert "docker" not in value.lower()
        if isinstance(value, tuple):
            for part in value:
                if isinstance(part, str):
                    assert not part.startswith("--")


def test_foundation_change_invalidates_requirement(tmp_path: Path) -> None:
    eligibility, foundation, host, native, descriptors, models, view, envelope = _ready(
        tmp_path
    )
    first = assess_entry(
        view,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert first.requirement_status is RequirementStatus.READY
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
        catalog_facts(models),
        policy,
        components={"vllm": "missing"},
    )
    assert changed.status is not EligibleViewStatus.CURRENT
    second = assess_entry(
        changed,
        _named(models, SMALL),
        envelope,
        KultrunRequirementEstimator(),
        SelectionPolicy(),
    )
    assert second.requirement_status is not RequirementStatus.READY
    assert second.basis != first.basis


def test_capacity_only_change_keeps_eligibility(tmp_path: Path) -> None:
    _, _, host, _, _, models, view, envelope = _ready(tmp_path)
    tiny = replace(host.accelerators[0], memory_total_bytes=2 * GIB)
    poor = CapacityService().compute(replace(host, accelerators=(tiny,)), {})
    estimator = KultrunRequirementEstimator()
    first = _assess(view, _named(models, SEVEN), envelope, estimator)
    second = _assess(view, _named(models, SEVEN), poor, estimator)
    assert first.eligibility_status == second.eligibility_status
    assert first.requirement is not None
    assert second.requirement is not None
    assert (
        first.requirement.estimated_vram_bytes
        == second.requirement.estimated_vram_bytes
    )
    assert first.capacity_verdict != second.capacity_verdict


def test_reservations_do_not_change_planning_requirement(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    host = platform.hosts.current
    envelope = platform.capacity.compute(host, {})
    view = platform.eligibility.evaluate(
        host,
        (
            platform.executions.capabilities(host),
            platform.plane.container_capability(host),
        ),
        platform.runtimes.descriptors(),
        catalog_facts(platform.models),
        RuntimePolicy(),
        components={"vllm": "missing"},
    )
    estimator = platform.selection.estimator
    policy = platform.selection.policy
    before = assess_catalog(view, platform.models, envelope, estimator, policy)
    from kultrun.model.acquisition import request_from_entry
    from tests.test_resource_admission import _request as resource_request

    entry = platform.models.acquirable(SMALL)
    assert entry is not None
    receipt = platform.acquisition.acquire(
        request_from_entry(entry), envelope, host.host_id
    )
    artifact = platform.inventory.get(receipt.artifact_id)
    assert artifact is not None
    admitted = platform.resources.admit(
        resource_request(artifact, envelope, ram=GIB, vram=GIB),
        envelope,
        artifact,
    )
    assert admitted.reservation is not None
    after = assess_catalog(view, platform.models, envelope, estimator, policy)
    left = _rows_by_name(before)[SMALL]
    right = _rows_by_name(after)[SMALL]
    assert left.basis == right.basis
    assert left.capacity_verdict == right.capacity_verdict
    assert left.requirement_status == right.requirement_status


def test_restart_recomputes_coherently(tmp_path: Path) -> None:
    platform = _product(tmp_path)
    _realize(platform)
    first = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/requirements")
    )
    assert first.status == 200
    payload = first.body["payload"]
    assert isinstance(payload, dict)
    assert payload["view_status"] == "current"
    assert payload["mutations"] is False
    restarted = _product(tmp_path)
    second = restarted.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/requirements")
    )
    assert second.status == 200
    again = second.body["payload"]
    assert isinstance(again, dict)
    assert again["view_status"] == "current"
    assert again["selected_runtime"] == payload["selected_runtime"]


def test_k94_missing_mapping_is_unresolved_not_compatible() -> None:
    signature = inspect.signature(SelectionService.recommend)
    assert "runtime" in signature.parameters
    assert "runtime_compatibility" in signature.parameters
    param = signature.parameters["runtime_compatibility"]
    assert param.default is inspect.Parameter.empty
    source = (SOURCE / "kultrun" / "planning" / "service.py").read_text(
        encoding="utf-8"
    )
    assert "CompatibilityVerdict.UNRESOLVED" in source
    assert "or CompatibilityVerdict.COMPATIBLE" not in source
    admission = (SOURCE / "kultrun" / "platform" / "admission.py").read_text(
        encoding="utf-8"
    )
    assert "runtime_compatibility is None" not in admission
    assert "or CompatibilityVerdict.COMPATIBLE" not in admission
    evaluate_sig = inspect.signature(evaluate)
    assert (
        evaluate_sig.parameters["runtime_compatibility"].default
        is inspect.Parameter.empty
    )


def test_old_runtime_hint_is_not_estimator_authority() -> None:
    from kultrun.model.contracts import MemoryPlacement

    text = (SOURCE / "kultrun" / "planning" / "service.py").read_text(encoding="utf-8")
    assert "meta.supported_runtimes" not in text
    request = estimation_request(
        packaged_candidates()[0],
        MemoryPlacement.DISCRETE_GPU,
        runtime="explicit-runtime",
    )
    assert request.runtime == "explicit-runtime"


def test_product_surfaces(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    platform = _product(tmp_path)
    empty = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/requirements")
    )
    assert empty.status == 200
    body = empty.body["payload"]
    assert isinstance(body, dict)
    assert body["view_status"] == "unavailable"
    _realize(platform)
    requirements = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/requirements")
    )
    assert requirements.status == 200
    payload = requirements.body["payload"]
    assert isinstance(payload, dict)
    assert payload["view_status"] == "current"
    assert payload["selected_runtime"] == "vllm"
    names = {item["logical_name"]: item for item in payload["assessments"]}
    assert names[SMALL]["requirement_status"] == "ready"
    assert names[SMALL]["capacity_verdict"] == "feasible"
    assert names[LARGE]["capacity_verdict"] == "infeasible"
    assert names[BLOCKED]["requirement_status"] == "refused"
    assert names[BLOCKED]["capacity_verdict"] == "not_assessed"
    assert names[UNRESOLVED]["requirement_status"] == "unresolved"
    selection = platform.router.handle(
        ApiRequest(method=Method.GET, path="/v1/models/selection")
    )
    assert selection.status == 200
    select = selection.body["payload"]
    assert isinstance(select, dict)
    assert select["selected_runtime"] == "vllm"
    assert select["assessments"]
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
    monkeypatch.setenv("KULTRUN_MODEL_ACQUISITION_PROVIDER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
    assert main(["models", "requirements"]) == 0
    printed = capsys.readouterr().out
    assert "runtime vllm" in printed
    assert "ready" in printed
    html = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "index.html"
    ).read_text(encoding="utf-8")
    script = (
        SOURCE / "kultrun" / "adapters" / "http" / "console" / "app.js"
    ).read_text(encoding="utf-8")
    assert "selected runtime" in script
    assert "/models/requirements" in script
    assert "Select Model" not in script
    assert "Eligible models" in html


def test_recommend_from_view_skips_blocked(tmp_path: Path) -> None:
    _, _, _, _, _, models, view, envelope = _ready(tmp_path)
    recorder = RecordingEstimator(KultrunRequirementEstimator())
    rows = assess_catalog(view, models, envelope, recorder, SelectionPolicy())
    blocked_id = _named(models, BLOCKED).metadata.model_id.value
    recorded = {item.model_id.value for item in recorder.requests}
    assert blocked_id not in recorded
    before = len(recorder.requests)
    recommendation = recommend_from_view(
        SelectionService(recorder, FixedClock(now_utc())),
        view,
        envelope,
        models.entries(),
        rows,
    )
    assert all(item.model_id.value != blocked_id for item in recorder.requests[before:])
    assert recommendation.primary is not None
    assert recommendation.primary.logical_name.value != BLOCKED


def test_not_assessed_is_not_feasible() -> None:
    meta = packaged_candidates()[0].metadata
    evaluation = not_assessed(
        meta,
        compatibility=CompatibilityVerdict.UNSUPPORTED,
        reasons=("blocked",),
    )
    assert evaluation.capacity_fit.value == "unresolved"
    assert capacity_verdict(evaluation.capacity_fit, assessed=False) == "not_assessed"


def test_architecture_guards() -> None:
    names = {item.name for item in fields(ModelRequirement)}
    assert "assumed_runtime" in names
    assert names.isdisjoint(BANNED_IMPLEMENTATION_FIELDS)
    tree = SOURCE / "kultrun"
    text = "\n".join(path.read_text(encoding="utf-8") for path in tree.rglob("*.py"))
    assert "class ModelRequirementV2" not in text
    assert "class CapacityPlannerV2" not in text
    assert "class CapacityAssessmentV2" not in text
    assert (
        _imports_named(
            SOURCE / "kultrun" / "capacity" / "envelope.py",
            "kultrun.runtime",
            "kultrun.planning",
            "kultrun.model",
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
    assert (
        _imports_named(
            SOURCE / "kultrun" / "runtime" / "eligibility.py",
            "kultrun.capacity",
            "kultrun.planning",
            "kultrun.resource",
        )
        == []
    )
    assert (
        _imports_named(
            SOURCE / "kultrun" / "platform" / "requirement.py",
            "kultrun.resource",
            "kultrun.inference",
        )
        == []
    )
    offenders = [
        edge.describe()
        for edge in scan(SOURCE)
        if edge.source_package == "capacity" and edge.target_package == "runtime"
    ]
    assert offenders == []
