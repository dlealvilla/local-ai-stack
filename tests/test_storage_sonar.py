"""Empirical fallback Sonar. Fault-injected; never fills a development disk."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import StorageFailureCode
from kultrun.storage.failures import classify_errno
from kultrun.storage.ports import (
    EmpiricalWriteBudget,
    EmpiricalWriteResult,
)
from kultrun.storage.sonar import EmpiricalStorageProbe, _search_sizes
from tests.test_capacity import INSTANT

GIB = 1024**3
HOST = HostId.generate()


class FakeVolume:
    """In-memory capacity. Writes never touch a real disk."""

    def __init__(
        self,
        capacity: int,
        *,
        fail_with: StorageFailureCode | None = None,
        fail_at: int | None = None,
        io_error: bool = False,
        permission: bool = False,
    ) -> None:
        self.capacity = capacity
        self.fail_with = fail_with
        self.fail_at = fail_at if fail_at is not None else capacity + 1
        self.io_error = io_error
        self.permission = permission
        self.written = 0
        self.removed = False
        self.calls: list[int] = []

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> EmpiricalWriteResult:
        del path, budget
        self.calls.append(size)
        if cancelled is not None and cancelled():
            return EmpiricalWriteResult(written_bytes=0, detail="cancelled")
        if self.permission:
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
        if size > self.fail_at or size > self.capacity:
            code = self.fail_with or StorageFailureCode.STORAGE_SPACE_EXHAUSTED
            return EmpiricalWriteResult(
                written_bytes=0,
                failure_code=code,
                failure_errno=(
                    122 if code is StorageFailureCode.STORAGE_QUOTA_EXCEEDED else 28
                ),
            )
        self.written = max(self.written, size)
        return EmpiricalWriteResult(written_bytes=size)

    def remove(self, path: Path) -> bool:
        del path
        self.removed = True
        return True


def _probe(
    volume: FakeVolume,
    *,
    max_probe_bytes: int = 64,
    first_bytes: int = 4,
    granularity_bytes: int = 4,
    timeout_seconds: float = 60,
    emergency_reserve_bytes: int = 0,
) -> EmpiricalStorageProbe:
    return EmpiricalStorageProbe(
        volume,
        FixedClock(INSTANT),
        max_probe_bytes=max_probe_bytes,
        first_bytes=first_bytes,
        granularity_bytes=granularity_bytes,
        timeout_seconds=timeout_seconds,
        emergency_reserve_bytes=emergency_reserve_bytes,
    )


def test_search_sizes_are_progressive() -> None:
    assert _search_sizes(4, 32, 4) == (4, 8, 16, 32)


def test_lower_bound_when_ceiling_is_reached(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, max_probe_bytes=32).probe(HOST, "/pool", tmp_path)
    assert evidence.verified_lower_bound_bytes == 32
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert evidence.probe_ceiling_reached is True
    assert evidence.cleanup_success is True
    assert volume.removed is True
    assert max(volume.calls) <= 32


def test_failure_bracket(tmp_path: Path) -> None:
    volume = FakeVolume(20, fail_at=20)
    evidence = _probe(volume, max_probe_bytes=32, first_bytes=4).probe(
        HOST, "/pool", tmp_path
    )
    assert evidence.verified_lower_bound_bytes == 20
    assert evidence.observed_failure_upper_bytes == 24
    assert evidence.probe_ceiling_reached is False


def test_edquot_is_quota_exceeded(tmp_path: Path) -> None:
    volume = FakeVolume(
        8,
        fail_with=StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
        fail_at=8,
    )
    evidence = _probe(volume, max_probe_bytes=32, first_bytes=4).probe(
        HOST, "/pool", tmp_path
    )
    assert evidence.failure_code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value


def test_enospc_is_space_exhausted(tmp_path: Path) -> None:
    volume = FakeVolume(
        8,
        fail_with=StorageFailureCode.STORAGE_SPACE_EXHAUSTED,
        fail_at=8,
    )
    evidence = _probe(volume, max_probe_bytes=32, first_bytes=4).probe(
        HOST, "/pool", tmp_path
    )
    assert evidence.failure_code == StorageFailureCode.STORAGE_SPACE_EXHAUSTED.value


def test_permission_and_io_do_not_claim_capacity(tmp_path: Path) -> None:
    denied = _probe(FakeVolume(100, permission=True), max_probe_bytes=16).probe(
        HOST, "/pool", tmp_path
    )
    assert denied.interrupted is True
    assert not is_resolved(denied.verified_lower_bound_bytes)
    io = _probe(FakeVolume(100, io_error=True), max_probe_bytes=16).probe(
        HOST, "/pool", tmp_path
    )
    assert io.failure_code == StorageFailureCode.STORAGE_IO_FAILURE.value


def test_interruption_stops_writes(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, max_probe_bytes=32).probe(
        HOST, "/pool", tmp_path, cancelled=lambda: True
    )
    assert evidence.interrupted is True
    assert volume.calls == [] or evidence.bytes_physically_written == 0


def test_timeout_interrupts(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, max_probe_bytes=32, timeout_seconds=0).probe(
        HOST, "/pool", tmp_path
    )
    assert evidence.interrupted is True
    assert volume.calls == []


def test_emergency_headroom_reduces_ceiling(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, max_probe_bytes=32, emergency_reserve_bytes=20).probe(
        HOST, "/pool", tmp_path, native_available_bytes=24
    )
    assert evidence.max_probe_bytes == 4
    assert max(volume.calls or [0]) <= 4


def test_twenty_five_gib_means_ceiling_not_available(tmp_path: Path) -> None:
    """25 GiB is exploration budget. Success is lower-bound, not available=25."""
    volume = FakeVolume(100 * GIB)
    evidence = EmpiricalStorageProbe(
        volume,
        FixedClock(INSTANT),
        max_probe_bytes=25 * GIB,
        first_bytes=25 * GIB,
        granularity_bytes=25 * GIB,
        emergency_reserve_bytes=0,
    ).probe(HOST, "/pool", tmp_path)
    assert evidence.probe_ceiling_reached is True
    assert evidence.verified_lower_bound_bytes == 25 * GIB
    assert not is_resolved(evidence.observed_failure_upper_bytes)
    assert evidence.max_probe_bytes == 25 * GIB


def test_no_writes_beyond_configured_maximum(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    _probe(volume, max_probe_bytes=16, first_bytes=4).probe(HOST, "/pool", tmp_path)
    assert all(size <= 16 for size in volume.calls)


def test_classify_errno() -> None:
    import errno

    assert classify_errno(errno.EDQUOT) is StorageFailureCode.STORAGE_QUOTA_EXCEEDED
    assert classify_errno(errno.ENOSPC) is StorageFailureCode.STORAGE_SPACE_EXHAUSTED


def test_skips_large_writes_when_known_low(tmp_path: Path) -> None:
    volume = FakeVolume(10_000)
    evidence = _probe(volume, max_probe_bytes=32).probe(
        HOST, "/pool", tmp_path, known_low_bytes=0
    )
    assert volume.calls == []
    assert evidence.bytes_physically_written == 0
