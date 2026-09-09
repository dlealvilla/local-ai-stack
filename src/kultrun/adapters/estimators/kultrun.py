"""Kultrun packaged/formula requirement estimator."""

from __future__ import annotations

from dataclasses import replace

from kultrun.adapters.estimators.common import unavailable_requirement
from kultrun.adapters.estimators.vllm_serving import (
    compose_vllm_vram,
    is_vllm_runtime,
    kv_cache_bytes,
)
from kultrun.adapters.model_source.candidates import (
    PROVIDER_VERSION,
    packaged_candidates,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import (
    EstimatorFailureReason,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)

IDENTITY = Name("kultrun")


class KultrunRequirementEstimator:
    """Looks up packaged components, then derives a runtime-specific total."""

    def __init__(self, entries: tuple[ModelCatalogEntry, ...] | None = None) -> None:
        self._entries = entries if entries is not None else packaged_candidates()
        self._by_id = {entry.metadata.model_id.value: entry for entry in self._entries}

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def version(self) -> str:
        return PROVIDER_VERSION

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        if request.tensor_parallel != 1 or request.batch_size != 1:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="v0 estimates are single-device batch-1 only",
                failure=EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        if request.offload_allowed:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="cpu offload is not assumed by the Kultrun estimator",
                failure=EstimatorFailureReason.UNSUPPORTED_CONFIGURATION,
            )
        entry = self._by_id.get(request.model_id.value)
        if entry is None:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="candidate is not in the Kultrun packaged set",
                failure=EstimatorFailureReason.UNSUPPORTED_MODEL,
            )
        meta = entry.metadata
        if (
            is_resolved(request.quantization)
            and is_resolved(meta.quantization)
            and _norm(request.quantization) != _norm(meta.quantization)
        ):
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="quantization does not match the packaged variant",
                failure=EstimatorFailureReason.ASSUMPTION_MISMATCH,
            )
        if (
            is_resolved(request.source_revision)
            and is_resolved(meta.source_revision)
            and request.source_revision != meta.source_revision
        ):
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="model revision does not match the packaged variant",
                failure=EstimatorFailureReason.ASSUMPTION_MISMATCH,
            )
        packaged = entry.requirement
        context: Maybe[int] = (
            request.context_tokens
            if is_resolved(request.context_tokens)
            else packaged.assumed_context_tokens
        )
        if is_vllm_runtime(request.runtime):
            return _vllm_requirement(request, packaged, context)
        return _packaged_with_context(request, packaged, context)


def build(
    entries: tuple[ModelCatalogEntry, ...] | None = None,
) -> KultrunRequirementEstimator:
    return KultrunRequirementEstimator(entries)


def _vllm_requirement(
    request: ModelEstimationRequest,
    packaged: ModelRequirement,
    context: Maybe[int],
) -> ModelRequirement:
    composed = compose_vllm_vram(
        weights_bytes=packaged.vram_weights_bytes,
        kv_per_token=packaged.vram_kv_bytes_per_token,
        context_tokens=context,
        batch_size=request.batch_size,
        overhead_bytes=packaged.vram_overhead_bytes,
        activation_bytes=packaged.activation_bytes,
    )
    assumptions = tuple(dict.fromkeys((*packaged.assumptions, *composed.assumptions)))
    if composed.unresolved:
        return replace(
            packaged,
            estimated_vram_bytes=NOT_PROVIDED,
            assumed_context_tokens=context,
            assumed_batch_size=request.batch_size,
            assumed_runtime=request.runtime,
            assumed_runtime_version=request.runtime_version,
            vram_kv_cache_bytes=composed.kv_cache_bytes,
            safety_allowance_bytes=composed.safety_allowance_bytes,
            assumptions=(*assumptions, *composed.unresolved),
            estimator_version=PROVIDER_VERSION,
        )
    return replace(
        packaged,
        estimated_vram_bytes=composed.total_bytes,
        assumed_context_tokens=context,
        assumed_batch_size=request.batch_size,
        assumed_runtime=request.runtime,
        assumed_runtime_version=request.runtime_version,
        vram_kv_cache_bytes=composed.kv_cache_bytes,
        safety_allowance_bytes=composed.safety_allowance_bytes,
        assumptions=assumptions,
        estimator_version=PROVIDER_VERSION,
        estimator_failure=NOT_PROVIDED,
    )


def _packaged_with_context(
    request: ModelEstimationRequest,
    packaged: ModelRequirement,
    context: Maybe[int],
) -> ModelRequirement:
    per_token = packaged.vram_kv_bytes_per_token
    if isinstance(per_token, int) and isinstance(context, int):
        kv_computed = kv_cache_bytes(per_token, context, request.batch_size)
        weights = packaged.vram_weights_bytes
        overhead = packaged.vram_overhead_bytes
        activation = packaged.activation_bytes
        if isinstance(weights, int) and isinstance(overhead, int):
            total = weights + kv_computed + overhead
            if isinstance(activation, int):
                total += activation
            return replace(
                packaged,
                estimated_vram_bytes=total,
                assumed_context_tokens=context,
                assumed_batch_size=request.batch_size,
                assumed_runtime=request.runtime,
                assumed_runtime_version=request.runtime_version,
                vram_kv_cache_bytes=kv_computed,
                estimator_version=PROVIDER_VERSION,
            )
    if (
        is_resolved(request.context_tokens)
        and is_resolved(packaged.assumed_context_tokens)
        and request.context_tokens != packaged.assumed_context_tokens
        and not is_resolved(per_token)
    ):
        return unavailable_requirement(
            request,
            provider=IDENTITY.value,
            version=PROVIDER_VERSION,
            method="unsupported",
            reason="context changed but KV per token is unresolved",
            failure=EstimatorFailureReason.MISSING_LOAD_BEARING_REQUIREMENT,
        )
    return replace(
        packaged,
        assumed_context_tokens=context,
        assumed_batch_size=request.batch_size,
        assumed_runtime=request.runtime,
        assumed_runtime_version=request.runtime_version,
        estimator_version=PROVIDER_VERSION,
    )


def _norm(value: object) -> str:
    return str(value).lower().replace("-", "_")
