"""Choose one model configuration for this host.

AI_DEPLOYMENT_MODEL_SELECTION

    feasible candidates + evaluation evidence -> one selection

Two rules do the work. Hard feasibility is not this module's business:
`core.capacity_feasibility` has already decided which candidates could
run, and a candidate it rejected can never be selected here no matter
what a provider says about it. And a fully compatible candidate always
outranks a merely conditional one, because preferring an uncertain
candidate over a proven one would be a strange definition of "best".

Within the active tier, an evaluation provider orders the candidates. If
there is no provider, or it cannot be consulted, or none of the eligible
candidates appear in its results, selection falls back to closest safe
fit: the candidate using the most of its safe primary inference memory
without exceeding it. That reuses the utilization figure feasibility
already computed, so feasibility is never re-derived here.

Deliberately vendor-neutral. This module reasons about candidate
identity, a feasibility verdict, normalized provider evidence and a
utilization ratio. It contains no accelerator vendor, runtime or
quantization decisions, so supporting new hardware means writing an
adapter rather than changing selection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.capacity_feasibility import (
    CHECK_PASS,
    RESOURCE_PRIMARY_INFERENCE_MEMORY,
    VERDICT_COMPATIBLE,
    VERDICT_CONDITIONALLY_COMPATIBLE,
    FeasibilityResult,
)
from core.model_evaluation import (
    ModelEvaluationEvidence,
)
from core.model_requirement import ModelRequirement


MODEL_SELECTION_SCHEMA_VERSION = 1


TIER_COMPATIBLE = "compatible"
TIER_CONDITIONAL = "conditional"

STATUS_SELECTED = "selected"
STATUS_NO_SELECTION = "no_selection"

PROVIDER_NONE = "none"
PROVIDER_FALLBACK = (
    "safe_primary_memory_fallback"
)


@dataclass(frozen=True)
class SelectionCandidate:
    """One candidate configuration with its feasibility verdict.

    `evaluation_id` is the only identity seam to a provider: the name
    that provider knows this candidate by, when it differs from ours.
    It defaults to `candidate_id`. Matching is exact by design — a
    fuzzy match that silently paired the wrong model would be worse
    than no evidence at all.
    """

    candidate_id: str
    requirement: ModelRequirement
    feasibility: FeasibilityResult
    evaluation_id: str | None = None

    @property
    def provider_identity(self) -> str:
        return (
            self.evaluation_id
            or self.candidate_id
        )


@dataclass(frozen=True)
class ModelSelectionResult:
    schema_version: int
    status: str
    selected_candidate_id: str | None
    eligibility_tier: str | None
    selection_provider: str
    evidence: ModelEvaluationEvidence | None
    fallback_utilization: float | None
    reason: str
    considered_count: int
    excluded_unsupported_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "selected_candidate_id": (
                self.selected_candidate_id
            ),
            "eligibility_tier": (
                self.eligibility_tier
            ),
            "selection_provider": (
                self.selection_provider
            ),
            "evidence": (
                self.evidence.to_dict()
                if self.evidence is not None
                else None
            ),
            "fallback_utilization": (
                self.fallback_utilization
            ),
            "reason": self.reason,
            "considered_count": (
                self.considered_count
            ),
            "excluded_unsupported_count": (
                self.excluded_unsupported_count
            ),
        }


def _no_selection(
    *,
    tier,
    reason,
    considered,
    excluded,
) -> ModelSelectionResult:
    return ModelSelectionResult(
        schema_version=(
            MODEL_SELECTION_SCHEMA_VERSION
        ),
        status=STATUS_NO_SELECTION,
        selected_candidate_id=None,
        eligibility_tier=tier,
        selection_provider=PROVIDER_NONE,
        evidence=None,
        fallback_utilization=None,
        reason=reason,
        considered_count=considered,
        excluded_unsupported_count=excluded,
    )


def _eligible_tier(candidates):
    """Compatible candidates if any exist, else conditional ones."""

    compatible = [
        candidate
        for candidate in candidates
        if candidate.feasibility.verdict
        == VERDICT_COMPATIBLE
    ]

    if compatible:
        return TIER_COMPATIBLE, compatible

    conditional = [
        candidate
        for candidate in candidates
        if candidate.feasibility.verdict
        == VERDICT_CONDITIONALLY_COMPATIBLE
    ]

    return TIER_CONDITIONAL, conditional


def _safe_utilization(candidate):
    """The candidate's proven primary-memory utilization, or None.

    Taken from the feasibility result rather than recomputed, so
    selection cannot disagree with the gate that admitted the
    candidate. Only a passing check yields a figure; an unresolved one
    leaves the candidate without fallback information.
    """

    check = candidate.feasibility.check(
        RESOURCE_PRIMARY_INFERENCE_MEMORY
    )

    if check is None:
        return None

    if check.status != CHECK_PASS:
        return None

    if check.utilization is None:
        return None

    if check.utilization > 1.0:
        return None

    return check.utilization


def _select_by_provider(
    *,
    eligible,
    evaluation,
):
    """The provider's best-ranked eligible candidate, or None.

    Ties, and candidates the provider ranked identically, fall back to
    the order the caller supplied.
    """

    ranked = []

    for position, candidate in enumerate(eligible):
        evidence = evaluation.for_candidate(
            candidate.candidate_id
        )

        if evidence is None or not evidence.usable:
            continue

        if evidence.rank is None:
            continue

        ranked.append(
            (evidence.rank, position, candidate, evidence)
        )

    if not ranked:
        return None, None

    ranked.sort(key=lambda entry: entry[:2])

    return ranked[0][2], ranked[0][3]


def _select_by_safe_fit(eligible):
    """The candidate using the most safe primary memory without exceeding it."""

    scored = []

    for position, candidate in enumerate(eligible):
        utilization = _safe_utilization(candidate)

        if utilization is None:
            continue

        #
        # Negative utilization sorts the largest first while position
        # breaks ties in favour of the caller's order.
        #
        scored.append(
            (-utilization, position, candidate, utilization)
        )

    if not scored:
        return None, None

    scored.sort(key=lambda entry: entry[:2])

    return scored[0][2], scored[0][3]


def select_model(
    *,
    candidates,
    envelope,
    evaluation_provider=None,
    config=None,
):
    """Select one candidate configuration, or report that none can be.

    Never downloads, reserves, starts or mutates anything. The result
    is a decision for a later step to act on.
    """

    candidates = list(candidates)

    for candidate in candidates:
        if not isinstance(
            candidate,
            SelectionCandidate,
        ):
            raise TypeError(
                "candidates must be SelectionCandidate "
                "instances"
            )

    excluded = len([
        candidate
        for candidate in candidates
        if candidate.feasibility.verdict
        not in {
            VERDICT_COMPATIBLE,
            VERDICT_CONDITIONALLY_COMPATIBLE,
        }
    ])

    tier, eligible = _eligible_tier(candidates)

    if not eligible:
        return _no_selection(
            tier=None,
            reason=(
                "no candidate is compatible or "
                "conditionally compatible"
            ),
            considered=0,
            excluded=excluded,
        )

    evaluation = None

    if evaluation_provider is not None:
        evaluation = evaluation_provider.evaluate(
            candidates=eligible,
            envelope=envelope,
            config=config,
        )

    if evaluation is not None and evaluation.available:
        candidate, evidence = _select_by_provider(
            eligible=eligible,
            evaluation=evaluation,
        )

        if candidate is not None:
            return ModelSelectionResult(
                schema_version=(
                    MODEL_SELECTION_SCHEMA_VERSION
                ),
                status=STATUS_SELECTED,
                selected_candidate_id=(
                    candidate.candidate_id
                ),
                eligibility_tier=tier,
                selection_provider=(
                    evaluation.provider
                ),
                evidence=evidence,
                fallback_utilization=None,
                reason=(
                    "highest ranked "
                    + tier
                    + " candidate according to "
                    + evaluation.provider
                ),
                considered_count=len(eligible),
                excluded_unsupported_count=excluded,
            )

    #
    # Closest safe fit. Reached when there is no provider, the provider
    # could not be consulted, or none of the eligible candidates had
    # usable provider evidence.
    #
    candidate, utilization = _select_by_safe_fit(
        eligible
    )

    if candidate is None:
        return _no_selection(
            tier=tier,
            reason=(
                "no eligible candidate has a resolved "
                "primary inference memory requirement to "
                "select on"
            ),
            considered=len(eligible),
            excluded=excluded,
        )

    if evaluation is None:
        detail = "no evaluation provider was supplied"

    elif not evaluation.available:
        detail = (
            "evaluation provider unavailable: "
            + str(evaluation.reason)
        )

    else:
        detail = (
            "no eligible candidate had usable "
            + evaluation.provider
            + " evidence"
        )

    return ModelSelectionResult(
        schema_version=(
            MODEL_SELECTION_SCHEMA_VERSION
        ),
        status=STATUS_SELECTED,
        selected_candidate_id=(
            candidate.candidate_id
        ),
        eligibility_tier=tier,
        selection_provider=PROVIDER_FALLBACK,
        evidence=None,
        fallback_utilization=utilization,
        reason=(
            "closest safe primary-memory fit; "
            + detail
        ),
        considered_count=len(eligible),
        excluded_unsupported_count=excluded,
    )
