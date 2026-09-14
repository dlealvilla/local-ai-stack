"""Platform time.

Every timestamp Machi persists is timezone-aware UTC. A naive datetime
is refused rather than assumed. Time is injected so journal tests do not
wait on the wall clock.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol, runtime_checkable

from machi.kernel.errors import ValidationError


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
    """A clock that does not move, or moves only when told to."""

    def __init__(self, instant: dt.datetime) -> None:
        self._instant = require_utc(instant, what="fixed clock instant")

    def now(self) -> dt.datetime:
        return self._instant

    def advance(self, seconds: float) -> None:
        self._instant = self._instant + dt.timedelta(seconds=seconds)
