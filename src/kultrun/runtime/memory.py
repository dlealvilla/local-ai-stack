"""Runtime-memory classing, pressure, and measured-profile arithmetic.

Core-owned. No process launch, no ResourceManager, no model imports.
vLLM log interpretation lives in the adapter; this module consumes numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_UNRESOLVED = "unresolved"


def is_vllm_family(runtime: object) -> bool:
    """True only for the native vLLM family identity."""
    if not isinstance(runtime, str):
        return False
    return runtime.strip().lower().replace("-", "_") == "vllm"


def normalize_token(value: object) -> str | None:
    """Lowercase identity token. Empty and non-strings are unresolved."""
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    return token or None


@dataclass(frozen=True, slots=True)
class RuntimeMemoryClassKey:
    """Deterministic validation class. Not a clustering engine."""

    token: str
    singleton: bool
    runtime: str
    runtime_version: str
    executor: str
    capability_basis: str
    accelerator_architecture: str
    model_architecture: str
    quantization: str
    kv_dtype: str
    context_tokens: str
    concurrency: str
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class PressureMember:
    """One estimated-feasible candidate's pressure against one snapshot."""

    model_id: str
    required_vram_bytes: int
    vram_pressure: float


@dataclass(frozen=True, slots=True)
class RuntimeExtraResult:
    """Derived runtime-extra, or a typed invalid result. Never silently zero."""

    extra_bytes: int | None
    valid: bool
    reason: str | None = None


def runtime_memory_class(
    *,
    runtime: object,
    runtime_version: object,
    executor: object,
    capability_basis: object,
    accelerator_architecture: object,
    model_architecture: object,
    quantization: object,
    context_tokens: object,
    concurrency: object,
    kv_dtype: object = None,
    model_id: object = None,
) -> RuntimeMemoryClassKey:
    """Same material metadata → same class. Unresolved material → singleton."""
    runtime_n = normalize_token(runtime) or _UNRESOLVED
    version_n = normalize_token(runtime_version) or _UNRESOLVED
    executor_n = normalize_token(executor) or _UNRESOLVED
    basis_n = normalize_token(capability_basis) or _UNRESOLVED
    accel_n = normalize_token(accelerator_architecture) or _UNRESOLVED
    arch_n = normalize_token(model_architecture) or _UNRESOLVED
    quant_n = normalize_token(quantization) or _UNRESOLVED
    kv_n = normalize_token(kv_dtype) or "unknown"
    context_n = _int_token(context_tokens)
    concurrency_n = _int_token(concurrency)
    material = (
        runtime_n,
        version_n,
        executor_n,
        basis_n,
        accel_n,
        arch_n,
        quant_n,
        context_n,
        concurrency_n,
    )
    singleton = _UNRESOLVED in material
    ident = normalize_token(model_id) if singleton else None
    if singleton and ident is None:
        ident = "missing-model-id"
    parts = (
        "v1",
        runtime_n,
        version_n,
        executor_n,
        basis_n,
        accel_n,
        arch_n,
        quant_n,
        kv_n,
        context_n,
        concurrency_n,
    )
    token = "|".join(parts)
    if singleton:
        token = f"singleton|{ident}|{token}"
    return RuntimeMemoryClassKey(
        token=token,
        singleton=singleton,
        runtime=runtime_n,
        runtime_version=version_n,
        executor=executor_n,
        capability_basis=basis_n,
        accelerator_architecture=accel_n,
        model_architecture=arch_n,
        quantization=quant_n,
        kv_dtype=kv_n,
        context_tokens=context_n,
        concurrency=concurrency_n,
        model_id=ident,
    )


def vram_pressure(required_bytes: int, available_bytes: int) -> float:
    """required / available. Unknown-as-zero is forbidden; callers pass ints."""
    if available_bytes <= 0:
        return math.inf if required_bytes > 0 else 0.0
    return required_bytes / available_bytes


