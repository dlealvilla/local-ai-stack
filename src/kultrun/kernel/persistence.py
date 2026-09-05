"""The persistence boundary.

A narrow port — get, put, delete, keys, records, reconcile — because a wide
query interface written before any caller exists is precisely the mistake
`docs/ROADMAP.md` Milestone 0 warns about. Implementations live in
``adapters/persistence``; nothing in the kernel imports them.

The reconciliation contract deserves attention, because it is where two of
the platform's rules first bite. A store **reports** the records it cannot
understand rather than skipping them, since a silently skipped record is how
a platform ends up lying about its own state. And it reports them as facts,
leaving policy to decide whether an unreadable record should stop startup —
which is "facts are immutable; policy reinterprets them" applied to the
kernel's own recovery path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol, TypeVar, runtime_checkable

from kultrun.kernel.errors import ValidationError
from kultrun.kernel.schema import Contract, contract, meaning

RecordT = TypeVar("RecordT", bound=Contract)

_KEY_MAX_LENGTH: Final = 128
_KEY_PATTERN: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def validate_record_key(key: str) -> str:
    """Return the key, or refuse it.

    A record key reaches the filesystem in the reference implementation, so a
    key containing a separator or a parent reference is **rejected, not
    sanitized**. Silently rewriting a key would mean the record is stored
    somewhere other than where the caller believes it is.
    """
    if not isinstance(key, str):
        raise ValidationError(
            "record key must be a string", actual_type=type(key).__name__
        )
    if len(key) > _KEY_MAX_LENGTH:
        raise ValidationError(
            "record key is too long", maximum=_KEY_MAX_LENGTH, length=len(key)
        )
    if not _KEY_PATTERN.match(key):
        raise ValidationError(
            "record key must be alphanumeric, with '.', '-' or '_' inside "
            "but not at either end; separators and parent references are refused",
            key=key,
        )
    if ".." in key:
        raise ValidationError("record key must not contain a parent reference", key=key)
    return key


@contract(kind="store_defect", version=1)
@dataclass(frozen=True, slots=True)
class StoreDefect(Contract):
    """A stored record the store could not load."""

    location: str = meaning("where the record is, relative to the store root")
    problem: str = meaning("why it could not be loaded")
    record_kind: str | None = meaning(
        "the kind it claimed to be, when that much was readable", default=None
    )


@contract(kind="store_reconciliation", version=1)
@dataclass(frozen=True, slots=True)
class ReconciliationReport(Contract):
    """What the store found when it opened.

    Facts only. Whether a defect should prevent startup is a policy question,
    answered by `platform` from Stage 0.3 onward.
    """

    swept_temporaries: int = meaning(
        "interrupted writes cleaned up; each was an orphan, never a record"
    )
    records_verified: int = meaning("records that loaded and validated")
    defects: tuple[StoreDefect, ...] = meaning(
        "records that could not be loaded, reported rather than skipped",
        default=(),
    )

    @property
    def is_clean(self) -> bool:
        """True when nothing needed sweeping and nothing was unreadable."""
        return self.swept_temporaries == 0 and len(self.defects) == 0


@runtime_checkable
class Store(Protocol):
    """A replaceable record store, keyed by contract kind and record key."""

    def put(self, key: str, record: Contract) -> None:
        """Write a record, atomically. An interrupted write leaves the old one."""
        ...

    def get(self, contract_type: type[RecordT], key: str) -> RecordT | None:
        """Read a record, or None when it does not exist."""
        ...

    def delete(self, contract_type: type[Contract], key: str) -> bool:
        """Remove a record. True when something was removed."""
        ...

    def keys(self, contract_type: type[Contract]) -> tuple[str, ...]:
        """Every key stored for this contract kind."""
        ...

    def records(self, contract_type: type[RecordT]) -> tuple[RecordT, ...]:
        """Every record of this kind."""
        ...

    def reconcile(self) -> ReconciliationReport:
        """Clean up interrupted writes and report what cannot be loaded."""
        ...
