"""Estimator router: llmfit primary, Kultrun fallback, no estimate shopping."""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.estimators.common import unavailable_requirement
from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import LlmfitRequirementEstimator, fixture_plan
from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.errors import ConfigError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import build, config_schema, resolve_estimator
from kultrun.model.contracts import (
    EstimatorFailureReason,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)
from kultrun.model.estimator_router import EstimatorRouter
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.planning.contracts import (
    CapacityFitClass,
    CompatibilityVerdict,
    SelectionPolicy,
)
from kultrun.planning.evaluate import evaluate
from kultrun.planning.service import SelectionService
from kultrun.platform.contracts import PlatformSettings
from tests.test_capacity import accelerator, host, mount
from tests.test_capacity import service as capacity_service
from tests.test_estimators import _request
from tests.test_planning_selection import GIB, INSTANT

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"


class CountingEstimator:
    """Test double that records invocations."""

    def __init__(self, inner: ModelRequirementEstimator) -> None:
        self.inner = inner
        self.calls = 0

    @property
    def identity(self) -> Name:
        return self.inner.identity

    @property
    def version(self) -> str:
        return self.inner.version

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        self.calls += 1
        return self.inner.estimate(request)


def _tiny() -> ModelCatalogEntry:
    return packaged_candidates()[0]


def _seven() -> ModelCatalogEntry:
    return next(
        entry
        for entry in packaged_candidates()
        if entry.metadata.logical_name.value == "qwen2.5-7b-instruct-awq"
    )


def _llmfit() -> LlmfitRequirementEstimator:
    return LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT))


class TestConfigurationModes:
    def test_absent_setting_is_auto(self) -> None:
        settings = config_schema().load({}).section(PlatformSettings)
        assert settings.model_requirement_estimator == "auto"

    def test_auto_resolves_to_a_router(self) -> None:
        router = resolve_estimator("auto")
        assert isinstance(router, EstimatorRouter)
        assert router.identity.value == "auto"
        assert router.requested_primary == "llmfit"

    def test_strict_llmfit_does_not_fall_back(self) -> None:
        router = resolve_estimator("llmfit")
        assert isinstance(router, EstimatorRouter)
        assert router.identity.value == "llmfit"
        assert router.allow_fallback is False

    def test_strict_kultrun_does_not_fall_back(self) -> None:
        router = resolve_estimator("kultrun")
        assert isinstance(router, EstimatorRouter)
        assert router.identity.value == "kultrun"
        assert router.allow_fallback is False

    def test_invalid_mode_is_a_configuration_error(self, tmp_path: Path) -> None:
        configuration = config_schema().load(
            {
                "platform": {
                    "state_root": str(tmp_path / "state"),
                    "model_requirement_estimator": "ensemble",
                }
            }
        )
        with pytest.raises(ConfigError, match="unknown model requirement estimator"):
            build(configuration)


