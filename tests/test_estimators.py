"""Stage 1.4B — replaceable ModelRequirementEstimator adapters.

Product execution selects one provider. These tests prove the port, both
adapters, unknown-is-not-zero, and that a third estimator needs no
Planning change.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.estimators.common import unavailable_requirement
from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import (
    TESTED_VERSION,
    LlmfitRequirementEstimator,
    fixture_plan,
)
from kultrun.adapters.model_source.candidates import (
    ORIGINAL_FIXTURES,
    PROVIDER_VERSION,
    packaged_candidates,
)
from kultrun.kernel.errors import ConfigError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.main import ESTIMATOR_VARIABLE, build, config_schema, estimator_registry
from kultrun.model.contracts import (
    MemoryPlacement,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.platform.contracts import PlatformSettings

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"
GiB = 1024**3


def _request(
    entry: ModelCatalogEntry | None = None,
    *,
    quantization: Maybe[str] | None = None,
    context: Maybe[int] | None = None,
    offload: bool = False,
    tensor_parallel: int = 1,
    batch_size: int = 1,
    placement: MemoryPlacement = MemoryPlacement.DISCRETE_GPU,
) -> ModelEstimationRequest:
    candidate = entry or packaged_candidates()[0]
    meta = candidate.metadata
    req = candidate.requirement
    return ModelEstimationRequest(
        model_id=meta.model_id,
        source_ref=meta.source_ref,
        source_revision=meta.source_revision,
        artifact_format=NOT_PROVIDED,
        quantization=meta.quantization if quantization is None else quantization,
        context_tokens=(req.assumed_context_tokens if context is None else context),
        runtime=meta.supported_runtimes[0],
        placement=placement,
        offload_allowed=offload,
        tensor_parallel=tensor_parallel,
        batch_size=batch_size,
    )


def _fixture_llmfit() -> LlmfitRequirementEstimator:
    return LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT))


class TestThePort:
    def test_both_adapters_satisfy_the_port(self) -> None:
        assert isinstance(KultrunRequirementEstimator(), ModelRequirementEstimator)
        assert isinstance(_fixture_llmfit(), ModelRequirementEstimator)

    def test_composition_registers_both_and_defaults_to_kultrun(self) -> None:
        registry = estimator_registry()
        assert "kultrun" in registry
        assert "llmfit" in registry
        assert set(registry.names()) == {"kultrun", "llmfit"}
        built = registry.create("kultrun")
        assert built.identity.value == "kultrun"
        assert built.version == PROVIDER_VERSION

    def test_an_unknown_provider_is_a_configuration_error(
        self, tmp_path: Path
    ) -> None:
        configuration = config_schema().load(
            {
                "platform": {
                    "state_root": str(tmp_path / "state"),
                    "model_requirement_estimator": "no-such-provider",
                }
            }
        )
        with pytest.raises(ConfigError, match="unknown model requirement estimator"):
            build(configuration)

    def test_environment_selects_the_provider(self) -> None:
        from kultrun.main import resolve_configuration

        loaded = resolve_configuration({ESTIMATOR_VARIABLE: "llmfit"}).section(
            PlatformSettings
        )
        assert loaded.model_requirement_estimator == "llmfit"


class TestKultrunEstimator:
    def test_packaged_lookup_preserves_curated_method(self) -> None:
        estimator = KultrunRequirementEstimator()
        tiny = next(
            entry
            for entry in packaged_candidates()
            if entry.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        result = estimator.estimate(_request(tiny))
        assert result.estimator_provider == "kultrun"
        assert result.estimation_method == "curated"
        assert result.estimated_vram_bytes == tiny.requirement.estimated_vram_bytes
        assert result.measured is False

    def test_expanded_candidates_report_formula_v0(self) -> None:
        estimator = KultrunRequirementEstimator()
        extra = next(
            entry
            for entry in packaged_candidates()
            if entry.metadata.logical_name.value not in ORIGINAL_FIXTURES
        )
        result = estimator.estimate(_request(extra))
        assert result.estimation_method == "formula_v0"

    def test_quantization_mismatch_is_unsupported(self) -> None:
        result = KultrunRequirementEstimator().estimate(_request(quantization="fp16"))
        assert result.estimation_method == "unsupported"
        assert not is_resolved(result.estimated_vram_bytes)
        assert result.estimated_vram_bytes != 0

    def test_context_mismatch_is_unsupported(self) -> None:
        result = KultrunRequirementEstimator().estimate(_request(context=13))
        assert result.estimation_method == "unsupported"

    def test_offload_is_unsupported(self) -> None:
        result = KultrunRequirementEstimator().estimate(_request(offload=True))
        assert result.estimation_method == "unsupported"

    def test_tensor_parallel_is_unsupported(self) -> None:
        result = KultrunRequirementEstimator().estimate(_request(tensor_parallel=2))
        assert result.estimation_method == "unsupported"


class TestLlmfitEstimator:
    def test_fixture_plan_normalizes_to_bytes(self) -> None:
        tiny = next(
            entry
            for entry in packaged_candidates()
            if entry.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        result = _fixture_llmfit().estimate(_request(tiny))
        assert result.estimator_provider == "llmfit"
        assert result.estimator_version == TESTED_VERSION
        assert result.estimation_method == "llmfit-plan"
        assert result.assumed_context_tokens == 2048
        assert isinstance(result.estimated_vram_bytes, int)
        assert result.estimated_vram_bytes == round(1.18099681272 * GiB)
        assert result.ram_bytes == 8 * GiB
        assert result.measured is False
        assert not is_resolved(result.storage_bytes)

    def test_unknown_is_never_zero_when_unavailable(self) -> None:
        def missing(model: str, context: int, quant: str) -> dict[str, object]:
            raise FileNotFoundError("llmfit executable not found")

        result = LlmfitRequirementEstimator(plan=missing).estimate(_request())
        assert result.estimation_method == "provider-unavailable"
        for field in (
            "ram_bytes",
            "estimated_vram_bytes",
            "vram_weights_bytes",
            "storage_bytes",
            "peak_additional_bytes",
        ):
            value = getattr(result, field)
            assert not is_resolved(value)
            assert value != 0

    def test_substituted_quantization_is_rejected(self) -> None:
        def swapped(model: str, context: int, quant: str) -> dict[str, object]:
            return {
                "model_name": model,
                "context": context,
                "quantization": "F16",
                "minimum": {"vram_gb": 1.0, "ram_gb": 8.0},
            }

        result = LlmfitRequirementEstimator(plan=swapped).estimate(_request())
        assert result.estimation_method == "unsupported"
        assert "substituted quantization" in result.assumptions[0]

    def test_unmapped_quantization_is_unsupported(self) -> None:
        result = _fixture_llmfit().estimate(_request(quantization="mystery-quant"))
        assert result.estimation_method == "unsupported"

    def test_cpu_only_uses_cpu_run_path_ram(self) -> None:
        tiny = next(
            entry
            for entry in packaged_candidates()
            if entry.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        result = _fixture_llmfit().estimate(
            _request(tiny, placement=MemoryPlacement.CPU_ONLY)
        )
        assert not is_resolved(result.estimated_vram_bytes)
        assert isinstance(result.ram_bytes, int)
        assert result.ram_bytes < 8 * GiB


class TestEstimatorCNeedsNoPlanningChange:
    def test_a_third_provider_implements_only_the_port(self) -> None:
        class EstimatorC:
            identity = Name("estimator-c")
            version = "test"

            def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
                return unavailable_requirement(
                    request,
                    provider="estimator-c",
                    version="test",
                    method="constant",
                    reason="test-only provider C",
                )

        extra = EstimatorC()
        assert isinstance(extra, ModelRequirementEstimator)
        planning = (
            Path(__file__).resolve().parent.parent / "src" / "kultrun" / "planning"
        )
        for path in planning.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "estimator-c" not in text
            assert "llmfit" not in text
            assert "KultrunRequirementEstimator" not in text
            assert "RequirementEvidenceReconciler" not in text
        result = extra.estimate(_request())
        assert result.estimator_provider == "estimator-c"


class TestLlmfitAbsenceDoesNotBreakKultrun:
    def test_default_build_does_not_require_llmfit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", raising=False)
        monkeypatch.setenv("PATH", "/nonexistent")
        configuration = config_schema().load(
            {"platform": {"state_root": str(tmp_path / "state")}}
        )
        platform = build(configuration)
        assert platform.selection.estimator.identity.value == "kultrun"
        tiny = packaged_candidates()[0]
        result = platform.selection.estimator.estimate(_request(tiny))
        assert result.estimator_provider == "kultrun"
        assert is_resolved(result.estimated_vram_bytes)
