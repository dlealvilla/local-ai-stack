"""Identify FUSE mounts. Identification is not a capacity figure."""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)

_FUSE = {"fuse", "fuseblk", "fuse.sshfs", "fuse.mfs"}


class FuseIdentifyProbe:
    """Detect FUSE. Does not invent available bytes."""

    name = "fuse-identify"
    technology = "fuse"

    def supports(self, environment: StorageEnvironment) -> bool:
        family = (
            str(environment.filesystem_type).lower()
            if is_resolved(environment.filesystem_type)
            else ""
        )
        device = (
            str(environment.device).lower() if is_resolved(environment.device) else ""
        )
        return family in _FUSE or family.startswith("fuse.") or "fuse" in device

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        family = (
            str(environment.filesystem_type)
            if is_resolved(environment.filesystem_type)
            else "fuse"
        )
        return CapacityProbeResult(
            executed=True,
            available=True,
            detail=f"identified {family}; FUSE reported size is not an entitlement",
        )
