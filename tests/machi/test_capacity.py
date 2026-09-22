"""Capacity Tier 2: reported, proven, and SAFE stay distinct."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from machi.adapters.capacity.execution import read_execution_limit
from machi.adapters.capacity.sonar_file import FileSonarMedia
from machi.adapters.discover.linux_mount import LinuxMountProvider
from machi.capacity.compose import compose_envelope, is_stale
from machi.capacity.contracts import (
    AdministratorBound,
    EvidenceStrength,
    SonarFailure,
    SonarStatus,
    SpecialistBound,
)
from machi.capacity.events import capacity_events
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import SonarMedia, SonarWriteResult, run_sonar
from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorObservation,
    AcceleratorProviderReport,
    AcceleratorSource,
    AcceleratorVendor,
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    ProviderInspectionStatus,
)
from machi.discover.mounts import default_mount_settings
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import NOT_MEASURED, Unresolved, is_resolved

FIXED = dt.datetime(2026, 9, 22, 3, 0, tzinfo=dt.UTC)
GIB = 1024 * 1024 * 1024


class _VFS:
    def __init__(self, available: int) -> None:
        self.f_frsize = 1
        self.f_bsize = 1
        self.f_blocks = available + 10
        self.f_bfree = available + 5
        self.f_bavail = available


def _mounts(clock: FixedClock, table: str, available: dict[str, int]):
    provider = LinuxMountProvider(
        mountinfo_text=table,
        statvfs=lambda path: _VFS(available[path]),
        clock=clock,
    )
    return provider.observe(default_mount_settings(), clock.now())


def _memory(total: int) -> MemoryObservation:
    return MemoryObservation(
        physical_total_bytes=total,
        physical_total_status=ObservationStatus.NORMALIZED,
        source=MemorySource.LINUX_PROC,
        raw_total=f"MemTotal:{total}",
        observed_at=FIXED,
        observer="native",
    )


def _device(
    ordinal: int,
    identity: str,
    total: int | Unresolved,
    topology: AcceleratorMemoryTopology,
) -> AcceleratorDevice:
    resolved = isinstance(total, int)
    return AcceleratorDevice(
        ordinal=ordinal,
        vendor=AcceleratorVendor.NVIDIA,
        vendor_status=ObservationStatus.NORMALIZED,
        model_name="GPU",
        model_status=ObservationStatus.NORMALIZED,
        device_type=AcceleratorDeviceType.DISCRETE_GPU,
        device_type_status=ObservationStatus.NORMALIZED,
        memory_topology=topology,
        memory_topology_status=ObservationStatus.NORMALIZED,
        memory_total_bytes=total if resolved else NOT_MEASURED,
        memory_total_status=(
            ObservationStatus.NORMALIZED if resolved else ObservationStatus.UNOBSERVED
        ),
        identity=identity,
        source=AcceleratorSource.NVIDIA_SMI,
        raw=f"index={ordinal}",
    )


def _accelerators(*devices: AcceleratorDevice) -> AcceleratorObservation:
    return AcceleratorObservation(
        devices=devices,
        providers=(
            AcceleratorProviderReport(
                provider="nvidia",
                status=ProviderInspectionStatus.OBSERVED,
                detail="",
                device_count=len(devices),
            ),
        ),
        status=ObservationStatus.NORMALIZED,
        observed_at=FIXED,
        observer="native",
    )


def _envelope(**kwargs):
    settings = kwargs.pop("settings",
        default_capacity_settings(
            memory_reserve_bytes=100,
            accelerator_reserve_bytes=10,
            storage_reserve_bytes=10,
        )
    )
    return compose_envelope(
        evidence_id="cap_test",
        settings=settings,
        observed_at=FIXED,
        provider="native",
        input_parts=("inputs",),
        **kwargs,
    )


def test_reported_proven_and_safe_stay_distinct(clock: FixedClock) -> None:
    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 1000},
    )
    envelope = _envelope(memory=_memory(5000), execution_limit_bytes=2000,
        mounts=mounts)
    assert envelope.memory.physical_bytes == 5000
    assert envelope.memory.hard_ceiling_bytes == 2000
    assert envelope.memory.safe_bytes == 1900
    domain = envelope.storage_domains[0]
    assert domain.reported_available_bytes == 1000
    assert domain.safe_bytes == 990
    assert domain.safe_bytes != domain.reported_available_bytes


def test_specialist_beats_larger_report(clock: FixedClock) -> None:
    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 10_000},
    )
    domain_id = envelope_domain(mounts)
    envelope = _envelope(
        mounts=mounts,
        specialists=(SpecialistBound(backing_store_id=domain_id,
            remaining_bytes=180, source="quota"),),
    )
    domain = envelope.storage_domains[0]
    assert domain.hard_bound_bytes == 180
    assert domain.strength is EvidenceStrength.SPECIALIST
    assert domain.safe_bytes == 170


def test_unresolved_is_not_zero() -> None:
    envelope = _envelope(memory=None, execution_limit_bytes=NOT_MEASURED)
    assert not isinstance(envelope.memory.safe_bytes, int)
    assert envelope.memory.safe_bytes != 0


def test_negative_reserve_is_rejected() -> None:
    with pytest.raises(ValidationError):
        default_capacity_settings(memory_reserve_bytes=-1)


def test_execution_limit_smaller_than_physical() -> None:
    envelope = _envelope(memory=_memory(10_000), execution_limit_bytes=1000)
    assert envelope.memory.safe_bytes == 900
    assert envelope.memory.strength is EvidenceStrength.AUTHORITATIVE


def test_unknown_execution_limit_uses_physical_only() -> None:
    envelope = _envelope(memory=_memory(10_000), execution_limit_bytes=NOT_MEASURED)
    assert envelope.memory.hard_ceiling_bytes == 10_000
    assert envelope.memory.strength is EvidenceStrength.REPORTED


def test_reserve_larger_than_ceiling_stays_unresolved() -> None:
    envelope = _envelope(
        memory=_memory(50),
        execution_limit_bytes=NOT_MEASURED,
        settings=default_capacity_settings(memory_reserve_bytes=50,
            storage_reserve_bytes=0, accelerator_reserve_bytes=0),
    )
    assert not is_resolved(envelope.memory.safe_bytes)


def test_gpus_stay_separate() -> None:
    observation = _accelerators(
        _device(0, "gpu0", 48 * GIB, AcceleratorMemoryTopology.DISCRETE),
        _device(1, "gpu1", 48 * GIB, AcceleratorMemoryTopology.DISCRETE),
    )
    envelope = _envelope(accelerators=observation)
    assert len(envelope.accelerators) == 2
    assert envelope.accelerators[0].safe_bytes != 96 * GIB
    assert not hasattr(envelope, "pooled_vram_bytes")


def test_unified_memory_is_not_a_vram_pool() -> None:
    observation = _accelerators(
        _device(0, "apple", NOT_MEASURED, AcceleratorMemoryTopology.UNIFIED)
    )
    envelope = _envelope(accelerators=observation)
    assert not is_resolved(envelope.accelerators[0].safe_bytes)
    assert envelope.accelerators[0].topology == "unified"


def test_current_accelerator_use_stays_unresolved() -> None:
    observation = _accelerators(
        _device(0, "gpu0", 1000, AcceleratorMemoryTopology.DISCRETE)
    )
    envelope = _envelope(accelerators=observation)
    assert not is_resolved(envelope.accelerators[0].current_used_bytes)


def test_shared_backing_is_not_summed(clock: FixedClock) -> None:
    mounts = _mounts(
        clock,
        (
            "22 1 8:1 / /a rw - ext4 /dev/sda1 rw\n"
            "41 22 8:1 /b /b rw - ext4 /dev/sda1 rw\n"
        ),
        {"/a": 100, "/b": 80},
    )
    envelope = _envelope(mounts=mounts)
    assert len(envelope.storage_domains) == 1
    assert envelope.storage_domains[0].reported_available_bytes == 80


def test_read_only_storage_is_excluded(clock: FixedClock) -> None:
    mounts = _mounts(
        clock,
        "22 1 8:2 / /ro ro - ext4 /dev/sdb1 ro\n",
        {"/ro": 500},
    )
    envelope = _envelope(mounts=mounts)
    assert envelope.storage_domains[0].usable is False
    assert not is_resolved(envelope.storage_domains[0].safe_bytes)


def test_sonar_does_not_inflate_above_reported(clock: FixedClock) -> None:
    from machi.capacity.contracts import SonarEvidence

    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 80},
    )
    domain_id = envelope_domain(mounts)
    sonar = SonarEvidence(
        status=SonarStatus.CORROBORATED,
        proven_lower_bytes=96,
        contradictory_upper_bytes=NOT_MEASURED,
        failure=SonarFailure.NONE,
        tiers_attempted=(96,),
        cleanup_completed=True,
        reason="wrote more than reported",
    )
    envelope = _envelope(mounts=mounts, sonar_by_domain={domain_id: sonar})
    assert envelope.storage_domains[0].hard_bound_bytes == 80


def test_sonar_contradiction_downgrades_report(clock: FixedClock) -> None:
    from machi.capacity.contracts import SonarEvidence

    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 200},
    )
    domain_id = envelope_domain(mounts)
    sonar = SonarEvidence(
        status=SonarStatus.CONTRADICTED,
        proven_lower_bytes=64,
        contradictory_upper_bytes=96,
        failure=SonarFailure.EDQUOT,
        tiers_attempted=(64, 96),
        cleanup_completed=True,
        reason="quota",
    )
    envelope = _envelope(mounts=mounts, sonar_by_domain={domain_id: sonar})
    assert envelope.storage_domains[0].hard_bound_bytes == 64
    assert envelope.storage_domains[0].strength is EvidenceStrength.EMPIRICALLY_PROVEN


def test_corroboration_keeps_reported_value(clock: FixedClock) -> None:
    from machi.capacity.contracts import SonarEvidence

    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 100},
    )
    domain_id = envelope_domain(mounts)
    sonar = SonarEvidence(
        status=SonarStatus.CORROBORATED,
        proven_lower_bytes=70,
        contradictory_upper_bytes=NOT_MEASURED,
        failure=SonarFailure.NONE,
        tiers_attempted=(70,),
        cleanup_completed=True,
        reason="signed off",
    )
    envelope = _envelope(mounts=mounts, sonar_by_domain={domain_id: sonar})
    assert envelope.storage_domains[0].hard_bound_bytes == 100


def test_admin_bound_cannot_raise_a_hard_proof(clock: FixedClock) -> None:
    mounts = _mounts(
        clock,
        "22 1 8:1 / /data rw - ext4 /dev/sda1 rw\n",
        {"/data": 100},
    )
    domain_id = envelope_domain(mounts)
    envelope = _envelope(
        mounts=mounts,
        admins=(AdministratorBound(domain_id=domain_id, bound_bytes=500,
            reason="guess"),),
    )
    assert envelope.storage_domains[0].hard_bound_bytes == 100


def test_admin_bound_used_when_nothing_harder_exists(clock: FixedClock) -> None:
    provider = LinuxMountProvider(
        mountinfo_text="22 1 0:23 / /tmp rw - tmpfs tmpfs rw\n",
        statvfs=lambda _path: (_ for _ in ()).throw(OSError("no")),
        clock=clock,
    )
    mounts = provider.observe(default_mount_settings(), clock.now())
    entry = mounts.entries[0]
    if is_resolved(entry.backing_store_id):
        domain_id = str(entry.backing_store_id)
    else:
        domain_id = entry.mount_id
    envelope = _envelope(
        mounts=mounts,
        admins=(AdministratorBound(domain_id=domain_id, bound_bytes=40,
            reason="operator"),),
    )
    assert envelope.storage_domains[0].hard_bound_bytes == 40
    strength = envelope.storage_domains[0].strength
    assert strength is EvidenceStrength.ADMINISTRATOR_BOUNDED


def test_stale_token_detects_changed_inputs() -> None:
    envelope = _envelope(memory=_memory(1000), execution_limit_bytes=NOT_MEASURED)
    assert is_stale(envelope, "other") is True
    assert is_stale(envelope, envelope.input_token) is False


def test_events_omit_paths() -> None:
    envelope = _envelope(memory=_memory(1000), execution_limit_bytes=NOT_MEASURED)
    events = capacity_events(envelope, clock=FixedClock(FIXED))
    blob = json.dumps([to_dict(event) for event in events])
    assert "/data" not in blob
    assert "vllm" not in blob.lower()
    assert all(event.privacy is PrivacyClass.OPERATIONAL for event in events)


class _Script(SonarMedia):
    def __init__(self, script: list[SonarFailure]) -> None:
        self._script = list(script)
        self.cleaned = False
        self.targets: list[int] = []

    def extend_to(self, nbytes: int) -> SonarWriteResult:
        self.targets.append(nbytes)
        failure = self._script.pop(0)
        committed = nbytes if failure is SonarFailure.NONE else 0
        return SonarWriteResult(failure, committed)

    def cleanup(self) -> bool:
        self.cleaned = True
        return True


def test_sonar_upward_then_quota_then_cleanup() -> None:
    media = _Script([SonarFailure.NONE, SonarFailure.EDQUOT, SonarFailure.NONE])
    evidence = run_sonar(
        media,
        upward=(64, 128),
        refine=(96,),
        downward=(48, 32),
        reported_available_bytes=200,
        reserve_bytes=0,
        max_tier_bytes=256,
    )
    assert evidence.status is SonarStatus.CONTRADICTED
    assert evidence.proven_lower_bytes == 96 or 64 in evidence.tiers_attempted
    assert 64 in evidence.tiers_attempted
    assert evidence.failure is SonarFailure.EDQUOT
    assert media.cleaned is True


def test_sonar_stops_before_consuming_reserve() -> None:
    media = _Script([])
    evidence = run_sonar(
        media,
        upward=(64,),
        refine=(),
        downward=(),
        reported_available_bytes=50,
        reserve_bytes=10,
        max_tier_bytes=256,
    )
    assert evidence.status is SonarStatus.STOPPED_FOR_RESERVE
    assert media.targets == []


def test_permission_does_not_look_like_a_quota( ) -> None:
    media = _Script([SonarFailure.PERMISSION])
    evidence = run_sonar(
        media,
        upward=(64,),
        refine=(),
        downward=(32,),
        reported_available_bytes=200,
        reserve_bytes=0,
        max_tier_bytes=256,
    )
    assert evidence.failure is SonarFailure.PERMISSION
    assert evidence.status is SonarStatus.UNRESOLVED


def test_file_sonar_extends_and_cleans_up(tmp_path: Path) -> None:
    media = FileSonarMedia(tmp_path)
    first = media.extend_to(100)
    second = media.extend_to(250)
    assert first.failure is SonarFailure.NONE
    assert second.committed_bytes == 250
    assert media.path.stat().st_size == 250
    assert media.cleanup() is True
    assert not media.path.exists()


def test_execution_limit_parser_rejects_unlimited(tmp_path: Path) -> None:
    unlimited = tmp_path / "memory.max"
    unlimited.write_text("max\n", encoding="utf-8")
    missing = tmp_path / "missing"
    assert not is_resolved(read_execution_limit(v2_path=unlimited, v1_path=missing))
    finite = tmp_path / "finite"
    finite.write_text("4096\n", encoding="utf-8")
    assert read_execution_limit(v2_path=finite, v1_path=missing) == 4096


def envelope_domain(mounts) -> str:
    entry = mounts.entries[0]
    if is_resolved(entry.backing_store_id):
        return str(entry.backing_store_id)
    return entry.mount_id
