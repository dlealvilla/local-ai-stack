"""Mount observation contracts owned by Discover 2.4.1.

These documents record filesystem/mount topology as the operating system
reported it. They are not Steward ownership, not Capacity envelopes, and
not SAFE deployable storage. Reported bytes, a successful tiny write, and
SAFE capacity remain distinct.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.discover.contracts import ObservationStatus, OSFamily
from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, Unresolved, is_resolved

_TOKEN_MAX = 64
_REASON_MAX = 240
_ALLOWED_MAX = 160
_PATH_MAX = 512
_SOURCE_MAX = 256
_FSTYPE_MAX = 64
_RAW_OPTIONS_MAX = 240
_DETAIL_MAX = 160
_IDENTITY_MAX = 80
_OBSERVER_MAX = 64
_CLASS_LIST_MAX = 160
_MAX_ENTRIES = 512
_MAX_OPTIONS = 24
_MAX_REASONS = 12
_MAX_SETTINGS = 16
_MAX_CANDIDATES = 8
_CAPACITY_MAX = 1 << 60
_PROBE_MAX = 4096


class StorageClass(StrEnum):
    """What kind of storage the observer could recognize. Not a safety label."""

    LOCAL_PHYSICAL = "local_physical"
    LOCAL_VIRTUAL = "local_virtual"
    NETWORK = "network"
    OVERLAY = "overlay"
    TMPFS = "tmpfs"
    PSEUDO = "pseudo"
    UNKNOWN = "unknown"


class MountNamespace(StrEnum):
    """Filesystem namespace this process can see. Not host/container identity."""

    HOST = "host"
    CONTAINER = "container"
    UNKNOWN = "unknown"


class AccessMode(StrEnum):
    """VFS read-write flag as observed. Not proven writability."""

    READ_WRITE = "rw"
    READ_ONLY = "ro"
    UNKNOWN = "unknown"


class CapacitySource(StrEnum):
    """Where reported totals came from. Not a Capacity method."""

    NATIVE_STAT = "native_stat"
    UNOBSERVED = "unobserved"
    UNSUPPORTED = "unsupported"


class QuotaEvidenceStatus(StrEnum):
    """Whether native quota/limit facts were captured. Not a SAFE limit."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


class QuotaSource(StrEnum):
    """Where quota evidence came from, when any was captured."""

    MOUNT_OPTION = "mount_option"
    UNOBSERVED = "unobserved"
    UNSUPPORTED = "unsupported"


class WriteProbePolicy(StrEnum):
    """Whether a tiny observational write is attempted."""

    DISABLED = "disabled"
    BOUNDED = "bounded"


class WriteProbeOutcome(StrEnum):
    """Result of one bounded write probe. Success is not a capacity proof."""

    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CLEANUP_FAILED = "cleanup_failed"
    SKIPPED = "skipped"


class SuitabilityReason(StrEnum):
    """Why a path is or is not a descriptive managed-storage candidate."""

    READ_ONLY = "read_only"
    PSEUDO_FILESYSTEM = "pseudo_filesystem"
    TMPFS = "tmpfs"
    NETWORK_STORAGE = "network_storage"
    OVERLAY_STORAGE = "overlay_storage"
    UNKNOWN_BACKING = "unknown_backing_capacity"
    NO_WRITE_PROOF = "no_write_proof"
    WRITE_PROBE_FAILED = "write_probe_failed"
    INACCESSIBLE = "inaccessible"
    CLASS_IGNORED = "class_ignored"
    UNKNOWN_CLASS = "unknown_class"


class NetworkMountPolicy(StrEnum):
    """How network mounts are treated in this observation."""

    OBSERVE = "observe"


class PseudoMountPolicy(StrEnum):
    """How pseudo/system filesystems are treated in this observation."""

    TOPOLOGY_NOT_CANDIDATE = "topology_not_candidate"


class ReadOnlyHandling(StrEnum):
    """How read-only mounts are treated in this observation."""

    OBSERVE = "observe"


class MountSettingProvenance(StrEnum):
    """Who selected a mount-observation setting. Not optimizer provenance."""

    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR = "administrator"


class MountSettingSupportState(StrEnum):
    """Whether the control-plane setting is usable now."""

    SUPPORTED = "supported"


