"""Typed errors the Kernel raises deliberately.

Anything not derived from :class:`MachiError` is a defect, not a domain
condition. Codes are part of the public surface and are not renamed once
shipped.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar


class ErrorCode(StrEnum):
    """Stable, wire-visible error codes."""

    VALIDATION = "validation"
    UNKNOWN_KIND = "unknown_kind"
    UNKNOWN_VERSION = "unknown_version"
    DUPLICATE_REGISTRATION = "duplicate_registration"
    NOT_FOUND = "not_found"
    PERSISTENCE = "persistence"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"
    INTERNAL = "internal"


class MachiError(Exception):
    """Base for every error the product raises deliberately."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL
    retryable: ClassVar[bool] = False

    def __init__(self, message: str, /, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(code={self.code.value!r}, message={self.message!r})"
        )


class ValidationError(MachiError):
    """A value does not satisfy its contract."""

    code = ErrorCode.VALIDATION


class UnknownKindError(MachiError):
    """A contract kind is not registered. Never parsed on a best-effort basis."""

    code = ErrorCode.UNKNOWN_KIND


class UnknownVersionError(MachiError):
    """The kind is registered, but not at the requested schema version."""

    code = ErrorCode.UNKNOWN_VERSION


class DuplicateRegistrationError(MachiError):
    """Two registrations claim one name. One concept, one owner."""

    code = ErrorCode.DUPLICATE_REGISTRATION


class NotFoundError(MachiError):
    """A requested record does not exist."""

    code = ErrorCode.NOT_FOUND


class PersistenceError(MachiError):
    """Required local persistence could not complete.

    Distinct from optional later analytics/export failure. A Kernel
    evidence write that cannot land is not a successful proof.
    """

    code = ErrorCode.PERSISTENCE
    retryable = True


class UnresolvedValueError(MachiError):
    """An unresolved value was used where a determinate value is required."""

    code = ErrorCode.UNRESOLVED


class ConflictError(MachiError):
    """Two facts disagree, or a claim is unsafe.

    Distinct from ValidationError (a value is malformed). Ownership
    collisions and copied markers are conflicts: fail closed, do not repair.
    """

    code = ErrorCode.CONFLICT


class InternalError(MachiError):
    """An invariant was violated. A defect, not a domain condition."""

    code = ErrorCode.INTERNAL
