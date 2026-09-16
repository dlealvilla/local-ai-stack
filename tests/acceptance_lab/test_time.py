"""UTC timestamps and millisecond durations."""

from __future__ import annotations

import datetime as dt

import pytest
from tools.acceptance_lab.timeutil import duration_ms, format_utc, parse_utc


def test_format_and_parse_roundtrip() -> None:
    when = dt.datetime(2026, 9, 16, 10, 20, 0, tzinfo=dt.UTC)
    text = format_utc(when)
    assert text.endswith("Z")
    assert "+00:00" not in text
    assert parse_utc(text) == when.replace(microsecond=0)


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_utc(dt.datetime(2026, 9, 16, 10, 20, 0))


def test_duration_ms() -> None:
    start = dt.datetime(2026, 9, 16, 10, 0, 0, tzinfo=dt.UTC)
    end = dt.datetime(2026, 9, 16, 10, 1, 30, tzinfo=dt.UTC)
    assert duration_ms(start, end) == 90_000
