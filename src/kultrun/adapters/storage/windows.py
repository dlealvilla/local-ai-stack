"""Windows native capacity via GetDiskFreeSpaceExW. NTFS quota is K-100 remainder."""

from __future__ import annotations

import sys

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.native import windows_available_bytes
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment


class WindowsCapacityProbe:
    """Live on win32. Bytes are native-class, not a quota entitlement."""

    name = "windows-capacity"
    technology = "windows"

    def supports(self, environment: StorageEnvironment) -> bool:
        return environment.os_name in {"windows", "win32"}

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        if sys.platform not in {"win32"}:
            return CapacityProbeResult(
                available=False,
                executed=False,
                detail="not a Windows process; GetDiskFreeSpaceExW skipped",
            )
        available = windows_available_bytes(environment.mount_point)
        if is_resolved(available):
            return CapacityProbeResult(
                available_bytes=available,
                available=True,
                executed=True,
                detail="GetDiskFreeSpaceExW caller-free bytes (native-class)",
            )
        return CapacityProbeResult(
            available=True,
            executed=True,
            detail="GetDiskFreeSpaceExW did not return numeric bytes",
        )
