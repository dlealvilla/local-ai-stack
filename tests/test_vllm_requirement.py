"""Stage 1.6L — runtime-aware ModelRequirement for native vLLM."""

from __future__ import annotations

import json
from pathlib import Path

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import LlmfitRequirementEstimator, fixture_plan
from kultrun.adapters.estimators.vllm_serving import (
    VLLM_ENGINE_FLOOR_BYTES,
    VLLM_ENGINE_WEIGHT_DIVISOR,
    compose_vllm_vram,
    vllm_engine_workspace_bytes,
)
from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import MemoryPlacement, ModelEstimationRequest
from kultrun.planning.contracts import CompatibilityVerdict, SelectionPolicy
from kultrun.planning.evaluate import evaluate
from tests.test_estimators import _request
from tests.test_planning_selection import _capacity, _metadata, _requirement

GiB = 1024**3
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"
QWEN = "qwen2.5-7b-instruct-awq"
SOURCE_REF = "Qwen/Qwen2.5-7B-Instruct-AWQ"


def _qwen():
    return next(
        entry
        for entry in packaged_candidates()
        if entry.metadata.logical_name.value == QWEN
    )


class TestLlmfitDiagnostic:
    def test_captured_llmfit_minimum_is_below_eight_gib(self) -> None:
        payload = json.loads(
            (FIXTURE_ROOT / "qwen2.5-7b-instruct-awq.json").read_text(encoding="utf-8")
        )
        assert payload["context"] == 8192
        assert payload["quantization"] == "AWQ-4bit"
        assert payload["minimum"]["vram_gb"] < 8.0
        kv = next(
            item["kv_cache_gb"]
            for item in payload["kv_alternatives"]
            if item["kv_quant"] == "fp16"
        )
        assert abs(kv - 0.4375) < 1e-9
        raw = LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT)).estimate(
            _request(_qwen(), context=8192, runtime="llama.cpp")
        )
        assert raw.estimator_provider == "llmfit"
        assert raw.estimated_vram_bytes == round(payload["minimum"]["vram_gb"] * GiB)
        assert raw.estimated_vram_bytes < 8 * GiB
        serving = LlmfitRequirementEstimator(plan=fixture_plan(FIXTURE_ROOT)).estimate(
            _request(_qwen(), context=8192)
        )
        assert serving.estimator_provider == "llmfit"
        assert not is_resolved(serving.estimated_vram_bytes)
        assert (
            "llmfit plan minimum is not native vLLM serving demand"
            in serving.assumptions
        )


class TestKultrunVllmServing:
    def test_qwen_vllm_8192_exceeds_packaged_eight_gib(self) -> None:
        entry = _qwen()
        result = KultrunRequirementEstimator().estimate(_request(entry, context=8192))
        assert entry.requirement.estimated_vram_bytes == 8 * GiB
        assert is_resolved(result.estimated_vram_bytes)
        assert result.estimated_vram_bytes > 8 * GiB
        assert result.assumed_context_tokens == 8192
        assert result.assumed_batch_size == 1
        assert is_resolved(result.vram_weights_bytes)
        assert is_resolved(result.vram_kv_cache_bytes)
        assert is_resolved(result.vram_overhead_bytes)
        assert is_resolved(result.safety_allowance_bytes)
        assert "Qwen" not in "".join(result.assumptions)
        assert "8.3" not in "".join(result.assumptions)
        assert result.safety_allowance_bytes == vllm_engine_workspace_bytes(
            result.vram_weights_bytes
        )
        expected = compose_vllm_vram(
            weights_bytes=entry.requirement.vram_weights_bytes,
            kv_per_token=entry.requirement.vram_kv_bytes_per_token,
            context_tokens=8192,
            batch_size=1,
            overhead_bytes=entry.requirement.vram_overhead_bytes,
            activation_bytes=entry.requirement.activation_bytes,
        )
        assert result.estimated_vram_bytes == expected.total_bytes

    def test_context_scales_kv_and_total(self) -> None:
        estimator = KultrunRequirementEstimator()
        entry = _qwen()
        short = estimator.estimate(_request(entry, context=4096))
        long = estimator.estimate(_request(entry, context=8192))
        assert long.vram_kv_cache_bytes == 2 * short.vram_kv_cache_bytes
        assert long.estimated_vram_bytes - long.vram_kv_cache_bytes == (
            short.estimated_vram_bytes - short.vram_kv_cache_bytes
        )

    def test_runtime_change_changes_total(self) -> None:
        entry = _qwen()
        vllm = KultrunRequirementEstimator().estimate(_request(entry, context=8192))
        other = KultrunRequirementEstimator().estimate(
            ModelEstimationRequest(
                model_id=entry.metadata.model_id,
                source_ref=entry.metadata.source_ref,
                source_revision=entry.metadata.source_revision,
                artifact_format=NOT_PROVIDED,
                quantization=entry.metadata.quantization,
                context_tokens=8192,
                runtime="llama.cpp",
                placement=MemoryPlacement.DISCRETE_GPU,
                offload_allowed=False,
                tensor_parallel=1,
                batch_size=1,
            )
        )
        assert vllm.estimated_vram_bytes != other.estimated_vram_bytes
        assert is_resolved(vllm.safety_allowance_bytes)
        assert not is_resolved(other.safety_allowance_bytes)

    def test_quantization_mismatch_is_unsupported(self) -> None:
        result = KultrunRequirementEstimator().estimate(
            _request(_qwen(), quantization="fp16")
        )
        assert result.estimation_method == "unsupported"
        assert not is_resolved(result.estimated_vram_bytes)

    def test_unresolved_kv_is_unresolved_total(self) -> None:
        tiny = next(
            entry
            for entry in packaged_candidates()
            if entry.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        result = KultrunRequirementEstimator().estimate(_request(tiny))
        assert not is_resolved(tiny.requirement.vram_kv_bytes_per_token)
        assert not is_resolved(result.estimated_vram_bytes)
        assert result.estimated_vram_bytes != 0

    def test_engine_allowance_is_explicit_and_not_qwen_specific(self) -> None:
        assert VLLM_ENGINE_FLOOR_BYTES == 768 * 1024 * 1024
        assert VLLM_ENGINE_WEIGHT_DIVISOR == 8
        small = vllm_engine_workspace_bytes(GiB)
        large = vllm_engine_workspace_bytes(40 * GiB)
        assert small == VLLM_ENGINE_FLOOR_BYTES
        assert large == 5 * GiB


class TestFeasibilityPredicates:
    def test_required_above_available_vram_is_infeasible_vram(self) -> None:
        meta = _metadata()
        req = _requirement(meta.model_id, estimated_vram_bytes=20 * GiB, ram_bytes=GiB)
        capacity = _capacity(vram=30 * GiB)
        from dataclasses import replace

        squeezed = replace(capacity, available_vram_bytes=18 * GiB)
        result = evaluate(
            meta,
            req,
            squeezed,
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        )
        assert "infeasible_vram" in result.reasons
        assert result.available_vram_bytes == 18 * GiB
        assert result.safe_vram_bytes == 30 * GiB

    def test_unresolved_requirement_is_not_feasible(self) -> None:
        meta = _metadata()
        req = _requirement(
            meta.model_id, estimated_vram_bytes=NOT_PROVIDED, ram_bytes=GiB
        )
        result = evaluate(
            meta,
            req,
            _capacity(),
            SelectionPolicy(),
            runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        )
        assert result.capacity_fit.value == "unresolved"
        assert result.required_vram_bytes != 0
