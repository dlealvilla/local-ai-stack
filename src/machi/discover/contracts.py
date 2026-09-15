"""Discover observation contracts owned by Block 2.

``OSArchitectureObservation`` is the 2.1.1 output. ``MemoryObservation``
is the 2.2.1 output. Neither is a HostId, a support certificate, a
HostProfile, or a capacity envelope.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, Unresolved, is_resolved

_OBSERVER_MAX = 64
_RAW_MAX = 64
_MEMORY_RAW_MAX = 96
_MEMORY_TOTAL_MAX = 1 << 50


class OSFamily(StrEnum):
    """Observable operating-system families. Presence is not support."""

    LINUX = "linux"
    MACOS = "macos"
    WINDOWS = "windows"


class CpuArchitecture(StrEnum):
    """Observable CPU architectures. Presence is not support."""

    X86_64 = "x86_64"
    ARM64 = "arm64"


class ObservationStatus(StrEnum):
    """How a normalized field relates to the raw observation."""

    NORMALIZED = "normalized"
    UNRECOGNIZED = "unrecognized"
    UNOBSERVED = "unobserved"


class MemorySource(StrEnum):
    """Where physical/system memory bytes were read. Not a capacity method."""

    LINUX_PROC = "linux_proc"
    SYSCONF = "sysconf"
    UNOBSERVED = "unobserved"
    UNSUPPORTED = "unsupported"


@contract(kind="os_architecture_observation", version=1)
@dataclass(frozen=True, slots=True)
class OSArchitectureObservation(Contract):
    """One OS-family and CPU-architecture observation.

    Normalized fields are Unresolved when the raw value was missing or
    had no alias. Raw fields always retain the narrow platform strings
    that were read. This is not host identity and not a compatibility
    decision.
    """

    os_family: Maybe[OSFamily] = meaning(
        "normalized OS family when an alias matched; Unresolved otherwise"
    )
    architecture: Maybe[CpuArchitecture] = meaning(
        "normalized CPU architecture when an alias matched; Unresolved otherwise"
    )
    os_status: ObservationStatus = meaning(
        "normalized, unrecognized (raw present, no alias), or unobserved"
    )
    architecture_status: ObservationStatus = meaning(
        "normalized, unrecognized (raw present, no alias), or unobserved"
    )
    raw_os: str = meaning(
        "narrow platform OS string as observed; empty when unobserved"
    )
    raw_architecture: str = meaning(
        "narrow platform architecture string as observed; empty when unobserved"
    )
    observed_at: dt.datetime = meaning(
        "when this observation was taken; timezone-aware UTC; never rewritten"
    )
    observer: str = meaning(
        "adapter identifier that produced the raw values, for example native"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _require_token(self.observer, what="observer", maximum=_OBSERVER_MAX)
        _require_raw(self.raw_os, what="raw_os")
        _require_raw(self.raw_architecture, what="raw_architecture")
        _require_axis(
            status=self.os_status,
            normalized=self.os_family,
            raw=self.raw_os,
            what="operating system",
        )
        _require_axis(
            status=self.architecture_status,
            normalized=self.architecture,
            raw=self.raw_architecture,
            what="architecture",
        )


@contract(kind="memory_observation", version=1)
@dataclass(frozen=True, slots=True)
class MemoryObservation(Contract):
    """One physical/system memory observation.

    ``physical_total_bytes`` is what the environment reported as installed
    system memory. It is not safe allocatable memory, not a reservation,
    and not a HostId. Available memory, swap, and execution limits are not
    this contract.
    """

    physical_total_bytes: Maybe[int] = meaning(
        "reported physical/system memory in integer bytes; Unresolved when unobserved"
    )
    physical_total_status: ObservationStatus = meaning(
        "normalized when bytes were measured; unobserved when not measured"
    )
    source: MemorySource = meaning(
        "linux_proc, sysconf, unobserved, or unsupported; never a filesystem path"
    )
    raw_total: str = meaning(
        "compact source evidence such as MemTotal kB or sysconf page counts; "
        "empty when unobserved"
    )
    observed_at: dt.datetime = meaning(
        "when this observation was taken; timezone-aware UTC; never rewritten"
    )
    observer: str = meaning(
        "adapter identifier that produced the reading, for example native"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _require_token(self.observer, what="observer", maximum=_OBSERVER_MAX)
        _require_raw(self.raw_total, what="raw_total", maximum=_MEMORY_RAW_MAX)
        _require_memory_total(
            status=self.physical_total_status,
            total=self.physical_total_bytes,
            raw=self.raw_total,
            source=self.source,
        )


def _require_token(value: str, *, what: str, maximum: int) -> None:
    if not value:
        raise ValidationError(f"{what} is required", what=what)
    if len(value) > maximum:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=maximum,
            length=len(value),
        )
    if "/" in value or "\\" in value or " " in value:
        raise ValidationError(
            f"{what} must be a path-free adapter identifier",
            what=what,
        )


def _require_raw(value: str, *, what: str, maximum: int = _RAW_MAX) -> None:
    if not isinstance(value, str):
        raise ValidationError(
            f"{what} must be a string",
            what=what,
            actual_type=type(value).__name__,
        )
    if len(value) > maximum:
        raise ValidationError(
            f"{what} exceeds the narrow observation bound",
            what=what,
            maximum=maximum,
            length=len(value),
        )


def _require_axis(
    *,
    status: ObservationStatus,
    normalized: object,
    raw: str,
    what: str,
) -> None:
    resolved = is_resolved(normalized)
    if status is ObservationStatus.NORMALIZED:
        if not resolved:
            raise ValidationError(
                f"normalized {what} is required when status is normalized",
                what=what,
            )
        return
    if resolved:
        raise ValidationError(
            f"{what} must stay unresolved when it is not normalized",
            what=what,
            status=status.value,
        )
    if not isinstance(normalized, Unresolved):
        raise ValidationError(
            f"unnormalized {what} must be Unresolved",
            what=what,
        )
    if status is ObservationStatus.UNRECOGNIZED and not raw.strip():
        raise ValidationError(
            f"unrecognized {what} requires a non-empty raw value",
            what=what,
        )
    if status is ObservationStatus.UNOBSERVED and raw.strip():
        raise ValidationError(
            f"unobserved {what} cannot carry a non-empty raw value",
            what=what,
        )


def _require_memory_total(
    *,
    status: ObservationStatus,
    total: object,
    raw: str,
    source: MemorySource,
) -> None:
    resolved = is_resolved(total)
    if status is ObservationStatus.NORMALIZED:
        if not isinstance(total, int):
            raise ValidationError(
                "normalized physical_total_bytes must be an integer",
                what="physical_total_bytes",
            )
        if total <= 0:
            raise ValidationError(
                "physical_total_bytes must be greater than zero",
                what="physical_total_bytes",
                total=total,
            )
        if total > _MEMORY_TOTAL_MAX:
            raise ValidationError(
                "physical_total_bytes is implausibly large",
                what="physical_total_bytes",
                total=total,
            )
        if not raw.strip():
            raise ValidationError(
                "normalized physical memory requires compact raw evidence",
                what="raw_total",
            )
        if source not in {MemorySource.LINUX_PROC, MemorySource.SYSCONF}:
            raise ValidationError(
                "normalized physical memory requires a measured source",
                source=source.value,
            )
        return
    if status is not ObservationStatus.UNOBSERVED:
        raise ValidationError(
            "physical memory status must be normalized or unobserved",
            status=status.value,
        )
    if resolved:
        raise ValidationError(
            "physical_total_bytes must stay unresolved when it is not normalized",
            what="physical_total_bytes",
        )
    if not isinstance(total, Unresolved):
        raise ValidationError(
            "unobserved physical_total_bytes must be Unresolved",
            what="physical_total_bytes",
        )
    if raw.strip():
        raise ValidationError(
            "unobserved physical memory cannot carry raw evidence",
            what="raw_total",
        )
    if source not in {MemorySource.UNOBSERVED, MemorySource.UNSUPPORTED}:
        raise ValidationError(
            "unobserved physical memory requires an unobserved or unsupported source",
            source=source.value,
        )
