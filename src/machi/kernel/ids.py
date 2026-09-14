"""Typed identifiers (MACHI 0.2.1).

Minted identifiers are opaque, prefixed, and typed so an event id cannot
be passed where an install-run id is expected. Names are externally
meaningful. Hierarchy IDs are the architecture's ``N``, ``N.M``, ``N.M.P``
strings and are not names — they start with digits.

Generation uses the standard library only. Identity is a Machi concept.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import ClassVar, Final, Self

from machi.kernel.errors import InternalError, ValidationError

_TOKEN_BYTES: Final = 8
_TOKEN_LENGTH: Final = _TOKEN_BYTES * 2

_PREFIX_PATTERN: Final = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_TOKEN_PATTERN: Final = re.compile(rf"^[0-9a-f]{{{_TOKEN_LENGTH}}}$")

_NAME_MAX_LENGTH: Final = 64
_NAME_PATTERN: Final = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")

#: Block `N`, Capability `N.M`, or Component `N.M.P`.
_HIERARCHY_PATTERN: Final = re.compile(
    r"^(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){0,2}$"
)


@dataclass(frozen=True, slots=True)
class EntityId:
    """An opaque identifier for one kind of entity."""

    prefix: ClassVar[str] = ""
    value: str

    def __post_init__(self) -> None:
        prefix = self._require_prefix()
        expected_start = f"{prefix}_"
        if not self.value.startswith(expected_start):
            raise ValidationError(
                "identifier has the wrong prefix for its type",
                expected_prefix=prefix,
                value=self.value,
            )
        token = self.value[len(expected_start) :]
        if not _TOKEN_PATTERN.match(token):
            raise ValidationError(
                "identifier body is malformed",
                expected=f"{_TOKEN_LENGTH} lowercase hexadecimal characters",
                value=self.value,
            )

    @classmethod
    def _require_prefix(cls) -> str:
        if not cls.prefix:
            raise InternalError(
                "EntityId subclass declares no prefix", entity=cls.__qualname__
            )
        if not _PREFIX_PATTERN.match(cls.prefix):
            raise InternalError(
                "EntityId prefix must be lowercase snake_case",
                entity=cls.__qualname__,
                prefix=cls.prefix,
            )
        return cls.prefix

    @classmethod
    def generate(cls) -> Self:
        """Mint a new identifier. Collision probability is negligible at 64 bits."""
        prefix = cls._require_prefix()
        return cls(f"{prefix}_{secrets.token_hex(_TOKEN_BYTES)}")

    @classmethod
    def parse(cls, value: object) -> Self:
        """Read an identifier from persisted state. Malformed identity is refused."""
        if not isinstance(value, str):
            raise ValidationError(
                "identifier must be a string", actual_type=type(value).__name__
            )
        return cls(value)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Name:
    """A stable, externally meaningful identifier.

    Lowercase, 1 to 64 characters, alphanumeric with ``.``, ``-`` and ``_``
    permitted internally. Used for event types and similar dotted names.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError(
                "name must be a string", actual_type=type(self.value).__name__
            )
        if len(self.value) > _NAME_MAX_LENGTH:
            raise ValidationError(
                "name is too long",
                maximum=_NAME_MAX_LENGTH,
                length=len(self.value),
                value=self.value,
            )
        if not _NAME_PATTERN.match(self.value):
            raise ValidationError(
                "name must be lowercase alphanumeric, "
                "with '.', '-' or '_' inside but not at either end",
                value=self.value,
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class HierarchyId:
    """An architecture Block, Capability, or Component identifier."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValidationError(
                "hierarchy id must be a string", actual_type=type(self.value).__name__
            )
        if not _HIERARCHY_PATTERN.match(self.value):
            raise ValidationError(
                "hierarchy id must be N, N.M, or N.M.P with numeric segments",
                value=self.value,
            )

    def __str__(self) -> str:
        return self.value


class EventId(EntityId):
    """Identifies a single EventRecord."""

    prefix = "evt"


class InstallId(EntityId):
    """Identifies one Machi installation. Minted by Block 1, typed here."""

    prefix = "inst"


class InstallRunId(EntityId):
    """Identifies one deployment journey. Minted by Block 1, typed here."""

    prefix = "irun"


class HostId(EntityId):
    """Stable host fingerprint id. Minted by Block 2, typed here."""

    prefix = "host"
