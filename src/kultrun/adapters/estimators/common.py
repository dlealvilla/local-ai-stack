"""Blank and assumption-preserving requirement helpers."""

from __future__ import annotations

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.model.contracts import ModelEstimationRequest, ModelRequirement


def unavailable_requirement(
    request: ModelEstimationRequest,
    *,
    provider: str,
    version: str,
    method: str,
    reason: str,
) -> ModelRequirement:
    """Every load-bearing field unresolved. Never zero."""
    return ModelRequirement(
        model_id=request.model_id,
        confidence=Confidence.UNKNOWN,
        storage_bytes=NOT_PROVIDED,
        peak_additional_bytes=NOT_PROVIDED,
        vram_weights_bytes=NOT_PROVIDED,
        vram_kv_bytes_per_token=NOT_PROVIDED,
        vram_overhead_bytes=NOT_PROVIDED,
        ram_bytes=NOT_PROVIDED,
        unified_memory_bytes=NOT_PROVIDED,
        activation_bytes=NOT_PROVIDED,
        estimated_vram_bytes=NOT_PROVIDED,
        assumed_context_tokens=request.context_tokens,
        supported_runtimes=(),
        estimation_method=method,
        estimator_provider=provider,
        estimator_version=version,
        assumptions=(reason,),
        measured=False,
    )
