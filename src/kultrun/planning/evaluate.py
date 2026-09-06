"""Host-independent requirement math lives in estimators; this is fit.

Planning consumes ModelRequirement and CapacityEnvelope.SAFE. It does not
import an estimator adapter.
"""

from __future__ import annotations

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.kernel.unresolved import (
    NOT_PROVIDED,
    Maybe,
    Unresolved,
    UnresolvedReason,
    is_resolved,
)
from kultrun.model.contracts import MemoryPlacement, ModelMetadata, ModelRequirement
from kultrun.planning.contracts import (
    CapacityFitClass,
    CapacityUtilization,
    CompatibilityVerdict,
    DeploymentCapacity,
    ModelEvaluation,
    SelectionPolicy,
)

_QUANT_RANK = {
    "fp16": 40,
    "f16": 40,
    "bf16": 40,
    "q8_0": 30,
    "q8": 30,
    "awq": 20,
    "q5_k": 15,
    "q4_k": 10,
    "q4_k_m": 10,
    "gptq-int4": 10,
}


def deployment_capacity(envelope: CapacityEnvelope) -> DeploymentCapacity:
    """SAFE slice for v0: first assigned GPU, else CPU-only.

    Unified memory is a seam: Stage 1.2 does not assert a GPU budget on
    unified hosts, so this does not invent one.
    """
    gpu = next(
        (
            accelerator
            for accelerator in envelope.accelerators
            if is_resolved(accelerator.memory.safe_bytes)
        ),
        None,
    )
    storage = next(
        (
            pool.space.safe_bytes
            for pool in envelope.pools
            if is_resolved(pool.space.safe_bytes)
        ),
        NOT_PROVIDED,
    )
    if gpu is not None:
        return DeploymentCapacity(
            host_id=envelope.host_id,
            host_fingerprint=envelope.host_fingerprint,
            placement=MemoryPlacement.DISCRETE_GPU,
            accelerator_index=gpu.index,
            safe_ram_bytes=envelope.memory.safe_bytes,
            safe_vram_bytes=gpu.memory.safe_bytes,
            safe_unified_bytes=NOT_PROVIDED,
            safe_storage_bytes=storage,
            envelope_policy_version=envelope.policy_version,
        )
    return DeploymentCapacity(
        host_id=envelope.host_id,
        host_fingerprint=envelope.host_fingerprint,
        placement=MemoryPlacement.CPU_ONLY,
        accelerator_index=None,
        safe_ram_bytes=envelope.memory.safe_bytes,
        safe_vram_bytes=NOT_PROVIDED,
        safe_unified_bytes=NOT_PROVIDED,
        safe_storage_bytes=storage,
        envelope_policy_version=envelope.policy_version,
    )


def _ratio(required: object, safe: object) -> Maybe[float]:
    if not is_resolved(required) or not is_resolved(safe):
        return NOT_PROVIDED
    if not isinstance(required, int) or not isinstance(safe, int):
        return NOT_PROVIDED
    if safe <= 0:
        return Unresolved(
            UnresolvedReason.UNSUPPORTED,
            "safe capacity is not a positive quantity",
        )
    return required / safe


def utilization(
    requirement: ModelRequirement, capacity: DeploymentCapacity
) -> CapacityUtilization:
    """Limiting-resource ratio. Storage is not included."""
    ram_ratio = _ratio(requirement.ram_bytes, capacity.safe_ram_bytes)
    if capacity.placement is MemoryPlacement.CPU_ONLY:
        limiting = ram_ratio
        ram_known = is_resolved(requirement.ram_bytes)
        return CapacityUtilization(
            ratio=limiting if ram_known else NOT_PROVIDED,
            limiting_resource=(
                "ram" if ram_known and is_resolved(ram_ratio) else NOT_PROVIDED
            ),
            ram_ratio=ram_ratio,
            vram_ratio=NOT_PROVIDED,
            unified_ratio=NOT_PROVIDED,
        )
    if capacity.placement is MemoryPlacement.UNIFIED_MEMORY:
        unified_ratio = _ratio(
            requirement.unified_memory_bytes, capacity.safe_unified_bytes
        )
        load = requirement.unified_memory_bytes
        return CapacityUtilization(
            ratio=unified_ratio if is_resolved(load) else NOT_PROVIDED,
            limiting_resource="unified_memory" if is_resolved(load) else NOT_PROVIDED,
            ram_ratio=ram_ratio,
            vram_ratio=NOT_PROVIDED,
            unified_ratio=unified_ratio,
        )
    vram = requirement.estimated_vram_bytes
    vram_ratio = _ratio(vram, capacity.safe_vram_bytes)
    if not is_resolved(vram):
        return CapacityUtilization(
            ratio=NOT_PROVIDED,
            limiting_resource=NOT_PROVIDED,
            ram_ratio=ram_ratio,
            vram_ratio=vram_ratio,
            unified_ratio=NOT_PROVIDED,
        )
    candidates: list[tuple[str, Maybe[float]]] = [("vram", vram_ratio)]
    if is_resolved(ram_ratio):
        candidates.append(("ram", ram_ratio))
    resolved: list[tuple[str, float]] = []
    for resource, value in candidates:
        if is_resolved(value):
            resolved.append((resource, value))
    if not resolved:
        return CapacityUtilization(
            ratio=NOT_PROVIDED,
            limiting_resource=NOT_PROVIDED,
            ram_ratio=ram_ratio,
            vram_ratio=vram_ratio,
            unified_ratio=NOT_PROVIDED,
        )
    name, value = max(resolved, key=lambda item: item[1])
    return CapacityUtilization(
        ratio=value,
        limiting_resource=name,
        ram_ratio=ram_ratio,
        vram_ratio=vram_ratio,
        unified_ratio=NOT_PROVIDED,
    )


