"""Bounded reselection policy. Never rewrite a requirement by 0.9.

The percentage is a candidate-footprint *ceiling*. It does not scale a
measured requirement, inflate SAFE, or weaken ResourceManager admission.

Normalized metric (documented for K-110): remaining peak materialization
on the destination pool — `incremental_storage_bytes` for a model
artifact, `required_peak_free_bytes` for an unrealized runtime. An already
materialized valid runtime is not added again.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, TypeVar

from kultrun.storage.limits import (
    MAX_STORAGE_REDUCTIONS,
    REDUCTION_FACTOR_DENOMINATOR,
    REDUCTION_FACTOR_NUMERATOR,
)

T = TypeVar("T")

#: Attempt 0 is the original. Retries 1..3 are 90%, 81%, 72.9% via floor.
REDUCTION_RATIO_LABELS: Final = ("100%", "90%", "81%", "72.9%")

FOOTPRINT_RETRYABLE_CODES = frozenset(
    {
        "insufficient_safe_storage",
        "unresolved_safe_capacity",
        "runtime_storage_infeasible",
        "unresolved_storage_requirement",
        "storage_pool_unresolved",
        "storage_quota_exceeded",
        "storage_space_exhausted",
    }
)

NON_FOOTPRINT_CODES = frozenset(
    {
        "storage_permission_denied",
        "storage_io_failure",
        "artifact_incomplete",
        "artifact_integrity",
        "unsupported",
        "unsupported_architecture",
        "policy_blocked",
        "policy_denial",
        "authentication_failed",
        "runtime_process_exited",
        "runtime_crash",
        "model_not_eligible",
        "signature_failure",
    }
)


def peak_cap_bytes(original_peak: int, reduction: int) -> int:
    """Maximum footprint a candidate may have after `reduction` reselections.

    reduction 0 is the original plan (100%). Maximum reduction is 3.
    Rounding is conservative integer floor of ``original * (9/10)**n``.
    """
    if reduction < 0 or reduction > MAX_STORAGE_REDUCTIONS:
        raise ValueError("reduction must be 0..3")
    if original_peak < 0:
        raise ValueError("footprint cannot be negative")
    return int(
        original_peak
        * (REDUCTION_FACTOR_NUMERATOR**reduction)
        // (REDUCTION_FACTOR_DENOMINATOR**reduction)
    )


def select_smaller(
    candidates: Sequence[T],
    *,
    peak_of: Callable[[T], int],
    original_peak: int,
    reduction: int,
) -> T | None:
    """Pick the largest candidate that still fits the reduction cap.

    Candidates must be real configurations. This function does not scale
    numbers. Control-plane AUTO ranking may then choose among those that fit.
    """
    cap = peak_cap_bytes(original_peak, reduction)
    fitting = [item for item in candidates if peak_of(item) <= cap]
    if not fitting:
        return None
    return max(fitting, key=peak_of)


def exhausted(reduction: int) -> bool:
    return reduction >= MAX_STORAGE_REDUCTIONS


def is_footprint_retryable(code: str) -> bool:
    """Whether this failure may start a smaller-deployment search.

    Low-space is capacity-related but is *not* retryable here: the
    administrator must clear space first.
    """
    if code == "storage_low_space":
        return False
    return code in FOOTPRINT_RETRYABLE_CODES
