"""Windows storage probe contract. Physical GetDiskFreeSpaceEx is deferred."""

from __future__ import annotations

from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)


class WindowsCapacityProbe:
    """Compatible on Windows. v1 is fixture-tested, not a live Win32 call."""

    name = "windows-capacity"
    technology = "windows"

    def supports(self, environment: StorageEnvironment) -> bool:
        return environment.os_name in {"windows", "win32"}

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            available=False,
            executed=False,
            detail=(
                "Windows GetDiskFreeSpaceEx / NTFS quota adapter is fixture-"
                "tested; physical implementation is deferred"
            ),
        )
