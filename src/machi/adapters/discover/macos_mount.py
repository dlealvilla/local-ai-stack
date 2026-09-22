"""macOS filesystem/mount provider (MACHI 2.4.1).

Reads native mount statistics. Domain owns ``MountObservation``.
This module owns Darwin classification. It does not compute SAFE storage,
walk customer trees, or change mounts.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import datetime as dt
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from machi.adapters.discover.mount_probe import bounded_write_probe
from machi.discover.contracts import OSFamily
from machi.discover.mount_contracts import (
    AccessMode,
    MountEntry,
    MountNamespace,
    MountObservation,
    MountObservationSettings,
    PathCapability,
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
from machi.kernel.errors import InternalError
from machi.kernel.unresolved import (
    NOT_MEASURED,
    Maybe,
    Unresolved,
    UnresolvedReason,
)

MACOS_PROVIDER = "macos"
MNT_RDONLY = 0x00000001
MNT_NOWAIT = 2
_MFSTYPENAMELEN = 16
_MAXPATHLEN = 1024
_DOCKERENV = Path("/.dockerenv")
_PSEUDO_TYPES = frozenset({"devfs", "autofs", "synthfs", "volfs", "fdesc"})
_NETWORK_TYPES = frozenset({"nfs", "smbfs", "afpfs", "webdav", "ftp", "afp"})
_TMPFS_TYPES = frozenset({"tmpfs"})
_PHYSICAL_TYPES = frozenset(
    {"apfs", "hfs", "hfsx", "msdos", "exfat", "ntfs", "ufs", "cd9660"}
)
AccessFn = Callable[[str, int], bool]
ExistsFn = Callable[[str], bool]
ProbeFn = Callable[[str, int], tuple[WriteProbeOutcome, Maybe[int], Maybe[bool], str]]


class _Statfs(ctypes.Structure):
    _fields_ = [
        ("f_bsize", ctypes.c_uint32),
        ("f_iosize", ctypes.c_int32),
        ("f_blocks", ctypes.c_uint64),
        ("f_bfree", ctypes.c_uint64),
        ("f_bavail", ctypes.c_uint64),
        ("f_files", ctypes.c_uint64),
        ("f_ffree", ctypes.c_uint64),
        ("f_fsid", ctypes.c_int32 * 2),
        ("f_owner", ctypes.c_uint32),
        ("f_type", ctypes.c_uint32),
        ("f_flags", ctypes.c_uint32),
        ("f_fssubtype", ctypes.c_uint32),
        ("f_fstypename", ctypes.c_char * _MFSTYPENAMELEN),
        ("f_mntonname", ctypes.c_char * _MAXPATHLEN),
        ("f_mntfromname", ctypes.c_char * _MAXPATHLEN),
        ("f_flags_ext", ctypes.c_uint32),
        ("f_reserved", ctypes.c_uint32 * 7),
    ]


@dataclass(frozen=True, slots=True)
class MacOSMountRecord:
    """One Darwin mount. Adapter-local, not a product contract."""

    mount_point: str
    source: str
    filesystem_type: str
    flags: int
    block_size: int
    blocks: int
    bfree: int
    bavail: int
    fsid_a: int
    fsid_b: int


def classify_darwin_filesystem(filesystem_type: str) -> StorageClass:
    """Classify a Darwin filesystem. Classification is not a safety decision."""
    fstype = filesystem_type.lower()
    if fstype in _PSEUDO_TYPES:
        return StorageClass.PSEUDO
    if fstype in _NETWORK_TYPES or fstype.startswith("nfs"):
        return StorageClass.NETWORK
    if fstype in _TMPFS_TYPES:
        return StorageClass.TMPFS
    if fstype in _PHYSICAL_TYPES:
        return StorageClass.LOCAL_PHYSICAL
    if fstype.startswith("fuse"):
        return StorageClass.LOCAL_VIRTUAL
    return StorageClass.UNKNOWN


def read_native_statfs() -> tuple[MacOSMountRecord, ...]:
    """Enumerate mounts through getfsstat. Does not shell out."""
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        raise InternalError("Darwin libc was not available for mount observation")
    libc = ctypes.CDLL(libc_name, use_errno=True)
    getfsstat = libc.getfsstat
    getfsstat.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    getfsstat.restype = ctypes.c_int
    count = getfsstat(None, 0, MNT_NOWAIT)
    if count < 0:
        raise InternalError("getfsstat failed while counting mounts")
    if count == 0:
        return ()
    buf = (_Statfs * count)()
    filled = getfsstat(ctypes.byref(buf), ctypes.sizeof(buf), MNT_NOWAIT)
    if filled < 0:
        raise InternalError("getfsstat failed while reading mounts")
    records: list[MacOSMountRecord] = []
    for index in range(filled):
        row = buf[index]
        records.append(
            MacOSMountRecord(
                mount_point=_cstring(row.f_mntonname),
                source=_cstring(row.f_mntfromname),
                filesystem_type=_cstring(row.f_fstypename),
                flags=int(row.f_flags),
                block_size=int(row.f_bsize),
                blocks=int(row.f_blocks),
                bfree=int(row.f_bfree),
                bavail=int(row.f_bavail),
                fsid_a=int(row.f_fsid[0]),
                fsid_b=int(row.f_fsid[1]),
            )
        )
    return tuple(records)


class MacOSMountProvider:
    """Observe macOS mount topology from native mount statistics."""

    provider_id = MACOS_PROVIDER

    def __init__(
        self,
        *,
        records: Sequence[MacOSMountRecord] | None = None,
        access: AccessFn | None = None,
        exists: ExistsFn | None = None,
        probe: ProbeFn | None = None,
        dockerenv_path: Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._records = None if records is None else tuple(records)
        self._access = access
        self._exists = exists
        self._probe = probe
        self._dockerenv_path = dockerenv_path
        self._clock = clock or SystemClock()

    def observe(
        self,
        settings: MountObservationSettings,
        when: dt.datetime | None = None,
    ) -> MountObservation:
        """Read Darwin mounts. Failure to enumerate is unobserved, never zero SAFE."""
        observed_at = when if when is not None else self._clock.now()
        try:
            records = (
                self._records if self._records is not None else read_native_statfs()
            )
        except InternalError:
            raise
        except OSError as exc:
            raise InternalError("failed to observe macOS mounts") from exc
        if not records:
            return unobserved_mount_observation(
                settings=settings,
                reason=UnresolvedReason.NOT_MEASURED,
                detail="macOS mount table was empty",
                os_family=OSFamily.MACOS,
                provider=self.provider_id,
                observed_at=observed_at,
            )
        namespace = self._namespace()
        entries: list[MountEntry] = []
        truncated = 0
        for index, record in enumerate(records):
            if not record.mount_point or not record.filesystem_type:
                continue
            if len(entries) >= MAX_MOUNT_ENTRIES:
                truncated += 1
                continue
            entries.append(
                self._entry(
                    record,
                    ordinal=index,
                    settings=settings,
                    namespace=namespace,
                    observed_at=observed_at,
                )
            )
        if not entries:
            return unobserved_mount_observation(
                settings=settings,
                reason=UnresolvedReason.NOT_MEASURED,
                detail="macOS mount rows were not usable",
                os_family=OSFamily.MACOS,
                provider=self.provider_id,
                observed_at=observed_at,
            )
        return mount_observation(
            entries=tuple(entries),
            settings=settings,
            os_family=OSFamily.MACOS,
            namespace_context=namespace,
            invalid_record_count=0,
            truncated_entry_count=truncated,
            provider=self.provider_id,
            observed_at=observed_at,
        )

    def _namespace(self) -> MountNamespace:
        dockerenv = self._dockerenv_path or _DOCKERENV
        if dockerenv.exists():
            return MountNamespace.CONTAINER
        return MountNamespace.HOST

    def _entry(
        self,
        record: MacOSMountRecord,
        *,
        ordinal: int,
        settings: MountObservationSettings,
        namespace: MountNamespace,
        observed_at: dt.datetime,
    ) -> MountEntry:
        storage_class = classify_darwin_filesystem(record.filesystem_type)
        read_only = bool(record.flags & MNT_RDONLY)
        access_mode = AccessMode.READ_ONLY if read_only else AccessMode.READ_WRITE
        options = ("ro",) if read_only else ("rw",)
        backing = _fsid_identity(record.fsid_a, record.fsid_b)
        quota = (
            advertised_unread_quota()
            if "quota" in record.filesystem_type.lower()
            else unsupported_quota()
        )
        capacity = _capacity_from_record(record)
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
            mount_id=f"mnt:{ordinal}",
            mount_point=record.mount_point,
            source=_bound(record.source, 256),
            filesystem_type=_bound(record.filesystem_type, 64),
            mount_options=options,
            raw_options=f"flags={record.flags}",
            access_mode=access_mode,
            storage_class=storage_class,
            backing_store_id=backing,
            device_id=backing,
            reported_capacity=capacity,
            quota=quota,
            path_capability=capability,
            suitability=suitability,
            namespace_context=namespace,
            provider=self.provider_id,
            observed_at=observed_at,
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
            outcome = WriteProbeOutcome.NOT_ATTEMPTED
            detail = ""
            if settings.write_probe_policy is WriteProbePolicy.BOUNDED:
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


def _capacity_from_record(record: MacOSMountRecord) -> ReportedCapacity:
    if record.block_size <= 0:
        return unobserved_capacity()
    return measured_capacity(
        total_bytes=record.block_size * record.blocks,
        free_bytes=record.block_size * record.bfree,
        available_bytes=record.block_size * record.bavail,
    )


def _fsid_identity(fsid_a: int, fsid_b: int) -> Maybe[str]:
    if fsid_a == 0 and fsid_b == 0:
        return Unresolved(
            UnresolvedReason.INCONCLUSIVE,
            "filesystem identifier was zero",
        )
    return f"fsid:{fsid_a}:{fsid_b}"


def _cstring(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def _bound(value: str, maximum: int) -> str:
    if len(value) <= maximum:
        return value
    return value[: maximum - 3] + "..."
