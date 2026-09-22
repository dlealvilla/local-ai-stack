"""Discover observation contracts owned by Block 2.

``OSArchitectureObservation`` is the 2.1.1 output. ``MemoryObservation``
is the 2.2.1 output. ``AcceleratorObservation`` is the 2.3 output.
``MountObservation`` is the 2.4.1 output. None is a HostId, a support
certificate, a HostProfile, or a capacity envelope.
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
_MODEL_MAX = 96
_IDENTITY_MAX = 80
_DEVICE_RAW_MAX = 160
_PROVIDER_DETAIL_MAX = 160
_ACCELERATOR_MEMORY_MAX = 1 << 50
_MAX_DEVICES = 64
_MAX_PROVIDER_REPORTS = 16


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


class AcceleratorVendor(StrEnum):
    """Observable accelerator vendors. Presence in the enum is not a provider."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"


class AcceleratorDeviceType(StrEnum):
    """How the device is attached. Not a runtime backend name."""

    DISCRETE_GPU = "discrete_gpu"
    INTEGRATED_GPU = "integrated_gpu"


class AcceleratorMemoryTopology(StrEnum):
    """How accelerator memory relates to system memory. Not a SAFE budget."""

    DISCRETE = "discrete"
    UNIFIED = "unified"


class AcceleratorSource(StrEnum):
    """Where one device observation was read. Provenance data, not policy."""

    NVIDIA_SMI = "nvidia_smi"
    AMD_SMI = "amd_smi"
    APPLE_DISPLAYS = "apple_displays"


class ProviderInspectionStatus(StrEnum):
    """Outcome of one provider invocation. Not a device count."""

    OBSERVED = "observed"
    NOT_APPLICABLE = "not_applicable"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


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


