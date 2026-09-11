"""OS-specific process identity for native reacquisition.

Core stores the cookie on ``ExecutorHandle.external_identity``. Linux uses
``/proc``; macOS uses libproc/sysctl. A PID alone is never enough.
"""

from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from kultrun.kernel.unresolved import is_resolved

EXECUTION_ENV = "KULTRUN_EXECUTION"
COOKIE_VERSION = "np1"


@dataclass(frozen=True, slots=True)
class ProcessCookie:
    boot_id: str
    start_token: str
    pgid: int
    grace_seconds: float
    execution_id: str

    def serialise(self) -> str:
        return (
            f"{COOKIE_VERSION}|{self.boot_id}|{self.start_token}|"
            f"{self.pgid}|{self.grace_seconds}|{self.execution_id}"
        )


def parse_cookie(value: object) -> ProcessCookie | None:
    if not is_resolved(value) or not isinstance(value, str):
        return None
    parts = value.split("|")
    if len(parts) != 6 or parts[0] != COOKIE_VERSION:
        return None
    try:
        return ProcessCookie(
            boot_id=parts[1],
            start_token=parts[2],
            pgid=int(parts[3]),
            grace_seconds=float(parts[4]),
            execution_id=parts[5],
        )
    except ValueError:
        return None


def capture_cookie(
    pid: int, execution_id: str, *, grace_seconds: float
) -> ProcessCookie | None:
    boot = boot_id()
    if boot is None:
        return None
    start = start_token(pid) or ""
    try:
        pgid = os.getpgid(pid)
    except OSError:
        pgid = pid
    return ProcessCookie(
        boot_id=boot,
        start_token=start,
        pgid=pgid,
        grace_seconds=grace_seconds,
        execution_id=execution_id,
    )


class IdentityMatch:
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


def verify_live(pid: int, cookie: ProcessCookie, execution_id: str) -> str:
    """Prove this PID is the process named by the cookie."""
    if not pid_exists(pid):
        return IdentityMatch.MISMATCH
    if cookie.execution_id != execution_id:
        return IdentityMatch.MISMATCH
    live_boot = boot_id()
    if live_boot is not None and live_boot != cookie.boot_id:
        return IdentityMatch.MISMATCH
    env_id = execution_id_from_environ(pid)
    if env_id is not None:
        if env_id == cookie.execution_id:
            start = start_token(pid)
            if (
                start is not None
                and cookie.start_token
                and start != cookie.start_token
            ):
                return IdentityMatch.MISMATCH
            return IdentityMatch.MATCH
        return IdentityMatch.MISMATCH
    try:
        live_pgid = os.getpgid(pid)
    except OSError:
        return IdentityMatch.UNKNOWN
    start = start_token(pid)
    if start is None:
        return IdentityMatch.UNKNOWN
    if live_pgid == cookie.pgid and start == cookie.start_token:
        if live_boot is None or live_boot == cookie.boot_id:
            return IdentityMatch.MATCH
        return IdentityMatch.MISMATCH
    return IdentityMatch.MISMATCH


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def boot_id() -> str | None:
    linux = Path("/proc/sys/kernel/random/boot_id")
    try:
        if linux.is_file():
            return linux.read_text(encoding="ascii").strip()
    except OSError:
        pass
    return _darwin_boot()


def start_token(pid: int) -> str | None:
    linux = Path(f"/proc/{pid}/stat")
    try:
        if linux.is_file():
            text = linux.read_text(encoding="utf-8")
            rparen = text.rfind(")")
            if rparen < 0:
                return None
            fields = text[rparen + 2 :].split()
            if len(fields) < 20:
                return None
            return fields[19]
    except OSError:
        pass
    return _darwin_start(pid)


def execution_id_from_environ(pid: int) -> str | None:
    env = _environ_map(pid)
    if env is None:
        return None
    return env.get(EXECUTION_ENV)


def _environ_map(pid: int) -> dict[str, str] | None:
    linux = Path(f"/proc/{pid}/environ")
    try:
        if linux.is_file():
            raw = linux.read_bytes()
            found: dict[str, str] = {}
            for chunk in raw.split(b"\0"):
                if not chunk or b"=" not in chunk:
                    continue
                name, _, value = chunk.partition(b"=")
                found[name.decode("utf-8", "replace")] = value.decode(
                    "utf-8", "replace"
                )
            return found
    except OSError:
        pass
    return _darwin_environ(pid)


def _darwin_boot() -> str | None:
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    except OSError:
        return None
    timeval = ctypes.c_long * 2
    boot = timeval()
    size = ctypes.c_size_t(ctypes.sizeof(boot))
    name = b"kern.boottime"
    if libc.sysctlbyname(name, ctypes.byref(boot), ctypes.byref(size), None, 0) != 0:
        return None
    return str(int(boot[0]))


def _darwin_start(pid: int) -> str | None:
    info = _darwin_bsdinfo(pid)
    if info is None:
        return None
    return f"{info[0]}.{info[1]}"


def _darwin_bsdinfo(pid: int) -> tuple[int, int] | None:
    proc_pidtbsdinfo = 3
    try:
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    except OSError:
        return None
    buf = ctypes.create_string_buffer(1024)
    proc_pidinfo = lib.proc_pidinfo
    proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    proc_pidinfo.restype = ctypes.c_int
    n = proc_pidinfo(pid, proc_pidtbsdinfo, 0, buf, 1024)
    if n < 128:
        return None
    # Classic 64-bit proc_bsdinfo: pbi_start_tvsec at 168.
    # Compact Darwin layout is 136 bytes with start at 120.
    if n >= 184:
        sec = int.from_bytes(buf.raw[168:176], sys.byteorder)
        usec = int.from_bytes(buf.raw[176:184], sys.byteorder)
    else:
        sec = int.from_bytes(buf.raw[120:128], sys.byteorder)
        usec = int.from_bytes(buf.raw[128:136], sys.byteorder)
    return sec, usec


def _darwin_environ(pid: int) -> dict[str, str] | None:
    ctl_kern = 1
    kern_procargs2 = 49
    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    except OSError:
        return None
    mib = (ctypes.c_int * 3)(ctl_kern, kern_procargs2, pid)
    size = ctypes.c_size_t()
    sysctl = libc.sysctl
    sysctl.argtypes = [
        ctypes.POINTER(ctypes.c_int),
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    sysctl.restype = ctypes.c_int
    if sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0:
        return None
    buf = ctypes.create_string_buffer(size.value)
    if sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return None
    data = buf.raw[: size.value]
    if len(data) < 4:
        return None
    argc = int.from_bytes(data[:4], sys.byteorder)
    rest = data[4:]
    strings = rest.split(b"\0")
    # executable, then argv, then env KEY=VAL
    found: dict[str, str] = {}
    skipped = 0
    for chunk in strings:
        if not chunk:
            continue
        skipped += 1
        if skipped <= argc + 1:
            continue
        if b"=" not in chunk:
            continue
        name, _, value = chunk.partition(b"=")
        found[name.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return found
