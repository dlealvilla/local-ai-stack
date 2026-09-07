"""Runtime eligibility. Not capacity. Does not import the runtime package."""

from __future__ import annotations

from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import ModelMetadata
from kultrun.planning.contracts import (
    EligibilityVerdict,
    RuntimeCapabilitySnapshot,
    RuntimeEligibleModelCandidate,
)

_FORMAT_FROM_QUANT = {
    "awq": "safetensors",
    "gptq": "safetensors",
    "gptq-int4": "safetensors",
    "fp16": "safetensors",
    "f16": "safetensors",
    "bf16": "safetensors",
    "q4": "gguf",
    "q4_k": "gguf",
    "q4_k_m": "gguf",
    "q5_k": "gguf",
    "q8": "gguf",
    "q8_0": "gguf",
}


def inferred_format(metadata: ModelMetadata) -> object:
    """Best local inference of artifact format. Unknown stays unknown."""
    if is_resolved(metadata.quantization):
        key = str(metadata.quantization).lower()
        if key in _FORMAT_FROM_QUANT:
            return _FORMAT_FROM_QUANT[key]
    return NOT_PROVIDED


def snapshot_is_authorizing(snapshot: RuntimeCapabilitySnapshot) -> bool:
    """Only VERIFIED product/fixture profiles may authorize executable selection."""
    return snapshot.status == "verified" and snapshot.support_tier in {
        "product",
        "fixture",
    }


class RuntimeEligibilityEvaluator:
    """Hard filter: can this verified runtime plausibly serve the model?"""

    def evaluate(
        self,
        metadata: ModelMetadata,
        snapshot: RuntimeCapabilitySnapshot,
    ) -> RuntimeEligibleModelCandidate:
        reasons: list[str] = []
        verdict = EligibilityVerdict.ELIGIBLE
        artifact_format = inferred_format(metadata)

        if snapshot.status != "verified":
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append(f"runtime profile is {snapshot.status}")
        elif snapshot.support_tier in {"reference", "future"}:
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append(
                f"runtime support tier {snapshot.support_tier} cannot authorize "
                "executable-model selection"
            )

        architecture = (
            str(metadata.architecture).lower()
            if is_resolved(metadata.architecture)
            else None
        )
        if (
            verdict is EligibilityVerdict.ELIGIBLE
            and architecture
            and snapshot.supported_architectures
            and not _architecture_matches(
                architecture, snapshot.supported_architectures
            )
        ):
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append("architecture unsupported by verified runtime")

        if (
            verdict is EligibilityVerdict.ELIGIBLE
            and is_resolved(artifact_format)
            and snapshot.supported_formats
            and str(artifact_format).lower()
            not in {item.lower() for item in snapshot.supported_formats}
        ):
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append("artifact format unsupported by verified runtime")

        quantization = (
            str(metadata.quantization).lower()
            if is_resolved(metadata.quantization)
            else None
        )
        if (
            verdict is EligibilityVerdict.ELIGIBLE
            and quantization
            and snapshot.supported_quantizations
            and quantization
            not in {item.lower() for item in snapshot.supported_quantizations}
        ):
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append("quantization unsupported by verified runtime")

        if (
            verdict is EligibilityVerdict.ELIGIBLE
            and metadata.supported_runtimes
            and snapshot.runtime_family
            and snapshot.runtime_family not in metadata.supported_runtimes
        ):
            verdict = EligibilityVerdict.INELIGIBLE
            reasons.append("model metadata does not name this runtime family")

        if verdict is EligibilityVerdict.ELIGIBLE and not reasons:
            reasons.append(
                "architecture, format and quantization match verified runtime"
            )

        return RuntimeEligibleModelCandidate(
            model_id=metadata.model_id,
            logical_name=metadata.logical_name,
            profile_id=snapshot.profile_id,
            runtime_provider=snapshot.runtime_provider,
            runtime_family=snapshot.runtime_family,
            runtime_version=snapshot.runtime_version,
            executor_kind=snapshot.executor_kind,
            host_id=snapshot.host_id,
            architecture=metadata.architecture,
            artifact_format=artifact_format,
            quantization=metadata.quantization,
            verdict=verdict,
            reasons=tuple(reasons),
            confidence="high",
        )


def _architecture_matches(architecture: str, supported: tuple[str, ...]) -> bool:
    names = {item.lower() for item in supported}
    if architecture in names:
        return True
    # qwen2.5 is a qwen2 family member in catalog data.
    if architecture.startswith("qwen2") and "qwen2" in names:
        return True
    return architecture.startswith("llama") and "llama" in names
