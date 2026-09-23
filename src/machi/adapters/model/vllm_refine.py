"""vLLM serving overhead. The formula stays the estimate; this adds the runtime."""

from __future__ import annotations

from machi.kernel.unresolved import NOT_MEASURED, Maybe, is_resolved
from machi.model.estimate import ServingEstimate, apply_overhead

_FLOOR = 768 * 1024 * 1024
_DIVISOR = 8


def refine_vllm(estimate: ServingEstimate) -> ServingEstimate:
    """Engine workspace is explicit. It does not invent KV or weights."""
    weights = estimate.weights_vram_bytes
    overhead: Maybe[int]
    if isinstance(weights, int) and is_resolved(weights):
        overhead = max(_FLOOR, weights // _DIVISOR)
    else:
        overhead = NOT_MEASURED
    refined = apply_overhead(estimate, overhead)
    return ServingEstimate(
        weights_vram_bytes=refined.weights_vram_bytes,
        kv_cache_vram_bytes=refined.kv_cache_vram_bytes,
        runtime_overhead_vram_bytes=refined.runtime_overhead_vram_bytes,
        workspace_activation_bytes=refined.workspace_activation_bytes,
        safety_allowance_bytes=refined.safety_allowance_bytes,
        total_required_vram_bytes=refined.total_required_vram_bytes,
        required_ram_bytes=refined.required_ram_bytes,
        incremental_storage_bytes=refined.incremental_storage_bytes,
        context=refined.context,
        concurrency=refined.concurrency,
        tensor_parallel=refined.tensor_parallel,
        confidence=refined.confidence,
        provenance="machi.formula+vllm_workspace",
        measured=False,
    )
