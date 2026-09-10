"""Host-independent requirement math lives in estimators; this is fit.

Planning consumes ModelRequirement and current available capacity
(SAFE minus ACTIVE). It does not import an estimator adapter or the
reservation ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.evidence.contracts import Confidence
from kultrun.kernel.unresolved import (
    NOT_PROVIDED,
    Maybe,
    is_resolved,
)
from kultrun.model.contracts import (
    CheapSizeClass,
    MemoryPlacement,
    ModelMetadata,
    ModelRequirement,
    WeightFootprintEvidence,
)
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


def deployment_capacity(
    envelope: CapacityEnvelope, *, storage_mount: str | None = None
) -> DeploymentCapacity:
    """SAFE slice for v0: first assigned GPU, else CPU-only.

    Unified memory is a seam: Stage 1.2 does not assert a GPU budget on
    unified hosts, so this does not invent one.

    Storage is the named destination pool. Several mounts must not collapse
    to the first SAFE figure — that reintroduces the FUSE first-pool leak.
    """
    gpu = next(
        (
            accelerator
            for accelerator in envelope.accelerators
            if is_resolved(accelerator.memory.safe_bytes)
        ),
        None,
    )
    storage = _pool_safe(envelope, storage_mount)
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
            available_ram_bytes=envelope.memory.safe_bytes,
            available_vram_bytes=gpu.memory.safe_bytes,
            available_unified_bytes=NOT_PROVIDED,
            available_storage_bytes=storage,
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
        available_ram_bytes=envelope.memory.safe_bytes,
        available_vram_bytes=NOT_PROVIDED,
        available_unified_bytes=NOT_PROVIDED,
        available_storage_bytes=storage,
    )


def _pool_safe(envelope: CapacityEnvelope, storage_mount: str | None) -> Maybe[int]:
    """SAFE bytes on the destination pool.

    Unnamed callers may use the unique pool that has resolved SAFE. Several
    authorizing pools stay unresolved — that is not a first-pool shortcut.
    """
    if storage_mount:
        for pool in envelope.pools:
            if pool.mount_point == storage_mount:
                return pool.space.safe_bytes
        return NOT_PROVIDED
    resolved = [
        pool.space.safe_bytes
        for pool in envelope.pools
        if is_resolved(pool.space.safe_bytes)
    ]
    if len(resolved) == 1:
        return resolved[0]
    return NOT_PROVIDED


def _budget(available: Maybe[int], safe: Maybe[int]) -> Maybe[int]:
    """Current available when present; otherwise SAFE (zero-commitment case)."""
    if is_resolved(available):
        return available
    return safe


def _ratio(required: object, budget: object) -> Maybe[float]:
    if not is_resolved(required) or not is_resolved(budget):
        return NOT_PROVIDED
    if not isinstance(required, int) or not isinstance(budget, int):
        return NOT_PROVIDED
    if budget <= 0:
        return 2.0 if required > 0 else 0.0
    return required / budget


def utilization(
    requirement: ModelRequirement, capacity: DeploymentCapacity
) -> CapacityUtilization:
    """Limiting-resource ratio against current available capacity. Storage excluded."""
    ram_ratio = _ratio(
        requirement.ram_bytes,
        _budget(capacity.available_ram_bytes, capacity.safe_ram_bytes),
    )
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
            requirement.unified_memory_bytes,
            _budget(capacity.available_unified_bytes, capacity.safe_unified_bytes),
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
    vram_ratio = _ratio(
        vram, _budget(capacity.available_vram_bytes, capacity.safe_vram_bytes)
    )
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
    policy: SelectionPolicy,
    *,
    runtime_compatibility: CompatibilityVerdict,
    incremental_storage_bytes: Maybe[int] | None = None,
) -> ModelEvaluation:
    """One candidate, current available capacity, one policy. Deterministic.

    Runtime/model compatibility is supplied by the eligible-model view.
    Callers always pass that token. There is no omit-mapping COMPATIBLE
    default. This function still owns capacity fit. It does not re-derive
    runtime support from catalog ``supported_runtimes``.
    """
    reasons: list[str] = []
    unresolved: list[str] = []
    compatibility = runtime_compatibility
    if runtime_compatibility is CompatibilityVerdict.UNSUPPORTED:
        reasons.append("runtime eligibility blocked")
    elif runtime_compatibility is CompatibilityVerdict.UNRESOLVED:
        unresolved.append("runtime_eligibility")
        reasons.append("runtime eligibility unresolved")
    method = requirement.estimation_method
    if is_resolved(method) and method in {"unsupported", "provider-unavailable"}:
        if method == "unsupported":
            compatibility = CompatibilityVerdict.UNSUPPORTED
        elif compatibility is not CompatibilityVerdict.UNSUPPORTED:
            compatibility = CompatibilityVerdict.UNRESOLVED
        reasons.extend(requirement.assumptions or (str(method),))

    storage_demand: Maybe[int] = (
        requirement.peak_additional_bytes
        if incremental_storage_bytes is None
        else incremental_storage_bytes
    )
    storage_budget = _budget(
        capacity.available_storage_bytes, capacity.safe_storage_bytes
    )
    storage_ok: Maybe[bool] = NOT_PROVIDED
    if not is_resolved(storage_demand):
        unresolved.append("incremental_storage_bytes")
        storage_ok = NOT_PROVIDED
    elif is_resolved(storage_budget):
        storage_ok = storage_demand <= storage_budget
        if storage_ok is False:
            reasons.append("infeasible_storage")
    else:
        unresolved.append("available_storage_bytes")
        storage_ok = NOT_PROVIDED

    used = utilization(requirement, capacity)
    fit = CapacityFitClass.UNRESOLVED
    preferred = False
    if compatibility is CompatibilityVerdict.UNSUPPORTED:
        fit = CapacityFitClass.EXCEEDS_SAFE
        reasons.append("unsupported; not a capacity-fit candidate")
    elif compatibility is CompatibilityVerdict.UNRESOLVED:
        fit = CapacityFitClass.UNRESOLVED
        reasons.append("runtime eligibility unresolved; capacity not a fit")
    else:
        failed = _hard_capacity_failures(requirement, capacity, storage_ok)
        if failed:
            fit = CapacityFitClass.EXCEEDS_SAFE
            reasons.extend(failed)
        elif not is_resolved(used.ratio):
            fit = CapacityFitClass.UNRESOLVED
            unresolved.append("capacity_utilization")
            reasons.append(
                "load-bearing requirement or current available capacity is unknown"
            )
        else:
            ratio = used.ratio
            if ratio > policy.maximum_capacity_utilization:
                fit = CapacityFitClass.EXCEEDS_SAFE
                limiting = (
                    used.limiting_resource
                    if is_resolved(used.limiting_resource)
                    else "vram"
                )
                reasons.append(f"infeasible_{limiting}")
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
        required_storage_bytes=storage_demand,
        safe_ram_bytes=capacity.safe_ram_bytes,
        safe_vram_bytes=capacity.safe_vram_bytes,
        safe_unified_bytes=capacity.safe_unified_bytes,
        available_ram_bytes=_budget(
            capacity.available_ram_bytes, capacity.safe_ram_bytes
        ),
        available_vram_bytes=_budget(
            capacity.available_vram_bytes, capacity.safe_vram_bytes
        ),
        available_unified_bytes=_budget(
            capacity.available_unified_bytes, capacity.safe_unified_bytes
        ),
        available_storage_bytes=storage_budget,
        incremental_storage_bytes=storage_demand,
        snapshot_basis=capacity.snapshot_basis,
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
        supported_runtimes=(
            requirement.supported_runtimes or metadata.supported_runtimes
        ),
    )


def _exceeds(required: object, budget: object) -> bool | None:
    if not is_resolved(required) or not is_resolved(budget):
        return None
    if not isinstance(required, int) or not isinstance(budget, int):
        return None
    return required > budget


def _hard_capacity_failures(
    requirement: ModelRequirement,
    capacity: DeploymentCapacity,
    storage_ok: object,
) -> tuple[str, ...]:
    """Dimension-specific hard failures. Compatibility is handled by the caller."""
    failed: list[str] = []
    if capacity.placement is MemoryPlacement.DISCRETE_GPU:
        vram = _exceeds(
            requirement.estimated_vram_bytes,
            _budget(capacity.available_vram_bytes, capacity.safe_vram_bytes),
        )
        if vram is True:
            failed.append("infeasible_vram")
    elif capacity.placement is MemoryPlacement.UNIFIED_MEMORY:
        unified = _exceeds(
            requirement.unified_memory_bytes,
            _budget(capacity.available_unified_bytes, capacity.safe_unified_bytes),
        )
        if unified is True:
            failed.append("infeasible_vram")
    ram = _exceeds(
        requirement.ram_bytes,
        _budget(capacity.available_ram_bytes, capacity.safe_ram_bytes),
    )
    if ram is True:
        failed.append("infeasible_ram")
    if storage_ok is False and "infeasible_storage" not in failed:
        failed.append("infeasible_storage")
    return tuple(failed)


@dataclass(frozen=True, slots=True)
class CheapSizeDecision:
    """Stage C gate. PASS and UNKNOWN continue; only proven-impossible excludes."""

    classification: CheapSizeClass
    allowed_placement_bytes: Maybe[int]
    reason: str | None = None


def cheap_weight_fit(
    evidence: WeightFootprintEvidence,
    capacity: DeploymentCapacity,
    *,
    gpu_resident: bool,
) -> CheapSizeDecision:
    """Reject only when factual weight bytes exceed the current placement budget.

    Equality is conservative: weights that fill the budget leave no room for
    KV, runtime, or workspace, so they are proven impossible for GPU-resident
    serving. Unknown evidence never rejects. Offload-enabled policy must not
    apply a GPU-only impossibility.
    """
    weight = evidence.serialized_weight_tensor_bytes
    if not gpu_resident or capacity.placement is not MemoryPlacement.DISCRETE_GPU:
        return CheapSizeDecision(CheapSizeClass.UNKNOWN, NOT_PROVIDED)
    allowed = _budget(capacity.available_vram_bytes, capacity.safe_vram_bytes)
    if not is_resolved(weight) or not isinstance(weight, int):
        return CheapSizeDecision(CheapSizeClass.UNKNOWN, allowed)
    if not is_resolved(allowed) or not isinstance(allowed, int):
        return CheapSizeDecision(CheapSizeClass.UNKNOWN, allowed)
    if weight >= allowed:
        return CheapSizeDecision(
            CheapSizeClass.PROVEN_IMPOSSIBLE,
            allowed,
            "weights_exceed_available_placement",
        )
    return CheapSizeDecision(CheapSizeClass.PASS, allowed)


def not_assessed(
    metadata: ModelMetadata,
    *,
    compatibility: CompatibilityVerdict,
    reasons: tuple[str, ...],
) -> ModelEvaluation:
    """Blocked or unresolved eligibility: no estimator, no SAFE comparison."""
    return ModelEvaluation(
        model_id=metadata.model_id,
        logical_name=metadata.logical_name,
        source_ref=metadata.source_ref,
        compatibility=compatibility,
        capacity_fit=CapacityFitClass.UNRESOLVED,
        storage_feasible=NOT_PROVIDED,
        required_ram_bytes=NOT_PROVIDED,
        required_vram_bytes=NOT_PROVIDED,
        required_unified_bytes=NOT_PROVIDED,
        required_storage_bytes=NOT_PROVIDED,
        safe_ram_bytes=NOT_PROVIDED,
        safe_vram_bytes=NOT_PROVIDED,
        safe_unified_bytes=NOT_PROVIDED,
        utilization=CapacityUtilization(
            ratio=NOT_PROVIDED,
            limiting_resource=NOT_PROVIDED,
            ram_ratio=NOT_PROVIDED,
        ),
        preferred=False,
        reasons=reasons,
        unresolved=("runtime_eligibility",),
        confidence=Confidence.UNKNOWN,
        estimator_provider=NOT_PROVIDED,
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
    ratio = (
        evaluation.utilization.ratio
        if is_resolved(evaluation.utilization.ratio)
        else 10.0
    )
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
