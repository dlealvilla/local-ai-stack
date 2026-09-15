"""Kernel-owned Store proof contract and proof event (MACHI 0.4.1).

``StoreProof`` is test/proof data. It is not a registry seed, not
ownership evidence, and not an Install record. Future 1.3.2 must
define its own contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from machi.kernel.clock import Clock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.store import StoreCreateResult

STORE_COMPONENT = "0.4.1"
STORE_PROVED_TYPE = "kernel.store.proved"
_TOKEN_MAX = 128


@contract(kind="kernel.store.proof", version=1)
@dataclass(frozen=True, slots=True)
class StoreProof(Contract):
    """Proof/test entity for Store. Not production ownership state."""

    token: str = meaning(
        "opaque proof token; not a domain identity and not customer content"
    )

    def __post_init__(self) -> None:
        if not self.token:
            raise ValidationError("store proof token must be a non-empty string")
        if len(self.token) > _TOKEN_MAX:
            raise ValidationError(
                "store proof token is too long",
                maximum=_TOKEN_MAX,
                length=len(self.token),
            )
        if "\x00" in self.token or "\n" in self.token or "\r" in self.token:
            raise ValidationError(
                "store proof token must not contain control characters"
            )


@contract(kind="kernel.store.proved", version=1)
@dataclass(frozen=True, slots=True)
class StoreProvedPayload(Contract):
    """Safe operational body for a Store proof. No path, no entity body."""

    record_kind: str = meaning("kind of the persisted proof contract")
    key_fingerprint: str = meaning(
        "SHA-256 hex digest of the UTF-8 logical key; the key itself is omitted"
    )
    created: bool = meaning("whether this invocation created a new record")
    existed: bool = meaning("whether a record already existed at this key")


def key_fingerprint(key: str) -> str:
    """Stable non-reversible identifier of a logical store key."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def store_proved(
    result: StoreCreateResult, *, key: str, clock: Clock | None = None
) -> EventRecord:
    """Mint the proof event. Does not persist it. Store does not depend on Journal."""
    return EventRecord.create(
        event_type=STORE_PROVED_TYPE,
        block_id="0",
        component_id=STORE_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.RESTRICTED,
        payload=StoreProvedPayload(
            record_kind=result.record.kind,
            key_fingerprint=key_fingerprint(key),
            created=result.created,
            existed=result.existed,
        ),
        clock=clock,
    )
