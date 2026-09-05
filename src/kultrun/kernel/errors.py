"""The typed error hierarchy and the stable codes the platform exposes.

Every failure Kultrun reports deliberately carries a code from
:class:`ErrorCode`. Codes are part of the public surface: the Platform API,
the Admin Agent and eventually a customer support path all key on them, so
a code is never renamed once shipped, only deprecated alongside a new one.

Anything not derived from :class:`KultrunError` is a defect, not a domain
condition.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar


class ErrorCode(StrEnum):
    """Stable, wire-visible error codes. These string values must not change."""

    VALIDATION = "validation"
    UNKNOWN_KIND = "unknown_kind"
    UNKNOWN_VERSION = "unknown_version"
    UNKNOWN_ADAPTER = "unknown_adapter"
    DUPLICATE_REGISTRATION = "duplicate_registration"
    CONFIG_INVALID = "config_invalid"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    PRECONDITION_FAILED = "precondition_failed"
    PERSISTENCE = "persistence"
    UNRESOLVED = "unresolved"
    CANCELLED = "cancelled"
    INTERNAL = "internal"


class KultrunError(Exception):
    """Base for every error the platform raises deliberately."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL
    retryable: ClassVar[bool] = False

    def __init__(self, message: str, /, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code.value!r}, "
            f"message={self.message!r})"
        )


class ValidationError(KultrunError):
    """A value does not satisfy its contract."""

    code = ErrorCode.VALIDATION


class UnknownKindError(KultrunError):
    """A contract kind is not registered. Never parsed on a best-effort basis."""

    code = ErrorCode.UNKNOWN_KIND


class UnknownVersionError(KultrunError):
    """The kind is registered, but not at the requested schema version."""

    code = ErrorCode.UNKNOWN_VERSION


class UnknownAdapterError(KultrunError):
    """No adapter is registered under this name. There is no default."""

    code = ErrorCode.UNKNOWN_ADAPTER


class DuplicateRegistrationError(KultrunError):
    """Two registrations claim one name. One concept, one owner."""

    code = ErrorCode.DUPLICATE_REGISTRATION


class ConfigError(KultrunError):
    """Configuration is absent, unrecognised, or invalid."""

    code = ErrorCode.CONFIG_INVALID


class NotFoundError(KultrunError):
    """A requested record does not exist."""

    code = ErrorCode.NOT_FOUND


class ConflictError(KultrunError):
    """The operation conflicts with existing state."""

    code = ErrorCode.CONFLICT


class PreconditionFailedError(KultrunError):
    """The system is not in a state where this operation is permitted."""

    code = ErrorCode.PRECONDITION_FAILED


class PersistenceError(KultrunError):
    """The store could not complete an operation."""

    code = ErrorCode.PERSISTENCE
    retryable = True


class UnresolvedValueError(KultrunError):
    """An unresolved value was used where a determinate value is required.

    Raised rather than defaulting, because "unknown is not zero and is not a
    pass" cannot be enforced if unknown can be read as false.
    """

    code = ErrorCode.UNRESOLVED


class CancelledError(KultrunError):
    """The operation was cancelled before completion and cleaned up after itself."""

    code = ErrorCode.CANCELLED


class InternalError(KultrunError):
    """An invariant was violated. This indicates a defect, not a domain condition."""

    code = ErrorCode.INTERNAL
