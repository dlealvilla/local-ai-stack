"""NFS quota seam. Numeric rquota is Track P (K-103), not this stage."""

from __future__ import annotations

import shutil

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment

_NFS = {"nfs", "nfs4"}


class NFSQuotaProbe:
    """Compatible on NFS. Does not invent bytes from helper presence."""

    name = "nfs-quota"
    technology = "nfs"

    def supports(self, environment: StorageEnvironment) -> bool:
        family = (
            str(environment.filesystem_type).lower()
            if is_resolved(environment.filesystem_type)
            else ""
        )
        return family in _NFS

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        helper = shutil.which("quota") or shutil.which("nfsstat")
        if helper is None:
            return CapacityProbeResult(
                available=False,
                executed=False,
                detail="NFS quota helper is not installed",
            )
        return CapacityProbeResult(
            available=True,
            executed=False,
            detail=(
                f"helper {helper} present; numeric NFS rquota is not parsed "
                "in this stage (K-103)"
            ),
        )
