"""Authoritative Ollama qualification. Not a warehouse QualificationEvidence."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.foundation.metrics import MetricAvailability
from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe
from machi.model.identity import input_token
from machi.model.provider_candidate import canonical_digest
from machi.model.qualification import QualificationOutcome

_TOKEN_MAX = 80
_REASON_MAX = 240
_VRAM_SEMANTICS = "runtime_reported"


class ProviderFitState(StrEnum):
    """Specialist fit. It is not the overall qualification outcome."""

    FIT = "fit"
    NO_FIT = "no_fit"
    UNRESOLVED = "unresolved"


@contract(kind="model.ollama_qualification", version=2)
@dataclass(frozen=True, slots=True)
class OllamaQualificationEvidence(Contract):
    """Provider-owned fit result. Shadow evaluation is not a field."""

    qualification_id: str = meaning("identity of this provider result")
    digest: str = meaning("ollama model digest that was qualified")
    display_name: str = meaning("tag used to address the catalog entry")
    generation_id: str = meaning("foundation generation")
    engine_version: str = meaning("ollama version")
    hardware_class: str = meaning("capability class, not a host name")
    execution_environment_fingerprint: str = meaning(
        "material accelerator environment"
    )
    context: int = meaning(
        "context requested from the provider as num_ctx; not an observed slot"
    )
    concurrency: int = meaning("qualification concurrency")
    context_binding: str = meaning(
        "requested when num_ctx was sent; not_sent cannot cover a plan"
    )
    outcome: QualificationOutcome = meaning("pass, model failure, or host failure")
    provider_fit: ProviderFitState = meaning(
        "specialist fit verdict; not inferred from a later proof failure"
    )
    failure: str = meaning("typed provider failure, or none")
    authority: str = meaning("ollama; shadow is not this authority")
    size_bytes: Maybe[int] = meaning("provider-reported model size")
    size_vram_bytes: Maybe[int] = meaning("provider-reported loaded vram")
    size_vram_availability: MetricAvailability = meaning(
        "whether size_vram was reported"
    )
    size_vram_source: str = meaning("ollama.api.ps or not_exposed")
    size_vram_semantics: str = meaning("runtime_reported; not an observed peak")
    load_seconds: Maybe[float] = meaning(
        "initial preload load_duration converted from nanoseconds"
    )
    input_tokens: Maybe[int] = meaning("probe input tokens when exposed")
    output_tokens: Maybe[int] = meaning("probe output tokens when exposed")
    generation_seconds: Maybe[float] = meaning("provider generation duration")
    tokens_per_second: Maybe[float] = meaning("derived rate when both operands exist")
    token_proved: bool = meaning("true only when a real output token was counted")
    unload_failure: str = meaning("none, not_attempted, or a separate unload fault")
    observed_at: dt.datetime = meaning("when this result was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        for label, value in (
            ("qualification", self.qualification_id),
            ("digest", self.digest),
            ("name", self.display_name),
            ("generation", self.generation_id),
            ("version", self.engine_version),
            ("hardware", self.hardware_class),
            ("environment", self.execution_environment_fingerprint),
            ("failure", self.failure),
            ("source", self.size_vram_source),
            ("unload", self.unload_failure),
        ):
            limit = _REASON_MAX if label in {"failure", "unload"} else _TOKEN_MAX
            if not value or len(value) > limit:
                raise ValidationError(f"{label} is empty or too long")
        if self.authority != "ollama":
            raise ValidationError("ollama qualification authority is ollama")
        if self.size_vram_semantics != _VRAM_SEMANTICS:
            raise ValidationError("size_vram is runtime-reported, not a peak")
        if self.context_binding not in {"requested", "not_sent"}:
            raise ValidationError("context binding is not requested or not_sent")
        if self.context < 1 or self.concurrency < 1:
            raise ValidationError("qualification envelope must be positive")
        if self.outcome is QualificationOutcome.PASS:
            if self.context_binding != "requested":
                raise ValidationError("a pass requires a requested context")
            if not self.token_proved:
                raise ValidationError("a pass requires a counted output token")
            if self.provider_fit is not ProviderFitState.FIT:
                raise ValidationError("a pass requires provider fit")


def ollama_qualification_id(
    *,
    digest: str,
    generation_id: str,
    engine_version: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    context: int,
    concurrency: int,
) -> str:
    token = input_token(
        digest,
        generation_id,
        engine_version,
        hardware_class,
        execution_environment_fingerprint,
        str(context),
        str(concurrency),
    )
    return f"oqev_{token[:16]}"


def qualification_covers(
    evidence: OllamaQualificationEvidence,
    *,
    digest: str,
    generation_id: str,
    context: int,
    concurrency: int,
) -> bool:
    """A pass covers the requested context only when num_ctx was sent."""
    if evidence.schema_version != 2 or evidence.context_binding != "requested":
        return False
    if evidence.outcome is not QualificationOutcome.PASS:
        return False
    if evidence.provider_fit is not ProviderFitState.FIT:
        return False
    try:
        same_digest = canonical_digest(digest) == canonical_digest(evidence.digest)
    except ValidationError:
        return False
    if not same_digest or evidence.generation_id != generation_id:
        return False
    if evidence.concurrency != 1 or concurrency != 1:
        return False
    return 1 <= context <= evidence.context
