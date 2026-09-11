"""CephFS directory quota via xattrs. Cluster-free is not an entitlement."""

from __future__ import annotations

import os
from pathlib import Path

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment

_CEPH = {"ceph", "cephfs", "fuse.ceph"}
_MAX = "ceph.quota.max_bytes"
_USED = "ceph.dir.rbytes"


class CephfsQuotaProbe:
    """Walk ancestors for ceph.quota.max_bytes. Optional; no extra package."""

    name = "cephfs-quota"
    technology = "cephfs"

    def supports(self, environment: StorageEnvironment) -> bool:
        family = (
            str(environment.filesystem_type).lower()
            if is_resolved(environment.filesystem_type)
            else ""
        )
        device = (
            str(environment.device).lower() if is_resolved(environment.device) else ""
        )
        return family in _CEPH or family.startswith("fuse.ceph") or "ceph" in device

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        found = _quota_from_path(environment.mount_point)
        if found is None:
            return CapacityProbeResult(
                available=True,
                executed=True,
                detail="no ceph.quota.max_bytes xattr on path or ancestors",
            )
        ceiling, used, source = found
        remaining = max(0, ceiling - used) if used is not None else ceiling
        return CapacityProbeResult(
            available_bytes=remaining,
            hard_maximum_bytes=ceiling,
            available=True,
            executed=True,
            detail=f"ceph quota xattr at {source}",
        )


def _quota_from_path(mount_point: str) -> tuple[int, int | None, str] | None:
    path = Path(mount_point)
    candidates = [path, *list(path.parents)]
    for current in candidates:
        maximum = _xattr_int(current, _MAX)
        if maximum is None or maximum <= 0:
            continue
        used = _xattr_int(current, _USED)
        return maximum, used, str(current)
    return None


def _xattr_int(path: Path, name: str) -> int | None:
    getter = getattr(os, "getxattr", None)
    if getter is None:
        return None
    try:
        raw = getter(path, name)
    except OSError:
        return None
    if isinstance(raw, bytes):
        text = raw.decode("utf-8", errors="replace").strip()
    else:
        text = str(raw).strip()
    if not text.isdigit():
        return None
    return int(text)
