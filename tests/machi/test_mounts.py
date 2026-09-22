"""Mount observer (MACHI 2.4.1)."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pytest

from machi.adapters.discover.linux_mount import (
    LinuxMountProvider,
    ProbeFn,
    classify_linux_filesystem,
    parse_linux_mountinfo,
    unescape_mount_field,
)
from machi.adapters.discover.macos_mount import (
    MacOSMountProvider,
    MacOSMountRecord,
    classify_darwin_filesystem,
)
from machi.adapters.discover.mount_probe import PROBE_PREFIX, bounded_write_probe
from machi.adapters.discover.native_mount import NativeMountObserver
from machi.discover.contracts import (
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
)
from machi.discover.events import MOUNT_OBSERVED_TYPE, mounts_observed
from machi.discover.mount_contracts import (
    AccessMode,
    CapacitySource,
    MountEntry,
    MountObservation,
    QuotaEvidenceStatus,
    StorageClass,
    SuitabilityReason,
    WriteProbeOutcome,
    WriteProbePolicy,
)
from machi.discover.mounts import default_mount_settings
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import MountObserver
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import from_dict, to_dict, unresolved_fields
from machi.kernel.unresolved import is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 22, 4, 0, tzinfo=dt.UTC)
LINUX_TABLE = """\
22 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw,errors=remount-ro
23 22 0:21 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw
24 22 0:22 / /sys rw,nosuid,nodev,noexec,relatime - sysfs sysfs rw
36 22 0:45 / /overlay rw,relatime - overlay overlay rw,lowerdir=/a,upperdir=/b
40 22 0:46 / /nfs rw,relatime - nfs4 10.0.0.1:/export rw
41 22 8:1 /home /home rw,relatime - ext4 /dev/sda1 rw
42 22 8:2 / /mnt/ro ro,relatime - ext4 /dev/sdb1 ro
43 22 0:0 / /mystery rw - mysteryfs mystery rw
not a valid mount record
44 22 8:1 / /dup rw - ext4 /dev/sda1 rw
22 22 8:3 / /dup-id rw - ext4 /dev/sdc1 rw
45 22 8:4 / /mnt/data\\040dir rw - ext4 /dev/sdd1 rw,usrquota
46 22 0:23 / /tmp rw,nosuid,nodev - tmpfs tmpfs rw
47 22 8:5 / /locked rw - ext4 /dev/sde1 rw
"""


class _FixedOS:
    def __init__(self, raw_os: str, raw_arch: str = "x86_64") -> None:
        self._raw_os = raw_os
        self._raw_arch = raw_arch

    def observe(self) -> OSArchitectureObservation:
        return normalize_os_architecture(
            self._raw_os, self._raw_arch, observed_at=FIXED
        )


class _VFS:
    def __init__(self, frsize: int, blocks: int, bfree: int, bavail: int) -> None:
        self.f_frsize = frsize
        self.f_bsize = frsize
        self.f_blocks = blocks
        self.f_bfree = bfree
        self.f_bavail = bavail


_VFS_MAP = {
    "/": _VFS(4096, 1_000_000, 400_000, 300_000),
    "/home": _VFS(4096, 1_000_000, 400_000, 300_000),
    "/dup": _VFS(4096, 1_000_000, 400_000, 300_000),
    "/mnt/ro": _VFS(4096, 200_000, 100_000, 50_000),
    "/overlay": _VFS(4096, 50_000, 20_000, 10_000),
    "/nfs": _VFS(4096, 80_000, 30_000, 25_000),
    "/proc": _VFS(4096, 0, 0, 0),
    "/sys": _VFS(4096, 0, 0, 0),
    "/dup-id": _VFS(4096, 10, 5, 4),
    "/mnt/data dir": _VFS(4096, 100, 40, 30),
    "/tmp": _VFS(4096, 1_000, 800, 700),
    "/locked": _VFS(4096, 10, 5, 4),
}


def _statvfs(path: str) -> _VFS:
    if path == "/mystery":
        raise OSError("stat failed")
    try:
        return _VFS_MAP[path]
    except KeyError as exc:
        raise OSError("missing") from exc


def _exists(path: str) -> bool:
    return path != "/locked"


def _access(path: str, mode: int) -> bool:
    return not (path == "/locked" or (path == "/mnt/ro" and mode == os.W_OK))


def _linux_observer(
    *,
    clock: FixedClock,
    write_probe_policy: WriteProbePolicy = WriteProbePolicy.DISABLED,
    probe: ProbeFn | None = None,
) -> NativeMountObserver:
    linux = LinuxMountProvider(
        mountinfo_text=LINUX_TABLE,
        statvfs=_statvfs,
        exists=_exists,
        access=_access,
        probe=probe,
        dockerenv_path=Path("/nonexistent-dockerenv"),
        containerenv_path=Path("/nonexistent-containerenv"),
        clock=clock,
    )
    return NativeMountObserver(
        os_observer=_FixedOS("Linux"),
        write_probe_policy=(
            None
            if write_probe_policy is WriteProbePolicy.DISABLED
            else write_probe_policy
        ),
        linux_provider=linux,
        clock=clock,
    )


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


def _by_point(observation: MountObservation) -> dict[str, MountEntry]:
    return {entry.mount_point: entry for entry in observation.entries}


def test_native_observer_satisfies_the_port(clock: FixedClock) -> None:
    observer = NativeMountObserver(clock=clock)
    assert isinstance(observer, MountObserver)


def test_native_adapter_observes_the_current_host(clock: FixedClock) -> None:
    observed = NativeMountObserver(clock=clock).observe()
    assert observed.observer == "native"
    assert observed.observed_at == FIXED
    assert observed.status is ObservationStatus.NORMALIZED
    assert observed.entries
    root = next(entry for entry in observed.entries if entry.mount_point == "/")
    assert is_resolved(root.reported_capacity.total_bytes)
    assert is_resolved(root.reported_capacity.free_bytes)
    assert is_resolved(root.reported_capacity.available_bytes)
    document = to_dict(observed)
    assert "safe_storage_bytes" not in json.dumps(document)
    host = __import__("platform").system()
    if host == "Darwin":
        assert observed.provider == "macos"
        assert observed.os_family is OSFamily.MACOS
        assert root.storage_class is StorageClass.LOCAL_PHYSICAL
        return
    if host == "Linux":
        assert observed.provider == "linux"
        assert observed.os_family is OSFamily.LINUX
        return
    pytest.fail(f"native mount test has no harness truth for {host}")


def test_linux_local_rw_filesystem(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    root = _by_point(observed)["/"]
    assert root.filesystem_type == "ext4"
    assert root.access_mode is AccessMode.READ_WRITE
    assert root.storage_class is StorageClass.LOCAL_PHYSICAL
    assert root.backing_store_id == "dev:8:1"
    assert root.suitability.can_host_model is True
    assert SuitabilityReason.PSEUDO_FILESYSTEM not in root.suitability.reasons


def test_linux_read_only_filesystem(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    ro = _by_point(observed)["/mnt/ro"]
    assert ro.access_mode is AccessMode.READ_ONLY
    assert ro.path_capability.mount_read_only is True
    assert ro.suitability.can_host_model is False
    assert SuitabilityReason.READ_ONLY in ro.suitability.reasons


def test_linux_pseudo_filesystem_is_topology_not_candidate(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    proc = _by_point(observed)["/proc"]
    assert proc.storage_class is StorageClass.PSEUDO
    assert proc.suitability.can_host_machi_state is False
    assert SuitabilityReason.PSEUDO_FILESYSTEM in proc.suitability.reasons
    assert SuitabilityReason.CLASS_IGNORED in proc.suitability.reasons


def test_linux_overlay_filesystem(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    overlay = _by_point(observed)["/overlay"]
    assert overlay.storage_class is StorageClass.OVERLAY
    assert overlay.suitability.can_host_model is True
    assert SuitabilityReason.OVERLAY_STORAGE in overlay.suitability.reasons


def test_linux_network_filesystem(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    nfs = _by_point(observed)["/nfs"]
    assert nfs.storage_class is StorageClass.NETWORK
    assert nfs.suitability.can_host_model is True
    assert SuitabilityReason.NETWORK_STORAGE in nfs.suitability.reasons


def test_shared_backing_identity(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    points = _by_point(observed)
    assert points["/"].backing_store_id == points["/home"].backing_store_id
    assert points["/"].backing_store_id == points["/dup"].backing_store_id
    assert points["/"].backing_store_id != points["/mnt/ro"].backing_store_id


def test_unresolved_backing_identity(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    mystery = _by_point(observed)["/mystery"]
    assert not is_resolved(mystery.backing_store_id)
    assert SuitabilityReason.UNKNOWN_BACKING in mystery.suitability.reasons
    assert not is_resolved(mystery.reported_capacity.total_bytes)


def test_invalid_and_duplicate_records(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    assert observed.invalid_record_count == 1
    ids = [entry.mount_id for entry in observed.entries]
    assert len(ids) == len(set(ids))
    assert "mnt:22" in ids
    assert "mnt:22-1" in ids
    assert unescape_mount_field("/mnt/data\\040dir") == "/mnt/data dir"
    assert "/mnt/data dir" in _by_point(observed)


def test_reported_capacity_fields_stay_distinct(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    root = _by_point(observed)["/"]
    assert root.reported_capacity.total_bytes == 4096 * 1_000_000
    assert root.reported_capacity.free_bytes == 4096 * 400_000
    assert root.reported_capacity.available_bytes == 4096 * 300_000
    assert root.reported_capacity.source is CapacitySource.NATIVE_STAT
    assert root.reported_capacity.free_bytes != root.reported_capacity.available_bytes
    document = to_dict(root.reported_capacity)
    assert set(document) >= {"total_bytes", "free_bytes", "available_bytes"}
    assert "safe_storage_bytes" not in document


def test_unknown_capacity_stays_unresolved(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    mystery = _by_point(observed)["/mystery"]
    assert mystery.reported_capacity.source is CapacitySource.UNOBSERVED
    fields = unresolved_fields(mystery.reported_capacity)
    assert "total_bytes" in fields
    assert "free_bytes" in fields
    assert "available_bytes" in fields


def test_observation_does_not_compute_safe_capacity(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    dumped = json.dumps(to_dict(observed))
    assert "safe_storage_bytes" not in dumped
    assert "SAFE_STORAGE" not in dumped


def test_writable_path_capability(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    root = _by_point(observed)["/"]
    assert root.path_capability.path_exists is True
    assert root.path_capability.readable is True
    assert root.path_capability.writable_by_access is True
    assert root.path_capability.write_probe_outcome is WriteProbeOutcome.NOT_ATTEMPTED


def test_inaccessible_path_capability(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    locked = _by_point(observed)["/locked"]
    assert locked.path_capability.path_exists is False
    assert locked.suitability.can_host_model is False
    assert SuitabilityReason.INACCESSIBLE in locked.suitability.reasons


def test_write_probe_disabled_by_default(clock: FixedClock) -> None:
    calls: list[tuple[str, int]] = []

    def probe(path: str, max_bytes: int) -> tuple[WriteProbeOutcome, int, bool, str]:
        calls.append((path, max_bytes))
        return WriteProbeOutcome.SUCCEEDED, max_bytes, True, ""

    observed = _linux_observer(clock=clock, probe=probe).observe()
    assert observed.settings.write_probe_policy is WriteProbePolicy.DISABLED
    assert calls == []
    assert (
        _by_point(observed)["/"].path_capability.write_probe_outcome
        is WriteProbeOutcome.NOT_ATTEMPTED
    )


def test_write_probe_success_and_cleanup(tmp_path: Path, clock: FixedClock) -> None:
    mountinfo = f"22 1 8:1 / {tmp_path} rw,relatime - ext4 /dev/sda1 rw\n"
    provider = LinuxMountProvider(
        mountinfo_text=mountinfo,
        dockerenv_path=Path("/nonexistent-dockerenv"),
        containerenv_path=Path("/nonexistent-containerenv"),
        clock=clock,
    )
    observer = NativeMountObserver(
        os_observer=_FixedOS("Linux"),
        write_probe_policy=WriteProbePolicy.BOUNDED,
        linux_provider=provider,
        clock=clock,
    )
    observed = observer.observe()
    entry = observed.entries[0]
    assert entry.path_capability.write_probe_outcome is WriteProbeOutcome.SUCCEEDED
    assert entry.path_capability.write_probe_bytes == 64
    assert entry.path_capability.cleanup_completed is True
    leftovers = list(tmp_path.glob(f"{PROBE_PREFIX}*"))
    assert leftovers == []


def test_write_probe_failure(clock: FixedClock) -> None:
    def probe(path: str, max_bytes: int) -> tuple[WriteProbeOutcome, int, bool, str]:
        return WriteProbeOutcome.FAILED, max_bytes, True, "observational probe failed"

    observed = _linux_observer(
        clock=clock,
        write_probe_policy=WriteProbePolicy.BOUNDED,
        probe=probe,
    ).observe()
    root = _by_point(observed)["/"]
    assert root.path_capability.write_probe_outcome is WriteProbeOutcome.FAILED
    assert SuitabilityReason.WRITE_PROBE_FAILED in root.suitability.reasons
    proc = _by_point(observed)["/proc"]
    assert proc.path_capability.write_probe_outcome is WriteProbeOutcome.SKIPPED


def test_write_probe_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        default_mount_settings(write_probe_max_bytes=0)
    with pytest.raises(ValidationError):
        default_mount_settings(write_probe_max_bytes=5000)
    with pytest.raises(ValidationError):
        bounded_write_probe("/tmp", 0)


def test_pseudo_ignore_default_is_inspectable(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    names = {item.name: item.value for item in observed.settings.settings}
    assert names["filesystem.ignored_classes"] == "pseudo"
    assert "local_physical" in names["filesystem.included_classes"]
    assert observed.settings.write_probe_policy is WriteProbePolicy.DISABLED


def test_quota_option_is_unread_not_zero(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    quota = _by_point(observed)["/mnt/data dir"].quota
    assert quota.status is QuotaEvidenceStatus.UNAVAILABLE
    assert not is_resolved(quota.hard_limit_bytes)
    root_quota = _by_point(observed)["/"].quota
    assert root_quota.status is QuotaEvidenceStatus.UNSUPPORTED


def test_windows_is_unsupported_not_zero(clock: FixedClock) -> None:
    observed = NativeMountObserver(
        os_observer=_FixedOS("Windows"),
        clock=clock,
    ).observe()
    assert observed.status is ObservationStatus.UNOBSERVED
    assert observed.provider == "windows"
    assert observed.entries == ()
    assert observed.os_family is OSFamily.WINDOWS


def test_macos_fixture_and_classification(clock: FixedClock) -> None:
    records = (
        MacOSMountRecord(
            mount_point="/",
            source="/dev/disk3s1",
            filesystem_type="apfs",
            flags=0,
            block_size=4096,
            blocks=1000,
            bfree=400,
            bavail=300,
            fsid_a=1,
            fsid_b=2,
        ),
        MacOSMountRecord(
            mount_point="/dev",
            source="devfs",
            filesystem_type="devfs",
            flags=1,
            block_size=512,
            blocks=0,
            bfree=0,
            bavail=0,
            fsid_a=3,
            fsid_b=4,
        ),
        MacOSMountRecord(
            mount_point="/Volumes/share",
            source="server:/export",
            filesystem_type="nfs",
            flags=0,
            block_size=4096,
            blocks=200,
            bfree=80,
            bavail=70,
            fsid_a=0,
            fsid_b=0,
        ),
    )
    observer = NativeMountObserver(
        os_observer=_FixedOS("Darwin"),
        macos_provider=MacOSMountProvider(
            records=records,
            exists=lambda path: True,
            access=lambda path, mode: mode != os.W_OK or path != "/dev",
            dockerenv_path=Path("/nonexistent-dockerenv"),
            clock=clock,
        ),
        clock=clock,
    )
    observed = observer.observe()
    points = _by_point(observed)
    assert points["/"].storage_class is StorageClass.LOCAL_PHYSICAL
    assert points["/dev"].storage_class is StorageClass.PSEUDO
    assert points["/Volumes/share"].storage_class is StorageClass.NETWORK
    assert not is_resolved(points["/Volumes/share"].backing_store_id)
    assert points["/"].reported_capacity.total_bytes == 4096 * 1000
    assert points["/"].reported_capacity.free_bytes == 4096 * 400
    assert points["/"].reported_capacity.available_bytes == 4096 * 300


def test_container_namespace_from_overlay_root(clock: FixedClock) -> None:
    table = "22 1 0:45 / / rw - overlay overlay rw\n"
    provider = LinuxMountProvider(
        mountinfo_text=table,
        statvfs=_statvfs,
        exists=_exists,
        access=_access,
        dockerenv_path=Path("/nonexistent-dockerenv"),
        containerenv_path=Path("/nonexistent-containerenv"),
        clock=clock,
    )
    observed = NativeMountObserver(
        os_observer=_FixedOS("Linux"),
        linux_provider=provider,
        clock=clock,
    ).observe()
    assert observed.namespace_context.value == "container"


def test_contract_round_trip_and_privacy(clock: FixedClock) -> None:
    observed = _linux_observer(clock=clock).observe()
    restored = from_dict(to_dict(observed))
    assert restored == observed
    event = mounts_observed(observed)
    assert event.event_type.value == MOUNT_OBSERVED_TYPE
    assert event.privacy is PrivacyClass.OPERATIONAL
    payload = to_dict(event.payload)
    dumped = json.dumps(payload)
    assert "/home" not in dumped
    assert "/mnt/data dir" not in dumped
    assert "10.0.0.1" not in dumped
    assert payload["observer"] == "native"
    assert payload["entry_count"] == len(observed.entries)


def test_cli_observes_mounts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    journal = tmp_path / "journal"
    assert main(["discover", "mounts", "--journal-dir", str(journal)]) == 0
    out = capsys.readouterr().out
    assert "entries" in out
    assert '"kind": "mount.observation"' in out
    assert '"event_type": "discover.mounts.observed"' in out
    assert '"privacy": "operational"' in out
    assert "safe_storage_bytes" not in out
    journal_text = (journal / "events.jsonl").read_text(encoding="utf-8")
    assert "discover.mounts.observed" in journal_text
    event = json.loads(journal_text.splitlines()[-1])
    assert str(tmp_path) not in json.dumps(event["payload"])


def test_parse_helpers() -> None:
    records, invalid = parse_linux_mountinfo(LINUX_TABLE)
    assert invalid == 1
    assert any(record.mount_point == "/mnt/data dir" for record in records)
    assert (
        classify_linux_filesystem("ext4", "/dev/sda1", ())
        is StorageClass.LOCAL_PHYSICAL
    )
    assert classify_linux_filesystem("proc", "proc", ()) is StorageClass.PSEUDO
    assert classify_linux_filesystem("overlay", "overlay", ()) is StorageClass.OVERLAY
    assert (
        classify_linux_filesystem("nfs4", "server:/export", ()) is StorageClass.NETWORK
    )
    assert classify_linux_filesystem("tmpfs", "tmpfs", ()) is StorageClass.TMPFS
    assert (
        classify_linux_filesystem("ext4", "/dev/loop0", ())
        is StorageClass.LOCAL_VIRTUAL
    )
    assert classify_darwin_filesystem("apfs") is StorageClass.LOCAL_PHYSICAL
    assert classify_darwin_filesystem("devfs") is StorageClass.PSEUDO
    assert classify_darwin_filesystem("nfs") is StorageClass.NETWORK
