"""macOS storage probe. APFS quota remains K-101; native source is statvfs."""

from __future__ import annotations

from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment


class MacosCapacityProbe:
    """Compatible on Darwin. Does not echo statvfs as specialist bytes."""

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
                "macOS APFS/quota adapter is not an entitlement source; "
                "posix-statvfs remains the native figure. Physical "
                "F_PREALLOCATE is K-28."
            ),
        )
