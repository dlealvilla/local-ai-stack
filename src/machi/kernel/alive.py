"""kernel.alive — the first Kernel event (payload owned by Kernel).

Privacy is always public_ops. The payload is build identity, never
customer content, environment dumps, or filesystem secrets.

Each invocation mints a new EventRecord (new event_id) and appends.
Safe re-entry is not a singleton: the journal is append-oriented.
InstallRun remains Unresolved until Block 1.
"""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.build import BuildIdentity, identity
from machi.kernel.clock import Clock
from machi.kernel.errors import ValidationError
from machi.kernel.events import (
    EVENT_RECORD_COMPONENT,
    KERNEL_ALIVE_TYPE,
    KERNEL_BLOCK,
    EventOutcome,
    EventRecord,
    require_public_ops,
)
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning


@contract(kind="kernel.alive", version=1)
@dataclass(frozen=True, slots=True)
class KernelAlivePayload(Contract):
    """Public build identity for the first persisted event."""

    distribution: str = meaning("distribution name; always machi")
    version: str = meaning("installed or declared package version")
    origin: str = meaning("artifact or source")
    source_commit: str | None = meaning(
        "git commit the artifact was built from; None in a checkout",
        default=None,
    )
    build_id: str | None = meaning("traceable build identifier", default=None)
    built_at: str | None = meaning("UTC timestamp the artifact was built", default=None)
    clean_source: bool | None = meaning(
        "whether the source tree was clean at build time", default=None
    )

    def __post_init__(self) -> None:
        if self.distribution != "machi":
            raise ValidationError(
                "kernel.alive distribution must be machi",
                distribution=self.distribution,
            )


def payload_from_identity(build: BuildIdentity) -> KernelAlivePayload:
    """Map build identity onto the public_ops payload contract."""
    return KernelAlivePayload(
        distribution="machi",
        version=build.version,
        origin=build.origin.value,
        source_commit=build.source_commit,
        build_id=build.build_id,
        built_at=build.built_at,
        clean_source=build.clean_source,
    )


def kernel_alive(*, clock: Clock | None = None) -> EventRecord:
    """Construct the canonical first event. Does not persist it."""
    event = EventRecord.create(
        event_type=KERNEL_ALIVE_TYPE,
        block_id=KERNEL_BLOCK.value,
        component_id=EVENT_RECORD_COMPONENT.value,
        outcome=EventOutcome.INFO,
        privacy=PrivacyClass.PUBLIC_OPS,
        payload=payload_from_identity(identity()),
        clock=clock,
    )
    require_public_ops(event)
    return event
