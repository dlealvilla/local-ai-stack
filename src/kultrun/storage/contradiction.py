"""EDQUOT/ENOSPC contradict any claim that the failed write should have fit."""

from __future__ import annotations

from dataclasses import replace

from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.storage.contracts import (
    StorageCapacityEvidence,
    StorageEvidenceStatus,
    StorageFailureCode,
)
from kultrun.storage.failures import is_capacity_failure


def contradict(
    evidence: StorageCapacityEvidence, failure: StorageFailureCode
) -> StorageCapacityEvidence:
    """Authorizing capacity must not stay SAFE after a hard write failure."""
    if not is_capacity_failure(failure):
        return evidence
    return replace(
        evidence,
        status=StorageEvidenceStatus.CONTRADICTED,
        operational_available_bytes=NOT_PROVIDED,
        authorizing_available_bytes=NOT_PROVIDED,
        selected_reason=(
            f"{failure.value} contradicts prior authorizing capacity; "
            "unsafe retry is blocked until rediscovery"
        ),
        confidence=evidence.confidence,
    )
