"""20% reduction is reselection of real candidates, never requirement *= 0.8."""

from __future__ import annotations

import pytest

from kultrun.storage.limits import MAX_STORAGE_REDUCTIONS
from kultrun.storage.reduction import (
    NON_FOOTPRINT_CODES,
    exhausted,
    is_footprint_retryable,
    is_manual_capacity_required,
    peak_cap_bytes,
    select_smaller,
)

GIB = 1024**3


def test_caps_are_100_80_64_512_4096_32768() -> None:
    original = 1000
    assert peak_cap_bytes(original, 0) == 1000
    assert peak_cap_bytes(original, 1) == 800
    assert peak_cap_bytes(original, 2) == 640
    assert peak_cap_bytes(original, 3) == 512
    assert peak_cap_bytes(original, 4) == 409
    assert peak_cap_bytes(original, 5) == 327


def test_caps_use_integer_floor_not_percentage_points() -> None:
    original = 40 * GIB
    assert peak_cap_bytes(original, 0) == original
    assert peak_cap_bytes(original, 1) == original * 4 // 5
    assert peak_cap_bytes(original, 2) == original * 16 // 25
    assert peak_cap_bytes(original, 3) == original * 64 // 125
    assert peak_cap_bytes(original, 4) == original * 256 // 625
    assert peak_cap_bytes(original, 5) == original * 1024 // 3125
    assert peak_cap_bytes(original, 1) != original - (20 * GIB)
    assert peak_cap_bytes(original, 5) < peak_cap_bytes(original, 4)
    assert peak_cap_bytes(1000, 1) == 800
    assert peak_cap_bytes(1000, 1) < 801


def test_selects_actual_smaller_candidate() -> None:
    candidates = (
        ("A", 40 * GIB),
        ("B", 35 * GIB),
        ("C", 31 * GIB),
        ("D", 26 * GIB),
        ("E", 20 * GIB),
        ("F", 15 * GIB),
        ("G", 12 * GIB),
    )
    original = 40 * GIB

    def peak_of(item: tuple[str, int]) -> int:
        return item[1]

    first = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=1
    )
    assert first is not None
    assert first[0] == "C"
    assert first[1] == 31 * GIB
    second = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=2
    )
    assert second is not None
    assert second[0] == "E"
    assert second[1] == 20 * GIB
    third = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=3
    )
    assert third is not None
    assert third[0] == "E"
    fourth = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=4
    )
    assert fourth is not None
    assert fourth[0] == "F"
    fifth = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=5
    )
    assert fifth is not None
    assert fifth[0] == "G"
    assert fifth[1] == 12 * GIB


def test_may_skip_to_the_next_real_candidate_that_fits() -> None:
    candidates = (("A", 40 * GIB), ("C", 31 * GIB), ("D", 26 * GIB))
    chosen = select_smaller(
        candidates,
        peak_of=lambda item: item[1],
        original_peak=40 * GIB,
        reduction=1,
    )
    assert chosen is not None
    assert chosen[0] == "C"
    assert chosen[1] == 31 * GIB


def test_does_not_rewrite_requirement_numbers() -> None:
    original = 40 * GIB
    chosen = select_smaller(
        (("tiny", 20 * GIB),),
        peak_of=lambda item: item[1],
        original_peak=original,
        reduction=3,
    )
    assert chosen is not None
    assert chosen[1] == 20 * GIB
    assert chosen[1] != int(original * 0.512)
    assert chosen[1] != int(original * 0.80)


def test_maximum_five_reductions() -> None:
    assert MAX_STORAGE_REDUCTIONS == 5
    assert exhausted(5) is True
    assert exhausted(4) is False
    with pytest.raises(ValueError, match=r"reduction must be 0\.\.5"):
        peak_cap_bytes(1000, 6)


def test_footprint_retryable_codes() -> None:
    assert is_footprint_retryable("insufficient_safe_storage")
    assert is_footprint_retryable("runtime_storage_infeasible")
    assert is_footprint_retryable("storage_quota_exceeded")
    assert is_footprint_retryable("storage_space_exhausted")
    assert is_footprint_retryable("storage_low_space") is False
    assert is_footprint_retryable("unresolved_safe_capacity") is False
    assert is_manual_capacity_required("unresolved_safe_capacity")
    assert is_manual_capacity_required("manual_capacity_required")
    for code in NON_FOOTPRINT_CODES:
        assert is_footprint_retryable(code) is False
