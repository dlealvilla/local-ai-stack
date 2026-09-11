"""P0 specialist parsers and adapters. Fixtures only; no multi-GiB writes."""

from __future__ import annotations

from types import SimpleNamespace

from kultrun.adapters.storage.ceph import CephfsQuotaProbe
from kultrun.adapters.storage.linux_quota import LinuxQuotaProbe
from kultrun.adapters.storage.moosefs import MooseFSQuotaProbe
from kultrun.adapters.storage.quota_parse import (
    parse_linux_quota_w,
    parse_mfsgetquota,
    parse_size_token,
)
from kultrun.adapters.storage.windows import WindowsCapacityProbe
from kultrun.adapters.storage.zfs import ZfsDatasetProbe
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import EmpiricalProbeEvidence, StorageEvidenceStatus
from kultrun.storage.limits import POLICY_VERSION
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment
from kultrun.storage.probes import ProbeRegistry
from tests.test_capacity import INSTANT, host, mount

GIB = 1024**3
TIB = 1024**4


def _env(
    *,
    os_name: str = "linux",
    mount_point: str = "/workspace",
    filesystem_type: str = "ext4",
    device: str = "/dev/sda1",
) -> StorageEnvironment:
    return StorageEnvironment(
        os_name=os_name,
        architecture="x86_64",
        mount_point=mount_point,
        filesystem_type=filesystem_type,
        device=device,
    )


def test_parse_linux_quota_w_remaining_kib_blocks() -> None:
    output = """
Disk quotas for user alice (uid 1000):
     Filesystem  blocks   quota   limit   grace   files   quota   limit   grace
      /dev/sda1   204800  1048576 2097152           100       0       0
"""
    available, hard, _detail = parse_linux_quota_w(output, filesystem="/dev/sda1")
    assert available == (1048576 - 204800) * 1024
    assert hard == 2097152 * 1024


def test_parse_linux_quota_unlimited_is_unresolved() -> None:
    output = """
     Filesystem  blocks   quota   limit
      /dev/sda1   204800       0       0
"""
    available, hard, _detail = parse_linux_quota_w(output)
    assert not is_resolved(available)
    assert not is_resolved(hard)


def test_parse_mfsgetquota_prefers_realsize() -> None:
    output = """
# /workspace:
                   current             quota             limit
inodes                   10                 0                 0
length                    0                 0                 0
size                      0        10737418240        21474836480
realsize                  0         5368709120        10737418240
"""
    available, hard, detail = parse_mfsgetquota(output)
    assert available == 5368709120
    assert hard == 10737418240
    assert "realsize" in detail


def test_parse_mfsgetquota_human_size_when_realsize_unlimited() -> None:
    output = """
size                 1.0GiB              10GiB              20GiB
realsize                2GiB                 -                 -
"""
    available, hard, detail = parse_mfsgetquota(output)
    assert available == 9 * GIB
    assert hard == 20 * GIB
    assert "size" in detail


def test_parse_size_token_dash_is_unresolved() -> None:
    assert parse_size_token("-") is NOT_PROVIDED


def test_linux_quota_missing_binary_is_not_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "kultrun.adapters.storage.linux_quota.shutil.which", lambda _: None
    )
    result = LinuxQuotaProbe().probe(_env())
    assert result.executed is False
    assert not is_resolved(result.available_bytes)


def test_moosefs_missing_binary_is_not_success() -> None:
    result = MooseFSQuotaProbe().probe(_env(filesystem_type="fuse", device="mfs#x"))
    assert result.executed is False
    assert not is_resolved(result.available_bytes)


def test_moosefs_parses_when_binary_present(monkeypatch) -> None:
    monkeypatch.setattr(
        "kultrun.adapters.storage.moosefs.shutil.which",
        lambda _: "/usr/bin/mfsgetquota",
    )
    monkeypatch.setattr(
        "kultrun.adapters.storage.moosefs.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=(
                "size 0 10737418240 21474836480\nrealsize 0 5368709120 10737418240\n"
            ),
            stderr="",
            returncode=0,
        ),
    )
    result = MooseFSQuotaProbe().probe(_env(filesystem_type="fuse", device="mfs#x"))
    assert result.executed is True
    assert result.available_bytes == 5368709120


def test_zfs_missing_binary_is_not_success(monkeypatch) -> None:
    monkeypatch.setattr("kultrun.adapters.storage.zfs.shutil.which", lambda _: None)
    env = _env(filesystem_type="zfs")
    assert ZfsDatasetProbe().supports(env)
    result = ZfsDatasetProbe().probe(env)
    assert result.executed is False
    assert not is_resolved(result.available_bytes)


