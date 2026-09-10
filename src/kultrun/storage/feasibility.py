"""True/False/unresolved storage fit. Unresolved is not a pass."""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import (
    StorageCapacityEvidence,
    StorageEvidenceStatus,
    StorageRequirement,
)


def operational_available(evidence: StorageCapacityEvidence) -> int | None:
    """Arbitrated available writable bytes. Unresolved never reads as zero."""
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return None
    value = evidence.operational_available_bytes
    if not is_resolved(value):
        return None
    return value


def requirement_fits(
    requirement: StorageRequirement, evidence: StorageCapacityEvidence
) -> bool | None:
    """True/False when both sides are known. None means unresolved."""
    needed = requirement.required_peak_free_bytes
    if not is_resolved(needed):
        return None
    available = operational_available(evidence)
    if available is None:
        return None
    return needed <= available
