"""Generic POSIX filesystem statistics. A native/declared source, not a vendor."""

from __future__ import annotations

import os

from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)


class PosixStatvfsProbe:
    """os.statvfs available bytes. Independent of a quota API."""

    name = "posix-statvfs"
    technology = "posix-statvfs"

    def supports(self, environment: StorageEnvironment) -> bool:
        return environment.os_name in {"linux", "darwin"}

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        try:
            stats = os.statvfs(environment.mount_point)
        except OSError as error:
            return CapacityProbeResult(
                executed=True,
                available=True,
                detail=str(error),
            )
        available = stats.f_bavail * stats.f_frsize
        total = stats.f_blocks * stats.f_frsize
        return CapacityProbeResult(
            available_bytes=available,
            hard_maximum_bytes=total if total > 0 else NOT_PROVIDED,
            executed=True,
            available=True,
            detail="os.statvfs",
        )
