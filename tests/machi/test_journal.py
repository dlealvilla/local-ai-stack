"""JSONL journal append, order, readback, and failure isolation (MACHI 0.3.2)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from machi.adapters.journal.jsonl import JsonlJournal
from machi.kernel.alive import kernel_alive
from machi.kernel.clock import FixedClock
from machi.kernel.errors import PersistenceError
from machi.kernel.events import EventRecord
from machi.kernel.schema import from_dict, to_dict

FIXED = dt.datetime(2026, 9, 14, 11, 0, tzinfo=dt.UTC)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def test_append_then_readback_preserves_the_event(
    tmp_path: Path, clock: FixedClock
) -> None:
    journal = JsonlJournal(tmp_path, clock=clock)
    stored = journal.append(kernel_alive(clock=clock))
    assert stored.recorded_at == FIXED
    records = journal.records()
    assert len(records) == 1
    assert records[0] == stored
    assert from_dict(to_dict(records[0])) == stored


def test_multiple_appends_preserve_order(tmp_path: Path, clock: FixedClock) -> None:
    journal = JsonlJournal(tmp_path, clock=clock)
    first = journal.append(kernel_alive(clock=clock))
    clock.advance(5)
    second = journal.append(kernel_alive(clock=clock))
    records = journal.records()
    assert [item.event_id for item in records] == [first.event_id, second.event_id]
    assert records[0].occurred_at < records[1].occurred_at
    assert first.event_id != second.event_id


def test_malformed_line_is_isolated_and_does_not_drop_neighbors(
    tmp_path: Path, clock: FixedClock
) -> None:
    journal = JsonlJournal(tmp_path, clock=clock)
    first = journal.append(kernel_alive(clock=clock))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write("{not-json\n")
    clock.advance(1)
    third = journal.append(kernel_alive(clock=clock))
    records = journal.records()
    defects = journal.defects()
    assert [item.event_id for item in records] == [first.event_id, third.event_id]
    assert len(defects) == 1
    assert defects[0].line_number == 2
    assert "JSON" in defects[0].problem


def test_failed_append_does_not_corrupt_prior_records(
    tmp_path: Path, clock: FixedClock
) -> None:
    journal = JsonlJournal(tmp_path, clock=clock)
    first = journal.append(kernel_alive(clock=clock))
    journal.path.chmod(0o444)
    try:
        with pytest.raises(PersistenceError):
            journal.append(kernel_alive(clock=clock))
    finally:
        journal.path.chmod(0o644)
    records = journal.records()
    assert len(records) == 1
    assert records[0].event_id == first.event_id


def test_non_event_record_line_is_a_defect(tmp_path: Path, clock: FixedClock) -> None:
    journal = JsonlJournal(tmp_path, clock=clock)
    journal.append(kernel_alive(clock=clock))
    with journal.path.open("a", encoding="utf-8") as handle:
        handle.write(
            '{"kind":"journal_defect","schema_version":1,'
            '"line_number":99,"problem":"planted","record_kind":null}\n'
        )
    defects = journal.defects()
    assert any(item.record_kind == "journal_defect" for item in defects)
    assert all(isinstance(item, EventRecord) for item in journal.records())