@contract(kind="accelerator_device", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorDevice(Contract):
    """One accelerator device. Never a capacity envelope.

    Per-device, never aggregated. Dedicated memory bytes are not system
    RAM and are not safe allocatable VRAM. Unified topology forbids a
    fake dedicated total.
    """

    ordinal: int = meaning(
        "0-based position in this observation; not a vendor runtime index"
    )
    vendor: Maybe[AcceleratorVendor] = meaning(
        "normalized vendor when known; Unresolved otherwise"
    )
    vendor_status: ObservationStatus = meaning(
        "normalized, unrecognized, or unobserved for vendor"
    )
    model_name: str = meaning(
        "device model as reported; empty when unobserved; never a path"
    )
    model_status: ObservationStatus = meaning("how the model name was observed")
    device_type: Maybe[AcceleratorDeviceType] = meaning(
        "discrete or integrated when known; Unresolved otherwise"
    )
    device_type_status: ObservationStatus = meaning("how device type was observed")
    memory_topology: Maybe[AcceleratorMemoryTopology] = meaning(
        "discrete dedicated memory or unified/shared with system; Unresolved if unknown"
    )
    memory_topology_status: ObservationStatus = meaning(
        "how memory topology was observed"
    )
    memory_total_bytes: Maybe[int] = meaning(
        "dedicated accelerator memory in integer bytes when the source "
        "reported it; Unresolved for unified/unknown topology; never system RAM"
    )
    memory_total_status: ObservationStatus = meaning(
        "normalized only for a reported dedicated total; unobserved otherwise"
    )
    identity: str = meaning(
        "bounded provider-local identity; not a PCI requirement and not a HostId"
    )
    source: AcceleratorSource = meaning(
        "which provider source produced this device; never a filesystem path"
    )
    raw: str = meaning("compact source evidence; empty when nothing was retained")

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise ValidationError(
                "accelerator ordinal must be a non-negative integer",
                ordinal=self.ordinal,
            )
        if self.ordinal >= _MAX_DEVICES:
            raise ValidationError(
                "accelerator ordinal exceeds the observation bound",
                ordinal=self.ordinal,
            )
        _require_token(self.identity, what="identity", maximum=_IDENTITY_MAX)
        _require_raw(self.model_name, what="model_name", maximum=_MODEL_MAX)
        if "/" in self.model_name or "\\" in self.model_name:
            raise ValidationError(
                "model_name must not contain a filesystem path",
                model_name=self.model_name,
            )
        _require_raw(self.raw, what="raw", maximum=_DEVICE_RAW_MAX)
        if "/" in self.raw or "\\" in self.raw:
            raise ValidationError(
                "accelerator raw evidence must not contain a filesystem path"
            )
        _require_axis(
            status=self.vendor_status,
            normalized=self.vendor,
            raw=self.vendor.value if is_resolved(self.vendor) else "",
            what="vendor",
        )
        if self.model_status is ObservationStatus.NORMALIZED and not self.model_name:
            raise ValidationError("normalized model_name is required")
        if self.model_status is ObservationStatus.UNOBSERVED and self.model_name:
            raise ValidationError("unobserved model_name must be empty")
        _require_axis(
            status=self.device_type_status,
            normalized=self.device_type,
            raw=self.device_type.value if is_resolved(self.device_type) else "",
            what="device type",
        )
        _require_axis(
            status=self.memory_topology_status,
            normalized=self.memory_topology,
            raw=(
                self.memory_topology.value if is_resolved(self.memory_topology) else ""
            ),
            what="memory topology",
        )
        _require_accelerator_memory(
            status=self.memory_total_status,
            total=self.memory_total_bytes,
            topology=self.memory_topology,
        )


@contract(kind="accelerator_provider_report", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorProviderReport(Contract):
    """How one implemented provider participated in an observation.

    Unavailable is not a measured zero-device result. Observed with an
    empty device list is a successful inspection that found nothing.
    """

    provider: str = meaning("provider identifier, for example nvidia or apple")
    status: ProviderInspectionStatus = meaning(
        "observed, not_applicable, unavailable, unsupported, or failed"
    )
    detail: str = meaning("bounded reason or empty; not a filesystem path")
    device_count: Maybe[int] = meaning(
        "devices this provider emitted when status is observed; Unresolved otherwise"
    )

    def __post_init__(self) -> None:
        _require_token(self.provider, what="provider", maximum=_OBSERVER_MAX)
        _require_raw(self.detail, what="detail", maximum=_PROVIDER_DETAIL_MAX)
        if "/" in self.detail or "\\" in self.detail:
            raise ValidationError(
                "provider detail must not contain a filesystem path",
                provider=self.provider,
            )
        if self.status is ProviderInspectionStatus.OBSERVED:
            if not isinstance(self.device_count, int):
                raise ValidationError(
                    "observed provider report requires an integer device_count",
                    provider=self.provider,
                )
            if self.device_count < 0:
                raise ValidationError(
                    "device_count must not be negative",
                    provider=self.provider,
                )
            return
        if is_resolved(self.device_count):
            raise ValidationError(
                "device_count stays unresolved unless the provider observed",
                provider=self.provider,
                status=self.status.value,
            )


@contract(kind="accelerator_observation", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorObservation(Contract):
    """Accelerators visible to this process. Not a HostProfile or capacity.

    An empty device list with overall status normalized means applicable
    providers inspected and found none. Unobserved means no provider
    successfully inspected. Provider unavailability is recorded in
    ``providers`` and is never rewritten as zero devices.
    """

    devices: tuple[AcceleratorDevice, ...] = meaning(
        "observed devices in ordinal order; empty when none were successfully listed"
    )
    providers: tuple[AcceleratorProviderReport, ...] = meaning(
        "every implemented provider's inspection outcome for this invocation"
    )
    status: ObservationStatus = meaning(
        "normalized when at least one provider observed; unobserved otherwise"
    )
    observed_at: dt.datetime = meaning(
        "when this observation was taken; timezone-aware UTC; never rewritten"
    )
    observer: str = meaning(
        "adapter identifier that produced the observation, for example native"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _require_token(self.observer, what="observer", maximum=_OBSERVER_MAX)
        if len(self.devices) > _MAX_DEVICES:
            raise ValidationError(
                "accelerator observation exceeds the device bound",
                count=len(self.devices),
            )
        if len(self.providers) > _MAX_PROVIDER_REPORTS:
            raise ValidationError(
                "accelerator observation exceeds the provider-report bound",
                count=len(self.providers),
            )
        ordinals = tuple(device.ordinal for device in self.devices)
        if ordinals != tuple(range(len(self.devices))):
            raise ValidationError(
                "accelerator ordinals must be contiguous from zero",
                ordinals=ordinals,
            )
        observed_reports = [
            report
            for report in self.providers
            if report.status is ProviderInspectionStatus.OBSERVED
        ]
        observed_count = sum(
            report.device_count
            for report in observed_reports
            if isinstance(report.device_count, int)
        )
        if observed_count != len(self.devices):
            raise ValidationError(
                "device list must match observed provider device counts",
                devices=len(self.devices),
                reported=observed_count,
            )
        if self.status is ObservationStatus.NORMALIZED:
            if not observed_reports:
                raise ValidationError(
                    "normalized accelerator observation requires an observed provider"
                )
            return
        if self.status is not ObservationStatus.UNOBSERVED:
            raise ValidationError(
                "accelerator status must be normalized or unobserved",
                status=self.status.value,
            )
        if observed_reports:
            raise ValidationError(
                "unobserved accelerator observation cannot include an observed provider"
            )
        if self.devices:
            raise ValidationError(
                "unobserved accelerator observation cannot list devices"
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


def _require_accelerator_memory(
    *,
    status: ObservationStatus,
    total: object,
    topology: Maybe[AcceleratorMemoryTopology],
) -> None:
    if (
        is_resolved(topology)
        and topology is AcceleratorMemoryTopology.UNIFIED
        and status is ObservationStatus.NORMALIZED
    ):
        raise ValidationError(
            "unified accelerator memory must not invent a dedicated total"
        )
    if status is ObservationStatus.UNOBSERVED:
        if is_resolved(total):
            raise ValidationError(
                "unobserved accelerator memory_total_bytes must be Unresolved"
            )
        return
    if status is not ObservationStatus.NORMALIZED:
        raise ValidationError(
            "accelerator memory_total_status must be normalized or unobserved",
            status=status.value,
        )
    if not isinstance(total, int):
        raise ValidationError("normalized accelerator memory_total_bytes is required")
    if total <= 0:
        raise ValidationError(
            "accelerator memory_total_bytes must be a positive integer",
            total=total,
        )
    if total > _ACCELERATOR_MEMORY_MAX:
        raise ValidationError(
            "accelerator memory_total_bytes exceeds the observation bound",
            total=total,
        )
    if is_resolved(topology) and topology is not AcceleratorMemoryTopology.DISCRETE:
        raise ValidationError(
            "normalized accelerator memory_total_bytes is only for discrete topology"
        )
