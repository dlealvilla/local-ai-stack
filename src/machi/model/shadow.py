"""Non-authoritative shadow fit. It cannot admit or override a provider."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.capacity.contracts import CapacityEnvelope
from machi.foundation.metrics import MetricAvailability
from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_MEASURED, Maybe, is_resolved
from machi.model.contracts import DerivationKind, QuantizationKind
from machi.model.estimate import estimate_serving
from machi.model.identity import input_token
from machi.model.metadata import NormalizedMetadata
from machi.model.provider_candidate import OllamaCatalogCandidate

SHADOW_POLICY = "m6.shadow.1"
_TOKEN_MAX = 80
_REASON_MAX = 240


class FitState(StrEnum):
    FIT = "fit"
    NO_FIT = "no_fit"
    UNRESOLVED = "unresolved"


@contract(kind="model.shadow_evaluation", version=1)
@dataclass(frozen=True, slots=True)
class ShadowEvaluation(Contract):
    """Machi's prediction for one Ollama case. Not the admission decision."""

    evaluation_id: str = meaning("identity of this shadow result")
    candidate_id: str = meaning("normalized provider candidate")
    provider: str = meaning("macropath this shadow observed")
    digest: str = meaning("provider model digest")
    capacity_evidence_id: str = meaning("capacity snapshot consulted")
    policy_version: str = meaning("shadow policy identity")
    fit: FitState = meaning("fit, no fit, or unresolved")
    accelerator_bytes: Maybe[int] = meaning("estimated accelerator bytes")
    host_bytes: Maybe[int] = meaning("estimated host bytes")
    storage_bytes: Maybe[int] = meaning("estimated incremental storage")
    accelerator_availability: MetricAvailability = meaning(
        "how the accelerator figure was obtained"
    )
    host_availability: MetricAvailability = meaning("how the host figure was obtained")
    storage_availability: MetricAvailability = meaning(
        "how the storage figure was obtained"
    )
    reason: str = meaning("typed reason")
    provenance: str = meaning("estimator provenance")
    observed_at: dt.datetime = meaning("when the shadow ran; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        for label, value in (
            ("evaluation", self.evaluation_id),
            ("candidate", self.candidate_id),
            ("provider", self.provider),
            ("digest", self.digest),
            ("capacity", self.capacity_evidence_id),
            ("policy", self.policy_version),
            ("reason", self.reason),
            ("provenance", self.provenance),
        ):
            limit = _REASON_MAX if label == "reason" else _TOKEN_MAX
            if not value or len(value) > limit:
                raise ValidationError(f"{label} is empty or too long")
        if self.policy_version != SHADOW_POLICY:
            raise ValidationError("shadow policy version is not supported")


def evaluate_shadow(
    candidate: OllamaCatalogCandidate,
    envelope: CapacityEnvelope,
    *,
    accelerator_identity: str,
    context: int,
    concurrency: int,
    observed_at: dt.datetime,
) -> ShadowEvaluation:
    """Coarse Machi estimate from public facts and the current SAFE envelope."""
    device_safe = _device_safe(envelope, accelerator_identity)
    published = candidate.size_bytes
    storage = published if is_resolved(published) else NOT_MEASURED
    storage_availability = (
        MetricAvailability.ESTIMATED
        if isinstance(storage, int)
        else MetricAvailability.UNRESOLVED
    )
    estimate = estimate_serving(
        _metadata(candidate),
        weight_bytes=(
            candidate.size_bytes if isinstance(candidate.size_bytes, int) else None
        ),
        storage_bytes=(
            candidate.size_bytes if isinstance(candidate.size_bytes, int) else None
        ),
        context=context,
        concurrency=concurrency,
    )
    total = estimate.total_required_vram_bytes
    fit = FitState.UNRESOLVED
    reason = "attention_shape_not_exposed"
    accelerator: Maybe[int] = NOT_MEASURED
    accelerator_availability = MetricAvailability.UNRESOLVED
    if not isinstance(device_safe, int):
        reason = "capacity_unresolved"
    elif isinstance(total, int):
        accelerator = total
        accelerator_availability = MetricAvailability.ESTIMATED
        if total <= device_safe:
            fit = FitState.FIT
            reason = "estimated_requirement_within_safe"
        else:
            fit = FitState.NO_FIT
            reason = "estimated_requirement_exceeds_safe"
    elif isinstance(candidate.size_bytes, int) and candidate.size_bytes > device_safe:
        fit = FitState.NO_FIT
        reason = "published_size_exceeds_safe_accelerator"
        accelerator = candidate.size_bytes
        accelerator_availability = MetricAvailability.ESTIMATED
    token = input_token(
        candidate.candidate_id,
        candidate.digest,
        envelope.evidence_id,
        accelerator_identity,
        SHADOW_POLICY,
        str(context),
        str(concurrency),
    )
    return ShadowEvaluation(
        evaluation_id=f"shdw_{token[:16]}",
        candidate_id=candidate.candidate_id,
        provider="ollama",
        digest=candidate.digest,
        capacity_evidence_id=envelope.evidence_id,
        policy_version=SHADOW_POLICY,
        fit=fit,
        accelerator_bytes=accelerator,
        host_bytes=NOT_MEASURED,
        storage_bytes=storage,
        accelerator_availability=accelerator_availability,
        host_availability=MetricAvailability.NOT_EXPOSED,
        storage_availability=storage_availability,
        reason=reason,
        provenance="machi.formula",
        observed_at=observed_at,
    )


def _device_safe(envelope: CapacityEnvelope, identity: str) -> Maybe[int]:
    for device in envelope.accelerators:
        if device.identity == identity:
            return device.safe_bytes
    return NOT_MEASURED


def _metadata(candidate: OllamaCatalogCandidate) -> NormalizedMetadata:
    """Only explicit public numbers. Family and tags do not fill the shape."""
    return NormalizedMetadata(
        architecture=NOT_MEASURED,
        dtype=candidate.dtype,
        quantization=QuantizationKind.UNKNOWN,
        context_length=candidate.context_length,
        parameter_count=NOT_MEASURED,
        requires_remote_code=False,
        base_model=NOT_MEASURED,
        derivation=DerivationKind.UNKNOWN,
        config_sha256=NOT_MEASURED,
        hidden_size=NOT_MEASURED,
        attention_heads=NOT_MEASURED,
        key_value_heads=candidate.key_value_heads,
        explicit_head_dim=candidate.head_dim,
        derived_head_dim=NOT_MEASURED,
        layer_count=candidate.layer_count,
        sliding_window=False,
    )
