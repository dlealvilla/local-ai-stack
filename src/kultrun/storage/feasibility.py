"""True/False/unresolved storage fit. Unresolved is not a pass.

Foundation fit uses the same SAFE figure ResourceManager will spend:
authorizing capacity minus max(10%, 5 GiB). Operational bytes are not
an admission figure.
"""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import (
    StorageCapacityEvidence,
    StorageEvidenceStatus,
    StorageRequirement,
)
from kultrun.storage.limits import (
    STORAGE_RESERVE_FLOOR_BYTES,
    STORAGE_RESERVE_FRACTION,
)


def authorizing_available(evidence: StorageCapacityEvidence) -> int | None:
    """Bytes that may become SAFE. Unresolved never reads as zero."""
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return None
    value = evidence.authorizing_available_bytes
    if not is_resolved(value):
        return None
    return value


def operational_available(evidence: StorageCapacityEvidence) -> int | None:
    """Arbitrated available writable bytes. Unresolved never reads as zero.

    Diagnostic/display. Admission uses :func:`reservable_bytes`.
    """
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return None
    value = evidence.operational_available_bytes
    if not is_resolved(value):
        return None
    return value


def withhold_storage(
    authorizing: int,
    *,
    fraction: float = STORAGE_RESERVE_FRACTION,
    floor: int = STORAGE_RESERVE_FLOOR_BYTES,
) -> int | None:
    """Authorizing minus the larger of a fraction and a floor.

    Remaining <= 0 is unknown-safe, not zero.
    """
    reserve = max(int(authorizing * fraction), floor)
    remaining = authorizing - reserve
    if remaining <= 0:
        return None
    return remaining


def reservable_bytes(evidence: StorageCapacityEvidence) -> int | None:
    """SAFE for this pool. The figure ResourceManager admits against."""
    authorizing = authorizing_available(evidence)
    if authorizing is None:
        return None
    return withhold_storage(authorizing)


def requirement_fits(
    requirement: StorageRequirement, evidence: StorageCapacityEvidence
) -> bool | None:
    """True/False when both sides are known. None means unresolved.

    Compares peak requirement to SAFE, not to raw operational bytes.
    """
    needed = requirement.required_peak_free_bytes
    if not is_resolved(needed):
        return None
    available = reservable_bytes(evidence)
    if available is None:
        return None
    return needed <= available
