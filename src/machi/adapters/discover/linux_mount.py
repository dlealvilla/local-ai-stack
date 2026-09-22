"""Linux filesystem/mount provider (MACHI 2.4.1).

Reads the process mount table and native stat results. Domain owns
``MountObservation``. This module owns Linux parsing and classification.
It does not compute SAFE storage, walk customer trees, or change mounts.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from machi.adapters.discover.mount_probe import bounded_write_probe
from machi.discover.contracts import OSFamily
from machi.discover.mount_contracts import (
    AccessMode,
    MountEntry,
    MountNamespace,
    MountObservation,
    MountObservationSettings,
    PathCapability,
    QuotaEvidence,
    ReportedCapacity,
    StorageClass,
    WriteProbeOutcome,
    WriteProbePolicy,
)
from machi.discover.mounts import (
    MAX_MOUNT_ENTRIES,
    advertised_unread_quota,
    measured_capacity,
    mount_observation,
    skipped_path_capability,
    suitability_signals,
    unobserved_capacity,
    unobserved_mount_observation,
    unsupported_quota,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import InternalError, ValidationError
from machi.kernel.unresolved import (
    NOT_MEASURED,
    Maybe,
    Unresolved,
    UnresolvedReason,
)

LINUX_PROVIDER = "linux"
_MOUNT_TABLE = Path("/proc/self/mountinfo")
_DOCKERENV = Path("/.dockerenv")
_CONTAINERENV = Path("/run/.containerenv")
_KNOWN_OPTIONS = frozenset(
    {
        "ro",
        "rw",
        "nosuid",
        "nodev",
        "noexec",
        "relatime",
        "noatime",
        "strictatime",
        "quota",
        "usrquota",
        "grpquota",
        "prjquota",
        "usrjquota",
        "grpjquota",
        "overlay",
        "fuse",
        "bind",
        "rbind",
        "rprivate",
        "rshared",
        "private",
        "shared",
        "slave",
        "rslave",
        "unbindable",
        "runbindable",
    }
)
_QUOTA_OPTIONS = frozenset(
    {
        "quota",
        "usrquota",
        "grpquota",
        "prjquota",
        "usrjquota",
        "grpjquota",
    }
)
_PSEUDO_TYPES = frozenset(
    {
        "proc",
        "sysfs",
        "devtmpfs",
        "devfs",
        "securityfs",
        "debugfs",
        "tracefs",
        "pstore",
        "bpf",
        "nsfs",
        "configfs",
        "fusectl",
        "mqueue",
        "rpc_pipefs",
        "binfmt_misc",
        "autofs",
        "cgroup",
        "cgroup2",
        "hugetlbfs",
        "efivarfs",
        "selinuxfs",
        "ramfs",
        "devpts",
    }
)
_NETWORK_TYPES = frozenset(
    {
        "nfs",
        "nfs4",
        "cifs",
        "smb3",
        "smbfs",
        "fuse.sshfs",
        "fuse.nfs",
        "9p",
        "ceph",
        "glusterfs",
        "lustre",
        "afs",
        "fuse.rclone",
        "fuse.s3fs",
    }
)
_OVERLAY_TYPES = frozenset({"overlay", "overlay2"})
_TMPFS_TYPES = frozenset({"tmpfs"})
_PHYSICAL_TYPES = frozenset(
    {
        "ext4",
        "ext3",
        "ext2",
        "xfs",
        "btrfs",
        "f2fs",
        "zfs",
        "vfat",
        "msdos",
        "ntfs",
        "ntfs3",
        "erofs",
        "jfs",
        "reiserfs",
        "nilfs2",
        "ufs",
        "apfs",
    }
)


class StatVfsResult(Protocol):
    """Narrow filesystem-stat shape used by the Linux provider."""

    f_frsize: int
    f_bsize: int
    f_blocks: int
    f_bfree: int
    f_bavail: int


StatVfs = Callable[[str], StatVfsResult]
AccessFn = Callable[[str, int], bool]
ExistsFn = Callable[[str], bool]
ProbeFn = Callable[[str, int], tuple[WriteProbeOutcome, Maybe[int], Maybe[bool], str]]


@dataclass(frozen=True, slots=True)
class LinuxMountRecord:
    """One parsed Linux mount-table row. Adapter-local, not a product contract."""

    table_id: str
    major: str
    minor: str
    mount_point: str
    vfs_options: str
    filesystem_type: str
    source: str
    super_options: str


def unescape_mount_field(text: str) -> str:
    """Decode octal escapes used in the Linux mount table."""
    if not isinstance(text, str):
        raise ValidationError(
            "mount field must be text",
            actual_type=type(text).__name__,
        )
    out: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\\" and index + 3 < len(text):
            digits = text[index + 1 : index + 4]
            if all(char in "01234567" for char in digits):
                out.append(chr(int(digits, 8)))
                index += 4
                continue
        out.append(text[index])
        index += 1
    return "".join(out)


def parse_linux_mountinfo(text: str) -> tuple[tuple[LinuxMountRecord, ...], int]:
    """Parse a Linux mountinfo document. Invalid rows are counted, not invented."""
    if not isinstance(text, str):
        raise ValidationError(
            "Linux mount table must be text",
            actual_type=type(text).__name__,
        )
    records: list[LinuxMountRecord] = []
    invalid = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_mountinfo_line(line)
        if parsed is None:
            invalid += 1
            continue
        records.append(parsed)
    return tuple(records), invalid


def classify_linux_filesystem(
    filesystem_type: str,
    source: str,
    options: tuple[str, ...],
) -> StorageClass:
    """Classify a Linux filesystem. Classification is not a safety decision."""
    fstype = filesystem_type.lower()
    if fstype in _PSEUDO_TYPES:
        return StorageClass.PSEUDO
    if fstype in _OVERLAY_TYPES or "overlay" in options:
        return StorageClass.OVERLAY
    if fstype in _NETWORK_TYPES or fstype.startswith("nfs"):
        return StorageClass.NETWORK
    if fstype in _TMPFS_TYPES:
        return StorageClass.TMPFS
    if fstype.startswith("fuse.") and fstype in _NETWORK_TYPES:
        return StorageClass.NETWORK
    if source.startswith(("/dev/loop", "/dev/nbd")):
        return StorageClass.LOCAL_VIRTUAL
    if fstype.startswith("fuse"):
        return StorageClass.LOCAL_VIRTUAL
    if fstype in _PHYSICAL_TYPES:
        return StorageClass.LOCAL_PHYSICAL
    if fstype.startswith("fuse."):
        return StorageClass.UNKNOWN
    return StorageClass.UNKNOWN


def normalize_mount_options(*option_strings: str) -> tuple[str, ...]:
    """Keep relevant option tokens; drop huge opaque values."""
    found: list[str] = []
    for blob in option_strings:
        for token in blob.split(","):
            name = token.strip().split("=", 1)[0]
            if name in _KNOWN_OPTIONS and name not in found:
                found.append(name)
    return tuple(found)


def linux_quota_evidence(options: tuple[str, ...]) -> QuotaEvidence:
    """Advertised quota options are not read limits."""
    if any(option in _QUOTA_OPTIONS for option in options):
        return advertised_unread_quota()
    return unsupported_quota()


class LinuxMountProvider:
    """Observe Linux mount topology from the process mount table."""

    provider_id = LINUX_PROVIDER

    def __init__(
        self,
        *,
        mountinfo_text: str | None = None,
        mountinfo_path: Path | None = None,
        statvfs: StatVfs | None = None,
        access: AccessFn | None = None,
        exists: ExistsFn | None = None,
        probe: ProbeFn | None = None,
        dockerenv_path: Path | None = None,
        containerenv_path: Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._mountinfo_text = mountinfo_text
        self._mountinfo_path = mountinfo_path
        self._statvfs = statvfs
        self._access = access
        self._exists = exists
        self._probe = probe
        self._dockerenv_path = dockerenv_path
        self._containerenv_path = containerenv_path
        self._clock = clock or SystemClock()

    def observe(
        self,
        settings: MountObservationSettings,
        when: dt.datetime | None = None,
    ) -> MountObservation:
        """Read the mount table. Missing table is unobserved, never zero SAFE."""
        observed_at = when if when is not None else self._clock.now()
        text = self._mountinfo_text
        if text is None:
            path = self._mountinfo_path or _MOUNT_TABLE
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                return unobserved_mount_observation(
                    settings=settings,
                    reason=UnresolvedReason.NOT_MEASURED,
                    detail="Linux mount table was not present",
                    os_family=OSFamily.LINUX,
                    provider=self.provider_id,
                    observed_at=observed_at,
                )
            except PermissionError:
                return unobserved_mount_observation(
                    settings=settings,
                    reason=UnresolvedReason.NOT_MEASURED,
                    detail="Linux mount table was not readable",
                    os_family=OSFamily.LINUX,
                    provider=self.provider_id,
                    observed_at=observed_at,
                )
            except OSError as exc:
                raise InternalError("failed to observe Linux mounts") from exc
        records, invalid = parse_linux_mountinfo(text)
        namespace = self._namespace(records)
        entries: list[MountEntry] = []
        seen_ids: dict[str, int] = {}
        truncated = 0
        for record in records:
            if len(entries) >= MAX_MOUNT_ENTRIES:
                truncated += 1
                continue
            mount_id = _unique_mount_id(record.table_id, seen_ids)
            entries.append(
                self._entry(
                    record,
                    mount_id=mount_id,
                    settings=settings,
                    namespace=namespace,
                    observed_at=observed_at,
                )
            )
        return mount_observation(
            entries=tuple(entries),
            settings=settings,
            os_family=OSFamily.LINUX,
            namespace_context=namespace,
            invalid_record_count=invalid,
            truncated_entry_count=truncated,
            provider=self.provider_id,
            observed_at=observed_at,
        )

    def _namespace(self, records: tuple[LinuxMountRecord, ...]) -> MountNamespace:
        dockerenv = self._dockerenv_path or _DOCKERENV
        containerenv = self._containerenv_path or _CONTAINERENV
        if dockerenv.exists() or containerenv.exists():
            return MountNamespace.CONTAINER
        for record in records:
            if record.mount_point == "/" and record.filesystem_type.lower() in (
                _OVERLAY_TYPES
            ):
                return MountNamespace.CONTAINER
        return MountNamespace.HOST

    def _entry(
        self,
        record: LinuxMountRecord,
        *,
        mount_id: str,
        settings: MountObservationSettings,
        namespace: MountNamespace,
        observed_at: dt.datetime,
    ) -> MountEntry:
        options = normalize_mount_options(record.vfs_options, record.super_options)
        if record.filesystem_type.lower().startswith("fuse") and "fuse" not in options:
            options = (*options, "fuse")
        storage_class = classify_linux_filesystem(
            record.filesystem_type, record.source, options
        )
        access_mode = _access_mode(record.vfs_options)
        device_id = _device_identity(record.major, record.minor)
        backing = device_id
        quota = linux_quota_evidence(options)
        capacity = self._capacity(record.mount_point)
        capability = self._capability(
            record.mount_point,
            access_mode=access_mode,
            storage_class=storage_class,
            settings=settings,
        )
        suitability = suitability_signals(
            storage_class=storage_class,
            access_mode=access_mode,
            path_capability=capability,
            settings=settings,
            backing_store_id=backing,
        )
        return MountEntry(
            mount_id=mount_id,
            mount_point=record.mount_point,
            source=_bound(record.source, 256),
            filesystem_type=_bound(record.filesystem_type, 64),
            mount_options=options,
            raw_options=_bound(record.vfs_options, 240),
            access_mode=access_mode,
            storage_class=storage_class,
            backing_store_id=backing,
            device_id=device_id,
            reported_capacity=capacity,
            quota=quota,
            path_capability=capability,
            suitability=suitability,
            namespace_context=namespace,
            provider=self.provider_id,
            observed_at=observed_at,
        )

    def _capacity(self, mount_point: str) -> ReportedCapacity:
        reader = self._statvfs or os.statvfs
        try:
            result = reader(mount_point)
        except OSError:
            return unobserved_capacity()
        fragment = int(result.f_frsize or result.f_bsize or 0)
        if fragment <= 0:
            return unobserved_capacity()
        return measured_capacity(
            total_bytes=fragment * int(result.f_blocks),
            free_bytes=fragment * int(result.f_bfree),
            available_bytes=fragment * int(result.f_bavail),
        )

    def _capability(
        self,
        mount_point: str,
        *,
        access_mode: AccessMode,
        storage_class: StorageClass,
        settings: MountObservationSettings,
    ) -> PathCapability:
        exists_fn = self._exists or (lambda path: Path(path).exists())
        access_fn = self._access or os.access
        try:
            exists = bool(exists_fn(mount_point))
        except OSError:
            return skipped_path_capability(
                path_exists=NOT_MEASURED,
                readable=NOT_MEASURED,
                writable_by_access=NOT_MEASURED,
                mount_read_only=access_mode is AccessMode.READ_ONLY,
                detail="path existence could not be determined",
            )
        try:
            readable: Maybe[bool]
            writable: Maybe[bool]
            readable = bool(access_fn(mount_point, os.R_OK)) if exists else False
            writable = bool(access_fn(mount_point, os.W_OK)) if exists else False
        except OSError:
            readable = NOT_MEASURED
            writable = NOT_MEASURED
        read_only = access_mode is AccessMode.READ_ONLY
        skip_probe = (
            settings.write_probe_policy is WriteProbePolicy.DISABLED
            or storage_class in settings.ignored_filesystem_classes
            or read_only
            or exists is False
            or writable is not True
        )
        if skip_probe:
            detail = ""
            outcome = WriteProbeOutcome.NOT_ATTEMPTED
            if settings.write_probe_policy is WriteProbePolicy.BOUNDED and skip_probe:
                outcome = WriteProbeOutcome.SKIPPED
                detail = "bounded write probe skipped"
            return PathCapability(
                path_exists=exists,
                readable=readable,
                writable_by_access=writable,
                mount_read_only=read_only,
                write_probe_outcome=outcome,
                write_probe_bytes=NOT_MEASURED,
                cleanup_completed=NOT_MEASURED,
                detail=detail,
            )
        probe = self._probe or bounded_write_probe
        outcome, nbytes, cleaned, detail = probe(
            mount_point, settings.write_probe_max_bytes
        )
        return PathCapability(
            path_exists=exists,
            readable=readable,
            writable_by_access=writable,
            mount_read_only=read_only,
            write_probe_outcome=outcome,
            write_probe_bytes=nbytes,
            cleanup_completed=cleaned,
            detail=detail,
        )


def _parse_mountinfo_line(line: str) -> LinuxMountRecord | None:
    parts = line.split()
    if len(parts) < 10:
        return None
    try:
        separator = parts.index("-")
    except ValueError:
        return None
    if separator < 6 or len(parts) < separator + 4:
        return None
    table_id, _parent, device = parts[0], parts[1], parts[2]
    if not table_id.isdigit() or ":" not in device:
        return None
    major, minor = device.split(":", 1)
    if not major.isdigit() or not minor.isdigit():
        return None
    mount_point = unescape_mount_field(parts[4])
    vfs_options = parts[5]
    filesystem_type = parts[separator + 1]
    source = unescape_mount_field(parts[separator + 2])
    super_options = parts[separator + 3] if len(parts) > separator + 3 else ""
    if not mount_point or not filesystem_type:
        return None
    return LinuxMountRecord(
        table_id=table_id,
        major=major,
        minor=minor,
        mount_point=mount_point,
        vfs_options=vfs_options,
        filesystem_type=filesystem_type,
        source=source,
        super_options=super_options,
    )


def _unique_mount_id(table_id: str, seen: dict[str, int]) -> str:
    count = seen.get(table_id, 0)
    seen[table_id] = count + 1
    if count == 0:
        return f"mnt:{table_id}"
    return f"mnt:{table_id}-{count}"


def _access_mode(vfs_options: str) -> AccessMode:
    tokens = {token.strip() for token in vfs_options.split(",")}
    if "ro" in tokens:
        return AccessMode.READ_ONLY
    if "rw" in tokens:
        return AccessMode.READ_WRITE
    return AccessMode.UNKNOWN


def _device_identity(major: str, minor: str) -> Maybe[str]:
    if major == "0" and minor == "0":
        return Unresolved(
            UnresolvedReason.INCONCLUSIVE,
            "device identity 0:0 does not identify backing storage",
        )
    return f"dev:{major}:{minor}"


def _bound(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return value[: maximum - 3] + "..."
