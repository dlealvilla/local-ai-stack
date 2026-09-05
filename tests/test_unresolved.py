"""Unknown is a value, and it is not a pass."""

from __future__ import annotations

import pytest

from kultrun.kernel.errors import UnresolvedValueError
from kultrun.kernel.unresolved import (
    NOT_MEASURED,
    Unresolved,
    UnresolvedReason,
    is_resolved,
    require_resolved,
)


def test_unresolved_has_no_truth_value() -> None:
    """The rule that unknown is not a pass is only enforceable if this raises."""
    with pytest.raises(UnresolvedValueError):
        bool(NOT_MEASURED)


def test_unresolved_is_not_falsy_in_a_condition() -> None:
    def branch_on_it() -> str:
        # mypy knows this can never be truthy, which is the design; the test
        # is that the attempt raises at runtime rather than reading as false.
        return "resolved" if NOT_MEASURED else "falsy"  # type: ignore[redundant-expr]

    with pytest.raises(UnresolvedValueError):
        branch_on_it()


def test_unresolved_is_not_zero_or_none_or_false() -> None:
    # The non-overlap is exactly the invariant: an unknown value must not
    # compare equal to a determinate one. mypy proving it cannot is the
    # static half of the same guarantee.
    assert NOT_MEASURED != 0  # type: ignore[comparison-overlap]
    assert NOT_MEASURED is not None
    assert NOT_MEASURED != False  # type: ignore[comparison-overlap] # noqa: E712
    assert NOT_MEASURED != ""  # type: ignore[comparison-overlap]


def test_is_resolved_distinguishes_zero_from_unknown() -> None:
    """"Needs nothing" and "we do not know" must not be the same answer."""
    assert is_resolved(0)
    assert not is_resolved(NOT_MEASURED)


def test_require_resolved_returns_a_known_value() -> None:
    assert require_resolved(7, what="requested bytes") == 7


def test_require_resolved_fails_closed_rather_than_guessing() -> None:
    with pytest.raises(UnresolvedValueError) as raised:
        require_resolved(NOT_MEASURED, what="safe capacity")
    assert raised.value.context["what"] == "safe capacity"
    assert raised.value.context["reason"] == "not_measured"


def test_reason_carries_the_evidence_vocabulary() -> None:
    """Inconclusive is deliberately distinct from never-attempted."""
    inconclusive = Unresolved(UnresolvedReason.INCONCLUSIVE, "probe interrupted")
    assert inconclusive.reason is not UnresolvedReason.NOT_MEASURED
    assert "probe interrupted" in str(inconclusive)


def test_equal_reasons_compare_equal() -> None:
    assert Unresolved(UnresolvedReason.NOT_PROVIDED) == Unresolved(
        UnresolvedReason.NOT_PROVIDED
    )
    assert Unresolved(UnresolvedReason.NOT_PROVIDED) != NOT_MEASURED
