"""HOST-mode Storage Sonar V2. Real writes, owned reserve, official tiers.

This is the proprietary fallback of Storage Sonar. It characterizes the
writable capacity of a storage domain *before* runtime or model selection.
Hitting the top tier without failure means:

    verified lower bound >= 256 units
    upper bound = UNKNOWN

It never means available capacity equals that ceiling. Partial file size
is never a new tier; only completed fsynced official checkpoints count.
"""

from __future__ import annotations

import hashlib
import shutil
import time
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    LOCAL_OWNER_FILENAME,
    CleanupPolicy,
    EmpiricalProbeEvidence,
    LifecycleState,
    ManagedResourceType,
    OwnershipRecord,
    StoragePool,
)
from kultrun.storage.failures import is_capacity_failure
from kultrun.storage.limits import (
    DEFAULT_EMERGENCY_RESERVE_BYTES,
    DEFAULT_PROBE_CHUNK_BYTES,
    DEFAULT_PROBE_TIMEOUT_SECONDS,
    POLICY_VERSION,
    SONAR_ALGORITHM_VERSION,
    SONAR_UNIT_BYTES,
)
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.payload import PAYLOAD_VERSION
from kultrun.storage.ports import EmpiricalWriteBudget, EmpiricalWritePort
from kultrun.storage.probe_target import PROBE_DIRECTORY, assert_same_domain
from kultrun.storage.sonar_tree import (
    CHECKPOINTS_TO_64,
    SONAR_TIER_UNITS,
    SonarAttempt,
    classify_sonar_tree,
    specialist_bracket,
)

PRODUCER = Name("storage.empirical")
PROBE_FILENAME = "kultrun-empirical.probe"
RESERVE_FILENAME = "kultrun-sonar.reserve"
RUN_RUNNING = "running"
RUN_COMPLETE = "complete"
RUN_INTERRUPTED = "interrupted_recovered"
RUN_CLEANUP_FAILED = "cleanup_failed"
RUN_VERY_LOW = "very_low"
CORROBORATION_CONFIRMED = "confirmed_bracketed"
CORROBORATION_NOT_CONTRADICTED = "not_contradicted"
CORROBORATION_LOWER_ONLY = "lower_only"
CORROBORATION_INCONCLUSIVE = "inconclusive"
CORROBORATION_LIMITED = "limited"
CORROBORATION_CONTRADICTED = "contradicted"
_OWNED_SONAR_NAMES = frozenset(
    {PROBE_FILENAME, RESERVE_FILENAME, LOCAL_OWNER_FILENAME}
)


