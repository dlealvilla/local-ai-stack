"""Storage Sonar V2. Fault-injected; never fills a development disk."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.storage.empirical_write import RealWritePort
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import (
    CleanupPolicy,
    LifecycleState,
    ManagedResourceType,
    StorageFailureCode,
)
from kultrun.storage.failures import classify_errno
from kultrun.storage.limits import SONAR_ALGORITHM_VERSION
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.payload import PAYLOAD_VERSION
from kultrun.storage.ports import EmpiricalWriteBudget, EmpiricalWriteResult
from kultrun.storage.sonar import (
    PROBE_DIRECTORY,
    PROBE_FILENAME,
    RESERVE_FILENAME,
    EmpiricalStorageProbe,
)
from tests.test_capacity import INSTANT

HOST = HostId.generate()


class FakeVolume:
    """In-memory capacity. Writes never touch a real disk."""

    def __init__(
        self,
        capacity: int,
        *,
        fail_with: StorageFailureCode | None = None,
        fail_at: int | None = None,
        fail_reserve: bool = False,
        io_error: bool = False,
        permission: bool = False,
        permission_on: str | None = None,
        remove_fails: bool = False,
    ) -> None:
        self.capacity = capacity
        self.fail_with = fail_with
        self.fail_at = fail_at if fail_at is not None else capacity + 1
        self.fail_reserve = fail_reserve
        self.io_error = io_error
        self.permission = permission
        self.permission_on = permission_on
        self.remove_fails = remove_fails
        self.files: dict[str, int] = {}
        self.calls: list[tuple[str, int, int]] = []
        self.removed: list[str] = []

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> EmpiricalWriteResult:
        del budget
        name = path.name
        if cancelled is not None and cancelled():
            return EmpiricalWriteResult(written_bytes=0, detail="cancelled")
        if self.permission and (
            self.permission_on is None or name == self.permission_on
        ):
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=StorageFailureCode.STORAGE_PERMISSION_DENIED,
                failure_errno=13,
            )
        if self.io_error:
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=StorageFailureCode.STORAGE_IO_FAILURE,
                failure_errno=5,
            )
        current = self.files.get(str(path), 0)
        additional = max(0, size - current)
        if additional == 0:
            return EmpiricalWriteResult(written_bytes=0, detail="already at target")
        if name == RESERVE_FILENAME and self.fail_reserve:
            code = self.fail_with or StorageFailureCode.STORAGE_SPACE_EXHAUSTED
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=code,
                failure_errno=(
                    122 if code is StorageFailureCode.STORAGE_QUOTA_EXCEEDED else 28
                ),
            )
        if name == PROBE_FILENAME and size > self.fail_at:
            code = self.fail_with or StorageFailureCode.STORAGE_SPACE_EXHAUSTED
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=code,
                failure_errno=(
                    122 if code is StorageFailureCode.STORAGE_QUOTA_EXCEEDED else 28
                ),
            )
        occupied = sum(self.files.values())
        if occupied + additional > self.capacity:
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=StorageFailureCode.STORAGE_SPACE_EXHAUSTED,
                failure_errno=28,
            )
        self.files[str(path)] = size
        self.calls.append((name, size, additional))
        return EmpiricalWriteResult(written_bytes=additional)

    def remove(self, path: Path) -> bool:
        self.removed.append(path.name)
        if self.remove_fails:
            return False
        self.files.pop(str(path), None)
        return True

    def probe_additional(self) -> list[int]:
        return [item[2] for item in self.calls if item[0] == PROBE_FILENAME]


def _probe(
    volume: FakeVolume,
    *,
    timeout_seconds: float = 60,
    reserve_bytes: int = 1,
    on_progress: Callable | None = None,
    ownership: OwnershipService | None = None,
) -> EmpiricalStorageProbe:
    return EmpiricalStorageProbe(
        volume,
        FixedClock(INSTANT),
        ownership,
        unit_bytes=1,
        reserve_bytes=reserve_bytes,
        chunk_bytes=8,
        timeout_seconds=timeout_seconds,
        on_progress=on_progress,
    )


def test_ceiling_256_is_a_lower_bound(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 256
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert evidence.probe_ceiling_reached is True
    assert evidence.cleanup_success is True
    assert evidence.algorithm_version == SONAR_ALGORITHM_VERSION
    assert evidence.payload_version == PAYLOAD_VERSION
    assert evidence.completed_tier_units[:5] == (16, 24, 32, 48, 64)
    assert 256 in evidence.completed_tier_units
    assert volume.files == {}


def test_grow_64_to_128_writes_only_the_additional_64(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    _probe(volume).probe(HOST, "/pool", tmp_path)
    extra = [item[2] for item in volume.calls if item[0] == PROBE_FILENAME]
    assert 128 in [item[1] for item in volume.calls if item[0] == PROBE_FILENAME]
    at_128 = [item[2] for item in volume.calls if item[1] == 128]
    assert at_128 == [64]
    at_256 = [item[2] for item in volume.calls if item[1] == 256]
    assert at_256 == [128]
    assert sum(extra) == 256


def test_failure_bracket_preserves_last_official_checkpoint(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, fail_at=32)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 32
    assert evidence.observed_failure_upper_bytes == 48
    assert 20 not in evidence.completed_tier_units
    assert evidence.probe_ceiling_reached is False


def test_partial_bytes_are_not_a_new_tier(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, fail_at=20)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 16
    assert evidence.observed_failure_upper_bytes == 24
    assert evidence.completed_tier_units == (16,)


def test_edquot_is_quota_exceeded_and_releases_reserve_first(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=48,
    )
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.failure_code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value
    assert evidence.verified_lower_bound_bytes == 48
    assert RESERVE_FILENAME in volume.removed
    first_capacity = volume.removed.index(RESERVE_FILENAME)
    probe_pos = volume.removed.index(PROBE_FILENAME)
    assert first_capacity < probe_pos


def test_enospc_is_space_exhausted(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_with=StorageFailureCode.STORAGE_SPACE_EXHAUSTED,
        fail_at=48,
    )
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.failure_code == StorageFailureCode.STORAGE_SPACE_EXHAUSTED.value
    assert evidence.verified_lower_bound_bytes == 48


def test_permission_and_io_do_not_claim_capacity(tmp_path: Path) -> None:
    denied = _probe(FakeVolume(100, permission=True)).probe(HOST, "/pool", tmp_path)
    assert denied.interrupted is True
    assert not is_resolved(denied.verified_lower_bound_bytes)
    assert not is_resolved(denied.observed_failure_upper_bytes)
    io = _probe(FakeVolume(100, io_error=True)).probe(HOST, "/pool", tmp_path)
    assert io.failure_code == StorageFailureCode.STORAGE_IO_FAILURE.value
    assert not is_resolved(io.observed_failure_upper_bytes)


def test_interruption_stops_writes(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path, cancelled=lambda: True)
    assert evidence.interrupted is True
    assert not is_resolved(evidence.verified_lower_bound_bytes)


def test_timeout_keeps_completed_checkpoint(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, timeout_seconds=0).probe(HOST, "/pool", tmp_path)
    assert evidence.interrupted is True
    assert volume.probe_additional() == []
    assert not is_resolved(evidence.observed_failure_upper_bytes)


def test_reserve_failure_is_very_low_and_does_not_start_64(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, fail_reserve=True)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.run_state == "very_low"
    assert not is_resolved(evidence.verified_lower_bound_bytes)
    assert all(item[0] != PROBE_FILENAME for item in volume.calls)


def test_reserve_edquot_does_not_start_tree(tmp_path: Path) -> None:
    volume = FakeVolume(
        10_000,
        fail_reserve=True,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
    )
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.run_state == "very_low"
    assert evidence.failure_code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value
    assert all(item[0] != PROBE_FILENAME for item in volume.calls)


def test_reserve_permission_is_not_a_capacity_bound(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, permission=True, permission_on=RESERVE_FILENAME)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.interrupted is True
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert all(item[0] != PROBE_FILENAME for item in volume.calls)


def test_native_figure_does_not_cap_or_skip_sonar(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume).probe(
        HOST, "/pool", tmp_path, native_available_bytes=4, known_low_bytes=0
    )
    assert evidence.verified_lower_bound_bytes == 256


def test_mid_probe_progress_is_not_complete(tmp_path: Path) -> None:
    seen: list[str] = []

    def capture(item) -> None:
        state = item.run_state
        if is_resolved(state):
            seen.append(state)

    volume = FakeVolume(10_000)
    evidence = _probe(volume, on_progress=capture).probe(HOST, "/pool", tmp_path)
    assert "running" in seen
    assert evidence.run_state == "complete"
    assert evidence.cleanup_success is True


def test_leftover_workspace_is_recovered_not_promoted(tmp_path: Path) -> None:
    leftover = tmp_path / PROBE_DIRECTORY
    leftover.mkdir()
    (leftover / PROBE_FILENAME).write_bytes(b"partial")
    (leftover / RESERVE_FILENAME).write_bytes(b"r")
    volume = FakeVolume(10_000)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert not leftover.exists()
    assert evidence.verified_lower_bound_bytes == 256
    assert evidence.cleanup_success is True


def test_cleanup_failure_is_visible(tmp_path: Path) -> None:
    volume = FakeVolume(10_000, remove_fails=True)
    evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
    assert evidence.cleanup_success is False
    assert evidence.run_state == "cleanup_failed"


def test_owned_probe_and_reserve_are_disposable(tmp_path: Path) -> None:
    ownership = OwnershipService(
        FileStore(tmp_path / "records"), FixedClock(INSTANT), tmp_path
    )
    volume = FakeVolume(10_000)
    progress: list[object] = []
    evidence = _probe(volume, ownership=ownership, on_progress=progress.append).probe(
        HOST, "/pool", tmp_path, quota_identity="ext4:/pool"
    )
    assert evidence.cleanup_success is True
    assert not (tmp_path / PROBE_DIRECTORY).exists()
    marker_seen = any(getattr(item, "reserve_established", False) for item in progress)
    assert marker_seen is True


def test_step0_cleans_owned_sonar_and_spares_unrelated(tmp_path: Path) -> None:
    from kultrun.storage.cleanup import step0_cleanup

    ownership = OwnershipService(
        FileStore(tmp_path / "records"), FixedClock(INSTANT), tmp_path
    )
    workspace = tmp_path / PROBE_DIRECTORY
    ownership.assert_owned(
        workspace,
        HOST,
        ManagedResourceType.SONAR_PROBE,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
        quota_identity="ext4:/pool",
    )
    (workspace / PROBE_FILENAME).write_bytes(b"x")
    sentinel = tmp_path / "customer.txt"
    sentinel.write_text("keep")
    report = step0_cleanup(ownership, HOST)
    assert not workspace.exists()
    assert sentinel.exists()
    assert report.removed >= 1


def test_small_real_write_grows_and_is_nonzero(tmp_path: Path) -> None:
    port = RealWritePort()
    target = tmp_path / "probe.bin"
    budget = EmpiricalWriteBudget(chunk_bytes=1024)
    first = port.write_exactly(target, 4096, budget)
    second = port.write_exactly(target, 8192, budget)
    assert first.written_bytes == 4096
    assert second.written_bytes == 4096
    data = target.read_bytes()
    assert len(data) == 8192
    assert any(byte != 0 for byte in data)
    assert port.remove(target) is True
    assert not target.exists()


def test_classify_errno() -> None:
    import errno

    assert classify_errno(errno.EDQUOT) is StorageFailureCode.STORAGE_QUOTA_EXCEEDED
    assert classify_errno(errno.ENOSPC) is StorageFailureCode.STORAGE_SPACE_EXHAUSTED


def test_physical_tree_cases(tmp_path: Path) -> None:
    cases = (
        (1000, 256, None),
        (192, 192, 256),
        (128, 128, 192),
        (96, 96, 128),
        (64, 64, 96),
        (48, 48, 64),
        (32, 32, 48),
        (24, 24, 32),
        (16, 16, 24),
        (0, None, 16),
    )
    for fail_at, lower, upper in cases:
        volume = FakeVolume(10_000, fail_at=fail_at)
        evidence = _probe(volume).probe(HOST, "/pool", tmp_path)
        if lower is None:
            assert not is_resolved(evidence.verified_lower_bound_bytes)
        else:
            assert evidence.verified_lower_bound_bytes == lower
        if upper is None:
            assert not is_resolved(evidence.observed_failure_upper_bytes)
        else:
            assert evidence.observed_failure_upper_bytes == upper
