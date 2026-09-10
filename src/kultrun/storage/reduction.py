"""Bounded reselection policy. Never rewrite a requirement by 0.7."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

from kultrun.storage.limits import MAX_STORAGE_REDUCTIONS, REDUCTION_PEAK_CAPS

T = TypeVar("T")


def peak_cap_bytes(original_peak: int, reduction: int) -> int:
    """Maximum peak a candidate may have after `reduction` reselections.

    reduction 0 is the original plan (100%). Maximum reduction is 3.
    """
    if reduction < 0 or reduction > MAX_STORAGE_REDUCTIONS:
        raise ValueError("reduction must be 0..3")
    return int(original_peak * REDUCTION_PEAK_CAPS[reduction])


def select_smaller(
    candidates: Sequence[T],
    *,
    peak_of: Callable[[T], int],
    original_peak: int,
    reduction: int,
) -> T | None:
    """Pick the largest candidate that still fits the reduction cap.

    Candidates must be real configurations. This function does not scale
    numbers.
    """
    cap = peak_cap_bytes(original_peak, reduction)
    fitting = [item for item in candidates if peak_of(item) <= cap]
    if not fitting:
        return None
    return max(fitting, key=peak_of)


def exhausted(reduction: int) -> bool:
    return reduction >= MAX_STORAGE_REDUCTIONS
