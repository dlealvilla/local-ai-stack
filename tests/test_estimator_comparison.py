"""Development-only estimator comparison. Not product ranking."""

from __future__ import annotations

from pathlib import Path

from tools.compare_model_estimators import (
    GOOD_RELATIVE,
    WARNING_RELATIVE,
    classify_relative,
    compare_catalog,
    compare_pair,
    estimation_request,
    relative_difference,
)

from kultrun.adapters.estimators.kultrun import KultrunRequirementEstimator
from kultrun.adapters.estimators.llmfit import LlmfitRequirementEstimator
from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.model.contracts import MemoryPlacement, ModelEstimationRequest

GiB = 1024**3


class TestThresholdsLiveInTheTool:
    def test_thresholds_are_not_selection_policy(self) -> None:
        planning = (
            Path(__file__).resolve().parent.parent / "src" / "kultrun" / "planning"
        )
        for path in planning.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "GOOD_RELATIVE" not in text
            assert "LARGE_DIFFERENCE" not in text
        assert GOOD_RELATIVE == 0.15
        assert WARNING_RELATIVE == 0.35
        assert classify_relative(0.15) == "GOOD"
        assert classify_relative(0.16) == "WARNING"
        assert classify_relative(0.35) == "WARNING"
        assert classify_relative(0.36) == "LARGE_DIFFERENCE"
        assert relative_difference(85, 100) == 0.15


class TestFixtureComparison:
    def test_tinyllama_vram_is_close(self) -> None:
        report = compare_catalog(live=False)
        tiny = next(
            item
            for item in report["comparisons"]
            if item["logical_name"] == "tinyllama-1.1b-chat-q4"
        )
        vram = next(
            field
            for field in tiny["fields"]
            if field["field"] == "estimated_vram_bytes"
        )
        assert vram["classification"] == "GOOD"
        ram = next(field for field in tiny["fields"] if field["field"] == "ram_bytes")
        assert ram["classification"] == "LARGE_DIFFERENCE"
        assert ram["llmfit"] == 8 * GiB

    def test_qwen_7b_awq_vram_is_a_large_documented_gap(self) -> None:
        report = compare_catalog(live=False)
        qwen = next(
            item
            for item in report["comparisons"]
            if item["logical_name"] == "qwen2.5-7b-instruct-awq"
        )
        vram = next(
            field
            for field in qwen["fields"]
            if field["field"] == "estimated_vram_bytes"
        )
        assert vram["classification"] == "LARGE_DIFFERENCE"
        assert vram["lower_provider"] == "llmfit"
        assert qwen["overall_classification"] == "LARGE_DIFFERENCE"

    def test_same_request_identity_for_every_overlap(self) -> None:
        report = compare_catalog(live=False)
        assert report["product_feature"] is False
        assert report["candidate_count"] == len(packaged_candidates())
        for item in report["comparisons"]:
            assert item["kultrun"]["context_tokens"] == item["context_tokens"]
            assert item["llmfit"]["context_tokens"] in {item["context_tokens"], None}

    def test_assumption_mismatch_when_context_is_substituted_in_a_request(self) -> None:
        entry = packaged_candidates()[0]
        request = estimation_request(entry)
        broken = ModelEstimationRequest(
            model_id=request.model_id,
            source_ref=request.source_ref,
            source_revision=request.source_revision,
            artifact_format=NOT_PROVIDED,
            quantization=request.quantization,
            context_tokens=13,
            runtime=request.runtime,
            placement=MemoryPlacement.DISCRETE_GPU,
            offload_allowed=False,
        )
        kultrun = KultrunRequirementEstimator().estimate(broken)
        llmfit = LlmfitRequirementEstimator(
            plan=lambda model, context, quant: {
                "model_name": model,
                "context": 2048,
                "quantization": quant,
                "minimum": {"vram_gb": 1.0, "ram_gb": 8.0},
            }
        ).estimate(broken)
        compared = compare_pair(entry, kultrun, llmfit, broken)
        assert compared["overall_classification"] == "ASSUMPTION_MISMATCH"
        assert compared["assumption_mismatch"]

    def test_report_is_not_a_product_module(self) -> None:
        source = Path(__file__).resolve().parent.parent / "src" / "kultrun"
        for path in source.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "compare_model_estimators" not in text
            assert "RequirementEvidenceReconciler" not in text
