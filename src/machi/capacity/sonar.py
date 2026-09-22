"""Bounded Storage Sonar search. The schedule is data, not a fill loop."""

from __future__ import annotations

from dataclasses import dataclass

from machi.capacity.contracts import SonarEvidence, SonarFailure, SonarStatus
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_MEASURED, Maybe, is_resolved

_HARD = frozenset({SonarFailure.EDQUOT, SonarFailure.ENOSPC})
_STOP = frozenset(
    {
        SonarFailure.PERMISSION,
        SonarFailure.READ_ONLY,
        SonarFailure.IO_ERROR,
        SonarFailure.TIMEOUT,
        SonarFailure.INTERRUPTED,
        SonarFailure.UNEXPECTED,
    }
)


@dataclass(frozen=True, slots=True)
class SonarWriteResult:
    """One extend attempt. Not a throughput measurement."""

    failure: SonarFailure
    committed_bytes: int


class SonarMedia:
    """Grows one owned probe file. Implementations must not use sparse holes."""

    def extend_to(self, nbytes: int) -> SonarWriteResult:
        """Commit real bytes up to ``nbytes``. Do not follow links or fill the disk."""
        raise NotImplementedError

    def cleanup(self) -> bool:
        """Remove the owned probe file. True when nothing owned remains."""
        raise NotImplementedError


def run_sonar(
    media: SonarMedia,
    *,
    upward: tuple[int, ...],
    refine: tuple[int, ...],
    downward: tuple[int, ...],
    reported_available_bytes: Maybe[int],
    reserve_bytes: int,
    max_tier_bytes: int,
) -> SonarEvidence:
    """Search a tier ladder. Never attempt a tier that would consume the reserve."""
    if reserve_bytes < 0 or max_tier_bytes < 1:
        raise ValidationError("sonar bounds must be positive")
    budget = _budget(reported_available_bytes, reserve_bytes)
    if budget is not None and budget <= 0:
        return _evidence(
            SonarStatus.STOPPED_FOR_RESERVE,
            NOT_MEASURED,
            NOT_MEASURED,
            SonarFailure.NONE,
            (),
            True,
            "reported capacity does not cover the emergency reserve",
        )
    allowed_up = _fit(upward, budget, max_tier_bytes)
    allowed_down = _fit(downward, budget, max_tier_bytes)
    allowed_refine = _fit(refine, budget, max_tier_bytes)
    if not allowed_up and not allowed_down:
        return _evidence(
            SonarStatus.STOPPED_FOR_RESERVE,
            NOT_MEASURED,
            NOT_MEASURED,
            SonarFailure.NONE,
            (),
            True,
            "no sonar tier fits under the reserve",
        )
    proven = 0
    upper: int | None = None
    failure = SonarFailure.NONE
    attempted: list[int] = []
    pending = list(allowed_up) if allowed_up else sorted(allowed_down, reverse=True)
    refine_left = list(allowed_refine)
    down_left = sorted(allowed_down, reverse=True)

    def attempt(target: int) -> SonarFailure:
        attempted.append(target)
        result = media.extend_to(target)
        return result.failure

    while pending:
        target = pending.pop(0)
        if target <= proven:
            continue
        outcome = attempt(target)
        if outcome is SonarFailure.NONE:
            proven = target
            pending = [item for item in pending if item > proven]
            continue
        failure = outcome
        if outcome in _HARD:
            upper = target
            between = [
                item
                for item in (*refine_left, *down_left)
                if proven < item < target and item not in attempted
            ]
            pending = sorted(between, reverse=True)
            refine_left = []
            down_left = []
            continue
        break
    if failure in _STOP and proven == 0:
        cleaned = media.cleanup()
        return _evidence(
            SonarStatus.UNRESOLVED,
            NOT_MEASURED,
            NOT_MEASURED,
            failure,
            tuple(attempted),
            cleaned,
            f"sonar stopped on {failure.value} before any tier committed",
        )
    cleaned = media.cleanup()
    if upper is not None:
        return _evidence(
            SonarStatus.CONTRADICTED,
            proven if proven else NOT_MEASURED,
            upper,
            failure,
            tuple(attempted),
            cleaned,
            "a hard write failure landed below the reported available bytes",
        )
    if proven:
        return _evidence(
            SonarStatus.CORROBORATED,
            proven,
            NOT_MEASURED,
            SonarFailure.NONE,
            tuple(attempted),
            cleaned,
            "proven tier does not exceed the trusted reported ceiling",
        )
    return _evidence(
        SonarStatus.UNRESOLVED,
        NOT_MEASURED,
        NOT_MEASURED,
        failure,
        tuple(attempted),
        cleaned,
        "sonar did not establish a writable tier",
    )


def _budget(reported: Maybe[int], reserve: int) -> int | None:
    if not is_resolved(reported):
        return None
    return int(reported) - reserve


def _fit(tiers: tuple[int, ...], budget: int | None, maximum: int) -> list[int]:
    chosen = [tier for tier in tiers if 0 < tier <= maximum]
    if budget is None:
        return chosen
    return [tier for tier in chosen if tier <= budget]


def _evidence(
    status: SonarStatus,
    lower: Maybe[int],
    upper: Maybe[int],
    failure: SonarFailure,
    attempted: tuple[int, ...],
    cleaned: bool,
    reason: str,
) -> SonarEvidence:
    return SonarEvidence(
        status=status,
        proven_lower_bytes=lower,
        contradictory_upper_bytes=upper,
        failure=failure,
        tiers_attempted=attempted,
        cleanup_completed=cleaned,
        reason=reason,
    )


def not_attempted() -> SonarEvidence:
    """Sonar did not run. That is not a zero-byte proof."""
    return SonarEvidence(
        status=SonarStatus.NOT_ATTEMPTED,
        proven_lower_bytes=NOT_MEASURED,
        contradictory_upper_bytes=NOT_MEASURED,
        failure=SonarFailure.NONE,
        tiers_attempted=(),
        cleanup_completed=NOT_MEASURED,
        reason="sonar writes were not requested",
    )
