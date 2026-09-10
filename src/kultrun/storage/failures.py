"""Normalize write failures. The flavour of an installer is not the fact."""

from __future__ import annotations

import errno

from kultrun.storage.contracts import StorageFailureCode

_PERMISSION = {
    errno.EACCES,
    errno.EPERM,
    errno.EROFS,
}
_IO = {
    errno.EIO,
    errno.EAGAIN,
    errno.EBUSY,
    errno.ETIMEDOUT,
}


def classify_errno(code: int | None) -> StorageFailureCode:
    """Map a raw errno onto a storage failure. Unknown stays unresolved."""
    if code == errno.EDQUOT:
        return StorageFailureCode.STORAGE_QUOTA_EXCEEDED
    if code == errno.ENOSPC:
        return StorageFailureCode.STORAGE_SPACE_EXHAUSTED
    if code in _PERMISSION:
        return StorageFailureCode.STORAGE_PERMISSION_DENIED
    if code in _IO:
        return StorageFailureCode.STORAGE_IO_FAILURE
    return StorageFailureCode.STORAGE_UNRESOLVED


def classify_oserror(error: BaseException) -> StorageFailureCode:
    """Classify an OSError, or unresolved for anything else."""
    if isinstance(error, OSError):
        return classify_errno(error.errno)
    return StorageFailureCode.STORAGE_UNRESOLVED


def is_capacity_failure(code: StorageFailureCode) -> bool:
    """Whether this event contradicts a claim that a write should have fit."""
    return code in {
        StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        StorageFailureCode.STORAGE_SPACE_EXHAUSTED,
    }