class TestAutoFailover:
    def test_healthy_llmfit_does_not_invoke_kultrun(self) -> None:
        llmfit = CountingEstimator(_llmfit())
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        result = router.estimate(_request(_seven(), runtime="llama.cpp"))
        assert result.estimator_provider == "llmfit"
        assert result.fallback_used is False
        assert llmfit.calls == 1
        assert kultrun.calls == 0

    def test_vllm_llmfit_plan_minimum_falls_back_to_kultrun(self) -> None:
        llmfit = CountingEstimator(_llmfit())
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        result = router.estimate(_request(_seven(), context=8192))
        assert result.estimator_provider == "kultrun"
        assert result.fallback_used is True
        assert result.fallback_reason == (
            EstimatorFailureReason.MISSING_LOAD_BEARING_REQUIREMENT.value
        )
        assert llmfit.calls == 1
        assert kultrun.calls == 1
        assert is_resolved(result.estimated_vram_bytes)
        assert result.estimated_vram_bytes > 8 * (1024**3)

    def test_unavailable_llmfit_falls_back_to_kultrun(self) -> None:
        def missing(model: str, context: int, quant: str) -> dict[str, object]:
            raise FileNotFoundError("llmfit executable not found")

        llmfit = CountingEstimator(LlmfitRequirementEstimator(plan=missing))
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        result = router.estimate(_request(_seven()))
        assert result.estimator_provider == "kultrun"
        assert result.fallback_used is True
        assert result.fallback_reason == (
            EstimatorFailureReason.PROVIDER_UNAVAILABLE.value
        )
        assert llmfit.calls == 1
        assert kultrun.calls == 1
        assert is_resolved(result.estimated_vram_bytes)

    def test_timeout_falls_back_to_kultrun(self) -> None:
        def timed_out(model: str, context: int, quant: str) -> dict[str, object]:
            raise __import__("subprocess").TimeoutExpired(cmd="llmfit", timeout=1)

        router = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=timed_out),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_used is True
        assert result.fallback_reason == EstimatorFailureReason.PROVIDER_TIMEOUT.value
        assert result.estimator_provider == "kultrun"

    def test_invalid_json_falls_back_to_kultrun(self) -> None:
        def bad_json(model: str, context: int, quant: str) -> dict[str, object]:
            raise __import__("json").JSONDecodeError("bad", "x", 0)

        router = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=bad_json),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.INVALID_PROVIDER_OUTPUT.value
        )
        assert result.estimator_provider == "kultrun"

    def test_assumption_mismatch_falls_back_when_kultrun_supports_it(
        self,
    ) -> None:
        def swapped(model: str, context: int, quant: str) -> dict[str, object]:
            return {
                "model_name": model,
                "context": context,
                "quantization": "F16",
                "minimum": {"vram_gb": 1.0, "ram_gb": 8.0},
            }

        router = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=swapped),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.ASSUMPTION_MISMATCH.value
        )
        assert result.estimator_provider == "kultrun"

    def test_missing_load_bearing_requirement_falls_back(self) -> None:
        def empty(model: str, context: int, quant: str) -> dict[str, object]:
            return {
                "model_name": model,
                "context": context,
                "quantization": quant,
                "minimum": {},
            }

        router = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=empty),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.MISSING_LOAD_BEARING_REQUIREMENT.value
        )
        assert result.estimator_provider == "kultrun"
        assert is_resolved(result.estimated_vram_bytes)

    def test_both_fail_stays_unresolved(self) -> None:
        def missing(model: str, context: int, quant: str) -> dict[str, object]:
            raise FileNotFoundError("gone")

        class EmptyKultrun:
            identity = Name("kultrun")
            version = "test"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                return unavailable_requirement(
                    request,
                    provider="kultrun",
                    version="test",
                    method="unsupported",
                    reason="empty",
                    failure=EstimatorFailureReason.UNSUPPORTED_MODEL,
                )

        router = EstimatorRouter(
            mode="auto",
            providers=(LlmfitRequirementEstimator(plan=missing), EmptyKultrun()),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_used is True
        assert not is_resolved(result.estimated_vram_bytes)
        assert result.estimated_vram_bytes != 0

    def test_strict_llmfit_does_not_call_kultrun_on_failure(self) -> None:
        def missing(model: str, context: int, quant: str) -> dict[str, object]:
            raise FileNotFoundError("gone")

        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="llmfit",
            providers=(LlmfitRequirementEstimator(plan=missing),),
            allow_fallback=False,
        )
        result = router.estimate(_request(_seven()))
        assert result.estimator_provider == "llmfit"
        assert result.fallback_used is False
        assert not is_resolved(result.estimated_vram_bytes)
        assert kultrun.calls == 0

    def test_execution_error_falls_back_to_kultrun(self) -> None:
        def boom(model: str, context: int, quant: str) -> dict[str, object]:
            raise OSError("spawn failed")

        router = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=boom),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.PROVIDER_EXECUTION_ERROR.value
        )
        assert result.estimator_provider == "kultrun"
        assert "spawn failed" not in str(result.assumptions)

    def test_incompatible_version_falls_back_to_kultrun(self) -> None:
        class Incompatible:
            identity = Name("llmfit")
            version = "0.0.1"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                return unavailable_requirement(
                    request,
                    provider="llmfit",
                    version=self.version,
                    method="provider-unavailable",
                    reason="incompatible llmfit",
                    failure=EstimatorFailureReason.INCOMPATIBLE_PROVIDER_VERSION,
                )

        router = EstimatorRouter(
            mode="auto",
            providers=(Incompatible(), KultrunRequirementEstimator()),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.INCOMPATIBLE_PROVIDER_VERSION.value
        )
        assert result.estimator_provider == "kultrun"

    def test_unsupported_model_falls_back_when_kultrun_has_it(self) -> None:
        class UnknownToPrimary:
            identity = Name("llmfit")
            version = "test"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                return unavailable_requirement(
                    request,
                    provider="llmfit",
                    version="test",
                    method="unsupported",
                    reason="unknown to primary",
                    failure=EstimatorFailureReason.UNSUPPORTED_MODEL,
                )

        router = EstimatorRouter(
            mode="auto",
            providers=(UnknownToPrimary(), KultrunRequirementEstimator()),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == EstimatorFailureReason.UNSUPPORTED_MODEL.value
        assert result.estimator_provider == "kultrun"
        assert is_resolved(result.estimated_vram_bytes)

    def test_unsupported_configuration_falls_back_when_kultrun_supports_it(
        self,
    ) -> None:
        class StrictConfig:
            identity = Name("llmfit")
            version = "test"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                return unavailable_requirement(
                    request,
                    provider="llmfit",
                    version="test",
                    method="unsupported",
                    reason="config",
                    failure=EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
                )

        router = EstimatorRouter(
            mode="auto",
            providers=(StrictConfig(), KultrunRequirementEstimator()),
            allow_fallback=True,
        )
        result = router.estimate(_request(_seven()))
        assert result.fallback_reason == (
            EstimatorFailureReason.UNSUPPORTED_CONFIGURATION.value
        )
        assert result.estimator_provider == "kultrun"
        assert is_resolved(result.estimated_vram_bytes)

    def test_fallback_reason_is_typed_not_exception_text(self) -> None:
        def missing(model: str, context: int, quant: str) -> dict[str, object]:
            raise FileNotFoundError("llmfit: some internal traceback")

        result = EstimatorRouter(
            mode="auto",
            providers=(
                LlmfitRequirementEstimator(plan=missing),
                KultrunRequirementEstimator(),
            ),
            allow_fallback=True,
        ).estimate(_request(_tiny()))
        assert result.fallback_reason == (
            EstimatorFailureReason.PROVIDER_UNAVAILABLE.value
        )
        encoded = str(result)
        assert "traceback" not in encoded.lower()
        assert "FileNotFoundError" not in encoded


class TestNoEstimateShopping:
    def test_valid_over_capacity_llmfit_does_not_fall_back(self) -> None:
        def huge(model: str, context: int, quant: str) -> dict[str, object]:
            return {
                "model_name": model,
                "context": context,
                "quantization": quant,
                "minimum": {"vram_gb": 26.0, "ram_gb": 8.0},
            }

        llmfit = CountingEstimator(LlmfitRequirementEstimator(plan=huge))
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        request = _request(_tiny(), runtime="llama.cpp")
        requirement = router.estimate(request)
        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        from kultrun.planning.evaluate import deployment_capacity

        evaluation = evaluate(
            _tiny().metadata,
            requirement,
            deployment_capacity(envelope),
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        )
        assert evaluation.capacity_fit is CapacityFitClass.EXCEEDS_SAFE
        assert requirement.estimator_provider == "llmfit"
        assert requirement.fallback_used is False
        assert kultrun.calls == 0

    def test_valid_underutilized_llmfit_does_not_fall_back(self) -> None:
        llmfit = CountingEstimator(_llmfit())
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        requirement = router.estimate(_request(_tiny(), runtime="llama.cpp"))
        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        from kultrun.planning.evaluate import deployment_capacity

        evaluation = evaluate(
            _tiny().metadata,
            requirement,
            deployment_capacity(envelope),
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        )
        assert evaluation.capacity_fit is CapacityFitClass.UNDERUTILIZED
        assert requirement.fallback_used is False
        assert kultrun.calls == 0

    def test_selection_does_not_shop_for_a_better_rank(self) -> None:
        llmfit = CountingEstimator(_llmfit())
        kultrun = CountingEstimator(KultrunRequirementEstimator())
        router = EstimatorRouter(
            mode="auto", providers=(llmfit, kultrun), allow_fallback=True
        )
        envelope = capacity_service().compute(
            host(
                memory_total=64 * GIB,
                accelerators=(accelerator(memory=24 * GIB),),
                mounts=(mount(free=500 * GIB, total=1000 * GIB),),
            )
        )
        service = SelectionService(router, FixedClock(INSTANT))
        recommendation = service.recommend(
            envelope=envelope,
            candidates=packaged_candidates()[:6],
            runtime="llama.cpp",
            runtime_compatibility={
                item.metadata.model_id.value: CompatibilityVerdict.COMPATIBLE
                for item in packaged_candidates()[:6]
            },
        )
        assert recommendation.estimator_provider == "llmfit"
        assert recommendation.fallback_used is False
        assert kultrun.calls == 0
        assert llmfit.calls == 6
