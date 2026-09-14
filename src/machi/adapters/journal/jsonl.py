"""JSON Lines EventRecord journal.

Deterministic serialization (sorted keys, compact separators). One document
per line. A later append failure must not rewrite earlier lines.

This is not an entity store and not a warehouse. The directory is
injected; Kernel does not choose the host installation root.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import PersistenceError, ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.journal import JournalDefect
from machi.kernel.schema import from_dict, to_dict

JOURNAL_FILENAME = "events.jsonl"


class JsonlJournal:
    """Append-only JSONL adapter for :class:`EventRecord`."""

    def __init__(self, root: Path, *, clock: Clock | None = None) -> None:
        self._root = Path(root)
        self._clock = clock or SystemClock()
        self._path = self._root / JOURNAL_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: EventRecord) -> EventRecord:
        stamped = (
            event
            if event.recorded_at is not None
            else event.with_recorded_at(self._clock.now())
        )
        try:
            document = to_dict(stamped)
            line = json.dumps(
                document, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise PersistenceError(
                "event could not be serialized",
                event_id=str(event.event_id),
            ) from exc
        if "\n" in line or "\r" in line:
            raise PersistenceError(
                "serialized event contains a newline and cannot be journaled",
                event_id=str(event.event_id),
            )
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise PersistenceError(
                "failed to append event to the journal",
                path=str(self._path),
            ) from exc
        return stamped

    def records(self) -> tuple[EventRecord, ...]:
        valid, _defects = self._scan()
        return valid

    def defects(self) -> tuple[JournalDefect, ...]:
        _valid, defects = self._scan()
        return defects

    def _scan(self) -> tuple[tuple[EventRecord, ...], tuple[JournalDefect, ...]]:
        if not self._path.exists():
            return (), ()
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PersistenceError(
                "failed to read the journal",
                path=str(self._path),
            ) from exc
        records: list[EventRecord] = []
        defects: list[JournalDefect] = []
        for number, raw in enumerate(text.splitlines(), start=1):
            if raw.strip() == "":
                continue
            defect = _decode_line(number, raw)
            if isinstance(defect, JournalDefect):
                defects.append(defect)
            else:
                records.append(defect)
        return tuple(records), tuple(defects)


def _decode_line(line_number: int, raw: str) -> EventRecord | JournalDefect:
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError as exc:
        return JournalDefect(
            line_number=line_number,
            problem=f"malformed JSON: {exc.msg}",
            record_kind=None,
        )
    if not isinstance(loaded, dict):
        return JournalDefect(
            line_number=line_number,
            problem="line is not a JSON object",
            record_kind=None,
        )
    kind = loaded.get("kind") if isinstance(loaded.get("kind"), str) else None
    try:
        decoded = from_dict(loaded, extra="ignore")
    except (ValidationError, TypeError, ValueError) as exc:
        return JournalDefect(
            line_number=line_number,
            problem=str(exc),
            record_kind=kind,
        )
    if not isinstance(decoded, EventRecord):
        return JournalDefect(
            line_number=line_number,
            problem=f"journal line is {decoded.kind}, not event_record",
            record_kind=decoded.kind,
        )
    return decoded