def select_sentinel(members: tuple[PressureMember, ...]) -> PressureMember:
    """Highest VRAM pressure. Not parameter count."""
    if not members:
        raise ValueError("a validation class needs at least one member")
    ordered = sorted(
        members,
        key=lambda item: (
            -item.vram_pressure,
            -item.required_vram_bytes,
            item.model_id,
        ),
    )
    return ordered[0]


def probe_order(sentinels: tuple[PressureMember, ...]) -> tuple[PressureMember, ...]:
    """Global probe order: highest-pressure sentinel first."""
    return tuple(
        sorted(
            sentinels,
            key=lambda item: (
                -item.vram_pressure,
                -item.required_vram_bytes,
                item.model_id,
            ),
        )
    )


def measured_non_kv_bytes(probe_budget_bytes: int, available_kv_bytes: int) -> int:
    """B - K. Negative K is usable evidence."""
    return probe_budget_bytes - available_kv_bytes


def runtime_extra_bytes(
    measured_non_kv: object, model_load_bytes: object
) -> RuntimeExtraResult:
    """non-KV minus model-load. Negative/NaN/inf are invalid, never zero."""
    if not isinstance(measured_non_kv, int) or not isinstance(model_load_bytes, int):
        return RuntimeExtraResult(
            extra_bytes=None,
            valid=False,
            reason="model_load_or_non_kv_unresolved",
        )
    extra = measured_non_kv - model_load_bytes
    if not math.isfinite(float(extra)):
        return RuntimeExtraResult(
            extra_bytes=None,
            valid=False,
            reason="runtime_extra_not_finite",
        )
    if extra < 0:
        return RuntimeExtraResult(
            extra_bytes=None,
            valid=False,
            reason="runtime_extra_negative",
        )
    return RuntimeExtraResult(extra_bytes=extra, valid=True)


def base_model_memory(
    provider_base_bytes: int, factual_weight_lower_bound: int | None
) -> int:
    """Factual Safetensors floor. Not estimator shopping."""
    if factual_weight_lower_bound is None:
        return provider_base_bytes
    return max(provider_base_bytes, factual_weight_lower_bound)


def runtime_extra_ratio(
    runtime_extra: object, model_load_bytes: object
) -> float | None:
    """extra / load. Invalid when load is not a positive finite denominator."""
    if not isinstance(runtime_extra, int) or not isinstance(model_load_bytes, int):
        return None
    if model_load_bytes <= 0:
        return None
    ratio = runtime_extra / model_load_bytes
    if not math.isfinite(ratio) or ratio < 0:
        return None
    return ratio


def calibrated_runtime_extra(
    *,
    static_runtime_extra: int,
    sentinel_floor: int | None,
    sentinel_ratio: float | None,
    candidate_base_bytes: int,
) -> int:
    """Same-class transfer. May only raise the static extra."""
    extra = static_runtime_extra
    if sentinel_floor is not None:
        extra = max(extra, sentinel_floor)
    if (
        sentinel_ratio is not None
        and math.isfinite(sentinel_ratio)
        and sentinel_ratio >= 0
    ):
        extra = max(extra, round(sentinel_ratio * candidate_base_bytes))
    return extra


def compose_serving_vram(
    *,
    base_model_bytes: int,
    runtime_extra_bytes: int,
    kv_bytes: int,
    safety_bytes: int,
    activation_bytes: int = 0,
) -> int:
    """Non-overlapping VRAM parts. Callers must not pass negative components."""
    return (
        base_model_bytes
        + runtime_extra_bytes
        + kv_bytes
        + safety_bytes
        + activation_bytes
    )


def raise_only(static_total: int, calibrated_total: int) -> tuple[int, bool]:
    """Calibration may not reduce demand. Unexpected lowering is flagged."""
    if calibrated_total < static_total:
        return static_total, True
    return calibrated_total, False


def _int_token(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        return _UNRESOLVED
    return str(value)
