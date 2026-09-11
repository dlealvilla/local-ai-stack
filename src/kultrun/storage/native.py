"""Declared/native available figures. Generic statistics, not a vendor API."""

from __future__ import annotations

import os
import sys

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
    if live and environment.os_name in {"windows", "win32"}:
        windows = windows_available_bytes(environment.mount_point)
        if is_resolved(windows):
            return windows, "windows-getdiskfreespaceex"
    if is_resolved(mount.free_bytes):
        return mount.free_bytes, "host-mount-free"
    return NOT_PROVIDED, "none"


def windows_available_bytes(path: str) -> Maybe[int]:
    """``GetDiskFreeSpaceExW`` caller-free bytes. Unresolved off Windows."""
    if sys.platform == "win32":
        return _win32_disk_free(path)
    return NOT_PROVIDED


def _win32_disk_free(path: str) -> Maybe[int]:
    import ctypes
    from ctypes import wintypes

    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return NOT_PROVIDED
    free_for_caller = ctypes.c_ulonglong(0)
    total = ctypes.c_ulonglong(0)
    total_free = ctypes.c_ulonglong(0)
    getter = windll.kernel32.GetDiskFreeSpaceExW
    getter.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong),
    ]
    getter.restype = wintypes.BOOL
    ok = getter(
        path,
        ctypes.byref(free_for_caller),
        ctypes.byref(total),
        ctypes.byref(total_free),
    )
    if not ok:
        return NOT_PROVIDED
    return int(free_for_caller.value)