class EmpiricalStorageProbe:
    """Official-tier real-write search with a physical emergency reserve."""

    def __init__(
        self,
        writer: EmpiricalWritePort,
        clock: Clock,
        ownership: OwnershipService | None = None,
        *,
        unit_bytes: int = SONAR_UNIT_BYTES,
        reserve_bytes: int | None = None,
        chunk_bytes: int = DEFAULT_PROBE_CHUNK_BYTES,
        timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
        max_tier_units: int = 256,
        on_progress: Callable[[EmpiricalProbeEvidence], None] | None = None,
        max_probe_bytes: int | None = None,
        emergency_reserve_bytes: int | None = None,
        first_bytes: int | None = None,
        granularity_bytes: int | None = None,
    ) -> None:
        del first_bytes, granularity_bytes, max_probe_bytes
        self._writer = writer
        self._clock = clock
        self._ownership = ownership
        self._unit = max(1, unit_bytes)
        self._reserve = (
            reserve_bytes
            if reserve_bytes is not None
            else (
                emergency_reserve_bytes
                if emergency_reserve_bytes is not None
                else DEFAULT_EMERGENCY_RESERVE_BYTES
            )
        )
        self._chunk = max(1, chunk_bytes)
        self._timeout = timeout_seconds
        self._max_tier = max_tier_units if max_tier_units in SONAR_TIER_UNITS else 256
        self._on_progress = on_progress
        self.recovery_trace: list[str] = []

    def probe(
        self,
        host_id: HostId,
        mount_point: str,
        target_dir: Path,
        *,
        cancelled: object | None = None,
        known_low_bytes: int | None = None,
        native_available_bytes: int | None = None,
        quota_identity: Maybe[str] = NOT_PROVIDED,
        pool_fingerprint: Maybe[str] = NOT_PROVIDED,
        corroborate_bytes: int | None = None,
        intended_pool: StoragePool | None = None,
        pools: Sequence[StoragePool] | None = None,
    ) -> EmpiricalProbeEvidence:
        """Search writable capacity. Cleans probe and reserve on every exit.

        When ``corroborate_bytes`` is set, Sonar brackets that specialist
        candidate instead of walking the full tree, unless a capacity
        failure strictly below the candidate contradicts it.
        """
        del known_low_bytes, native_available_bytes
        self.recovery_trace = []
        workspace = Path(target_dir) / PROBE_DIRECTORY
        if intended_pool is not None:
            assert_same_domain(target_dir, intended_pool, pools or (intended_pool,))
            assert_same_domain(workspace, intended_pool, pools or (intended_pool,))
        probe_file = workspace / PROBE_FILENAME
        reserve_file = workspace / RESERVE_FILENAME
        started_mono = time.monotonic()
        started_at = self._clock.now()
        stop = _cancel_fn(cancelled)
        probe_id = _probe_id(host_id, mount_point, started_at)
        owned = None
        search = _SearchState(
            host_id=host_id,
            mount_point=mount_point,
            workspace=workspace,
            probe_id=probe_id,
            quota_identity=quota_identity,
            pool_fingerprint=pool_fingerprint,
            max_probe_bytes=self._max_tier * self._unit,
        )
        try:
            recovered = self._recover_leftovers(
                workspace, reserve_file, probe_file, search
            )
            if recovered:
                search.run_state = RUN_INTERRUPTED
                self._emit_safely(search, started_at, started_mono)
            workspace.mkdir(parents=True, exist_ok=True)
            owned = self._mark(workspace, host_id, quota_identity)
            if self._timed_out(started_mono, started_at) or stop():
                search.interrupted = True
                return self._finish(
                    search, owned, started_at, started_mono, probe_file, reserve_file
                )
            budget = EmpiricalWriteBudget(
                chunk_bytes=self._chunk,
                deadline=started_at + timedelta(seconds=max(0.0, self._timeout)),
                max_bytes=self._max_tier * self._unit,
                timeout_seconds=self._timeout,
            )
            search.run_state = RUN_RUNNING
            self._emit_safely(search, started_at, started_mono)
            if not self._establish_reserve(
                reserve_file, budget, stop, started_mono, started_at, search
            ):
                return self._finish(
                    search, owned, started_at, started_mono, probe_file, reserve_file
                )

            recorded: list[int] = []

            def attempt(target: int) -> SonarAttempt:
                recorded.append(target)
                return self._attempt(
                    target,
                    probe_file,
                    reserve_file,
                    budget,
                    stop,
                    started_mono,
                    started_at,
                    search,
                )

            settled = False
            if corroborate_bytes is not None and corroborate_bytes > 0:
                search.specialist_candidate = corroborate_bytes
                settled = self._corroborate(corroborate_bytes, attempt, search)
            if not settled:
                tree = classify_sonar_tree(attempt)
                lower = tree.lower_units
                if search.completed:
                    physical = max(search.completed)
                    if not is_resolved(lower) or physical > lower:
                        lower = physical
                search.lower_units = lower if is_resolved(lower) else None
                if not search.interrupted:
                    search.upper_units = (
                        tree.upper_units if is_resolved(tree.upper_units) else None
                    )
                if search.lower_units == self._max_tier and search.upper_units is None:
                    search.ceiling_reached = True
            search.attempted = tuple(recorded)
            keep_specialist = search.corroboration in {
                CORROBORATION_LIMITED,
                CORROBORATION_INCONCLUSIVE,
                CORROBORATION_CONFIRMED,
                CORROBORATION_NOT_CONTRADICTED,
                CORROBORATION_LOWER_ONLY,
            }
            if (
                search.lower_units is None
                and not search.interrupted
                and not keep_specialist
            ):
                search.run_state = RUN_VERY_LOW
        finally:
            pass
        return self._finish(
            search, owned, started_at, started_mono, probe_file, reserve_file
        )

    def _corroborate(
        self,
        candidate_bytes: int,
        attempt: Callable[[int], SonarAttempt],
        search: _SearchState,
    ) -> bool:
        """Bracket a specialist candidate. True when it remains authority."""
        s_units = candidate_bytes // self._unit
        lower_tier, upper_tier = specialist_bracket(s_units)
        if lower_tier is None:
            search.corroboration = CORROBORATION_LIMITED
            return True
        below = lower_tier * self._unit < candidate_bytes
        if upper_tier is None:
            result = attempt(self._max_tier)
            if result is SonarAttempt.SUCCESS:
                search.lower_units = self._max_tier
                search.upper_units = None
                search.ceiling_reached = True
                search.corroboration = (
                    CORROBORATION_LOWER_ONLY
                    if candidate_bytes > self._max_tier * self._unit
                    else CORROBORATION_CONFIRMED
                )
                return True
            if result is SonarAttempt.CAPACITY:
                if self._max_tier * self._unit < candidate_bytes:
                    search.corroboration = CORROBORATION_CONTRADICTED
                    return False
                search.corroboration = CORROBORATION_INCONCLUSIVE
                return True
            search.corroboration = CORROBORATION_INCONCLUSIVE
            return True

        lower_result = attempt(lower_tier)
        if lower_result is SonarAttempt.CAPACITY:
            if below:
                search.corroboration = CORROBORATION_CONTRADICTED
                return False
            search.corroboration = CORROBORATION_INCONCLUSIVE
            return True
        if lower_result is SonarAttempt.OTHER:
            search.corroboration = CORROBORATION_INCONCLUSIVE
            if search.completed:
                search.lower_units = max(search.completed)
            return True

        search.lower_units = lower_tier
        upper_result = attempt(upper_tier)
        if upper_result is SonarAttempt.CAPACITY:
            search.upper_units = upper_tier
            search.corroboration = CORROBORATION_CONFIRMED
            return True
        if upper_result is SonarAttempt.SUCCESS:
            search.lower_units = upper_tier
            search.upper_units = None
            if upper_tier == self._max_tier:
                search.ceiling_reached = True
            search.corroboration = CORROBORATION_NOT_CONTRADICTED
            return True
        search.corroboration = CORROBORATION_INCONCLUSIVE
        return True

    def _attempt(
        self,
        target: int,
        probe_file: Path,
        reserve_file: Path,
        budget: EmpiricalWriteBudget,
        stop: Callable[[], bool],
        started_mono: float,
        started_at: datetime,
        search: _SearchState,
    ) -> SonarAttempt:
        if target in search.completed:
            return SonarAttempt.SUCCESS
        failed_at = search.capacity_failed_at
        if failed_at is not None and target >= failed_at:
            return SonarAttempt.CAPACITY
        if search.interrupted or not search.reserve_established:
            return SonarAttempt.OTHER
        if stop() or self._timed_out(started_mono, started_at):
            search.interrupted = True
            return SonarAttempt.OTHER
        current = max(search.completed) if search.completed else 0
        for step in _growth_steps(current, target):
            if stop() or self._timed_out(started_mono, started_at):
                search.interrupted = True
                return SonarAttempt.OTHER
            result = self._writer.write_exactly(
                probe_file, step * self._unit, budget, cancelled=stop
            )
            search.written_total += result.written_bytes
            search.additional_last = result.written_bytes
            if result.detail == "cancelled" or (
                result.failure_code is None and stop()
            ):
                search.interrupted = True
                return SonarAttempt.OTHER
            if result.failure_code is not None and is_capacity_failure(
                result.failure_code
            ):
                search.capacity_failed_at = step
                search.failure_code = result.failure_code.value
                search.failure_errno = (
                    result.failure_errno
                    if result.failure_errno is not None
                    else NOT_PROVIDED
                )
                search.upper_units = step
                self._trace("capture")
                self._after_capacity_failure(
                    probe_file,
                    reserve_file,
                    budget,
                    stop,
                    started_mono,
                    started_at,
                    search,
                )
                return SonarAttempt.CAPACITY
            if result.failure_code is not None:
                search.interrupted = True
                search.failure_code = result.failure_code.value
                search.failure_errno = (
                    result.failure_errno
                    if result.failure_errno is not None
                    else NOT_PROVIDED
                )
                return SonarAttempt.OTHER
            search.completed.add(step)
            search.committed_bytes = step * self._unit
            self._emit_safely(search, started_at, started_mono)
        return SonarAttempt.SUCCESS

    def _establish_reserve(
        self,
        reserve_file: Path,
        budget: EmpiricalWriteBudget,
        stop: Callable[[], bool],
        started_mono: float,
        started_at: datetime,
        search: _SearchState,
    ) -> bool:
        if self._reserve <= 0:
            search.reserve_established = True
            search.reserve_released = True
            return True
        result = self._writer.write_exactly(
            reserve_file, self._reserve, budget, cancelled=stop
        )
        search.written_total += result.written_bytes
        if result.failure_code is not None or result.detail == "cancelled":
            self._writer.remove(reserve_file)
            search.reserve_established = False
            search.reserve_released = True
            if result.failure_code is not None and is_capacity_failure(
                result.failure_code
            ):
                search.run_state = RUN_VERY_LOW
                search.failure_code = result.failure_code.value
                search.failure_errno = (
                    result.failure_errno
                    if result.failure_errno is not None
                    else NOT_PROVIDED
                )
            else:
                search.interrupted = True
                if result.failure_code is not None:
                    search.failure_code = result.failure_code.value
                    search.failure_errno = (
                        result.failure_errno
                        if result.failure_errno is not None
                        else NOT_PROVIDED
                    )
            return False
        search.reserve_established = True
        search.reserve_released = False
        self._emit_safely(search, started_at, started_mono)
        return True

    def _after_capacity_failure(
        self,
        probe_file: Path,
        reserve_file: Path,
        budget: EmpiricalWriteBudget,
        stop: Callable[[], bool],
        started_mono: float,
        started_at: datetime,
        search: _SearchState,
    ) -> None:
        self._trace("release_reserve")
        self._writer.remove(reserve_file)
        search.reserve_released = True
        search.reserve_established = False
        self._trace("persist")
        self._emit_safely(search, started_at, started_mono)
        self._trace("remove_probe")
        self._writer.remove(probe_file)
        if stop() or self._timed_out(started_mono, started_at):
            search.interrupted = True
            return
        self._trace("reestablish_reserve")
        self._establish_reserve(
            reserve_file, budget, stop, started_mono, started_at, search
        )

    def _recover_leftovers(
        self,
        workspace: Path,
        reserve_file: Path,
        probe_file: Path,
        search: _SearchState,
    ) -> bool:
        if not workspace.exists():
            return False
        unknown = tuple(
            item.name
            for item in workspace.iterdir()
            if item.name not in _OWNED_SONAR_NAMES
        )
        if unknown:
            return False
        self._writer.remove(reserve_file)
        search.reserve_released = True
        self._writer.remove(probe_file)
        marker = workspace / LOCAL_OWNER_FILENAME
        with suppress(OSError):
            marker.unlink(missing_ok=True)
        try:
            workspace.rmdir()
        except OSError:
            shutil.rmtree(workspace, ignore_errors=True)
        return not workspace.exists()

    def _finish(
        self,
        search: _SearchState,
        owned: OwnershipRecord | None,
        started_at: datetime,
        started_mono: float,
        probe_file: Path,
        reserve_file: Path,
    ) -> EmpiricalProbeEvidence:
        probe_gone = self._writer.remove(probe_file)
        reserve_gone = self._writer.remove(reserve_file)
        search.reserve_released = True
        marker = search.workspace / LOCAL_OWNER_FILENAME
        with suppress(OSError):
            marker.unlink(missing_ok=True)
        foreign = _foreign_names(search.workspace)
        if not foreign and search.workspace.exists():
            try:
                search.workspace.rmdir()
            except OSError:
                shutil.rmtree(search.workspace, ignore_errors=True)
        gone = probe_gone and reserve_gone and (
            not search.workspace.exists() or bool(foreign)
        )
        search.cleanup_success = gone
        if not gone:
            search.run_state = RUN_CLEANUP_FAILED
        elif search.run_state != RUN_VERY_LOW:
            if search.interrupted:
                search.run_state = RUN_INTERRUPTED
            else:
                search.run_state = RUN_COMPLETE
        if owned is not None and self._ownership is not None:
            with suppress(Exception):
                self._ownership.forget(owned.ownership_id)
        evidence = self._evidence(search, started_at, time.monotonic() - started_mono)
        self._emit_safely(search, started_at, started_mono, evidence=evidence)
        return evidence

    def _trace(self, action: str) -> None:
        self.recovery_trace.append(action)

    def _timed_out(self, started_mono: float, started_at: datetime) -> bool:
        if self._timeout <= 0:
            return True
        if time.monotonic() - started_mono >= self._timeout:
            return True
        elapsed = self._clock.now() - started_at
        return elapsed.total_seconds() >= self._timeout

    def _mark(
        self,
        workspace: Path,
        host_id: HostId,
        quota_identity: Maybe[str],
    ) -> OwnershipRecord | None:
        if self._ownership is None:
            return None
        return self._ownership.assert_owned(
            workspace,
            host_id,
            ManagedResourceType.SONAR_PROBE,
            lifecycle=LifecycleState.DISPOSABLE,
            cleanup_policy=CleanupPolicy.DISPOSABLE,
            quota_identity=quota_identity,
            allowed_roots=(workspace,),
        )

    def _emit_safely(
        self,
        search: _SearchState,
        started_at: datetime,
        started_mono: float,
        *,
        evidence: EmpiricalProbeEvidence | None = None,
    ) -> None:
        try:
            self._emit(search, started_at, started_mono, evidence=evidence)
        except Exception:
            return

    def _emit(
        self,
        search: _SearchState,
        started_at: datetime,
        started_mono: float,
        *,
        evidence: EmpiricalProbeEvidence | None = None,
    ) -> None:
        if self._on_progress is None:
            return
        self._on_progress(
            evidence
            if evidence is not None
            else self._evidence(search, started_at, time.monotonic() - started_mono)
        )

    def _evidence(
        self, search: _SearchState, started_at: datetime, elapsed: float
    ) -> EmpiricalProbeEvidence:
        lower = (
            search.lower_units * self._unit
            if search.lower_units
            else (
                max(search.completed) * self._unit if search.completed else NOT_PROVIDED
            )
        )
        upper: Maybe[int] = NOT_PROVIDED
        if search.upper_units is not None and not search.interrupted:
            upper = search.upper_units * self._unit
        confidence = (
            Confidence.MEDIUM
            if is_resolved(lower) and not search.interrupted
            else Confidence.LOW
        )
        return EmpiricalProbeEvidence(
            host_id=search.host_id,
            mount_point=search.mount_point,
            target_path=str(search.workspace),
            max_probe_bytes=search.max_probe_bytes,
            bytes_physically_written=search.written_total,
            search_granularity_bytes=self._unit,
            probe_ceiling_reached=search.ceiling_reached,
            confidence=confidence,
            provenance=Provenance(
                producer=PRODUCER,
                producer_version=SONAR_ALGORITHM_VERSION,
                observed_at=self._clock.now(),
                policy_version=POLICY_VERSION,
            ),
            cleanup_success=search.cleanup_success,
            verified_lower_bound_bytes=lower,
            observed_failure_upper_bytes=upper,
            failure_code=search.failure_code,
            failure_errno=search.failure_errno,
            elapsed_seconds=elapsed,
            interrupted=search.interrupted,
            algorithm_version=SONAR_ALGORITHM_VERSION,
            payload_version=PAYLOAD_VERSION,
            completed_tier_units=tuple(sorted(search.completed)),
            committed_bytes=search.committed_bytes,
            run_state=search.run_state,
            reserve_established=search.reserve_established,
            reserve_released=search.reserve_released,
            quota_identity=search.quota_identity,
            pool_fingerprint=search.pool_fingerprint,
            probe_id=search.probe_id,
            attempted_tier_units=search.attempted,
            additional_bytes_last=search.additional_last,
            corroboration=(
                search.corroboration if search.corroboration else NOT_PROVIDED
            ),
            specialist_candidate_bytes=(
                search.specialist_candidate
                if search.specialist_candidate is not None
                else NOT_PROVIDED
            ),
        )


