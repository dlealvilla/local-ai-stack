"""Platform identity, in its two distinct forms.

The previous attempt kept `logical_name`, `model_id`, `provider` and
`service_id` as separate fields holding values like ``local-llm``,
``qwen3-8b-awq``, ``vllm`` and ``inference``, and recorded the instruction
"do not collapse these identities into one field." It was right, and the
consequence is that the platform needs two kinds of identifier, not one:

**A minted identifier** is opaque, platform-generated and prefixed. It is
typed, so a model id cannot be passed where a host id is expected;
prefixed, so an identifier in a log line is self-describing; and opaque, so
no consumer can extract meaning from its body.

**A name** is externally meaningful and stable — supplied by an
administrator or normalized from a source. It appears in URLs,
configuration keys, analytics group-bys and file paths, so it is validated
and normalized in ways a minted identifier never needs to be.

Generation uses the standard library only. Identity is a Kultrun concept
and `docs/ROADMAP.md` Part II §9 forbids a third-party package from owning
one.

Only the mechanism and the identifiers this stage itself needs live here.
Domain identifiers arrive with their contracts in Stage 0.2. "Identity" in
the authentication sense is a different concept, owned by the `identity`
module at tier 1.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import ClassVar, Final, Self

from kultrun.kernel.errors import InternalError, ValidationError

#: Body length in bytes; 8 bytes renders as 16 hexadecimal characters.
_TOKEN_BYTES: Final = 8
_TOKEN_LENGTH: Final = _TOKEN_BYTES * 2

_PREFIX_PATTERN: Final = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_TOKEN_PATTERN: Final = re.compile(rf"^[0-9a-f]{{{_TOKEN_LENGTH}}}$")

_NAME_MAX_LENGTH: Final = 64
_NAME_PATTERN: Final = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")


@dataclass(frozen=True, slots=True)
class EntityId:
    """An opaque identifier for one kind of entity.

    Subclasses declare a prefix and nothing else::

        class HostId(EntityId):
            prefix = "host"

        HostId.generate()       # HostId(value='host_9f2c1a0b7d3e5648')
        HostId.parse(from_disk) # validates prefix and body, or refuses

    Identifiers are not time-sortable in v1; see `docs/DEBT.md`.
    """

    #: Subclasses must override. The empty base prefix is never valid.
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
        """Read an identifier from persisted state or an API call.

        Refuses anything that is not a well-formed identifier of this type.
        Malformed identity is never coerced.
        """
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
    permitted internally. Used for the values that must stay distinct from
    one another and from minted identity: a client-facing logical name, a
    concrete model identity, a provider, a service, an event type.
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

    @classmethod
    def normalize(cls, raw: str) -> Self:
        """Best-effort normalization of an external string into a name.

        Intended for source adapters, which meet values like
        ``Qwen/Qwen3-8B-AWQ``. Deliberately lossy and deliberately not
        reversible: the verbatim source reference is kept in its own field
        on the contract, never reconstructed from the name.
        """
        lowered = raw.strip().lower()
        collapsed = re.sub(r"[^a-z0-9._-]+", "-", lowered)
        trimmed = collapsed.strip("._-")[:_NAME_MAX_LENGTH].strip("._-")
        if not trimmed:
            raise ValidationError("string does not normalize to a name", value=raw)
        return cls(trimmed)

    def __str__(self) -> str:
        return self.value


class EventId(EntityId):
    """Identifies a single domain event."""

    prefix = "evt"
