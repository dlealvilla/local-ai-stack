"""Normalized model-evaluation evidence from a replaceable provider.

AI_DEPLOYMENT_MODEL_EVALUATION

Model intelligence — which of several feasible candidates is actually
the better choice — is a domain the platform does not need to own. It is
therefore behind a provider boundary from the start:

    ModelEvaluationProvider          (this contract)
      + LlmfitEvaluationAdapter      (first implementation)
      + future providers

Core owns the normalized evidence shape and the selection policy that
consumes it. A provider owns its own invocation, its own wire format and
its own failure modes, and translates into this contract. Nothing here
knows what a provider's raw output looks like.

The contract is deliberately small. It carries the few figures a
selector can act on, every one of them optional except identity and
usability, because a provider that cannot score a candidate must be able
to say so rather than be forced to invent a number.

Evidence is advisory. It can order feasible candidates; it can never
make an infeasible one selectable. Hard feasibility stays with
`core.capacity_feasibility`, and safe capacity stays with the platform's
CapacityEnvelope.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


MODEL_EVALUATION_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelEvaluationEvidence:
    """What a provider concluded about one candidate.

    `rank` is the provider's own deterministic ordering, lower being
    better, and is the only ordering signal the selector acts on. The
    scores are carried for explainability rather than re-weighted:
    inventing a platform formula over a provider's numbers would make
    the provider unreplaceable.

    `usable` is false when the provider returned nothing actionable for
    this candidate, including the case where it simply could not be
    matched to a provider result.
    """

    candidate_id: str
    provider: str
    usable: bool
    rank: int | None = None
    overall_score: float | None = None
    fit_score: float | None = None
    quality_score: float | None = None
    speed_score: float | None = None
    context_score: float | None = None
    fit_level: str | None = None
    recommended_quantization: str | None = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelEvaluationResult:
    """A provider's response for a whole candidate set.

    `available` is false whenever the provider could not be consulted at
    all: not provisioned, failed to run, timed out, or produced output
    that could not be trusted. A selector treats that as a reason to
    fall back, never as a reason to fail.
    """

    schema_version: int
    provider: str
    available: bool
    reason: str | None = None
    evidence: tuple[ModelEvaluationEvidence, ...] = ()
    invocation: dict[str, Any] = field(
        default_factory=dict
    )

    def for_candidate(
        self,
        candidate_id: str,
    ) -> ModelEvaluationEvidence | None:
        for entry in self.evidence:
            if entry.candidate_id == candidate_id:
                return entry

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "available": self.available,
            "reason": self.reason,
            "evidence": [
                entry.to_dict()
                for entry in self.evidence
            ],
            "invocation": dict(self.invocation),
        }


def unavailable(
    provider: str,
    reason: str,
) -> ModelEvaluationResult:
    """The response every provider returns when it cannot be consulted."""

    return ModelEvaluationResult(
        schema_version=(
            MODEL_EVALUATION_SCHEMA_VERSION
        ),
        provider=provider,
        available=False,
        reason=reason,
    )


class ModelEvaluationProvider(Protocol):
    """Implemented by adapters; never by core.

    `candidates` are the platform's eligible candidates and `envelope`
    is the platform's authoritative safe capacity. A provider must
    describe capacity to its own tooling using the envelope, not by
    detecting hardware itself, so platform headroom policy cannot be
    bypassed.
    """

    def evaluate(
        self,
        *,
        candidates,
        envelope,
        config=None,
    ) -> ModelEvaluationResult:
        ...
