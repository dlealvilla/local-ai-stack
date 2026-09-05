"""Platform time.

Every timestamp Kultrun persists or exposes is timezone-aware UTC. A naive
datetime is refused rather than assumed to be local or assumed to be UTC,
because a persisted naive timestamp is not recoverable afterwards.

Time is injected rather than read from the module, so that reconciliation
and evidence-freshness behaviour is testable without waiting.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from kultrun.kernel.errors import ValidationError


def now_utc() -> dt.datetime:
    """The current instant, timezone-aware in UTC."""
    return dt.datetime.now(dt.UTC)


def require_utc(value: dt.datetime, *, what: str = "timestamp") -> dt.datetime:
    """Return the value normalized to UTC, or refuse a naive datetime."""
    if value.tzinfo is None:
        raise ValidationError(
            f"{what} must be timezone-aware; a naive datetime is ambiguous",
            what=what,
        )
    return value.astimezone(dt.UTC)


@runtime_checkable
class Clock(Protocol):
    """The source of platform time."""

    def now(self) -> dt.datetime:
        """The current instant, timezone-aware in UTC."""
        ...


class SystemClock:
    """The wall clock. First-class, not an adapter — there is no vendor here."""

    def now(self) -> dt.datetime:
        return now_utc()


class FixedClock:
    """A clock that does not move, or moves only when told to.

    Present in the kernel rather than in test support because deterministic
    time is needed by every later stage that reconciles state or ages
    evidence, not only by this one.
    """

    def __init__(self, instant: dt.datetime) -> None:
        self._instant = require_utc(instant, what="fixed clock instant")

    def now(self) -> dt.datetime:
        return self._instant

    def advance(self, seconds: float) -> None:
        self._instant = self._instant + dt.timedelta(seconds=seconds)
