"""The domain event envelope.

Only the envelope. There is no bus, no publisher and no subscriber in this
stage, because none exists to design against — `docs/ROADMAP.md` Milestone 0
warns specifically about contracts written before a caller exists.

The envelope carries a **correlation identifier from the first event**, so a
request stays traceable across gateway, inference, usage and analytics.
Threading correlation through a finished serving path afterwards is
expensive, and it is the cheapest thing in this module today.

Domain events are built by placing a payload contract inside this envelope
rather than by subclassing it: ``UsageEvent`` at Stage 1.7 and
``AuditEvent`` at Stage 0.2 are payloads with their own kinds and versions,
so they version independently of the envelope that carries them.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Self

from kultrun.kernel.clock import Clock, SystemClock, require_utc
from kultrun.kernel.ids import EventId, Name
from kultrun.kernel.schema import Contract, contract, meaning


@contract(kind="event", version=1)
@dataclass(frozen=True, slots=True)
class Event(Contract):
    """One thing that happened, with enough context to trace it."""

    event_id: EventId = meaning("platform-minted identity of this event")
    event_type: Name = meaning(
        "what happened, as a stable dotted name such as 'workload.admitted'"
    )
    occurred_at: dt.datetime = meaning(
        "when it happened, timezone-aware UTC; never the time it was recorded"
    )
    source: Name = meaning("the module that emitted it")
    correlation_id: str | None = meaning(
        "identifier tying this event to the request or operation that caused it",
        default=None,
    )
    payload: Contract | None = meaning(
        "the domain-specific body, itself a versioned contract", default=None
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, what="occurred_at")
        )

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        source: str,
        payload: Contract | None = None,
        correlation_id: str | None = None,
        clock: Clock | None = None,
    ) -> Self:
        """Mint a new event. Time is injected so that ordering is testable."""
        return cls(
            event_id=EventId.generate(),
            event_type=Name(event_type),
            occurred_at=(clock or SystemClock()).now(),
            source=Name(source),
            correlation_id=correlation_id,
            payload=payload,
        )
