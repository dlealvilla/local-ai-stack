"""Pure mount-observation helpers (MACHI 2.4.1).

Domain owns generic ``MountObservation`` factories and descriptive
suitability. Concrete Linux/macOS readers live in adapters. This module
does not read the host, does not parse platform tables, and does not
compute SAFE storage capacity.
"""

from __future__ import annotations

import datetime as dt

from machi.discover.contracts import ObservationStatus, OSFamily
from machi.discover.mount_contracts import (
    AccessMode,
    CapacitySource,
    MountEntry,
    MountNamespace,
    MountObservation,
    MountObservationSettings,
    MountSetting,
    MountSettingProvenance,
    MountSettingSupportState,
    NetworkMountPolicy,
    PathCapability,
    PseudoMountPolicy,
    QuotaEvidence,
    QuotaEvidenceStatus,
    QuotaSource,
    ReadOnlyHandling,
    ReportedCapacity,
    StorageClass,
    SuitabilityReason,
    SuitabilitySignals,
    WriteProbeOutcome,
    WriteProbePolicy,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import (
    NOT_MEASURED,
    Maybe,
    Unresolved,
    UnresolvedReason,
    is_resolved,
)

NATIVE_OBSERVER = "native"
DEFAULT_WRITE_PROBE_MAX_BYTES = 64
MAX_WRITE_PROBE_BYTES = 4096
MAX_MOUNT_ENTRIES = 512

_DEFAULT_INCLUDED = (
    StorageClass.LOCAL_PHYSICAL,
    StorageClass.LOCAL_VIRTUAL,
    StorageClass.NETWORK,
    StorageClass.OVERLAY,
    StorageClass.TMPFS,
    StorageClass.UNKNOWN,
)
_DEFAULT_IGNORED = (StorageClass.PSEUDO,)
_DISQUALIFYING_REASONS = frozenset(
    {
        SuitabilityReason.READ_ONLY,
        SuitabilityReason.PSEUDO_FILESYSTEM,
        SuitabilityReason.INACCESSIBLE,
        SuitabilityReason.CLASS_IGNORED,
    }
)


def default_mount_settings(
    *,
    write_probe_policy: WriteProbePolicy = WriteProbePolicy.DISABLED,
    write_probe_max_bytes: int = DEFAULT_WRITE_PROBE_MAX_BYTES,
    write_probe_provenance: MountSettingProvenance = (
        MountSettingProvenance.PRODUCT_DEFAULT
    ),
    managed_root_candidates: tuple[str, ...] = (),
) -> MountObservationSettings:
    """Product-default 2.4 settings. Probe off; pseudo not a candidate."""
    if write_probe_max_bytes < 1 or write_probe_max_bytes > MAX_WRITE_PROBE_BYTES:
        raise ValidationError(
            "write_probe_max_bytes is outside the observational bound",
            write_probe_max_bytes=write_probe_max_bytes,
        )
    probe_reason = (
        "bounded observational write is off unless an administrator enables it"
        if write_probe_policy is WriteProbePolicy.DISABLED
        else "tiny observational write only; never fill-until-failure"
    )
    settings = (
        MountSetting(
            name="write_probe.policy",
            value=write_probe_policy.value,
            provenance=write_probe_provenance,
            reason=probe_reason,
            allowed_values="disabled,bounded",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="write_probe.max_bytes",
            value=str(write_probe_max_bytes),
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="tiny payload bound; not a capacity target",
            allowed_values=f"1..{MAX_WRITE_PROBE_BYTES}",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="filesystem.included_classes",
            value=_join_classes(_DEFAULT_INCLUDED),
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="non-pseudo classes remain descriptive candidacy signals",
            allowed_values=_join_classes(tuple(StorageClass)),
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="filesystem.ignored_classes",
            value=_join_classes(_DEFAULT_IGNORED),
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="pseudo/system filesystems are topology, not ordinary storage",
            allowed_values=_join_classes(tuple(StorageClass)),
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="managed_root.candidates",
            value=",".join(managed_root_candidates) if managed_root_candidates else "",
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="Discover does not infer ownership from path names",
            allowed_values="up to 8 absolute paths; empty default",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="network.mount_policy",
            value=NetworkMountPolicy.OBSERVE.value,
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="network mounts are classified, not auto-rejected",
            allowed_values="observe",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="pseudo.mount_policy",
            value=PseudoMountPolicy.TOPOLOGY_NOT_CANDIDATE.value,
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="pseudo filesystems remain visible and are not candidates",
            allowed_values="topology_not_candidate",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
        MountSetting(
            name="read_only.handling",
            value=ReadOnlyHandling.OBSERVE.value,
            provenance=MountSettingProvenance.PRODUCT_DEFAULT,
            reason="read-only mounts are observed; Discover does not remount",
            allowed_values="observe",
            support_state=MountSettingSupportState.SUPPORTED,
            mutability="runtime",
            invalidation="reobserve",
        ),
    )
    return MountObservationSettings(
        write_probe_policy=write_probe_policy,
        write_probe_max_bytes=write_probe_max_bytes,
        included_filesystem_classes=_DEFAULT_INCLUDED,
        ignored_filesystem_classes=_DEFAULT_IGNORED,
        managed_root_candidates=managed_root_candidates,
        network_mount_policy=NetworkMountPolicy.OBSERVE,
        pseudo_mount_policy=PseudoMountPolicy.TOPOLOGY_NOT_CANDIDATE,
        read_only_handling=ReadOnlyHandling.OBSERVE,
        settings=settings,
    )


def unobserved_capacity() -> ReportedCapacity:
    """Unknown reported totals. Never substitutes zero bytes."""
    return ReportedCapacity(
        total_bytes=NOT_MEASURED,
        free_bytes=NOT_MEASURED,
        available_bytes=NOT_MEASURED,
        source=CapacitySource.UNOBSERVED,
    )


def measured_capacity(
    *,
    total_bytes: int,
    free_bytes: int,
    available_bytes: int,
) -> ReportedCapacity:
    """Keep total, free, and available distinct. None of these is SAFE."""
    return ReportedCapacity(
        total_bytes=total_bytes,
        free_bytes=free_bytes,
        available_bytes=available_bytes,
        source=CapacitySource.NATIVE_STAT,
    )


def unsupported_quota() -> QuotaEvidence:
    """This component does not read native quota specialists."""
    return QuotaEvidence(
        status=QuotaEvidenceStatus.UNSUPPORTED,
        hard_limit_bytes=NOT_MEASURED,
        soft_limit_bytes=NOT_MEASURED,
        usage_bytes=NOT_MEASURED,
        source=QuotaSource.UNSUPPORTED,
    )


def advertised_unread_quota() -> QuotaEvidence:
    """Quota options were visible; limits were not read. Not a zero quota."""
    return QuotaEvidence(
        status=QuotaEvidenceStatus.UNAVAILABLE,
        hard_limit_bytes=Unresolved(
            UnresolvedReason.NOT_MEASURED,
            "quota options were present and limits were not read",
        ),
        soft_limit_bytes=Unresolved(
            UnresolvedReason.NOT_MEASURED,
            "quota options were present and limits were not read",
        ),
        usage_bytes=Unresolved(
            UnresolvedReason.NOT_MEASURED,
            "quota options were present and limits were not read",
        ),
        source=QuotaSource.MOUNT_OPTION,
    )


def skipped_path_capability(
    *,
    path_exists: Maybe[bool],
    readable: Maybe[bool],
    writable_by_access: Maybe[bool],
    mount_read_only: Maybe[bool],
    detail: str = "",
) -> PathCapability:
    """Access facts without a write probe."""
    return PathCapability(
        path_exists=path_exists,
        readable=readable,
        writable_by_access=writable_by_access,
        mount_read_only=mount_read_only,
        write_probe_outcome=WriteProbeOutcome.NOT_ATTEMPTED,
        write_probe_bytes=NOT_MEASURED,
        cleanup_completed=NOT_MEASURED,
        detail=detail,
    )


def suitability_signals(
    *,
    storage_class: StorageClass,
    access_mode: AccessMode,
    path_capability: PathCapability,
    settings: MountObservationSettings,
    backing_store_id: Maybe[str],
) -> SuitabilitySignals:
    """Descriptive candidacy from topology facts. Not an admission decision."""
    reasons: list[SuitabilityReason] = []
    if storage_class in settings.ignored_filesystem_classes:
        reasons.append(SuitabilityReason.CLASS_IGNORED)
    if storage_class is StorageClass.PSEUDO:
        reasons.append(SuitabilityReason.PSEUDO_FILESYSTEM)
    if storage_class is StorageClass.TMPFS:
        reasons.append(SuitabilityReason.TMPFS)
    if storage_class is StorageClass.NETWORK:
        reasons.append(SuitabilityReason.NETWORK_STORAGE)
    if storage_class is StorageClass.OVERLAY:
        reasons.append(SuitabilityReason.OVERLAY_STORAGE)
    if storage_class is StorageClass.UNKNOWN:
        reasons.append(SuitabilityReason.UNKNOWN_CLASS)
    if access_mode is AccessMode.READ_ONLY or path_capability.mount_read_only is True:
        reasons.append(SuitabilityReason.READ_ONLY)
    if path_capability.path_exists is False or path_capability.readable is False:
        reasons.append(SuitabilityReason.INACCESSIBLE)
    if not is_resolved(backing_store_id):
        reasons.append(SuitabilityReason.UNKNOWN_BACKING)
    if path_capability.write_probe_outcome in {
        WriteProbeOutcome.FAILED,
        WriteProbeOutcome.CLEANUP_FAILED,
    }:
        reasons.append(SuitabilityReason.WRITE_PROBE_FAILED)
    elif path_capability.write_probe_outcome is not WriteProbeOutcome.SUCCEEDED:
        reasons.append(SuitabilityReason.NO_WRITE_PROOF)
    unique = tuple(dict.fromkeys(reasons))
    allowed = (
        storage_class in settings.included_filesystem_classes
        and storage_class not in settings.ignored_filesystem_classes
    )
    candidate = allowed and not any(
        reason in _DISQUALIFYING_REASONS for reason in unique
    )
    return SuitabilitySignals(
        can_host_machi_state=candidate,
        can_host_runtime=candidate,
        can_host_model=candidate,
        can_host_cache=candidate,
        can_host_staging=candidate,
        can_host_telemetry=candidate,
        reasons=unique,
    )


def mount_observation(
    *,
    entries: tuple[MountEntry, ...],
    settings: MountObservationSettings,
    os_family: OSFamily,
    namespace_context: MountNamespace,
    invalid_record_count: int = 0,
    truncated_entry_count: int = 0,
    provider: str,
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> MountObservation:
    """Build a normalized observation from provider entries."""
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    return MountObservation(
        entries=entries,
        settings=settings,
        status=ObservationStatus.NORMALIZED,
        os_family=os_family,
        namespace_context=namespace_context,
        invalid_record_count=invalid_record_count,
        truncated_entry_count=truncated_entry_count,
        provider=provider,
        observer=observer,
        observed_at=when,
    )


def unobserved_mount_observation(
    *,
    settings: MountObservationSettings,
    reason: UnresolvedReason,
    detail: str,
    os_family: Maybe[OSFamily] = NOT_MEASURED,
    namespace_context: MountNamespace = MountNamespace.UNKNOWN,
    provider: str,
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> MountObservation:
    """Build a truthful non-observation. Never substitutes an empty SAFE disk."""
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    if not isinstance(os_family, Unresolved) and not isinstance(os_family, OSFamily):
        raise ValidationError("os_family must be resolved or Unresolved")
    _ = reason, detail
    return MountObservation(
        entries=(),
        settings=settings,
        status=ObservationStatus.UNOBSERVED,
        os_family=os_family,
        namespace_context=namespace_context,
        invalid_record_count=0,
        truncated_entry_count=0,
        provider=provider,
        observer=observer,
        observed_at=when,
    )


def _join_classes(values: tuple[StorageClass, ...]) -> str:
    return ",".join(item.value for item in values)