def evaluate(
    metadata: ModelMetadata,
    requirement: ModelRequirement,
    capacity: DeploymentCapacity,
    available_runtimes: tuple[str, ...],
    policy: SelectionPolicy,
) -> ModelEvaluation:
    """One candidate, one envelope, one policy. Deterministic."""
    reasons: list[str] = []
    unresolved: list[str] = []
    compatibility = CompatibilityVerdict.COMPATIBLE
    available = set(available_runtimes)
    if metadata.supported_runtimes and available and not any(
        name in available for name in metadata.supported_runtimes
    ):
        compatibility = CompatibilityVerdict.UNSUPPORTED
        reasons.append("no overlapping runtime with this host")
    method = requirement.estimation_method
    if is_resolved(method) and method in {"unsupported", "provider-unavailable"}:
        compatibility = (
            CompatibilityVerdict.UNSUPPORTED
            if method == "unsupported"
            else CompatibilityVerdict.UNRESOLVED
        )
        reasons.extend(requirement.assumptions or (str(method),))

    storage_ok: object = NOT_PROVIDED
    peak = requirement.peak_additional_bytes
    if not is_resolved(peak):
        unresolved.append("peak_additional_bytes")
        storage_ok = NOT_PROVIDED
    elif is_resolved(capacity.safe_storage_bytes):
        storage_ok = peak <= capacity.safe_storage_bytes
        if not storage_ok:
            reasons.append("peak acquisition exceeds SAFE storage")
    else:
        unresolved.append("safe_storage_bytes")
        storage_ok = NOT_PROVIDED

    used = utilization(requirement, capacity)
    fit = CapacityFitClass.UNRESOLVED
    preferred = False
    if compatibility is CompatibilityVerdict.UNSUPPORTED:
        fit = CapacityFitClass.EXCEEDS_SAFE
        reasons.append("unsupported; not a capacity-fit candidate")
    elif storage_ok is False:
        fit = CapacityFitClass.EXCEEDS_SAFE
    elif compatibility is CompatibilityVerdict.UNRESOLVED or not is_resolved(
        used.ratio
    ):
        fit = CapacityFitClass.UNRESOLVED
        if not is_resolved(used.ratio):
            unresolved.append("capacity_utilization")
            reasons.append("load-bearing requirement or SAFE capacity is unknown")
    else:
        ratio = used.ratio
        if ratio > policy.maximum_capacity_utilization:
            fit = CapacityFitClass.EXCEEDS_SAFE
            reasons.append(
                "estimated deployment requirement exceeds safe capacity"
            )
        elif ratio < policy.minimum_capacity_utilization:
            fit = CapacityFitClass.UNDERUTILIZED
            reasons.append("underutilizes available deployment capacity")
        else:
            fit = CapacityFitClass.PREFERRED
            preferred = True
            reasons.append("inside the preferred capacity-fit band")

    return ModelEvaluation(
        model_id=metadata.model_id,
        logical_name=metadata.logical_name,
        source_ref=metadata.source_ref,
        compatibility=compatibility,
        capacity_fit=fit,
        storage_feasible=storage_ok if isinstance(storage_ok, bool) else NOT_PROVIDED,
        required_ram_bytes=requirement.ram_bytes,
        required_vram_bytes=requirement.estimated_vram_bytes,
        required_unified_bytes=requirement.unified_memory_bytes,
        required_storage_bytes=requirement.peak_additional_bytes,
        safe_ram_bytes=capacity.safe_ram_bytes,
        safe_vram_bytes=capacity.safe_vram_bytes,
        safe_unified_bytes=capacity.safe_unified_bytes,
        utilization=used,
        preferred=preferred,
        reasons=tuple(reasons),
        unresolved=tuple(unresolved),
        confidence=requirement.confidence,
        estimator_provider=requirement.estimator_provider,
        estimator_version=requirement.estimator_version,
        estimator_mode=requirement.estimator_mode,
        requested_primary=requirement.requested_primary,
        fallback_used=requirement.fallback_used,
        fallback_reason=requirement.fallback_reason,
        parameter_count=metadata.parameter_count,
        quantization=metadata.quantization,
        context_length_tokens=metadata.context_length_tokens,
        supported_runtimes=metadata.supported_runtimes,
    )


def rank_key(evaluation: ModelEvaluation) -> tuple[object, ...]:
    """Deterministic order: class, capability proxy, headroom, quant, name."""
    class_rank = {
        CapacityFitClass.PREFERRED: 0,
        CapacityFitClass.UNDERUTILIZED: 1,
        CapacityFitClass.EXCEEDS_SAFE: 2,
        CapacityFitClass.UNRESOLVED: 3,
    }[evaluation.capacity_fit]
    params = (
        evaluation.parameter_count if is_resolved(evaluation.parameter_count) else -1
    )
    ratio = evaluation.utilization.ratio if is_resolved(
        evaluation.utilization.ratio
    ) else 10.0
    quant = "unknown"
    if is_resolved(evaluation.quantization):
        quant = evaluation.quantization.lower()
    quality = _QUANT_RANK.get(quant, 0)
    context = (
        evaluation.context_length_tokens
        if is_resolved(evaluation.context_length_tokens)
        else 0
    )
    return (
        class_rank,
        -int(params),
        float(ratio) if evaluation.capacity_fit is CapacityFitClass.PREFERRED else 0.0,
        -quality,
        -int(context),
        evaluation.logical_name.value,
    )
