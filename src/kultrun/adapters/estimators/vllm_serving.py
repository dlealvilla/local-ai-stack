"""Native vLLM serving VRAM composition.

Kultrun owns ModelRequirement. This module is estimator-seam arithmetic for
the vLLM runtime family — not the vLLM adapter, ResourceManager, or selector.

The fresh-host T3 showed that a static packaged total of 8.0 GiB left the
runtime with ~0.21 GiB KV after a ~5.29 GiB weight load, while context 8192
needed ~0.44 GiB. The missing demand is engine/workspace remainder, not a
model-specific constant.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

MIB = 1024**2

#: CUDA graphs, torch compile, and allocator slack for native vLLM.
#: Floor 768 MiB; otherwise one eighth of weight bytes. Explicit allowance,
#: not a buried multiplier on the total.
VLLM_ENGINE_FLOOR_BYTES = 768 * MIB
VLLM_ENGINE_WEIGHT_DIVISOR = 8

VLLM_RUNTIME = "vllm"


def is_vllm_runtime(runtime: object) -> bool:
    if not is_resolved(runtime) or not isinstance(runtime, str):
        return False
    return runtime.strip().lower().replace("-", "_") == VLLM_RUNTIME


def vllm_engine_workspace_bytes(weights_bytes: int) -> int:
    """Deterministic native-vLLM engine/workspace remainder."""
    if weights_bytes <= 0:
        return VLLM_ENGINE_FLOOR_BYTES
    return max(VLLM_ENGINE_FLOOR_BYTES, weights_bytes // VLLM_ENGINE_WEIGHT_DIVISOR)


def kv_cache_bytes(per_token: int, context_tokens: int, batch_size: int) -> int:
    """KV demand for the requested context and concurrency assumption."""
    return per_token * context_tokens * batch_size


@dataclass(frozen=True, slots=True)
class VllmServingBreakdown:
    """Explainable VRAM parts. Unresolved parts stay unresolved."""

    weights_bytes: Maybe[int]
    kv_cache_bytes: Maybe[int]
    overhead_bytes: Maybe[int]
    activation_bytes: Maybe[int]
    safety_allowance_bytes: Maybe[int]
    total_bytes: Maybe[int]
    unresolved: tuple[str, ...]
    assumptions: tuple[str, ...]


def compose_vllm_vram(
    *,
    weights_bytes: object,
    kv_per_token: object,
    context_tokens: object,
    batch_size: int,
    overhead_bytes: object,
    activation_bytes: object,
) -> VllmServingBreakdown:
    """Sum resolved vLLM serving parts. Unknown load-bearing values stay unknown."""
    unresolved: list[str] = []
    assumptions = (
        "native vLLM serving composition",
        "single device",
        f"concurrency batch_size={batch_size}",
        (
            "vLLM engine workspace = max("
            f"{VLLM_ENGINE_FLOOR_BYTES} bytes, "
            f"weights/{VLLM_ENGINE_WEIGHT_DIVISOR})"
        ),
    )
    weights: Maybe[int] = (
        weights_bytes if isinstance(weights_bytes, int) else NOT_PROVIDED
    )
    if not isinstance(weights, int):
        unresolved.append("vram_weights_bytes")
    kv_total: Maybe[int] = NOT_PROVIDED
    if (
        isinstance(kv_per_token, int)
        and isinstance(context_tokens, int)
        and batch_size >= 1
    ):
        kv_total = kv_cache_bytes(kv_per_token, context_tokens, batch_size)
    else:
        unresolved.append("vram_kv_cache_bytes")
    overhead: Maybe[int] = (
        overhead_bytes if isinstance(overhead_bytes, int) else NOT_PROVIDED
    )
    if not isinstance(overhead, int):
        unresolved.append("vram_overhead_bytes")
    activation: Maybe[int] = (
        activation_bytes if isinstance(activation_bytes, int) else NOT_PROVIDED
    )
    safety: Maybe[int] = NOT_PROVIDED
    if isinstance(weights, int):
        safety = vllm_engine_workspace_bytes(weights)
    else:
        unresolved.append("safety_allowance_bytes")
    if (
        unresolved
        or not isinstance(weights, int)
        or not isinstance(kv_total, int)
        or not isinstance(overhead, int)
        or not isinstance(safety, int)
    ):
        return VllmServingBreakdown(
            weights_bytes=weights,
            kv_cache_bytes=kv_total,
            overhead_bytes=overhead,
            activation_bytes=activation,
            safety_allowance_bytes=safety,
            total_bytes=NOT_PROVIDED,
            unresolved=tuple(unresolved),
            assumptions=assumptions,
        )
    total = weights + kv_total + overhead + safety
    if isinstance(activation, int):
        total += activation
    return VllmServingBreakdown(
        weights_bytes=weights,
        kv_cache_bytes=kv_total,
        overhead_bytes=overhead,
        activation_bytes=activation,
        safety_allowance_bytes=safety,
        total_bytes=total,
        unresolved=(),
        assumptions=assumptions,
    )
