"""Discover events for OS/architecture, memory, accelerator, and mounts.

OS family, CPU architecture, reported memory size, and accelerator
identity are non-identifying machine facts. Privacy is ``public_ops``.
Mount topology events are ``operational``: they carry counts and classes,
not mount-point paths. Hostname, customer filenames, and content stay
out. HostId stays unresolved. Composition supplies Install correlation.
"""

from __future__ import annotations

from dataclasses import dataclass

from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorObservation,
    AcceleratorProviderReport,
    CpuArchitecture,
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
)
from machi.discover.mount_contracts import (
    MountNamespace,
    MountObservation,
    StorageClass,
)
from machi.kernel.clock import Clock, FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, is_resolved

DISCOVER_BLOCK = "2"
OS_ARCH_COMPONENT = "2.1.1"
OS_ARCH_OBSERVED_TYPE = "discover.os_arch.observed"
MEMORY_COMPONENT = "2.2.1"
MEMORY_OBSERVED_TYPE = "discover.memory.observed"
ACCELERATOR_COMPONENT = "2.3.1"
ACCELERATOR_OBSERVED_TYPE = "discover.accelerator.observed"
MOUNT_COMPONENT = "2.4.1"
MOUNT_OBSERVED_TYPE = "discover.mounts.observed"


@contract(kind="discover.os_arch.observed", version=1)
@dataclass(frozen=True, slots=True)
class OSArchObservedPayload(Contract):
    """Safe public operational body for an OS/arch observation."""

    os_family: Maybe[OSFamily] = meaning(
        "normalized OS family; Unresolved when unobserved or unrecognized"
    )
    architecture: Maybe[CpuArchitecture] = meaning(
        "normalized CPU architecture; Unresolved when unobserved or unrecognized"
    )
    os_status: ObservationStatus = meaning("how the OS family was normalized")
    architecture_status: ObservationStatus = meaning(
        "how the CPU architecture was normalized"
    )
    raw_os: str = meaning("narrow raw OS string; not a hostname or path")
    raw_architecture: str = meaning("narrow raw architecture string")
    observer: str = meaning("adapter identifier, for example native")


