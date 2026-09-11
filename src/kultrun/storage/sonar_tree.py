"""HOST-mode Sonar V2 decision tree. Units are abstract.

Production maps one unit to 1 GiB. Tests inject a tiny unit. The tree
does not search for an exact quota. Only CAPACITY may form an upper bound.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe

SONAR_TIER_UNITS: tuple[int, ...] = (16, 24, 32, 48, 64, 96, 128, 192, 256)
CHECKPOINTS_TO_64: tuple[int, ...] = (16, 24, 32, 48, 64)


class SonarAttempt(StrEnum):
    """Result of one target attempt. Only CAPACITY forms an upper bound."""

    SUCCESS = "success"
    CAPACITY = "capacity"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SonarTreeResult:
    """Proven lower-bound tier and optional exclusive upper bound, in units."""

    lower_units: Maybe[int]
    upper_units: Maybe[int]
    attempted: tuple[int, ...]


def specialist_bracket(s_units: int) -> tuple[int | None, int | None]:
    """Official V2 bracket around a specialist candidate, in units.

    ``L`` is the greatest tier ``<= S``. ``U`` is the smallest tier ``> S``.
    ``S < 16`` has no lower corroboration tier. ``S >= 256`` has no upper
    V2 tier.
    """
    lower: int | None = None
    upper: int | None = None
    for tier in SONAR_TIER_UNITS:
        if tier <= s_units:
            lower = tier
        elif upper is None:
            upper = tier
            break
    return lower, upper


def classify_sonar_tree(
    test: Callable[[int], SonarAttempt],
) -> SonarTreeResult:
    """Walk the V2 tree. ``test`` is attempted at most once per distinct target."""
    attempted: list[int] = []

    def run(target: int) -> SonarAttempt:
        attempted.append(target)
        return test(target)

    def proven(lower: int | None, upper: int | None) -> SonarTreeResult:
        return SonarTreeResult(
            lower_units=lower if lower else NOT_PROVIDED,
            upper_units=upper if upper else NOT_PROVIDED,
            attempted=tuple(attempted),
        )

    first = run(64)
    if first is SonarAttempt.OTHER:
        return proven(None, None)
    if first is SonarAttempt.SUCCESS:
        at_128 = run(128)
        if at_128 is SonarAttempt.OTHER:
            return proven(64, None)
        if at_128 is SonarAttempt.SUCCESS:
            at_256 = run(256)
            if at_256 is SonarAttempt.SUCCESS:
                return proven(256, None)
            if at_256 is SonarAttempt.OTHER:
                return proven(128, None)
            at_192 = run(192)
            if at_192 is SonarAttempt.SUCCESS:
                return proven(192, 256)
            if at_192 is SonarAttempt.CAPACITY:
                return proven(128, 192)
            return proven(128, 256)
        at_96 = run(96)
        if at_96 is SonarAttempt.SUCCESS:
            return proven(96, 128)
        if at_96 is SonarAttempt.CAPACITY:
            return proven(64, 96)
        return proven(64, 128)

    at_32 = run(32)
    if at_32 is SonarAttempt.OTHER:
        return proven(None, None)
    if at_32 is SonarAttempt.SUCCESS:
        at_48 = run(48)
        if at_48 is SonarAttempt.SUCCESS:
            return proven(48, 64)
        if at_48 is SonarAttempt.CAPACITY:
            return proven(32, 48)
        return proven(32, 64)

    at_16 = run(16)
    if at_16 is SonarAttempt.OTHER:
        return proven(None, None)
    if at_16 is SonarAttempt.SUCCESS:
        at_24 = run(24)
        if at_24 is SonarAttempt.SUCCESS:
            return proven(24, 32)
        if at_24 is SonarAttempt.CAPACITY:
            return proven(16, 24)
        return proven(16, 32)
    return proven(None, 16)
