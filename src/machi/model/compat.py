"""Compatibility against an injected runtime. Does not load weights."""

from __future__ import annotations

from dataclasses import dataclass

from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.unresolved import NOT_MEASURED, is_resolved
from machi.model.contracts import (
    CompatibilityState,
    ModelCompatibility,
    ModelFailure,
    ModelRequirement,
    ProviderQualification,
    QuantizationKind,
    WeightFormat,
)
from machi.model.metadata import NormalizedMetadata
from machi.model.predicates import (
    RuntimePredicate,
    StructuralVerdict,
    structural_verdict,
)


@dataclass(frozen=True, slots=True)
class RuntimeView:
    """What the installed engine reported, plus qualification evidence."""

    architectures: frozenset[str]
    quantizations: frozenset[str]
    foundation_id: str
    provider_qualification: ProviderQualification
    capability_known: bool
    predicates: tuple[RuntimePredicate, ...] = ()


def requirement_for(sizes: tuple[int | None, ...]) -> ModelRequirement:
    """Sum known file sizes. Unknown stays unresolved rather than zero."""
    if any(size is None for size in sizes):
        return ModelRequirement(
            persistent_bytes=NOT_MEASURED,
            transient_bytes=NOT_MEASURED,
            static_weight_bytes=NOT_MEASURED,
        )
    total = sum(size for size in sizes if size is not None)
    return ModelRequirement(
        persistent_bytes=total,
        transient_bytes=total,
        static_weight_bytes=total,
    )


def storage_fits(
    capacity: CapacityEnvelope | None,
    needed: ModelRequirement,
) -> bool | None:
    """True, false, or None when the byte need is not known."""
    needed_bytes = needed.persistent_bytes
    transient = needed.transient_bytes
    if not is_resolved(needed_bytes) or not is_resolved(transient):
        return None
    if capacity is None:
        return None
    total = int(needed_bytes) + int(transient)
    for domain in capacity.storage_domains:
        if not domain.usable:
            continue
        if is_resolved(domain.safe_bytes) and int(domain.safe_bytes) >= total:
            return True
    return False


def assess(
    *,
    architecture: str | None,
    quantization: QuantizationKind,
    weight_format: WeightFormat,
    requires_remote_code: bool,
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    requirement: ModelRequirement,
    weights_exceed_accelerator: bool | None,
    license_blocks: bool = False,
    metadata: NormalizedMetadata | None = None,
) -> ModelCompatibility:
    """Compose technical fit and policy. Qualification is a caveat, not a ban."""
    if requires_remote_code:
        return _result(
            CompatibilityState.BLOCKED_BY_POLICY,
            ModelFailure.REMOTE_CODE_REQUIRED,
            CompatibilityState.UNRESOLVED,
            CompatibilityState.BLOCKED_BY_POLICY,
            runtime,
            "repository code would have to execute and policy refuses that",
        )
    if not runtime.capability_known:
        return _result(
            CompatibilityState.UNRESOLVED,
            ModelFailure.RUNTIME_CAPABILITY_UNRESOLVED,
            CompatibilityState.UNRESOLVED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "installed engine did not report architecture support",
        )
    if architecture is None:
        return _result(
            CompatibilityState.UNSUPPORTED,
            ModelFailure.UNSUPPORTED_ARCHITECTURE,
            CompatibilityState.UNSUPPORTED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "config did not name an architecture",
        )
    if architecture not in runtime.architectures:
        return _result(
            CompatibilityState.UNSUPPORTED,
            ModelFailure.UNSUPPORTED_ARCHITECTURE,
            CompatibilityState.UNSUPPORTED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "installed engine does not recognize this architecture",
        )
    if weight_format is not WeightFormat.SAFETENSORS:
        return _result(
            CompatibilityState.UNSUPPORTED,
            ModelFailure.UNSUPPORTED_WEIGHT_FORMAT,
            CompatibilityState.UNSUPPORTED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "selected weights are not safetensors",
        )
    quant_name = quantization.value
    if (
        quantization is not QuantizationKind.NONE
        and quant_name not in runtime.quantizations
    ):
        return _result(
            CompatibilityState.UNSUPPORTED,
            ModelFailure.UNSUPPORTED_QUANTIZATION,
            CompatibilityState.UNSUPPORTED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "installed engine does not list this quantization",
        )
    structural = _structural(metadata, runtime.predicates)
    if structural is StructuralVerdict.UNSUPPORTED:
        return _result(
            CompatibilityState.UNSUPPORTED,
            ModelFailure.ATTENTION_CONFIGURATION_UNSUPPORTED,
            CompatibilityState.UNSUPPORTED,
            CompatibilityState.COMPATIBLE,
            runtime,
            "no finite runtime predicate supports this attention shape",
        )
    if structural is StructuralVerdict.UNRESOLVED:
        return _caveat(
            runtime,
            CompatibilityState.CONDITIONALLY_COMPATIBLE,
            ModelFailure.NONE,
            "attention support is unresolved",
        )
    fits = storage_fits(capacity, requirement)
    if fits is False:
        return _result(
            CompatibilityState.INSUFFICIENT_CAPACITY,
            ModelFailure.INSUFFICIENT_STORAGE,
            CompatibilityState.INSUFFICIENT_CAPACITY,
            CompatibilityState.COMPATIBLE,
            runtime,
            "safe storage is below the artifact requirement",
        )
    if weights_exceed_accelerator is True:
        return _result(
            CompatibilityState.INSUFFICIENT_CAPACITY,
            ModelFailure.INSUFFICIENT_BASELINE_CAPACITY,
            CompatibilityState.INSUFFICIENT_CAPACITY,
            CompatibilityState.COMPATIBLE,
            runtime,
            "static weights exceed the accelerator baseline",
        )
    if weights_exceed_accelerator is None or fits is None:
        return _caveat(
            runtime,
            CompatibilityState.CONDITIONALLY_COMPATIBLE,
            ModelFailure.NONE,
            "baseline memory or storage still depends on a later plan",
        )
    if runtime.provider_qualification is ProviderQualification.DEFERRED:
        result = _caveat(
            runtime,
            CompatibilityState.CONDITIONALLY_COMPATIBLE,
            ModelFailure.NONE,
            "architecture fits the engine; provider qualification is still deferred",
        )
    elif runtime.provider_qualification is ProviderQualification.UNKNOWN:
        result = _caveat(
            runtime,
            CompatibilityState.CONDITIONALLY_COMPATIBLE,
            ModelFailure.NONE,
            "architecture fits the engine; provider qualification is not established",
        )
    else:
        result = _result(
            CompatibilityState.COMPATIBLE,
            ModelFailure.NONE,
            CompatibilityState.COMPATIBLE,
            CompatibilityState.COMPATIBLE,
            runtime,
            "architecture, format, and storage match this snapshot",
        )
    return _apply_license(result, license_blocks)


