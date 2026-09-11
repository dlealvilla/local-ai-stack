"""Specialist / Sonar corroboration. FakeVolume only; no production GiB writes."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.storage.moosefs import MooseFSQuotaProbe
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import StorageFailureCode
from kultrun.storage.ports import (
    CapacityProbeResult,
    EmpiricalWriteBudget,
    EmpiricalWriteResult,
    StorageEnvironment,
)
from kultrun.storage.probes import ProbeRegistry
from kultrun.storage.sonar import (
    CORROBORATION_CONFIRMED,
    CORROBORATION_CONTRADICTED,
    CORROBORATION_INCONCLUSIVE,
    CORROBORATION_LIMITED,
    CORROBORATION_LOWER_ONLY,
    CORROBORATION_NOT_CONTRADICTED,
    PROBE_FILENAME,
    EmpiricalStorageProbe,
)
from tests.test_capacity import INSTANT, host, mount
from tests.test_storage_sonar import FakeVolume, _probe

HOST = HostId.generate()


def _mounted(root: Path, filesystem: str = "ext4", **kwargs):
    root.mkdir(parents=True, exist_ok=True)
    kwargs.setdefault("free", 80)
    kwargs.setdefault("total", 100)
    return host(mounts=(mount(str(root), filesystem, **kwargs),)), str(root)


def _characterize(service, root: Path, filesystem: str = "ext4"):
    subject, point = _mounted(root, filesystem)
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    return result, point


class _OtherAt(FakeVolume):
    """Non-capacity failure at a probe size. Reserve still succeeds."""

    def __init__(self, capacity: int, other_at: int, **kwargs) -> None:
        super().__init__(capacity, **kwargs)
        self.other_at = other_at

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled=None,
    ) -> EmpiricalWriteResult:
        if path.name == PROBE_FILENAME and size > self.other_at:
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=StorageFailureCode.STORAGE_IO_FAILURE,
                failure_errno=60,
                detail="timeout",
            )
        return super().write_exactly(path, size, budget, cancelled=cancelled)


class _BytesQuota:
    name = "linux-quota"
    technology = "linux-quota"

    def __init__(self, available: int, hard: int | None = None) -> None:
        self._available = available
        self._hard = available if hard is None else hard

    def supports(self, environment: StorageEnvironment) -> bool:
        del environment
        return True

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            available_bytes=self._available,
            hard_maximum_bytes=self._hard,
            executed=True,
            available=True,
            detail="fixture",
        )


class _Malformed:
    name = "linux-quota"
    technology = "linux-quota"

    def supports(self, environment: StorageEnvironment) -> bool:
        del environment
        return True

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        del environment
        return CapacityProbeResult(
            executed=True,
            available=True,
            detail="malformed specialist output",
        )


def _service(
    volume: FakeVolume,
    registry: ProbeRegistry,
) -> StorageCharacterizationService:
    return StorageCharacterizationService(
        FixedClock(INSTANT),
        registry,
        empirical=_probe(volume),
        use_live_native=False,
    )


def _run(
    volume: FakeVolume,
    tmp_path: Path,
    candidate: int,
) -> object:
    return _probe(volume).probe(
        HOST, "/pool", tmp_path, corroborate_bytes=candidate
    )


def test_bracket_50_confirms_specialist(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=48,
    )
    evidence = _run(volume, tmp_path, 50)
    assert evidence.corroboration == CORROBORATION_CONFIRMED
    assert evidence.verified_lower_bound_bytes == 48
    assert evidence.observed_failure_upper_bytes == 64
    assert evidence.specialist_candidate_bytes == 50
    assert evidence.attempted_tier_units == (48, 64)
    assert 96 not in evidence.attempted_tier_units
    assert 128 not in evidence.attempted_tier_units
    assert 256 not in evidence.attempted_tier_units
    assert evidence.cleanup_success is True
    service = _service(volume, ProbeRegistry((_BytesQuota(50),)))
    result, point = _characterize(service, tmp_path / "char")
    item = result.evidence[point]
    assert item.operational_available_bytes == 50
    assert item.probe_name == "linux-quota"
    assert "sonar corroborated" in item.selected_reason
    emp = result.empirical_evidence[point]
    assert emp.corroboration == CORROBORATION_CONFIRMED
    assert emp.verified_lower_bound_bytes == 48
    assert emp.observed_failure_upper_bytes == 64


def test_upper_pass_does_not_inflate(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _run(volume, tmp_path, 50)
    assert evidence.corroboration == CORROBORATION_NOT_CONTRADICTED
    assert evidence.verified_lower_bound_bytes == 64
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert 96 not in evidence.attempted_tier_units
    service = _service(FakeVolume(10_000), ProbeRegistry((_BytesQuota(50),)))
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 50
    assert "conservative" in result.evidence[point].selected_reason


def test_lower_capacity_failure_contradicts_and_falls_to_tree(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=32,
    )
    evidence = _run(volume, tmp_path, 50)
    assert evidence.corroboration == CORROBORATION_CONTRADICTED
    assert evidence.verified_lower_bound_bytes == 32
    assert evidence.observed_failure_upper_bytes == 48
    assert evidence.specialist_candidate_bytes == 50
    service = _service(
        FakeVolume(
            10_000,
            fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
            fail_at=32,
        ),
        ProbeRegistry((_BytesQuota(50),)),
    )
    result, point = _characterize(service, tmp_path / "char")
    item = result.evidence[point]
    assert item.operational_available_bytes == 32
    assert item.probe_name == "empirical-fallback"
    assert result.empirical_evidence[point].specialist_candidate_bytes == 50
    assert result.empirical_evidence[point].corroboration == (
        CORROBORATION_CONTRADICTED
    )


def test_lower_permission_is_inconclusive(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, permission=True, permission_on=PROBE_FILENAME)
    evidence = _run(volume, tmp_path, 50)
    assert evidence.corroboration == CORROBORATION_INCONCLUSIVE
    assert evidence.attempted_tier_units == (48,)
    service = _service(
        FakeVolume(10_000, permission=True, permission_on=PROBE_FILENAME),
        ProbeRegistry((_BytesQuota(50),)),
    )
    result, point = _characterize(service, tmp_path / "char")
    item = result.evidence[point]
    assert item.operational_available_bytes == 50
    assert item.probe_name == "linux-quota"
    assert "inconclusive" in item.selected_reason


def test_upper_timeout_is_inconclusive(tmp_path: Path) -> None:
    volume = _OtherAt(10_000, other_at=48)
    evidence = _run(volume, tmp_path, 50)
    assert evidence.corroboration == CORROBORATION_INCONCLUSIVE
    assert evidence.verified_lower_bound_bytes == 48
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    service = _service(_OtherAt(10_000, other_at=48), ProbeRegistry((_BytesQuota(50),)))
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 50
    assert result.evidence[point].probe_name == "linux-quota"


def test_specialist_220_bracket(tmp_path: Path) -> None:
    fail_upper = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=192,
    )
    confirmed = _run(fail_upper, tmp_path, 220)
    assert confirmed.corroboration == CORROBORATION_CONFIRMED
    assert confirmed.verified_lower_bound_bytes == 192
    assert confirmed.observed_failure_upper_bytes == 256
    assert confirmed.attempted_tier_units == (192, 256)
    both = _run(FakeVolume(10_000), tmp_path, 220)
    assert both.corroboration == CORROBORATION_NOT_CONTRADICTED
    assert both.verified_lower_bound_bytes == 256
    service = _service(FakeVolume(10_000), ProbeRegistry((_BytesQuota(220),)))
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 220


def test_specialist_500_256_pass_retains_500(tmp_path: Path) -> None:
    evidence = _run(FakeVolume(10_000), tmp_path, 500)
    assert evidence.corroboration == CORROBORATION_LOWER_ONLY
    assert evidence.verified_lower_bound_bytes == 256
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert evidence.probe_ceiling_reached is True
    assert evidence.attempted_tier_units == (256,)
    assert 128 not in evidence.attempted_tier_units
    service = _service(FakeVolume(10_000), ProbeRegistry((_BytesQuota(500),)))
    result, point = _characterize(service, tmp_path / "char")
    item = result.evidence[point]
    assert item.operational_available_bytes == 500
    assert item.probe_name == "linux-quota"
    assert ">=256" in item.selected_reason


def test_specialist_500_256_edquot_contradicts(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=192,
    )
    evidence = _run(volume, tmp_path, 500)
    assert evidence.corroboration == CORROBORATION_CONTRADICTED
    assert evidence.verified_lower_bound_bytes == 192
    assert evidence.specialist_candidate_bytes == 500
    service = _service(
        FakeVolume(
            10_000,
            fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
            fail_at=192,
        ),
        ProbeRegistry((_BytesQuota(500),)),
    )
    result, point = _characterize(service, tmp_path / "char")
    item = result.evidence[point]
    assert item.operational_available_bytes == 192
    assert item.probe_name == "empirical-fallback"


def test_specialist_500_256_timeout_keeps_500(tmp_path: Path) -> None:
    evidence = _run(_OtherAt(10_000, other_at=255), tmp_path, 500)
    assert evidence.corroboration == CORROBORATION_INCONCLUSIVE
    service = _service(
        _OtherAt(10_000, other_at=255), ProbeRegistry((_BytesQuota(500),))
    )
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 500
    assert result.evidence[point].probe_name == "linux-quota"


def test_exactly_256_no_higher_probe(tmp_path: Path) -> None:
    evidence = _run(FakeVolume(10_000), tmp_path, 256)
    assert evidence.corroboration == CORROBORATION_CONFIRMED
    assert evidence.verified_lower_bound_bytes == 256
    assert evidence.attempted_tier_units == (256,)
    service = _service(FakeVolume(10_000), ProbeRegistry((_BytesQuota(256),)))
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 256


def test_hard_bound_caps_candidate_before_corroboration(tmp_path: Path) -> None:
    service = _service(
        FakeVolume(
            10_000,
            fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
            fail_at=192,
        ),
        ProbeRegistry((_BytesQuota(500, hard=200),)),
    )
    result, point = _characterize(service, tmp_path)
    item = result.evidence[point]
    assert item.operational_available_bytes == 200
    emp = result.empirical_evidence[point]
    assert emp.specialist_candidate_bytes == 200
    assert emp.corroboration == CORROBORATION_CONFIRMED
    assert emp.verified_lower_bound_bytes == 192
    assert emp.observed_failure_upper_bytes == 256


def test_no_specialist_full_tree_representative(tmp_path: Path) -> None:
    cases = (
        (1000, 256, None),
        (96, 96, 128),
        (48, 48, 64),
        (24, 24, 32),
        (0, None, 16),
    )
    for fail_at, lower, upper in cases:
        volume = FakeVolume(10_000, fail_at=fail_at)
        evidence = _probe(volume).probe(HOST, "/pool", tmp_path / str(fail_at))
        assert not is_resolved(evidence.corroboration)
        if lower is None:
            assert not is_resolved(evidence.verified_lower_bound_bytes)
        else:
            assert evidence.verified_lower_bound_bytes == lower
        if upper is None:
            assert not is_resolved(evidence.observed_failure_upper_bytes)
        else:
            assert evidence.observed_failure_upper_bytes == upper
        service = _service(
            FakeVolume(10_000, fail_at=fail_at), ProbeRegistry(())
        )
        result, point = _characterize(
            service, tmp_path / f"c{fail_at}", filesystem="fuse"
        )
        item = result.evidence[point]
        if lower is None:
            assert not is_resolved(item.authorizing_available_bytes)
        else:
            assert item.operational_available_bytes == lower
            assert item.probe_name == "empirical-fallback"


def test_missing_mfsgetquota_runs_full_sonar(tmp_path: Path) -> None:
    from unittest.mock import patch

    volume = FakeVolume(10_000, fail_at=48)
    service = _service(volume, ProbeRegistry((MooseFSQuotaProbe(),)))
    with patch("kultrun.adapters.storage.moosefs.shutil.which", return_value=None):
        result, point = _characterize(service, tmp_path, filesystem="fuse.mfs")
    emp = result.empirical_evidence[point]
    assert not is_resolved(emp.corroboration)
    assert emp.verified_lower_bound_bytes == 48
    assert result.evidence[point].probe_name == "empirical-fallback"


def test_malformed_specialist_runs_full_sonar(tmp_path: Path) -> None:
    service = _service(
        FakeVolume(10_000, fail_at=48), ProbeRegistry((_Malformed(),))
    )
    result, point = _characterize(service, tmp_path)
    emp = result.empirical_evidence[point]
    assert not is_resolved(emp.corroboration)
    assert result.evidence[point].operational_available_bytes == 48
    assert result.evidence[point].probe_name == "empirical-fallback"


def test_cheap_get_does_not_corroborate() -> None:
    class _Recorder:
        def __init__(self) -> None:
            self.calls = 0

        def probe(self, *args, **kwargs):
            del args, kwargs
            self.calls += 1
            raise AssertionError("cheap GET must not call Sonar")

    recorder = _Recorder()
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry((_BytesQuota(50),)),
        empirical=recorder,
        use_live_native=False,
    )
    result = service.characterize(
        host(mounts=(mount("/workspace", "ext4", free=80, total=100),)),
        run_cleanup=False,
        run_empirical=False,
    )
    assert recorder.calls == 0
    assert result.empirical_ran == ()
    assert result.evidence["/workspace"].operational_available_bytes == 50


def test_below_16_is_limited_and_keeps_specialist(tmp_path: Path) -> None:
    evidence = _run(FakeVolume(10_000), tmp_path, 10)
    assert evidence.corroboration == CORROBORATION_LIMITED
    assert evidence.attempted_tier_units == ()
    service = _service(FakeVolume(10_000), ProbeRegistry((_BytesQuota(10),)))
    result, point = _characterize(service, tmp_path / "char")
    assert result.evidence[point].operational_available_bytes == 10
    assert 16 not in result.empirical_evidence[point].attempted_tier_units


def test_mid_probe_progress_is_not_final_authority(tmp_path: Path) -> None:
    seen: list[object] = []

    def capture(item) -> None:
        seen.append(item)

    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=48,
    )
    probe = EmpiricalStorageProbe(
        volume,
        FixedClock(INSTANT),
        unit_bytes=1,
        reserve_bytes=1,
        chunk_bytes=8,
        timeout_seconds=60,
        on_progress=capture,
    )
    evidence = probe.probe(HOST, "/pool", tmp_path, corroborate_bytes=50)
    assert evidence.corroboration == CORROBORATION_CONFIRMED
    assert evidence.cleanup_success is True
    running = [
        item
        for item in seen
        if is_resolved(item.run_state) and item.run_state == "running"
    ]
    assert running
    assert all(item.cleanup_success is False for item in running)
    assert all(
        not (is_resolved(item.run_state) and item.run_state == "complete")
        for item in running
    )
