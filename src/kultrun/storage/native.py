"""Declared/native available figures. Generic statistics, not a vendor API."""

from __future__ import annotations

import os

from kultrun.host.contracts import MountFacts
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.ports import StorageEnvironment


def native_available_bytes(
    mount: MountFacts,
    environment: StorageEnvironment,
    *,
    live: bool = True,
) -> tuple[Maybe[int], str]:
    """Strongest cheap native figure: live statvfs, else reported mount free.

    Fixture replay must not ``statvfs`` the machine doing the replaying.
    Those mount points describe the captured host, not this disk.
    """
    if live and environment.os_name in {"linux", "darwin"}:
        try:
            stats = os.statvfs(environment.mount_point)
            return stats.f_bavail * stats.f_frsize, "posix-statvfs"
        except OSError:
            pass
    if is_resolved(mount.free_bytes):
        return mount.free_bytes, "host-mount-free"
    return NOT_PROVIDED, "none"