def _structural(
    metadata: NormalizedMetadata | None,
    predicates: tuple[RuntimePredicate, ...],
) -> StructuralVerdict:
    if metadata is None:
        return StructuralVerdict.UNRESOLVED
    return structural_verdict(metadata, predicates)


def weights_exceed(
    static_bytes: int | None,
    accelerator_safe_bytes: int | None,
) -> bool | None:
    """True only when weights alone exceed the device baseline."""
    if static_bytes is None or accelerator_safe_bytes is None:
        return None
    return static_bytes > accelerator_safe_bytes


def _apply_license(
    result: ModelCompatibility,
    license_blocks: bool,
) -> ModelCompatibility:
    """A license block does not rewrite a technical failure."""
    if not license_blocks:
        return result
    if result.technical_state not in {
        CompatibilityState.COMPATIBLE,
        CompatibilityState.CONDITIONALLY_COMPATIBLE,
    }:
        return result
    return ModelCompatibility(
        state=CompatibilityState.BLOCKED_BY_POLICY,
        failure=ModelFailure.LICENSE_POLICY_BLOCKED,
        technical_state=result.technical_state,
        policy_state=CompatibilityState.BLOCKED_BY_POLICY,
        provider_qualification=result.provider_qualification,
        reason="license policy blocked selection; technical fit is unchanged",
    )


def _caveat(
    runtime: RuntimeView,
    state: CompatibilityState,
    failure: ModelFailure,
    reason: str,
) -> ModelCompatibility:
    return _result(
        state,
        failure,
        CompatibilityState.CONDITIONALLY_COMPATIBLE,
        CompatibilityState.COMPATIBLE,
        runtime,
        reason,
    )


def _result(
    state: CompatibilityState,
    failure: ModelFailure,
    technical: CompatibilityState,
    policy: CompatibilityState,
    runtime: RuntimeView,
    reason: str,
) -> ModelCompatibility:
    return ModelCompatibility(
        state=state,
        failure=failure,
        technical_state=technical,
        policy_state=policy,
        provider_qualification=runtime.provider_qualification,
        reason=reason,
    )
