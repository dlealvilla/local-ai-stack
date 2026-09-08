"""Stage 1.4B — SAFE-capacity feasibility, 20-100% band, deterministic rank.

Planning consumes ModelRequirement and never a concrete estimator adapter.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from tools.compare_model_estimators import estimation_request

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import LlmfitRequirementEstimator, fixture_plan
from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import (
    MemoryPlacement,
    ModelEstimationRequest,
    ModelId,
    ModelMetadata,
    ModelRequirement,
)
from kultrun.planning.contracts import (
    CapacityFitClass,
    CompatibilityVerdict,
    DeploymentCapacity,
    ModelEvaluation,
    SelectionOutcome,
    SelectionPolicy,
)
from kultrun.planning.evaluate import evaluate, rank_key, utilization
from kultrun.planning.service import SelectionService, plan_from
from tests.test_capacity import accelerator, host, mount
from tests.test_capacity import service as capacity_service

INSTANT = dt.datetime(2026, 9, 6, 10, 0, tzinfo=dt.UTC)
GIB = 1024**3
SAFE_VRAM = 10_000_000_000
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"


def _capacity(
    *,
    vram: Maybe[int] = SAFE_VRAM,
    ram: Maybe[int] = 64 * GIB,
    storage: Maybe[int] = 500 * GIB,
    placement: MemoryPlacement = MemoryPlacement.DISCRETE_GPU,
) -> DeploymentCapacity:
    gpu = placement is MemoryPlacement.DISCRETE_GPU
    return DeploymentCapacity(
        host_id=HostId.generate(),
        host_fingerprint="test-envelope",
        placement=placement,
        accelerator_index=0 if gpu else None,
        safe_ram_bytes=ram,
        safe_vram_bytes=vram if gpu else NOT_PROVIDED,
        safe_unified_bytes=NOT_PROVIDED,
        safe_storage_bytes=storage,
        envelope_policy_version="test",
    )


def _metadata(**overrides: object) -> ModelMetadata:
    fields: dict[str, object] = {
        "model_id": ModelId.generate(),
        "logical_name": Name("probe-model"),
        "source": Name("huggingface"),
        "source_ref": "probe/model",
        "source_revision": NOT_PROVIDED,
        "family": "probe",
        "parameter_count": 7_000_000_000,
        "context_length_tokens": 8192,
        "quantization": "q4_k",
        "license_id": NOT_PROVIDED,
        "commercial_use_restricted": NOT_PROVIDED,
        "supported_runtimes": ("vllm",),
    }
    fields.update(overrides)
    return ModelMetadata(**fields)  # type: ignore[arg-type]


def _requirement(model_id: ModelId, **overrides: object) -> ModelRequirement:
    fields: dict[str, object] = {
        "model_id": model_id,
        "confidence": Confidence.MEDIUM,
        "storage_bytes": GIB,
        "peak_additional_bytes": GIB,
        "vram_weights_bytes": GIB,
        "vram_kv_bytes_per_token": NOT_PROVIDED,
        "vram_overhead_bytes": NOT_PROVIDED,
        "ram_bytes": GIB,
        "estimated_vram_bytes": 2_000_000_000,
        "assumed_context_tokens": 8192,
        "estimation_method": "test",
        "estimator_provider": "kultrun",
        "estimator_version": "test",
        "measured": False,
    }
    fields.update(overrides)
    return ModelRequirement(**fields)  # type: ignore[arg-type]


def _evaluate(
    *,
    vram: Maybe[int] = 2_000_000_000,
    ram: Maybe[int] = GIB,
    peak: Maybe[int] = GIB,
    safe_vram: Maybe[int] = SAFE_VRAM,
    safe_storage: Maybe[int] = 500 * GIB,
    placement: MemoryPlacement = MemoryPlacement.DISCRETE_GPU,
    policy: SelectionPolicy | None = None,
    metadata: ModelMetadata | None = None,
    **requirement_overrides: object,
) -> ModelEvaluation:
    meta = metadata or _metadata()
    req = _requirement(
        meta.model_id,
        estimated_vram_bytes=vram,
        ram_bytes=ram,
        peak_additional_bytes=peak,
        **requirement_overrides,
    )
    return evaluate(
        meta,
        req,
        _capacity(vram=safe_vram, storage=safe_storage, placement=placement),
        policy or SelectionPolicy(),
    )


class TestUtilizationBoundaries:
    def test_19_99_percent_is_underutilized(self) -> None:
        result = _evaluate(vram=1_999_000_000)
        assert result.capacity_fit is CapacityFitClass.UNDERUTILIZED
        assert result.preferred is False
        assert result.utilization.ratio == 0.1999

    def test_20_percent_is_preferred(self) -> None:
        result = _evaluate(vram=2_000_000_000)
        assert result.capacity_fit is CapacityFitClass.PREFERRED
        assert result.preferred is True
        assert result.utilization.ratio == 0.20

    def test_100_percent_is_preferred(self) -> None:
        result = _evaluate(vram=SAFE_VRAM)
        assert result.capacity_fit is CapacityFitClass.PREFERRED
        assert result.utilization.ratio == 1.00

    def test_100_01_percent_exceeds_safe(self) -> None:
        result = _evaluate(vram=10_001_000_000)
        assert result.capacity_fit is CapacityFitClass.EXCEEDS_SAFE
        assert result.preferred is False
        assert result.utilization.ratio == 1.0001

    def test_unknown_requirement_is_unresolved_not_zero(self) -> None:
        result = _evaluate(vram=NOT_PROVIDED, ram=NOT_PROVIDED)
        assert result.capacity_fit is CapacityFitClass.UNRESOLVED
        assert not is_resolved(result.utilization.ratio)
        assert result.utilization.ratio != 0

    def test_storage_failure_is_independent_of_memory_fit(self) -> None:
        result = _evaluate(vram=2_000_000_000, peak=20 * GIB, safe_storage=GIB)
        assert result.capacity_fit is CapacityFitClass.EXCEEDS_SAFE
        assert result.storage_feasible is False
        assert result.utilization.ratio == 0.20

    def test_cpu_only_uses_ram(self) -> None:
        result = _evaluate(
            ram=32 * GIB,
            vram=NOT_PROVIDED,
            placement=MemoryPlacement.CPU_ONLY,
            safe_vram=NOT_PROVIDED,
        )
        assert result.utilization.limiting_resource == "ram"
        assert result.capacity_fit is CapacityFitClass.PREFERRED

    def test_policy_bounds_are_not_hardcoded_in_evaluate(self) -> None:
        policy = SelectionPolicy(
            minimum_capacity_utilization=0.50,
            maximum_capacity_utilization=0.80,
        )
        low = _evaluate(vram=2_000_000_000, policy=policy)
        assert low.capacity_fit is CapacityFitClass.UNDERUTILIZED
        high = _evaluate(vram=9_000_000_000, policy=policy)
        assert high.capacity_fit is CapacityFitClass.EXCEEDS_SAFE


class TestRanking:
    def test_larger_capability_wins_inside_the_preferred_band(self) -> None:
        small = _evaluate(
            vram=3_000_000_000,
            metadata=_metadata(
                logical_name=Name("small"), parameter_count=1_000_000_000
            ),
        )
        large = _evaluate(
            vram=8_000_000_000,
            metadata=_metadata(
                logical_name=Name("large"), parameter_count=8_000_000_000
            ),
        )
        assert rank_key(large) < rank_key(small)

    def test_lower_utilization_is_the_headroom_tiebreak(self) -> None:
        tight = _evaluate(
            vram=9_000_000_000,
            metadata=_metadata(
                logical_name=Name("tight"), parameter_count=8_000_000_000
            ),
        )
        roomy = _evaluate(
            vram=3_000_000_000,
            metadata=_metadata(
                logical_name=Name("roomy"), parameter_count=8_000_000_000
            ),
        )
        assert rank_key(roomy) < rank_key(tight)


class TestProviderIndependence:
    def test_the_same_evaluate_function_is_used_for_both_estimators(self) -> None:
        entry = next(
            item
            for item in packaged_candidates()
            if item.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        request = estimation_request(entry)
        kultrun = KultrunRequirementEstimator().estimate(request)
        llmfit = LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT)).estimate(
            request
        )
        capacity = _capacity(vram=24 * GIB)
        policy = SelectionPolicy()
        left = evaluate(entry.metadata, kultrun, capacity, policy)
        right = evaluate(entry.metadata, llmfit, capacity, policy)
        assert left.estimator_provider == "kultrun"
        assert right.estimator_provider == "llmfit"
        assert left.required_vram_bytes == kultrun.estimated_vram_bytes
        assert right.required_vram_bytes == llmfit.estimated_vram_bytes
        assert left.capacity_fit is CapacityFitClass.UNDERUTILIZED
        assert right.capacity_fit is CapacityFitClass.UNDERUTILIZED

    def test_estimator_c_flows_through_selection_without_planning_edits(self) -> None:
        class EstimatorC:
            identity = Name("estimator-c")
            version = "test"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                for entry in packaged_candidates():
                    if entry.metadata.model_id.value == request.model_id.value:
                        return entry.requirement
                return packaged_candidates()[0].requirement

        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        service = SelectionService(EstimatorC(), FixedClock(INSTANT))
        recommendation = service.recommend(
            envelope=envelope,
            candidates=packaged_candidates()[:3],
        )
        assert recommendation.estimator_provider == "estimator-c"
        assert recommendation.outcome is SelectionOutcome.RECOMMENDED
        planned = plan_from(recommendation)
        assert planned is not None
        assert planned.estimator_provider == "estimator-c"


class TestGpuAndCpuShapes:
    def test_a_tiny_host_rejects_large_candidates(self) -> None:
        envelope = capacity_service().compute(
            host(
                memory_total=8 * GIB,
                accelerators=(accelerator(memory=2 * GIB),),
                mounts=(mount(free=20 * GIB, total=40 * GIB),),
            )
        )
        service = SelectionService(KultrunRequirementEstimator(), FixedClock(INSTANT))
        recommendation = service.recommend(
            envelope=envelope,
            candidates=packaged_candidates(),
        )
        if recommendation.primary is not None:
            assert recommendation.primary.capacity_fit is CapacityFitClass.PREFERRED

    def test_a_medium_gpu_has_a_preferred_band(self) -> None:
        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        service = SelectionService(KultrunRequirementEstimator(), FixedClock(INSTANT))
        recommendation = service.recommend(
            envelope=envelope,
            candidates=packaged_candidates(),
        )
        assert recommendation.outcome is SelectionOutcome.RECOMMENDED
        assert recommendation.primary is not None
        planned = plan_from(recommendation)
        assert planned is not None
        assert planned.estimator_provider == "kultrun"

    def test_llmfit_fixture_path_uses_the_same_planning(self) -> None:
        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        service = SelectionService(
            LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT)),
            FixedClock(INSTANT),
        )
        recommendation = service.recommend(
            envelope=envelope,
            candidates=packaged_candidates(),
        )
        assert recommendation.estimator_provider == "llmfit"


class TestUtilizationUsesSafeOnly:
    def test_storage_is_not_a_utilization_input(self) -> None:
        req = _requirement(
            ModelId.generate(), estimated_vram_bytes=2 * GIB, ram_bytes=GIB
        )
        used = utilization(req, _capacity(vram=10 * GIB, storage=1))
        assert used.limiting_resource == "vram"
        assert used.ratio == 0.2


class TestRuntimeEligibilityShim:
    def test_blocked_eligibility_is_not_a_capacity_fit(self) -> None:
        blocked = _evaluate()
        blocked = evaluate(
            _metadata(),
            _requirement(ModelId.generate(), estimated_vram_bytes=2_000_000_000),
            _capacity(),
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.UNSUPPORTED,
        )
        assert blocked.compatibility is CompatibilityVerdict.UNSUPPORTED
        assert blocked.preferred is False
        assert blocked.capacity_fit is CapacityFitClass.EXCEEDS_SAFE

    def test_evaluate_does_not_intersect_supported_runtimes(self) -> None:
        text = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "kultrun"
            / "planning"
            / "evaluate.py"
        ).read_text(encoding="utf-8")
        assert "no overlapping runtime" not in text
        assert "available_runtimes" not in text