@contract(kind="mount.setting", version=1)
@dataclass(frozen=True, slots=True)
class MountSetting(Contract):
    """One inspectable 2.4 setting for later command-center aggregation."""

    name: str = meaning("dotted setting name, for example write_probe.policy")
    value: str = meaning("current selected/desired value as text")
    provenance: MountSettingProvenance = meaning("who selected this value")
    reason: str = meaning("why this value is in force")
    allowed_values: str = meaning("compact allowed-value or bound description")
    support_state: MountSettingSupportState = meaning("whether this setting is usable")
    mutability: str = meaning("runtime or restart_required")
    invalidation: str = meaning("what must re-run if this setting changes")

    def __post_init__(self) -> None:
        _require_token(self.name, what="setting name", maximum=_TOKEN_MAX)
        _require_bounded(self.value, what="setting value", maximum=_CLASS_LIST_MAX)
        _require_bounded(self.reason, what="setting reason", maximum=_REASON_MAX)
        _require_bounded(
            self.allowed_values, what="allowed values", maximum=_ALLOWED_MAX
        )
        if self.mutability not in {"runtime", "restart_required"}:
            raise ValidationError(
                "setting mutability is not supported",
                mutability=self.mutability,
            )
        _require_token(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="mount.observation_settings", version=1)
@dataclass(frozen=True, slots=True)
class MountObservationSettings(Contract):
    """Typed 2.4 configuration. Not a global settings registry."""

    write_probe_policy: WriteProbePolicy = meaning(
        "disabled or bounded; never fill-until-failure"
    )
    write_probe_max_bytes: int = meaning(
        "tiny observational payload size; not a capacity target"
    )
    included_filesystem_classes: tuple[StorageClass, ...] = meaning(
        "classes eligible for descriptive managed-storage candidacy"
    )
    ignored_filesystem_classes: tuple[StorageClass, ...] = meaning(
        "classes observed for topology but not ordinary candidacy"
    )
    managed_root_candidates: tuple[str, ...] = meaning(
        "optional administrator paths; empty means Discover infers none from names"
    )
    network_mount_policy: NetworkMountPolicy = meaning(
        "network mounts are observed; they are not auto-rejected"
    )
    pseudo_mount_policy: PseudoMountPolicy = meaning(
        "pseudo filesystems stay in topology and are not ordinary candidates"
    )
    read_only_handling: ReadOnlyHandling = meaning(
        "read-only mounts are observed; they are not mutated"
    )
    settings: tuple[MountSetting, ...] = meaning(
        "inspectable setting records for command-center aggregation"
    )

    def __post_init__(self) -> None:
        if not 1 <= self.write_probe_max_bytes <= _PROBE_MAX:
            raise ValidationError(
                "write_probe_max_bytes must stay inside the observational bound",
                write_probe_max_bytes=self.write_probe_max_bytes,
                maximum=_PROBE_MAX,
            )
        _require_class_list(
            self.included_filesystem_classes, what="included_filesystem_classes"
        )
        _require_class_list(
            self.ignored_filesystem_classes, what="ignored_filesystem_classes"
        )
        if len(self.managed_root_candidates) > _MAX_CANDIDATES:
            raise ValidationError(
                "managed_root_candidates exceeds the observation bound",
                count=len(self.managed_root_candidates),
            )
        for candidate in self.managed_root_candidates:
            _require_path(candidate, what="managed_root_candidate")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError(
                "mount settings exceed the inspectable bound",
                count=len(self.settings),
            )
        names = tuple(item.name for item in self.settings)
        if len(set(names)) != len(names):
            raise ValidationError("mount setting names must be unique")


