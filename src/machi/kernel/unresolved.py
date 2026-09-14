"""The unknown-value semantic (MACHI 0.1.2).

Python's ``None`` cannot carry both "not applicable" and "we do not know",
so the Kernel uses three:

===============  ==========================================================
``0`` or a value  a determinate answer
``None``          absent, or not applicable to this shape
``Unresolved``    we do not know, and here is why
===============  ==========================================================

An unresolved value **has no truth value**. Asking whether it is truthy
raises, because "unknown is not a pass" is unenforceable if ``if value:``
silently reads as false.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, TypeAlias, TypeGuard, TypeVar

from machi.kernel.errors import UnresolvedValueError

T = TypeVar("T")


class UnresolvedReason(StrEnum):
    """Why a value is not known."""

    NOT_MEASURED = "not_measured"
    NOT_PROVIDED = "not_provided"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Unresolved:
    """A value that is not known.

    Never equal to ``0``, ``None``, ``False`` or an empty string.
    """

    reason: UnresolvedReason
    detail: str | None = None

    def __bool__(self) -> NoReturn:
        raise UnresolvedValueError(
            "an unresolved value has no truth value; "
            "test it with is_resolved() or handle the unknown case explicitly",
            reason=self.reason.value,
            detail=self.detail,
        )

    def __str__(self) -> str:
        if self.detail is None:
            return f"unresolved({self.reason.value})"
        return f"unresolved({self.reason.value}: {self.detail})"


#: A value that may not be known. ``Maybe[int]`` is ``int | Unresolved``.
Maybe: TypeAlias = T | Unresolved

NOT_MEASURED = Unresolved(UnresolvedReason.NOT_MEASURED)
NOT_PROVIDED = Unresolved(UnresolvedReason.NOT_PROVIDED)


def is_resolved(value: Maybe[T]) -> TypeGuard[T]:
    """True when the value is determinate. The safe way to branch."""
    return not isinstance(value, Unresolved)


def require_resolved(value: Maybe[T], *, what: str) -> T:
    """Return the value, or fail closed if it is not known."""
    if isinstance(value, Unresolved):
        raise UnresolvedValueError(
            f"{what} is required but not known",
            what=what,
            reason=value.reason.value,
            detail=value.detail,
        )
    return value
