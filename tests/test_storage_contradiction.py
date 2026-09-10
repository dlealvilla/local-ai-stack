"""EDQUOT/ENOSPC contradict authorizing SAFE. Unsafe retry is blocked."""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import StorageEvidenceStatus, StorageFailureCode
from kultrun.storage.contradiction import contradict
from tests.test_storage_evidence import _evidence


def test_edquot_clears_authorizing_capacity() -> None:
    item = _evidence(native_available=50 * 1024**3)
    assert is_resolved(item.authorizing_available_bytes)
    broken = contradict(item, StorageFailureCode.STORAGE_QUOTA_EXCEEDED)
    assert broken.status is StorageEvidenceStatus.CONTRADICTED
    assert not is_resolved(broken.authorizing_available_bytes)
    assert not is_resolved(broken.operational_available_bytes)


def test_enospc_is_the_same_contradiction() -> None:
    item = _evidence(native_available=50 * 1024**3)
    broken = contradict(item, StorageFailureCode.STORAGE_SPACE_EXHAUSTED)
    assert broken.status is StorageEvidenceStatus.CONTRADICTED
    assert "unsafe retry" in broken.selected_reason