def test_zfs_dataset_quota_remaining(monkeypatch) -> None:
    monkeypatch.setattr(
        "kultrun.adapters.storage.zfs.shutil.which", lambda _: "/sbin/zfs"
    )

    def fake_run(argv, **kwargs):
        del kwargs
        if argv[1] == "list":
            return SimpleNamespace(
                stdout="tank/data\t/workspace\n", stderr="", returncode=0
            )
        return SimpleNamespace(
            stdout=(
                "available\t53687091200\nquota\t53687091200\nrefquota\tnone\nused\t0\n"
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr("kultrun.adapters.storage.zfs.subprocess.run", fake_run)
    result = ZfsDatasetProbe().probe(_env(filesystem_type="zfs"))
    assert result.executed is True
    assert result.available_bytes == 50 * GIB
    assert result.hard_maximum_bytes == 50 * GIB


def test_ceph_xattr_remaining(monkeypatch) -> None:
    def fake_xattr(path, name):
        del path
        if name == "ceph.quota.max_bytes":
            return b"10737418240"
        if name == "ceph.dir.rbytes":
            return b"1073741824"
        raise OSError("missing")

    monkeypatch.setattr(
        "kultrun.adapters.storage.ceph.os.getxattr", fake_xattr, raising=False
    )
    env = _env(filesystem_type="ceph")
    assert CephfsQuotaProbe().supports(env)
    result = CephfsQuotaProbe().probe(env)
    assert result.executed is True
    assert result.available_bytes == 9 * GIB
    assert result.hard_maximum_bytes == 10 * GIB


def test_windows_probe_skipped_off_win32() -> None:
    result = WindowsCapacityProbe().probe(
        _env(os_name="windows", filesystem_type="ntfs")
    )
    assert result.executed is False
    assert not is_resolved(result.available_bytes)


class _Quota:
    name = "linux-quota"
    technology = "linux-quota"

    def supports(self, environment: StorageEnvironment) -> bool:
        return True

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            available_bytes=50 * GIB,
            hard_maximum_bytes=50 * GIB,
            executed=True,
            available=True,
            detail="fixture",
        )


class _RecordingSonar:
    def __init__(self, evidence: EmpiricalProbeEvidence) -> None:
        self.calls = 0
        self._evidence = evidence

    def probe(self, *args, **kwargs):
        del args, kwargs
        self.calls += 1
        return self._evidence


def _emp(
    *,
    lower: int | object = NOT_PROVIDED,
    fingerprint: object = NOT_PROVIDED,
    interrupted: bool = False,
    ceiling: bool = False,
) -> EmpiricalProbeEvidence:
    resolved = isinstance(lower, int)
    return EmpiricalProbeEvidence(
        host_id=HostId.generate(),
        mount_point="/workspace",
        target_path="/workspace",
        max_probe_bytes=lower if resolved else 1,
        bytes_physically_written=0,
        search_granularity_bytes=1,
        probe_ceiling_reached=ceiling,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=True,
        verified_lower_bound_bytes=lower,
        interrupted=interrupted,
        pool_fingerprint=fingerprint,
        run_state="complete",
    )


def test_characterize_specialist_wins_over_huge_native() -> None:
    sonar = _RecordingSonar(_emp(lower=48 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_Quota(),)),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(
            mount(
                "/workspace",
                "ext4",
                free=180 * TIB,
                total=180 * TIB,
            ),
        )
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    item = result.evidence["/workspace"]
    assert item.operational_available_bytes == 50 * GIB
    assert item.status is StorageEvidenceStatus.CONTRADICTED
    assert sonar.calls == 1
    assert "/workspace" in result.empirical_ran
    assert "sonar confirmed" in item.selected_reason


def test_characterize_sonar_replaces_disagreed_specialist() -> None:
    sonar = _RecordingSonar(_emp(lower=32 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_Quota(),)),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "ext4", free=180 * TIB, total=180 * TIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    item = result.evidence["/workspace"]
    assert item.operational_available_bytes == 32 * GIB
    assert item.probe_name == "empirical-fallback"
    assert sonar.calls == 1


def test_characterize_keeps_specialist_when_sonar_cannot() -> None:
    sonar = _RecordingSonar(_emp(interrupted=True))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_Quota(),)),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "ext4", free=180 * TIB, total=180 * TIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    item = result.evidence["/workspace"]
    assert item.operational_available_bytes == 50 * GIB
    assert sonar.calls == 1


def test_cheap_characterize_does_not_sonar() -> None:
    sonar = _RecordingSonar(_emp(lower=32 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_Quota(),)),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "ext4", free=180 * GIB, total=180 * GIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=False)
    assert sonar.calls == 0
    assert result.empirical_ran == ()
    assert result.evidence["/workspace"].operational_available_bytes == 50 * GIB


def test_characterize_fuse_without_bytes_would_sonar() -> None:
    class _Identify:
        name = "fuse-identify"
        technology = "fuse"

        def supports(self, environment: StorageEnvironment) -> bool:
            return True

        def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
            del environment
            return CapacityProbeResult(
                executed=True,
                available=True,
                detail="identified fuse",
            )

    class _Sonar:
        def probe(self, *args, **kwargs):
            del args, kwargs
            return _emp(lower=32 * GIB)

    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_Identify(),)),
        empirical=_Sonar(),
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "fuse", free=80 * GIB, total=100 * GIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    assert "/workspace" in result.empirical_ran
    assert result.evidence["/workspace"].operational_available_bytes == 32 * GIB


def test_expensive_trusted_ext4_still_sonars() -> None:
    sonar = _RecordingSonar(_emp(lower=128 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "ext4", free=180 * GIB, total=180 * GIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    assert sonar.calls == 1
    assert result.evidence["/workspace"].operational_available_bytes == 128 * GIB
    assert result.evidence["/workspace"].probe_name == "empirical-fallback"


def test_identity_change_does_not_promote_old_sonar() -> None:
    sonar = _RecordingSonar(_emp(lower=32 * GIB, fingerprint="old-pool"))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=sonar,
        use_live_native=False,
    )
    subject = host(
        mounts=(mount("/workspace", "fuse", free=80 * GIB, total=100 * GIB),)
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    item = result.evidence["/workspace"]
    assert sonar.calls == 1
    assert not is_resolved(item.authorizing_available_bytes)
    assert item.status is StorageEvidenceStatus.UNRESOLVED
