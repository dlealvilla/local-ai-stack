"""30% reduction is reselection of real candidates, never requirement *= 0.7."""

from __future__ import annotations

from kultrun.storage.reduction import exhausted, peak_cap_bytes, select_smaller


def test_caps_are_100_70_49_343() -> None:
    original = 40
    assert peak_cap_bytes(original, 0) == 40
    assert peak_cap_bytes(original, 1) == 28
    assert peak_cap_bytes(original, 2) == 19
    assert peak_cap_bytes(original, 3) == 13


def test_selects_actual_smaller_candidate() -> None:
    candidates = (
        ("A", 40 * 1024**3),
        ("B", 27 * 1024**3),
        ("C", 18 * 1024**3),
        ("D", 12 * 1024**3),
    )
    original = 40 * 1024**3

    def peak_of(item: tuple[str, int]) -> int:
        return item[1]

    first = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=1
    )
    assert first is not None
    assert first[0] == "B"
    second = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=2
    )
    assert second is not None
    assert second[0] == "C"
    third = select_smaller(
        candidates, peak_of=peak_of, original_peak=original, reduction=3
    )
    assert third is not None
    assert third[0] == "D"


def test_does_not_rewrite_requirement_numbers() -> None:
    original = 40 * 1024**3
    chosen = select_smaller(
        (("tiny", 12 * 1024**3),),
        peak_of=lambda item: item[1],
        original_peak=original,
        reduction=3,
    )
    assert chosen is not None
    assert chosen[1] == 12 * 1024**3
    assert chosen[1] != int(original * 0.343)


def test_maximum_three_reductions() -> None:
    assert exhausted(3) is True
    assert exhausted(2) is False
