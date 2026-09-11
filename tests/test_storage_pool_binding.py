"""Pool-bound Sonar targeting and reserve-first capacity-failure recovery."""

from __future__ import annotations

import errno
from dataclasses import replace
from pathlib import Path

import pytest

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.cleanup import step0_cleanup
from kultrun.storage.contracts import (
    CleanupPolicy,
    LifecycleState,
    ManagedResourceType,
    StorageEvidenceStatus,
    StorageFailureCode,
)
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.probe_target import (
    StorageTargetMismatchError,
    probe_parent_for,
)
from kultrun.storage.probes import ProbeRegistry
from kultrun.storage.sonar import PROBE_DIRECTORY, PROBE_FILENAME, RESERVE_FILENAME
from kultrun.storage.topology import pools_from_host
from tests.test_capacity import INSTANT, host, mount
from tests.test_storage_sonar import HOST, FakeVolume, _probe
from tests.test_storage_specialists import _emp, _RecordingSonar

GIB = 1024**3


def _two_pools(tmp_path: Path):
    overlay = tmp_path / "overlay"
    workspace = tmp_path / "workspace"
    overlay.mkdir()
    workspace.mkdir()
    subject = host(
        mounts=(
            mount(str(overlay), "overlay", free=30 * GIB, total=32 * GIB),
            mount(str(workspace), "fuse", free=176 * GIB, total=180 * GIB),
        )
    )
    pools = pools_from_host(subject)
    overlay_pool = next(item for item in pools if item.mount_point == str(overlay))
    fuse_pool = next(item for item in pools if item.mount_point == str(workspace))
    return subject, overlay, workspace, overlay_pool, fuse_pool, pools


def test_sonar_for_overlay_resolves_on_overlay(tmp_path: Path) -> None:
    _subject, overlay, workspace, overlay_pool, fuse_pool, pools = _two_pools(tmp_path)
    recorder = _RecordingSonar(_emp(lower=16 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=recorder,
        use_live_native=False,
    )
    result = service.characterize(_subject, run_cleanup=False, run_empirical=True)
    assert str(overlay) not in result.empirical_ran
    assert str(workspace) in result.empirical_ran
    assert recorder.calls == 1
    assert recorder.kwargs[0]["intended_pool"].mount_point == str(workspace)
    assert probe_parent_for(overlay_pool, pools) == Path(overlay)
    assert probe_parent_for(fuse_pool, pools) == Path(workspace)
    overlay_parent = str(probe_parent_for(overlay_pool, pools))
    fuse_parent = str(probe_parent_for(fuse_pool, pools))
    assert not overlay_parent.startswith(str(workspace))
    assert not fuse_parent.startswith(str(overlay) + "/")
    assert result.evidence[str(overlay)].status is StorageEvidenceStatus.AUTHORITATIVE


def test_mismatched_override_is_not_used(tmp_path: Path) -> None:
    _subject, overlay, workspace, overlay_pool, _fuse, pools = _two_pools(tmp_path)
    parent = probe_parent_for(overlay_pool, pools, override=workspace)
    assert parent == Path(overlay)


def test_target_mismatch_refuses_before_write(tmp_path: Path) -> None:
    subject, _overlay, workspace, overlay_pool, _fuse, pools = _two_pools(tmp_path)
    volume = FakeVolume(10_000)
    with pytest.raises(StorageTargetMismatchError) as error:
        _probe(volume).probe(
            subject.host_id,
            overlay_pool.mount_point,
            workspace,
            intended_pool=overlay_pool,
            pools=pools,
        )
    assert error.value.context["reason"] == "storage_target_mismatch"
    assert volume.calls == []
    assert not (workspace / PROBE_DIRECTORY / RESERVE_FILENAME).exists()
    assert not (workspace / PROBE_DIRECTORY / PROBE_FILENAME).exists()


def test_edquot_32_to_48_retains_32_and_releases_reserve_first(
    tmp_path: Path,
) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=32,
    )
    probe = _probe(volume)
    evidence = probe.probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 32
    assert evidence.observed_failure_upper_bytes == 48
    assert evidence.failure_code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value
    assert probe.recovery_trace[:4] == [
        "capture",
        "release_reserve",
        "persist",
        "remove_probe",
    ]
    assert volume.removed.index(RESERVE_FILENAME) < volume.removed.index(PROBE_FILENAME)
    assert evidence.cleanup_success is True
    assert volume.files == {}


def test_enospc_32_to_48_same_recovery_order(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_SPACE_EXHAUSTED,
        fail_at=32,
    )
    probe = _probe(volume)
    evidence = probe.probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 32
    assert evidence.observed_failure_upper_bytes == 48
    assert evidence.failure_code == StorageFailureCode.STORAGE_SPACE_EXHAUSTED.value
    assert probe.recovery_trace[:4] == [
        "capture",
        "release_reserve",
        "persist",
        "remove_probe",
    ]
    assert evidence.cleanup_success is True


