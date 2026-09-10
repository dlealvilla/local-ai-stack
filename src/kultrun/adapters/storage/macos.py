"""macOS storage probe contract. Physical APFS/quota is deferred."""

from __future__ import annotations

from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)


class MacosCapacityProbe:
    """Compatible on Darwin. statvfs remains the native source on macOS."""

    name = "macos-capacity"
    technology = "macos"

    def supports(self, environment: StorageEnvironment) -> bool:
        return environment.os_name in {"darwin", "macos"}

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            available=False,
            executed=False,
            detail=(
                "macOS APFS/quota adapter is fixture-tested; use posix-statvfs "
                "as the native source. Physical F_PREALLOCATE is K-28."
            ),
        )