@contract(kind="mount.reported_capacity", version=1)
@dataclass(frozen=True, slots=True)
class ReportedCapacity(Contract):
    """Filesystem-reported totals. Not proven writable bytes and not SAFE."""

    total_bytes: Maybe[int] = meaning(
        "f_blocks * fragment size when measured; Unresolved when unknown; "
        "never rewritten as SAFE storage"
    )
    free_bytes: Maybe[int] = meaning(
        "f_bfree * fragment size when measured; includes reserved blocks; "
        "Unresolved when unknown; not Machi-usable bytes"
    )
    available_bytes: Maybe[int] = meaning(
        "f_bavail * fragment size when measured; unprivileged leftover; "
        "Unresolved when unknown; not SAFE deployable bytes"
    )
    source: CapacitySource = meaning(
        "native_stat when a platform stat succeeded; unobserved/unsupported otherwise"
    )

    def __post_init__(self) -> None:
        _require_capacity_field(self.total_bytes, what="total_bytes")
        _require_capacity_field(self.free_bytes, what="free_bytes")
        _require_capacity_field(self.available_bytes, what="available_bytes")
        if self.source is CapacitySource.NATIVE_STAT:
            return
        if is_resolved(self.total_bytes) or is_resolved(self.free_bytes):
            raise ValidationError(
                "unobserved capacity cannot carry resolved byte totals",
                source=self.source.value,
            )
        if is_resolved(self.available_bytes):
            raise ValidationError(
                "unobserved capacity cannot carry resolved available bytes",
                source=self.source.value,
            )


@contract(kind="mount.quota_evidence", version=1)
@dataclass(frozen=True, slots=True)
class QuotaEvidence(Contract):
    """Native quota/limit capture status. Not Storage Sonar and not SAFE bytes."""

    status: QuotaEvidenceStatus = meaning(
        "available when limits were read; unavailable when advertised but unread; "
        "unsupported when this component does not read them; unresolved otherwise"
    )
    hard_limit_bytes: Maybe[int] = meaning(
        "hard quota in bytes when captured; Unresolved otherwise"
    )
    soft_limit_bytes: Maybe[int] = meaning(
        "soft quota in bytes when captured; Unresolved otherwise"
    )
    usage_bytes: Maybe[int] = meaning(
        "quota usage in bytes when captured; Unresolved otherwise"
    )
    source: QuotaSource = meaning("where this quota status was established")

    def __post_init__(self) -> None:
        _require_capacity_field(self.hard_limit_bytes, what="hard_limit_bytes")
        _require_capacity_field(self.soft_limit_bytes, what="soft_limit_bytes")
        _require_capacity_field(self.usage_bytes, what="usage_bytes")
        if self.status is QuotaEvidenceStatus.AVAILABLE:
            if not isinstance(self.hard_limit_bytes, int):
                raise ValidationError("available quota requires a hard limit")
            return
        if is_resolved(self.hard_limit_bytes) or is_resolved(self.soft_limit_bytes):
            raise ValidationError("unread quota cannot carry resolved limits")
        if is_resolved(self.usage_bytes):
            raise ValidationError("unread quota cannot carry resolved usage")


@contract(kind="mount.path_capability", version=1)
@dataclass(frozen=True, slots=True)
class PathCapability(Contract):
    """Non-destructive path checks. A tiny write is not a capacity measurement."""

    path_exists: Maybe[bool] = meaning("whether the mount point existed")
    readable: Maybe[bool] = meaning("whether a read-access check succeeded")
    writable_by_access: Maybe[bool] = meaning(
        "whether a permission access check reported write; not proven usable bytes"
    )
    mount_read_only: Maybe[bool] = meaning(
        "whether the VFS options included the read-only flag"
    )
    write_probe_outcome: WriteProbeOutcome = meaning(
        "bounded observational probe result; success is not SAFE capacity"
    )
    write_probe_bytes: Maybe[int] = meaning(
        "payload size of the probe attempt; Unresolved when not attempted"
    )
    cleanup_completed: Maybe[bool] = meaning(
        "whether the probe file was removed; Unresolved when not attempted"
    )
    detail: str = meaning("bounded probe or access detail; not a customer filename")

    def __post_init__(self) -> None:
        _require_maybe_bool(self.path_exists, what="path_exists")
        _require_maybe_bool(self.readable, what="readable")
        _require_maybe_bool(self.writable_by_access, what="writable_by_access")
        _require_maybe_bool(self.mount_read_only, what="mount_read_only")
        _require_bounded(
            self.detail, what="path capability detail", maximum=_DETAIL_MAX
        )
        if self.write_probe_outcome is WriteProbeOutcome.NOT_ATTEMPTED:
            if is_resolved(self.write_probe_bytes) or is_resolved(
                self.cleanup_completed
            ):
                raise ValidationError(
                    "a probe that was not attempted cannot report bytes or cleanup"
                )
            return
        if self.write_probe_outcome is WriteProbeOutcome.SKIPPED:
            if is_resolved(self.write_probe_bytes):
                raise ValidationError("a skipped probe cannot report write bytes")
            return
        if not isinstance(self.write_probe_bytes, int):
            raise ValidationError("an attempted probe requires write_probe_bytes")
        if not 1 <= self.write_probe_bytes <= _PROBE_MAX:
            raise ValidationError(
                "write_probe_bytes must stay inside the observational bound",
                write_probe_bytes=self.write_probe_bytes,
            )
        if (
            self.write_probe_outcome is WriteProbeOutcome.SUCCEEDED
            and self.cleanup_completed is not True
        ):
            raise ValidationError("a successful probe must complete cleanup")


