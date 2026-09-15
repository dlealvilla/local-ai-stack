"""Pure OS/architecture alias mapping (MACHI 2.1.1).

Normalization does not call platform APIs. Adapters supply raw strings.
Unknown raw values stay unrecognized; they are never defaulted to Linux
or x86_64.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import TypeVar

from machi.discover.contracts import (
    CpuArchitecture,
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.unresolved import (
    NOT_MEASURED,
    Maybe,
    Unresolved,
    UnresolvedReason,
)

NATIVE_OBSERVER = "native"

_OS_ALIASES: dict[str, OSFamily] = {
    "linux": OSFamily.LINUX,
    "darwin": OSFamily.MACOS,
    "macos": OSFamily.MACOS,
    "windows": OSFamily.WINDOWS,
    "win32": OSFamily.WINDOWS,
    "win64": OSFamily.WINDOWS,
}

_ARCH_ALIASES: dict[str, CpuArchitecture] = {
    "x86_64": CpuArchitecture.X86_64,
    "amd64": CpuArchitecture.X86_64,
    "x64": CpuArchitecture.X86_64,
    "aarch64": CpuArchitecture.ARM64,
    "arm64": CpuArchitecture.ARM64,
}

EnumT = TypeVar("EnumT", bound=StrEnum)


def normalize_os_architecture(
    raw_os: str,
    raw_architecture: str,
    *,
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> OSArchitectureObservation:
    """Map narrow raw platform strings onto Machi OS/arch vocabulary."""
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    os_status, os_family = _map_alias(raw_os, _OS_ALIASES, what="operating system")
    arch_status, architecture = _map_alias(
        raw_architecture, _ARCH_ALIASES, what="architecture"
    )
    return OSArchitectureObservation(
        os_family=os_family,
        architecture=architecture,
        os_status=os_status,
        architecture_status=arch_status,
        raw_os=raw_os,
        raw_architecture=raw_architecture,
        observed_at=when,
        observer=observer,
    )


def _map_alias(
    raw: str,
    table: dict[str, EnumT],
    *,
    what: str,
) -> tuple[ObservationStatus, Maybe[EnumT]]:
    key = raw.strip().lower()
    if not key:
        return ObservationStatus.UNOBSERVED, NOT_MEASURED
    matched = table.get(key)
    if matched is None:
        return (
            ObservationStatus.UNRECOGNIZED,
            Unresolved(
                UnresolvedReason.UNSUPPORTED,
                f"observed {raw.strip()!r} has no Machi {what} alias",
            ),
        )
    return ObservationStatus.NORMALIZED, matched
