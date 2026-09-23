"""Serving-byte estimate. Unknown stays unresolved. This does not authorize."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe
from machi.model.metadata import NormalizedMetadata

_DTYPE_BYTES = {"float32": 4, "float16": 2, "bfloat16": 2, "half": 2}


@dataclass(frozen=True, slots=True)
class ServingEstimate:
    """Parts of one serving configuration. Not a reservation."""

    weights_vram_bytes: Maybe[int]
    kv_cache_vram_bytes: Maybe[int]
    runtime_overhead_vram_bytes: Maybe[int]
    workspace_activation_bytes: Maybe[int]
    safety_allowance_bytes: Maybe[int]
    total_required_vram_bytes: Maybe[int]
    required_ram_bytes: Maybe[int]
    incremental_storage_bytes: Maybe[int]
    context: int
    concurrency: int
    tensor_parallel: int
    confidence: str
    provenance: str
    measured: bool


def estimate_serving(
    metadata: NormalizedMetadata,
    *,
    weight_bytes: int | None,
    storage_bytes: int | None,
    context: int,
    concurrency: int,
    tensor_parallel: int = 1,
) -> ServingEstimate:
    """Generic attention KV plus known weight bytes. Overhead stays unresolved."""
    weights: Maybe[int] = weight_bytes if weight_bytes is not None else NOT_MEASURED
    storage: Maybe[int] = storage_bytes if storage_bytes is not None else NOT_MEASURED
    kv = _kv(metadata, context=context, concurrency=concurrency)
    total = _sum(weights, kv)
    return ServingEstimate(
        weights_vram_bytes=weights,
        kv_cache_vram_bytes=kv,
        runtime_overhead_vram_bytes=NOT_PROVIDED,
        workspace_activation_bytes=NOT_PROVIDED,
        safety_allowance_bytes=NOT_PROVIDED,
        total_required_vram_bytes=total,
        required_ram_bytes=NOT_MEASURED,
        incremental_storage_bytes=storage,
        context=context,
        concurrency=concurrency,
        tensor_parallel=tensor_parallel,
        confidence="estimated" if isinstance(total, int) else "unresolved",
        provenance="machi.formula",
        measured=False,
    )


def apply_overhead(estimate: ServingEstimate, overhead: Maybe[int]) -> ServingEstimate:
    """Add a runtime-specific overhead. Missing overhead keeps the total unknown."""
    total = _sum(estimate.weights_vram_bytes, estimate.kv_cache_vram_bytes, overhead)
    return ServingEstimate(
        weights_vram_bytes=estimate.weights_vram_bytes,
        kv_cache_vram_bytes=estimate.kv_cache_vram_bytes,
        runtime_overhead_vram_bytes=overhead,
        workspace_activation_bytes=estimate.workspace_activation_bytes,
        safety_allowance_bytes=estimate.safety_allowance_bytes,
        total_required_vram_bytes=total,
        required_ram_bytes=estimate.required_ram_bytes,
        incremental_storage_bytes=estimate.incremental_storage_bytes,
        context=estimate.context,
        concurrency=estimate.concurrency,
        tensor_parallel=estimate.tensor_parallel,
        confidence="estimated" if isinstance(total, int) else "unresolved",
        provenance=estimate.provenance,
        measured=False,
    )


def _kv(
    metadata: NormalizedMetadata, *, context: int, concurrency: int
) -> Maybe[int]:
    layers = metadata.layer_count
    heads = metadata.key_value_heads
    width = metadata.explicit_head_dim
    if not isinstance(width, int):
        width = metadata.derived_head_dim
    if not all(isinstance(item, int) for item in (layers, heads, width)):
        return NOT_MEASURED
    if not isinstance(metadata.dtype, str):
        return NOT_MEASURED
    element = _DTYPE_BYTES.get(metadata.dtype)
    if element is None:
        return NOT_MEASURED
    assert isinstance(layers, int)
    assert isinstance(heads, int)
    assert isinstance(width, int)
    return 2 * layers * heads * width * context * concurrency * element


def _sum(*parts: Maybe[int]) -> Maybe[int]:
    if not all(isinstance(item, int) for item in parts):
        return NOT_MEASURED
    return sum(int(item) for item in parts if isinstance(item, int))