def test_log_write_failure_does_not_block_reserve_release(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=32,
    )

    def persist(item) -> None:
        if is_resolved(item.failure_code):
            raise OSError(errno.ENOSPC, "log volume full")

    probe = _probe(volume, on_progress=persist)
    evidence = probe.probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 32
    assert "release_reserve" in probe.recovery_trace
    assert "remove_probe" in probe.recovery_trace
    assert evidence.cleanup_success is True
    assert volume.files == {}


def test_evidence_write_succeeds_only_after_reserve_release(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=32,
    )
    persisted: list[object] = []

    def persist(item) -> None:
        reserve_held = any(Path(path).name == RESERVE_FILENAME for path in volume.files)
        if is_resolved(item.failure_code) and reserve_held:
            raise OSError(errno.ENOSPC, "need reserve headroom")
        persisted.append(item)

    probe = _probe(volume, on_progress=persist)
    evidence = probe.probe(HOST, "/pool", tmp_path)
    failed = [
        item
        for item in persisted
        if is_resolved(item.failure_code)
        and item.failure_code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value
    ]
    assert failed
    assert failed[0].reserve_released is True
    assert failed[0].verified_lower_bound_bytes == 32
    assert evidence.cleanup_success is True


def test_running_empirical_is_not_promoted(tmp_path: Path) -> None:
    subject, _overlay, workspace, _a, _b, _pools = _two_pools(tmp_path)
    running = replace(_emp(lower=32 * GIB), run_state="running", cleanup_success=False)
    recorder = _RecordingSonar(running)
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=recorder,
        use_live_native=False,
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    fuse = result.evidence[str(workspace)]
    assert not is_resolved(fuse.authorizing_available_bytes)
    assert fuse.status is StorageEvidenceStatus.UNRESOLVED


def test_crash_after_reserve_release_cleans_owned_probe(tmp_path: Path) -> None:
    subject, _overlay, workspace, _a, _b, _pools = _two_pools(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    ownership = OwnershipService(
        FileStore(state / "records"), FixedClock(INSTANT), state
    )
    leftover = workspace / PROBE_DIRECTORY
    ownership.assert_owned(
        leftover,
        subject.host_id,
        ManagedResourceType.SONAR_PROBE,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
        allowed_roots=(leftover,),
    )
    (leftover / PROBE_FILENAME).write_bytes(b"partial-32g")
    sentinel = workspace / "customer.txt"
    sentinel.write_text("keep")
    report = step0_cleanup(
        ownership,
        subject.host_id,
        allowed_roots=(state, leftover),
        extra_roots=(leftover,),
    )
    assert report.removed >= 1
    assert not leftover.exists()
    assert sentinel.exists()


def test_crash_before_promotion_does_not_invent_capacity(tmp_path: Path) -> None:
    subject, _overlay, workspace, _a, _b, _pools = _two_pools(tmp_path)
    leftover = workspace / PROBE_DIRECTORY
    leftover.mkdir()
    (leftover / PROBE_FILENAME).write_bytes(b"partial")
    (leftover / RESERVE_FILENAME).write_bytes(b"r")
    volume = FakeVolume(10_000, fail_at=32)
    evidence = _probe(volume).probe(subject.host_id, str(workspace), workspace)
    assert not leftover.exists()
    assert evidence.verified_lower_bound_bytes == 32
    assert evidence.run_state != "running"


def test_unknown_file_is_not_deleted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    leftover = workspace / PROBE_DIRECTORY
    leftover.mkdir()
    (leftover / PROBE_FILENAME).write_bytes(b"partial")
    stranger = leftover / "notes.txt"
    stranger.write_text("not ours")
    volume = FakeVolume(10_000)
    evidence = _probe(volume).probe(HOST, str(workspace), workspace)
    assert stranger.exists()
    assert evidence.interrupted is False
    assert stranger.read_text() == "not ours"


def test_multi_pool_evidence_is_independent(tmp_path: Path) -> None:
    subject, overlay, workspace, overlay_pool, fuse_pool, _pools = _two_pools(tmp_path)
    recorder = _RecordingSonar(_emp(lower=32 * GIB))
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=recorder,
        use_live_native=False,
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    overlay_item = result.evidence[str(overlay)]
    fuse_item = result.evidence[str(workspace)]
    assert overlay_item.quota_identity != fuse_item.quota_identity
    assert overlay_item.pool_fingerprint != fuse_item.pool_fingerprint
    assert overlay_item.status is StorageEvidenceStatus.AUTHORITATIVE
    assert overlay_item.authorizing_available_bytes == 30 * GIB
    assert fuse_item.operational_available_bytes == 32 * GIB
    assert overlay_pool.fingerprint != fuse_pool.fingerprint
    assert str(overlay) not in result.empirical_ran
    assert str(workspace) in result.empirical_ran


def test_permission_failure_is_not_a_capacity_bound(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, permission=True, permission_on=PROBE_FILENAME)
    probe = _probe(volume)
    evidence = probe.probe(HOST, "/pool", tmp_path)
    assert evidence.interrupted is True
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert "capture" not in probe.recovery_trace
