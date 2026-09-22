"""Turn a resolved candidate into a FoundationSelection. No host I/O."""

from __future__ import annotations

from machi.foundation.contracts import (
    AcceleratorBackend,
    FailureCode,
    FoundationCandidate,
    FoundationSelection,
    SupportState,
)
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved


def selection_from_candidate(
    candidate: FoundationCandidate,
    *,
    selection_id: str,
    capacity_evidence_id: str,
    generation_id: str | None = None,
    ready: bool = False,
) -> FoundationSelection:
    """Record the macropath decision. Ready only after verification."""
    support = SupportState.READY if ready else candidate.support
    usable = candidate.failure is FailureCode.NONE
    backend: Maybe[AcceleratorBackend]
    if is_resolved(candidate.backend):
        backend = candidate.backend
    else:
        backend = NOT_PROVIDED
    candidate_id = candidate.candidate_id if usable else NOT_PROVIDED
    generation = generation_id if generation_id else NOT_PROVIDED
    if ready and not is_resolved(generation):
        support = SupportState.VERIFICATION_FAILED
    return FoundationSelection(
        selection_id=selection_id,
        family=candidate.family,
        engine=candidate.engine,
        executor=candidate.executor,
        backend=backend,
        support=support,
        failure=candidate.failure if not ready else FailureCode.NONE,
        candidate_id=candidate_id,
        generation_id=generation,
        capacity_evidence_id=capacity_evidence_id,
        reason=candidate.reason,
    )
