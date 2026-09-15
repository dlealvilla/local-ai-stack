"""Entity Store port (MACHI 0.4.1).

Durably persist and retrieve versioned Machi contracts by a caller-owned
logical identity. The Store does not own domain meaning, filesystem
location policy, ownership, or cleanup.

This is not the event journal. Events record what happened. The Store
holds current entity contracts supplied by their owner. It is not
event-sourced: callers persist the contract; they do not reconstruct
it from the journal.

The storage root is injected. Kernel does not choose a host
installation root and does not read process environment configuration.
Exclusive create is the port contract. How a concrete adapter
publishes a new record (for example a filesystem link) is an
adapter choice, not a Store requirement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol, TypeVar, runtime_checkable

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract

RecordT = TypeVar("RecordT", bound=Contract)

_KEY_MAX_LENGTH: Final = 128
_KEY_PATTERN: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def validate_record_key(key: str) -> str:
    """Return the key, or refuse it.

    Logical keys are opaque identifiers. Separators and parent
    references are rejected, not sanitized, so a caller cannot be
    surprised by a rewritten identity. The reference filesystem
    adapter uses the key in a filename; that is an adapter choice,
    not a Store rule that every backend must be a filesystem.
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


@dataclass(frozen=True, slots=True)
class StoreCreateResult:
    """Outcome of an exclusive create. Not a persisted contract."""

    record: Contract
    created: bool
    existed: bool


@runtime_checkable
class Store(Protocol):
    """A replaceable entity store, keyed by contract kind and record key."""

    def create(self, key: str, record: Contract) -> StoreCreateResult:
        """Persist a new entity, or return an identical existing one.

        Conflicting or malformed existing records fail closed. The Store
        does not silently overwrite.
        """
        ...

    def get(self, contract_type: type[RecordT], key: str) -> RecordT:
        """Read and validate an entity. Missing and malformed fail closed."""
        ...