@contract(kind="mount.suitability", version=1)
@dataclass(frozen=True, slots=True)
class SuitabilitySignals(Contract):
    """Descriptive candidacy signals. Not deployment authority."""

    can_host_machi_state: bool = meaning("not disqualified for state by topology facts")
    can_host_runtime: bool = meaning("not disqualified for runtime by topology facts")
    can_host_model: bool = meaning("not disqualified for models by topology facts")
    can_host_cache: bool = meaning("not disqualified for cache by topology facts")
    can_host_staging: bool = meaning("not disqualified for staging by topology facts")
    can_host_telemetry: bool = meaning(
        "not disqualified for telemetry by topology facts"
    )
    reasons: tuple[SuitabilityReason, ...] = meaning(
        "evidence labels; never an admission decision"
    )

    def __post_init__(self) -> None:
        if len(self.reasons) > _MAX_REASONS:
            raise ValidationError(
                "suitability reasons exceed the observation bound",
                count=len(self.reasons),
            )
        if len(set(self.reasons)) != len(self.reasons):
            raise ValidationError("suitability reasons must be unique")


@contract(kind="mount.entry", version=1)
@dataclass(frozen=True, slots=True)
class MountEntry(Contract):
    """One visible mount/path. Not a storage pool and not a reservation."""

    mount_id: str = meaning("bounded observation identity; not a HostId")
    mount_point: str = meaning("mount point as observed in this namespace")
    source: str = meaning("device or source string as reported; empty if unobserved")
    filesystem_type: str = meaning("filesystem type token; empty if unobserved")
    mount_options: tuple[str, ...] = meaning(
        "normalized relevant options such as ro, rw, quota, fuse"
    )
    raw_options: str = meaning("bounded raw option evidence for diagnostics")
    access_mode: AccessMode = meaning("rw, ro, or unknown from VFS options")
    storage_class: StorageClass = meaning("observer classification; not a safety label")
    backing_store_id: Maybe[str] = meaning(
        "stable-enough backing identity when known; Unresolved when obscured"
    )
    device_id: Maybe[str] = meaning(
        "namespace-visible device identity when known; Unresolved otherwise"
    )
    reported_capacity: ReportedCapacity = meaning(
        "filesystem-reported totals; not proven writable and not SAFE"
    )
    quota: QuotaEvidence = meaning("native quota capture status for this mount")
    path_capability: PathCapability = meaning("existence, access, and bounded probe")
    suitability: SuitabilitySignals = meaning("descriptive candidacy; not authority")
    namespace_context: MountNamespace = meaning(
        "host, container, or unknown for this process view"
    )
    provider: str = meaning("provider identifier, for example linux or macos")
    observed_at: dt.datetime = meaning("when this entry was observed; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _require_token(self.mount_id, what="mount_id", maximum=_IDENTITY_MAX)
        _require_path(self.mount_point, what="mount_point")
        _require_bounded(self.source, what="mount source", maximum=_SOURCE_MAX)
        _require_bounded(
            self.filesystem_type, what="filesystem type", maximum=_FSTYPE_MAX
        )
        if len(self.mount_options) > _MAX_OPTIONS:
            raise ValidationError(
                "mount options exceed the observation bound",
                count=len(self.mount_options),
            )
        for option in self.mount_options:
            _require_token(option, what="mount option", maximum=_TOKEN_MAX)
        _require_bounded(self.raw_options, what="raw options", maximum=_RAW_OPTIONS_MAX)
        _require_maybe_identity(self.backing_store_id, what="backing_store_id")
        _require_maybe_identity(self.device_id, what="device_id")
        _require_token(self.provider, what="provider", maximum=_OBSERVER_MAX)


@contract(kind="mount.observation", version=1)
@dataclass(frozen=True, slots=True)
class MountObservation(Contract):
    """Mount topology visible to this process. Not HostProfile or SAFE storage.

    Reported filesystem capacity, a successful bounded write, and SAFE
    deployable capacity are different facts. This contract never computes
    the third.
    """

    entries: tuple[MountEntry, ...] = meaning(
        "observed mounts in table order; empty when unobserved"
    )
    settings: MountObservationSettings = meaning("typed inspectable 2.4 settings")
    status: ObservationStatus = meaning(
        "normalized when the mount table was read; unobserved otherwise"
    )
    os_family: Maybe[OSFamily] = meaning(
        "OS family used to select a provider; Unresolved when unobserved"
    )
    namespace_context: MountNamespace = meaning(
        "filesystem namespace this process observed"
    )
    invalid_record_count: int = meaning("malformed mount-table rows skipped")
    truncated_entry_count: int = meaning("valid rows omitted after the entry bound")
    provider: str = meaning("selected provider, or native when none applied")
    observer: str = meaning("adapter identifier, for example native")
    observed_at: dt.datetime = meaning(
        "when this observation was taken; timezone-aware UTC; never rewritten"
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _require_token(self.observer, what="observer", maximum=_OBSERVER_MAX)
        _require_token(self.provider, what="provider", maximum=_OBSERVER_MAX)
        if len(self.entries) > _MAX_ENTRIES:
            raise ValidationError(
                "mount observation exceeds the entry bound",
                count=len(self.entries),
            )
        if self.invalid_record_count < 0 or self.truncated_entry_count < 0:
            raise ValidationError("mount record counts must not be negative")
        ids = tuple(entry.mount_id for entry in self.entries)
        if len(set(ids)) != len(ids):
            raise ValidationError("mount_id values must be unique in one observation")
        if self.status is ObservationStatus.NORMALIZED:
            if not is_resolved(self.os_family):
                raise ValidationError(
                    "normalized mount observation requires a resolved OS family"
                )
            return
        if self.status is not ObservationStatus.UNOBSERVED:
            raise ValidationError(
                "mount status must be normalized or unobserved",
                status=self.status.value,
            )
        if self.entries:
            raise ValidationError("unobserved mount observation cannot list entries")


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
        raise ValidationError(f"{what} must be a path-free token", what=what)


def _require_bounded(value: str, *, what: str, maximum: int) -> None:
    if not isinstance(value, str):
        raise ValidationError(
            f"{what} must be a string",
            what=what,
            actual_type=type(value).__name__,
        )
    if len(value) > maximum:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=maximum,
            length=len(value),
        )


def _require_path(value: str, *, what: str) -> None:
    if not value:
        raise ValidationError(f"{what} is required", what=what)
    if "\x00" in value:
        raise ValidationError(f"{what} must not contain a NUL", what=what)
    if len(value) > _PATH_MAX:
        raise ValidationError(
            f"{what} is too long",
            what=what,
            maximum=_PATH_MAX,
            length=len(value),
        )


def _require_class_list(values: tuple[StorageClass, ...], *, what: str) -> None:
    if not values:
        raise ValidationError(f"{what} must not be empty", what=what)
    if len(set(values)) != len(values):
        raise ValidationError(f"{what} must not contain duplicates", what=what)


def _require_maybe_bool(value: object, *, what: str) -> None:
    if isinstance(value, (Unresolved, bool)):
        return
    raise ValidationError(f"{what} must be a boolean or Unresolved", what=what)


def _require_maybe_identity(value: object, *, what: str) -> None:
    if isinstance(value, Unresolved):
        return
    if not isinstance(value, str):
        raise ValidationError(f"{what} must be a token or Unresolved", what=what)
    _require_token(value, what=what, maximum=_IDENTITY_MAX)


def _require_capacity_field(value: object, *, what: str) -> None:
    if isinstance(value, Unresolved):
        return
    if not isinstance(value, int):
        raise ValidationError(f"{what} must be an integer or Unresolved", what=what)
    if value < 0:
        raise ValidationError(f"{what} must not be negative", what=what, value=value)
    if value > _CAPACITY_MAX:
        raise ValidationError(
            f"{what} exceeds the observation bound",
            what=what,
            value=value,
        )
