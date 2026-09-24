"""Compare a Machi shadow prediction with the authoritative provider result."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.foundation.metrics import MetricAvailability
from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_MEASURED, Maybe
from machi.model.identity import input_token
from machi.model.provider_qualification import (
    OllamaQualificationEvidence,
    ProviderFitState,
)
from machi.model.qualification import QualificationOutcome
from machi.model.shadow import SHADOW_POLICY, FitState, ShadowEvaluation

_TOKEN_MAX = 80
_REASON_MAX = 240
_VRAM_COMPARE = "estimate_vs_runtime_reported"


class ComparisonClass(StrEnum):
    AGREE_FIT = "agree_fit"
    AGREE_NO_FIT = "agree_no_fit"
    MACHI_FALSE_NEGATIVE = "machi_false_negative"
    MACHI_FALSE_POSITIVE = "machi_false_positive"
    MACHI_UNRESOLVED = "machi_unresolved"


@contract(kind="model.qualification_comparison", version=1)
@dataclass(frozen=True, slots=True)
class QualificationComparison(Contract):
    """Local analytics for one case. No prompt, path, or customer content."""

    comparison_id: str = meaning("identity of this comparison")
    provider: str = meaning("macropath")
    engine_version: str = meaning("provider version")
    generation_id: str = meaning("foundation generation")
    digest: str = meaning("provider model digest")
    display_name: str = meaning("provider display name")
    candidate_id: str = meaning("normalized candidate")
    capacity_evidence_id: str = meaning("capacity snapshot")
    hardware_class: str = meaning("hardware class")
    execution_environment_fingerprint: str = meaning("execution environment")
    context: int = meaning("case context")
    concurrency: int = meaning("case concurrency")
    shadow_policy_version: str = meaning("shadow policy")
    shadow_fit: FitState = meaning("machi shadow fit")
    shadow_reason: str = meaning("machi typed reason")
    shadow_accelerator_bytes: Maybe[int] = meaning("machi accelerator estimate")
    shadow_host_bytes: Maybe[int] = meaning("machi host estimate")
    shadow_storage_bytes: Maybe[int] = meaning("machi storage estimate")
    shadow_accelerator_availability: MetricAvailability = meaning(
        "availability of the machi accelerator estimate"
    )
    provider_fit: ProviderFitState = meaning("ollama specialist fit verdict")
    provider_outcome: QualificationOutcome = meaning("overall qualification outcome")
    provider_failure: str = meaning("authoritative failure")
    provider_size_bytes: Maybe[int] = meaning("provider reported size")
    provider_size_vram_bytes: Maybe[int] = meaning("provider size_vram")
    provider_size_vram_availability: MetricAvailability = meaning(
        "availability of size_vram"
    )
    provider_size_vram_source: str = meaning("size_vram source")
    load_seconds: Maybe[float] = meaning(
        "initial preload load duration in seconds"
    )
    input_tokens: Maybe[int] = meaning("provider input tokens")
    output_tokens: Maybe[int] = meaning("provider output tokens")
    generation_seconds: Maybe[float] = meaning("provider generation seconds")
    tokens_per_second: Maybe[float] = meaning("derived tokens per second")
    classification: ComparisonClass = meaning("agreement class")
    vram_semantics: str = meaning("estimate versus runtime-reported, or not comparable")
    vram_availability: MetricAvailability = meaning("whether a vram delta exists")
    vram_delta_bytes: Maybe[int] = meaning("estimate minus runtime-reported")
    vram_ratio: Maybe[float] = meaning("estimate divided by runtime-reported")
    observed_at: dt.datetime = meaning("when the comparison was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        for label, value in (
            ("comparison", self.comparison_id),
            ("provider", self.provider),
            ("version", self.engine_version),
            ("generation", self.generation_id),
            ("digest", self.digest),
            ("name", self.display_name),
            ("candidate", self.candidate_id),
            ("capacity", self.capacity_evidence_id),
            ("hardware", self.hardware_class),
            ("environment", self.execution_environment_fingerprint),
            ("policy", self.shadow_policy_version),
            ("reason", self.shadow_reason),
            ("failure", self.provider_failure),
            ("source", self.provider_size_vram_source),
            ("semantics", self.vram_semantics),
        ):
            limit = _REASON_MAX if label in {"reason", "failure"} else _TOKEN_MAX
            if not value or len(value) > limit:
                raise ValidationError(f"{label} is empty or too long")
        if self.shadow_policy_version != SHADOW_POLICY:
            raise ValidationError("comparison cites an unknown shadow policy")
        if self.context < 1 or self.concurrency < 1:
            raise ValidationError("comparison envelope must be positive")
        if self.vram_semantics not in {_VRAM_COMPARE, "not_comparable"}:
            raise ValidationError("vram comparison semantics are not supported")


def classify(shadow: FitState, provider: ProviderFitState) -> ComparisonClass:
    """Compare specialist fit verdicts. Later proof failures stay separate."""
    if shadow is FitState.UNRESOLVED or provider is ProviderFitState.UNRESOLVED:
        return ComparisonClass.MACHI_UNRESOLVED
    if shadow is FitState.FIT and provider is ProviderFitState.FIT:
        return ComparisonClass.AGREE_FIT
    if shadow is FitState.NO_FIT and provider is ProviderFitState.NO_FIT:
        return ComparisonClass.AGREE_NO_FIT
    if shadow is FitState.NO_FIT and provider is ProviderFitState.FIT:
        return ComparisonClass.MACHI_FALSE_NEGATIVE
    return ComparisonClass.MACHI_FALSE_POSITIVE


def compare(
    shadow: ShadowEvaluation,
    evidence: OllamaQualificationEvidence,
    *,
    hardware_class: str,
    execution_environment_fingerprint: str,
    observed_at: dt.datetime,
) -> QualificationComparison:
    """Record both results. The provider outcome is copied, not recomputed."""
    classification = classify(shadow.fit, evidence.provider_fit)
    delta, ratio, semantics, availability = _vram(
        shadow.accelerator_bytes, evidence.size_vram_bytes
    )
    token = input_token(
        evidence.digest,
        evidence.generation_id,
        shadow.capacity_evidence_id,
        hardware_class,
        execution_environment_fingerprint,
        str(evidence.context),
        str(evidence.concurrency),
        shadow.policy_version,
    )
    return QualificationComparison(
        comparison_id=f"qcmp_{token[:16]}",
        provider=shadow.provider,
        engine_version=evidence.engine_version,
        generation_id=evidence.generation_id,
        digest=evidence.digest,
        display_name=evidence.display_name,
        candidate_id=shadow.candidate_id,
        capacity_evidence_id=shadow.capacity_evidence_id,
        hardware_class=hardware_class,
        execution_environment_fingerprint=execution_environment_fingerprint,
        context=evidence.context,
        concurrency=evidence.concurrency,
        shadow_policy_version=shadow.policy_version,
        shadow_fit=shadow.fit,
        shadow_reason=shadow.reason,
        shadow_accelerator_bytes=shadow.accelerator_bytes,
        shadow_host_bytes=shadow.host_bytes,
        shadow_storage_bytes=shadow.storage_bytes,
        shadow_accelerator_availability=shadow.accelerator_availability,
        provider_fit=evidence.provider_fit,
        provider_outcome=evidence.outcome,
        provider_failure=evidence.failure,
        provider_size_bytes=evidence.size_bytes,
        provider_size_vram_bytes=evidence.size_vram_bytes,
        provider_size_vram_availability=evidence.size_vram_availability,
        provider_size_vram_source=evidence.size_vram_source,
        load_seconds=evidence.load_seconds,
        input_tokens=evidence.input_tokens,
        output_tokens=evidence.output_tokens,
        generation_seconds=evidence.generation_seconds,
        tokens_per_second=evidence.tokens_per_second,
        classification=classification,
        vram_semantics=semantics,
        vram_availability=availability,
        vram_delta_bytes=delta,
        vram_ratio=ratio,
        observed_at=observed_at,
    )


def _vram(
    estimate: Maybe[int], reported: Maybe[int]
) -> tuple[Maybe[int], Maybe[float], str, MetricAvailability]:
    if not isinstance(estimate, int) or not isinstance(reported, int):
        return (
            NOT_MEASURED,
            NOT_MEASURED,
            "not_comparable",
            MetricAvailability.UNRESOLVED,
        )
    if reported < 1:
        return (
            NOT_MEASURED,
            NOT_MEASURED,
            "not_comparable",
            MetricAvailability.UNRESOLVED,
        )
    return (
        estimate - reported,
        estimate / reported,
        _VRAM_COMPARE,
        MetricAvailability.DERIVED,
    )