class _SearchState:
    """Mutable physical search. Not a contract."""

    def __init__(
        self,
        *,
        host_id: HostId,
        mount_point: str,
        workspace: Path,
        probe_id: str,
        quota_identity: Maybe[str],
        pool_fingerprint: Maybe[str],
        max_probe_bytes: int,
    ) -> None:
        self.host_id = host_id
        self.mount_point = mount_point
        self.workspace = workspace
        self.probe_id = probe_id
        self.quota_identity = quota_identity
        self.pool_fingerprint = pool_fingerprint
        self.max_probe_bytes = max_probe_bytes
        self.completed: set[int] = set()
        self.capacity_failed_at: int | None = None
        self.written_total = 0
        self.additional_last = 0
        self.committed_bytes = 0
        self.failure_code: Maybe[str] = NOT_PROVIDED
        self.failure_errno: Maybe[int] = NOT_PROVIDED
        self.interrupted = False
        self.ceiling_reached = False
        self.reserve_established = False
        self.reserve_released = False
        self.cleanup_success = False
        self.run_state = RUN_RUNNING
        self.lower_units: int | None = None
        self.upper_units: int | None = None
        self.attempted: tuple[int, ...] = ()
        self.corroboration: str | None = None
        self.specialist_candidate: int | None = None


def _growth_steps(current: int, target: int) -> tuple[int, ...]:
    if target <= 64:
        return tuple(step for step in CHECKPOINTS_TO_64 if current < step <= target)
    if current < target:
        return (target,)
    return ()


def _probe_id(host_id: HostId, mount_point: str, started_at: datetime) -> str:
    raw = f"{host_id.value}:{mount_point}:{started_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


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


def _foreign_names(workspace: Path) -> tuple[str, ...]:
    if not workspace.exists() or not workspace.is_dir():
        return ()
    try:
        return tuple(
            item.name
            for item in workspace.iterdir()
            if item.name not in _OWNED_SONAR_NAMES
        )
    except OSError:
        return ()
