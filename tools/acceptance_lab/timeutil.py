"""UTC timestamps and millisecond durations."""

from __future__ import annotations

import datetime as dt

UTC = dt.UTC


def require_utc(when: dt.datetime) -> dt.datetime:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware UTC")
    return when.astimezone(UTC)


def format_utc(when: dt.datetime) -> str:
    """ISO-8601 with ``Z`` and millisecond precision."""
    converted = require_utc(when)
    stamp = converted.isoformat(timespec="milliseconds")
    if stamp.endswith("+00:00"):
        return stamp[:-6] + "Z"
    raise ValueError(f"expected UTC datetime, got {stamp}")


def parse_utc(value: str) -> dt.datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return require_utc(dt.datetime.fromisoformat(text))


def duration_ms(started: dt.datetime, ended: dt.datetime) -> int:
    delta = require_utc(ended) - require_utc(started)
    return int(delta / dt.timedelta(milliseconds=1))
