"""Bounded empirical capacity search. Real writes, not sparse files.

This is the proprietary fallback of Storage Sonar. It characterizes the
writable capacity of a storage domain *before* runtime or model selection.
Hitting the configured ceiling without failure means:

    verified lower bound >= ceiling
    upper bound = UNKNOWN

It never means available capacity equals the ceiling.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.storage.contracts import (
    EmpiricalProbeEvidence,
    LifecycleState,
    ManagedResourceType,
    OwnershipRecord,
)
from kultrun.storage.failures import is_capacity_failure
from kultrun.storage.limits import (
    DEFAULT_EMERGENCY_RESERVE_BYTES,
    DEFAULT_FIRST_PROBE_BYTES,
    DEFAULT_MAX_EMPIRICAL_PROBE_BYTES,
    DEFAULT_PROBE_CHUNK_BYTES,
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    DEFAULT_SEARCH_GRANULARITY_BYTES,
    POLICY_VERSION,
)
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.ports import EmpiricalWriteBudget, EmpiricalWritePort

PRODUCER = Name("storage.empirical")
PROBE_DIRECTORY = ".kultrun-sonar"
PROBE_FILENAME = "kultrun-empirical.probe"


class EmpiricalStorageProbe:
    """Progressive real-write search with a hard exploration ceiling."""

    def __init__(
        self,
        writer: EmpiricalWritePort,
        clock: Clock,
        ownership: OwnershipService | None = None,
        *,
        max_probe_bytes: int = DEFAULT_MAX_EMPIRICAL_PROBE_BYTES,
        emergency_reserve_bytes: int = DEFAULT_EMERGENCY_RESERVE_BYTES,
        chunk_bytes: int = DEFAULT_PROBE_CHUNK_BYTES,
        first_bytes: int = DEFAULT_FIRST_PROBE_BYTES,
        granularity_bytes: int = DEFAULT_SEARCH_GRANULARITY_BYTES,
        timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    ) -> None:
        self._writer = writer
        self._clock = clock
        self._ownership = ownership
        self._max = max(1, max_probe_bytes)
        self._reserve = max(0, emergency_reserve_bytes)
        self._chunk = max(1, chunk_bytes)
        self._first = max(1, first_bytes)
        self._granularity = max(1, granularity_bytes)
        self._timeout = timeout_seconds

    def _timed_out(self, started_mono: float, started_at: datetime) -> bool:
        if self._timeout <= 0:
            return True
        if time.monotonic() - started_mono >= self._timeout:
            return True
        elapsed = self._clock.now() - started_at
        return elapsed.total_seconds() >= self._timeout

    def probe(
        self,
        host_id: HostId,
        mount_point: str,
        target_dir: Path,
        *,
        cancelled: object | None = None,
        known_low_bytes: int | None = None,
        native_available_bytes: int | None = None,
    ) -> EmpiricalProbeEvidence:
        """Search writable capacity. Cleans up on every exit path."""
        if known_low_bytes is not None and known_low_bytes <= 0:
            return self._empty(
                host_id,
                mount_point,
                target_dir,
                reason="known insufficient; skipped large writes",
            )
        ceiling = self._max
        if native_available_bytes is not None:
            usable = max(0, native_available_bytes - self._reserve)
            ceiling = min(ceiling, usable)
        if ceiling <= 0:
            return self._empty(
                host_id,
                mount_point,
                target_dir,
                reason="emergency reserve consumes remaining space",
            )
        workspace = Path(target_dir) / PROBE_DIRECTORY
        workspace.mkdir(parents=True, exist_ok=True)
        owned = self._mark(workspace, host_id, mount_point)
        probe_file = workspace / PROBE_FILENAME
        started = time.monotonic()
        started_at = self._clock.now()
        deadline = started_at + timedelta(seconds=max(0.0, self._timeout))
        budget = EmpiricalWriteBudget(
            chunk_bytes=self._chunk,
            deadline=deadline,
            max_bytes=ceiling,
            timeout_seconds=self._timeout,
        )
        lower = 0
        upper: int | None = None
        written_total = 0
        failure_code: Maybe[str] = NOT_PROVIDED
        failure_errno: Maybe[int] = NOT_PROVIDED
        interrupted = False
        ceiling_reached = False
        stop = _cancel_fn(cancelled)
        sizes = _search_sizes(self._first, ceiling, self._granularity)
        try:
            if self._timeout <= 0:
                interrupted = True
            for size in sizes:
                if interrupted:
                    break
                if stop() or self._timed_out(started, started_at):
                    interrupted = True
                    break
                if size > ceiling:
                    size = ceiling
                if size <= 0:
                    break
                if size <= lower:
                    continue
                result = self._writer.write_exactly(
                    probe_file, size, budget, cancelled=stop
                )
                written_total += result.written_bytes
                if result.failure_code is not None and is_capacity_failure(
                    result.failure_code
                ):
                    upper = size
                    failure_code = result.failure_code.value
                    failure_errno = (
                        result.failure_errno
                        if result.failure_errno is not None
                        else NOT_PROVIDED
                    )
                    if result.written_bytes > 0 and result.written_bytes < size:
                        lower = max(lower, result.written_bytes)
                    break
                if result.failure_code is not None:
                    interrupted = True
                    failure_code = result.failure_code.value
                    failure_errno = (
                        result.failure_errno
                        if result.failure_errno is not None
                        else NOT_PROVIDED
                    )
                    break
                lower = max(lower, size)
                if size >= ceiling:
                    ceiling_reached = True
                    break
            if (
                not interrupted
                and upper is not None
                and upper - lower > self._granularity
            ):
                lower, extra, more_code, more_errno, more_interrupt, new_upper = (
                    self._refine(
                        probe_file,
                        budget,
                        stop,
                        started,
                        started_at,
                        lower,
                        upper,
                    )
                )
                written_total += extra
                if more_code is not NOT_PROVIDED:
                    failure_code = more_code
                    upper = new_upper
                if more_errno is not NOT_PROVIDED:
                    failure_errno = more_errno
                interrupted = more_interrupt
            if lower >= ceiling and upper is None:
                ceiling_reached = True
        finally:
            cleanup_success = self._writer.remove(probe_file)
            shutil.rmtree(workspace, ignore_errors=True)
            cleanup_success = cleanup_success and not workspace.exists()
            if owned is not None and self._ownership is not None:
                self._ownership.forget(owned.ownership_id)
        elapsed = time.monotonic() - started
        confidence = (
            Confidence.MEDIUM if lower > 0 and not interrupted else Confidence.LOW
        )
        return EmpiricalProbeEvidence(
            host_id=host_id,
            mount_point=mount_point,
            target_path=str(workspace),
            max_probe_bytes=ceiling,
            bytes_physically_written=written_total,
            verified_lower_bound_bytes=lower if lower > 0 else NOT_PROVIDED,
            observed_failure_upper_bytes=upper if upper is not None else NOT_PROVIDED,
            search_granularity_bytes=self._granularity,
            probe_ceiling_reached=ceiling_reached,
            failure_code=failure_code,
            failure_errno=failure_errno,
            confidence=confidence,
            provenance=Provenance(
                producer=PRODUCER,
                producer_version=NOT_PROVIDED,
                observed_at=self._clock.now(),
                policy_version=POLICY_VERSION,
            ),
            cleanup_success=cleanup_success,
            elapsed_seconds=elapsed,
            interrupted=interrupted,
        )

    def _refine(
        self,
        probe_file: Path,
        budget: EmpiricalWriteBudget,
        stop: Callable[[], bool],
        started_mono: float,
        started_at: datetime,
        lower: int,
        upper: int,
    ) -> tuple[int, int, Maybe[str], Maybe[int], bool, int]:
        written = 0
        code: Maybe[str] = NOT_PROVIDED
        errno: Maybe[int] = NOT_PROVIDED
        interrupted = False
        low, high = lower, upper
        while high - low > self._granularity:
            if stop() or self._timed_out(started_mono, started_at):
                interrupted = True
                break
            mid = low + (high - low) // 2
            if mid <= low:
                break
            result = self._writer.write_exactly(probe_file, mid, budget, cancelled=stop)
            written += result.written_bytes
            if result.failure_code is not None and is_capacity_failure(
                result.failure_code
            ):
                high = mid
                code = result.failure_code.value
                errno = (
                    result.failure_errno
                    if result.failure_errno is not None
                    else NOT_PROVIDED
                )
            elif result.failure_code is not None:
                interrupted = True
                code = result.failure_code.value
                break
            else:
                low = mid
        return low, written, code, errno, interrupted, high

    def _mark(
        self, workspace: Path, host_id: HostId, mount_point: str
    ) -> OwnershipRecord | None:
        del mount_point
        if self._ownership is None:
            return None
        from kultrun.storage.contracts import CleanupPolicy

        return self._ownership.assert_owned(
            workspace,
            host_id,
            ManagedResourceType.SONAR_PROBE,
            lifecycle=LifecycleState.DISPOSABLE,
            cleanup_policy=CleanupPolicy.DISPOSABLE,
        )

    def _empty(
        self, host_id: HostId, mount_point: str, target_dir: Path, *, reason: str
    ) -> EmpiricalProbeEvidence:
        del reason
        return EmpiricalProbeEvidence(
            host_id=host_id,
            mount_point=mount_point,
            target_path=str(target_dir),
            max_probe_bytes=self._max,
            bytes_physically_written=0,
            verified_lower_bound_bytes=NOT_PROVIDED,
            observed_failure_upper_bytes=NOT_PROVIDED,
            search_granularity_bytes=self._granularity,
            probe_ceiling_reached=False,
            confidence=Confidence.LOW,
            provenance=Provenance(
                producer=PRODUCER,
                producer_version=NOT_PROVIDED,
                observed_at=self._clock.now(),
                policy_version=POLICY_VERSION,
            ),
            cleanup_success=True,
        )


def _cancel_fn(cancelled: object | None) -> Callable[[], bool]:
    if cancelled is None:
        return lambda: False
    if callable(cancelled):
        fn = cancelled

        def _call() -> bool:
            return bool(fn())

        return _call

    def _flag() -> bool:
        return bool(getattr(cancelled, "cancelled", False))

    return _flag


def _search_sizes(first: int, ceiling: int, granularity: int) -> tuple[int, ...]:
    """Double until the ceiling, then the ceiling itself."""
    sizes: list[int] = []
    size = min(first, ceiling)
    while size < ceiling:
        sizes.append(size)
        nxt = size * 2
        if nxt <= size:
            break
        size = nxt
    if not sizes or sizes[-1] != ceiling:
        sizes.append(ceiling)
    del granularity
    return tuple(sizes)
