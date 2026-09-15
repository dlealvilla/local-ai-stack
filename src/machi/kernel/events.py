"""EventRecord envelope (MACHI 0.3.1).

One versioned document form. Payloads are versioned contracts owned by the
emitting Block. Kernel owns the envelope, not the meaning of future
domain events.

Events record what happened. They are not the authoritative current
deployment state and are not replayed into ResourceManager, Plan, or
Install truth.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self

from machi.kernel.clock import Clock, SystemClock, require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.ids import (
    EventId,
    HierarchyId,
    HostId,
    InstallId,
    InstallRunId,
    Name,
)
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, Unresolved, UnresolvedReason

KERNEL_BLOCK = HierarchyId("0")
EVENT_RECORD_COMPONENT = HierarchyId("0.3.1")
KERNEL_ALIVE_TYPE = "kernel.alive"


class EventOutcome(StrEnum):
    """What the recorded action concluded. Not a boolean."""

    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    INFO = "info"
    UNRESOLVED = "unresolved"


@contract(kind="event_record", version=1)
@dataclass(frozen=True, slots=True)
class EventRecord(Contract):
    """One thing that happened, with enough context to correlate later."""

    event_id: EventId = meaning("opaque identity of this event")
    event_type: Name = meaning(
        "what happened, as a stable dotted name such as kernel.alive"
    )
    occurred_at: dt.datetime = meaning(
        "when the fact happened, timezone-aware UTC; never persist time"
    )
    install_id: Maybe[InstallId] = meaning(
        "this Machi installation; Unresolved until 1.1.1 persists InstallRecord"
    )
    install_run_id: Maybe[InstallRunId] = meaning(
        "deployment-journey correlation; Unresolved until Block 1 mints InstallRun"
    )
    host_id: Maybe[HostId] = meaning(
        "stable non-sensitive host id; Unresolved until Block 2 Discover"
    )
    block_id: HierarchyId = meaning("emitting Block, for example 0")
    component_id: HierarchyId = meaning(
        "emitting Component when known, for example 0.3.1"
    )
    outcome: EventOutcome = meaning("pass, fail, blocked, info, or unresolved")
    privacy: PrivacyClass = meaning("explicit privacy posture for this record")
    payload: Contract = meaning(
        "versioned domain body; Kernel does not own future payload meaning"
    )
    recorded_at: dt.datetime | None = meaning(
        "when the journal persisted the event; None until append",
        default=None,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "occurred_at", require_utc(self.occurred_at, what="occurred_at")
        )
        if self.recorded_at is not None:
            object.__setattr__(
                self,
                "recorded_at",
                require_utc(self.recorded_at, what="recorded_at"),
            )

    def with_recorded_at(self, when: dt.datetime) -> EventRecord:
        """Return a copy stamped with persist time. Facts are not mutated."""
        return replace(self, recorded_at=require_utc(when, what="recorded_at"))

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        block_id: str,
        component_id: str,
        outcome: EventOutcome,
        privacy: PrivacyClass,
        payload: Contract,
        install_id: Maybe[InstallId] | None = None,
        install_run_id: Maybe[InstallRunId] | None = None,
        host_id: Maybe[HostId] | None = None,
        clock: Clock | None = None,
    ) -> Self:
        """Mint a new event. Time is injected so ordering is testable."""
        missing = Unresolved(
            UnresolvedReason.NOT_PROVIDED,
            "not provided before Install/Discover",
        )
        return cls(
            event_id=EventId.generate(),
            event_type=Name(event_type),
            occurred_at=(clock or SystemClock()).now(),
            recorded_at=None,
            install_id=missing if install_id is None else install_id,
            install_run_id=missing if install_run_id is None else install_run_id,
            host_id=missing if host_id is None else host_id,
            block_id=HierarchyId(block_id),
            component_id=HierarchyId(component_id),
            outcome=outcome,
            privacy=privacy,
            payload=payload,
        )


def require_public_ops(event: EventRecord) -> None:
    """Refuse a kernel heartbeat that is not public operational metadata."""
    if event.privacy is not PrivacyClass.PUBLIC_OPS:
        raise ValidationError(
            "kernel.alive must be public_ops",
            privacy=event.privacy.value,
        )
