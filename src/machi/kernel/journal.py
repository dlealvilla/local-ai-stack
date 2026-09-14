"""Append-oriented event journal port (MACHI 0.3.2).

The journal records what happened. It is not the entity store (0.4.1)
and it is not the Install state-root policy (Block 1). Callers inject
a directory. Implementations live in ``machi.adapters``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from machi.kernel.events import EventRecord
from machi.kernel.schema import Contract, contract, meaning


@contract(kind="journal_defect", version=1)
@dataclass(frozen=True, slots=True)
class JournalDefect(Contract):
    """A journal line the adapter could not load.

    Reported as a fact. Prior valid records remain readable. Policy decides
    whether a defect fails a later milestone; M0 readback never pretends
    a corrupt line was a successful event.
    """

    line_number: int = meaning("1-based line number in the journal file")
    problem: str = meaning("why the line could not be loaded")
    record_kind: str | None = meaning(
        "the kind it claimed to be, when that much was readable", default=None
    )


@runtime_checkable
class Journal(Protocol):
    """Durable append log of EventRecord documents."""

    def append(self, event: EventRecord) -> EventRecord:
        """Persist one event. Returns the record including ``recorded_at``.

        A failed append must not rewrite or delete previously valid lines.
        """
        ...

    def records(self) -> tuple[EventRecord, ...]:
        """Valid events in append order. Does not include defects."""
        ...

    def defects(self) -> tuple[JournalDefect, ...]:
        """Lines that could not be decoded. Empty when the file is clean."""
        ...