def os_arch_observed(
    observation: OSArchitectureObservation,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the OS/arch event. Does not persist it. Does not mint HostId."""
    event = EventRecord.create(
        event_type=OS_ARCH_OBSERVED_TYPE,
        block_id=DISCOVER_BLOCK,
        component_id=OS_ARCH_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.PUBLIC_OPS,
        payload=OSArchObservedPayload(
            os_family=observation.os_family,
            architecture=observation.architecture,
            os_status=observation.os_status,
            architecture_status=observation.architecture_status,
            raw_os=observation.raw_os,
            raw_architecture=observation.raw_architecture,
            observer=observation.observer,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or FixedClock(observation.observed_at),
    )
    if event.privacy is not PrivacyClass.PUBLIC_OPS:
        raise ValidationError(
            "discover.os_arch.observed must be public_ops",
            privacy=event.privacy.value,
        )
    return event


@contract(kind="discover.memory.observed", version=1)
@dataclass(frozen=True, slots=True)
class MemoryObservedPayload(Contract):
    """Safe public operational body for a physical/system memory observation."""

    physical_total_bytes: Maybe[int] = meaning(
        "reported physical/system memory in integer bytes; Unresolved when unobserved"
    )
    physical_total_status: ObservationStatus = meaning(
        "how physical/system memory was measured"
    )
    source: MemorySource = meaning("measured source or explicit non-measurement")
    raw_total: str = meaning("compact source evidence; not a path")
    observer: str = meaning("adapter identifier, for example native")


def memory_observed(
    observation: MemoryObservation,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the memory event. Does not persist it. Does not mint HostId."""
    event = EventRecord.create(
        event_type=MEMORY_OBSERVED_TYPE,
        block_id=DISCOVER_BLOCK,
        component_id=MEMORY_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.PUBLIC_OPS,
        payload=MemoryObservedPayload(
            physical_total_bytes=observation.physical_total_bytes,
            physical_total_status=observation.physical_total_status,
            source=observation.source,
            raw_total=observation.raw_total,
            observer=observation.observer,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or FixedClock(observation.observed_at),
    )
    if event.privacy is not PrivacyClass.PUBLIC_OPS:
        raise ValidationError(
            "discover.memory.observed must be public_ops",
            privacy=event.privacy.value,
        )
    return event


@contract(kind="discover.accelerator.observed", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorObservedPayload(Contract):
    """Safe public operational body for a generic accelerator observation."""

    devices: tuple[AcceleratorDevice, ...] = meaning(
        "observed devices in ordinal order; empty when none were successfully listed"
    )
    providers: tuple[AcceleratorProviderReport, ...] = meaning(
        "every implemented provider's inspection outcome for this invocation"
    )
    status: ObservationStatus = meaning(
        "normalized when at least one provider observed; unobserved otherwise"
    )
    observer: str = meaning("adapter identifier, for example native")


def accelerator_observed(
    observation: AcceleratorObservation,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the accelerator event. Does not persist it. Does not mint HostId."""
    event = EventRecord.create(
        event_type=ACCELERATOR_OBSERVED_TYPE,
        block_id=DISCOVER_BLOCK,
        component_id=ACCELERATOR_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.PUBLIC_OPS,
        payload=AcceleratorObservedPayload(
            devices=observation.devices,
            providers=observation.providers,
            status=observation.status,
            observer=observation.observer,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or FixedClock(observation.observed_at),
    )
    if event.privacy is not PrivacyClass.PUBLIC_OPS:
        raise ValidationError(
            "discover.accelerator.observed must be public_ops",
            privacy=event.privacy.value,
        )
    return event


@contract(kind="discover.mounts.observed", version=1)
@dataclass(frozen=True, slots=True)
class MountsObservedPayload(Contract):
    """Operational mount-topology metadata. Mount-point paths stay off the event."""

    entry_count: int = meaning("how many mount entries were retained")
    invalid_record_count: int = meaning("malformed table rows skipped")
    truncated_entry_count: int = meaning("valid rows omitted after the entry bound")
    unresolved_backing_count: int = meaning(
        "entries whose backing identity stayed Unresolved"
    )
    unresolved_capacity_count: int = meaning(
        "entries whose reported total_bytes stayed Unresolved"
    )
    storage_classes: str = meaning(
        "compact class histogram such as local_physical:2,pseudo:8"
    )
    write_probe_policy: str = meaning("disabled or bounded")
    status: ObservationStatus = meaning(
        "normalized when the mount table was read; unobserved otherwise"
    )
    namespace_context: MountNamespace = meaning(
        "filesystem namespace this process observed"
    )
    provider: str = meaning("selected provider identifier")
    observer: str = meaning("adapter identifier, for example native")


def mounts_observed(
    observation: MountObservation,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the mounts event. Does not persist it. Does not mint HostId."""
    counts: dict[str, int] = {}
    unresolved_backing = 0
    unresolved_capacity = 0
    for entry in observation.entries:
        key = entry.storage_class.value
        counts[key] = counts.get(key, 0) + 1
        if not is_resolved(entry.backing_store_id):
            unresolved_backing += 1
        if not is_resolved(entry.reported_capacity.total_bytes):
            unresolved_capacity += 1
    histogram = ",".join(
        f"{name}:{counts[name]}"
        for name in (
            StorageClass.LOCAL_PHYSICAL.value,
            StorageClass.LOCAL_VIRTUAL.value,
            StorageClass.NETWORK.value,
            StorageClass.OVERLAY.value,
            StorageClass.TMPFS.value,
            StorageClass.PSEUDO.value,
            StorageClass.UNKNOWN.value,
        )
        if name in counts
    )
    event = EventRecord.create(
        event_type=MOUNT_OBSERVED_TYPE,
        block_id=DISCOVER_BLOCK,
        component_id=MOUNT_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.OPERATIONAL,
        payload=MountsObservedPayload(
            entry_count=len(observation.entries),
            invalid_record_count=observation.invalid_record_count,
            truncated_entry_count=observation.truncated_entry_count,
            unresolved_backing_count=unresolved_backing,
            unresolved_capacity_count=unresolved_capacity,
            storage_classes=histogram,
            write_probe_policy=observation.settings.write_probe_policy.value,
            status=observation.status,
            namespace_context=observation.namespace_context,
            provider=observation.provider,
            observer=observation.observer,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or FixedClock(observation.observed_at),
    )
    if event.privacy is not PrivacyClass.OPERATIONAL:
        raise ValidationError(
            "discover.mounts.observed must be operational",
            privacy=event.privacy.value,
        )
    return event
