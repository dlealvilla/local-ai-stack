"""Discover observation contracts owned by Block 2.

``OSArchitectureObservation`` is the 2.1.1 output. It records what the
adapter saw and how Machi normalized it. It is not a HostId, not a
support certificate, and not a HostProfile.
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


def _require_raw(value: str, *, what: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(
            f"{what} must be a string",
            what=what,
            actual_type=type(value).__name__,
        )
    if len(value) > _RAW_MAX:
        raise ValidationError(
            f"{what} exceeds the narrow observation bound",
            what=what,
            maximum=_RAW_MAX,
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
