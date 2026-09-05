"""Storage sanity: can evidence support the policy decision?

Stage 1.2 bounds a pool whose reported size proves nothing — `/workspace`
advertises half a petabyte and gets 64 GiB of effective capacity from policy
alone. That is safe but unverified. This asks whether the bound is *earned*.

The question is deliberately narrow:

> Can a genuine reservation reach the amount policy already decided to
> allow?

Not *what is this filesystem's maximum?* On a mount advertising 2.15 PB that
question has no terminating answer, and the previous implementation spent 48
minutes discovering it — answering a transaction question by climbing toward
a pool ceiling, when a 32 GiB success had already settled a 6.70 GiB
requirement.

So the ladder stops at the policy ceiling and never goes past it. Nothing
above it can change the decision.

**Evidence may confirm or contradict, never expand.** A probe that reaches
the ceiling confirms the policy. One stopped early by a budget leaves the
policy untouched — a probe that ran out of time proved nothing about the
pool. Only a genuine space or quota failure *below* the ceiling moves
capacity, and it moves it down. Raising a bound is Stage 2.2's business,
with evidence this deliberately does not gather.

Not the Stage 2.2 characterization subsystem. No adaptive search, no
provider quota APIs, no host characterization, no scheduling, no aging.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    ProbeAttempt,
    ProbeOutcome,
    SanityStatus,
    SanityStopReason,
    StorageSanityEvidence,
)
from kultrun.storage.ports import ReservationBudget, StorageSanityProbe

_GIB: Final = 1024**3

#: Bumped when any default below changes, so old evidence stays explicable.
PROBE_POLICY_VERSION: Final = "0-sanity"

#: Where a probe artifact lives: a Kultrun-owned directory inside the pool
#: being tested. Never a customer directory, and the name is positively
#: identifiable so orphan recovery can be certain what it is deleting.
PROBE_DIRECTORY: Final = ".kultrun-probe"
PROBE_PREFIX: Final = "kultrun-sanity-"
PROBE_SUFFIX: Final = ".probe"


@dataclass(frozen=True, slots=True)
class SanityProbePolicy:
    """What a v0 probe is allowed to do.

    Provisional. Every value is a starting point rather than tuning, and
    `docs/DEBT.md` records that. Three independent budgets, because attempts
    alone are not a bound: the previous implementation stayed inside its
    attempt limit while spending 48 minutes, and at the ~110 MB/s its
    reference volume managed, a 64 GiB reservation costs about ten minutes.
    """

    #: The ladder's first rung.
    first_checkpoint_bytes: int = 8 * _GIB
    #: Each rung doubles.
    growth_factor: int = 2
    #: At most this many rungs, so the ladder is finite regardless.
    max_checkpoints: int = 5
    #: Reservation is extended in units this size, so it can be abandoned.
    chunk_bytes: int = 512 * 1024 * 1024
    #: Wall clock for the whole ladder.
    time_budget_seconds: float = 120.0
    #: Cumulative bytes the ladder may reserve, across all rungs.
    work_budget_bytes: int = 128 * _GIB
    version: str = PROBE_POLICY_VERSION


def checkpoints(policy: SanityProbePolicy, policy_target_bytes: int) -> tuple[int, ...]:
    """The rungs to try, ending exactly at the policy ceiling.

    The last rung *is* the ceiling, because that is the only value that can
    confirm the decision. Anything beyond it is spending money to learn
    something no decision depends on.
    """
    if policy_target_bytes <= 0:
        return ()
    rungs: list[int] = []
    candidate = policy.first_checkpoint_bytes
    while candidate < policy_target_bytes and len(rungs) < policy.max_checkpoints - 1:
        rungs.append(candidate)
        candidate *= policy.growth_factor
    rungs.append(policy_target_bytes)
    return tuple(rungs)


class StorageSanityService:
    """Runs the bounded ladder and records what it established."""

    component = Name("storage-sanity")

    def __init__(
        self,
        probe: StorageSanityProbe,
        store: Store,
        *,
        policy: SanityProbePolicy | None = None,
        clock: Clock | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._probe = probe
        self._store = store
        self._policy = policy or SanityProbePolicy()
        self._clock = clock or SystemClock()
        self._monotonic = monotonic

    @property
    def policy(self) -> SanityProbePolicy:
        return self._policy

    # -- reading -----------------------------------------------------------

    def evidence_for(
        self, mount_point: str, *, host_fingerprint: str, pool_fingerprint: str
    ) -> StorageSanityEvidence | None:
        """Stored evidence for this pool, if it still applies.

        Scoped by host and pool fingerprint so evidence cannot be reused for
        something it did not describe, and by policy version so a changed
        probe policy does not silently inherit an old conclusion.

        **A read never probes.** `GET /v1/capacity` and every console
        refresh land here, and a capacity read that allocated storage would
        be the previous implementation's mistake with a new name.
        """
        found = self._store.get(StorageSanityEvidence, _record_key(mount_point))
        if found is None:
            return None
        if (
            found.host_fingerprint != host_fingerprint
            or found.pool_fingerprint != pool_fingerprint
            or found.probe_policy_version != self._policy.version
        ):
            return None
        return found

    def all_evidence(self) -> tuple[StorageSanityEvidence, ...]:
        """Everything stored, for the diagnostic surfaces."""
        return self._store.records(StorageSanityEvidence)

    # -- running -----------------------------------------------------------

    def check(
        self,
        mount_point: str,
        *,
        policy_target_bytes: int,
        host_fingerprint: str,
        pool_fingerprint: str,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> StorageSanityEvidence:
        """Climb the ladder toward the policy ceiling, then stop.

        Persists after **every** rung, before starting the next. The
        previous implementation wrote evidence only when its coordinator
        returned, so an interrupted 48-minute run kept nothing — and the
        expensive part had already succeeded.
        """
        directory = Path(mount_point) / PROBE_DIRECTORY
        orphans = self._remove_orphans(directory)
        started = self._monotonic()
        deadline = self._clock.now() + dt.timedelta(
            seconds=self._policy.time_budget_seconds
        )

        evidence = StorageSanityEvidence(
            mount_point=mount_point,
            host_fingerprint=host_fingerprint,
            pool_fingerprint=pool_fingerprint,
            probe_policy_version=self._policy.version,
            probe_method=self._probe.method,
            status=SanityStatus.INCONCLUSIVE,
            stop_reason=SanityStopReason.ERROR,
            observed_at=self._clock.now(),
            policy_target_bytes=policy_target_bytes,
            orphans_removed=orphans,
        )

        remaining_work = self._policy.work_budget_bytes
        attempts: list[ProbeAttempt] = []
        verified: Maybe[int] = NOT_PROVIDED
        failure_upper: Maybe[int] = NOT_PROVIDED
        stop = SanityStopReason.CHECKPOINT_BUDGET
        cleanup_verified = True

        for target in checkpoints(self._policy, policy_target_bytes):
            if cancelled():
                stop = SanityStopReason.CANCELLED
                break
            if self._clock.now() >= deadline:
                stop = SanityStopReason.TIME_BUDGET
                break
            if remaining_work < target:
                stop = SanityStopReason.WORK_BUDGET
                break

            attempt_started = self._monotonic()
            path = directory / f"{PROBE_PREFIX}{target}{PROBE_SUFFIX}"
            result = self._probe.reserve(
                path,
                target,
                ReservationBudget(
                    chunk_bytes=self._policy.chunk_bytes,
                    deadline=deadline,
                    remaining_work_bytes=remaining_work,
                ),
            )
            cleanup_verified = cleanup_verified and not path.exists()
            attempts.append(
                ProbeAttempt(
                    target_bytes=target,
                    outcome=result.outcome,
                    reserved_bytes=result.reserved_bytes,
                    duration_seconds=round(self._monotonic() - attempt_started, 3),
                    detail=result.detail,
                )
            )
            remaining_work -= result.reserved_bytes

            evidence = replace(
                evidence,
                attempts=tuple(attempts),
                total_reserved_bytes=sum(a.reserved_bytes for a in attempts),
                elapsed_seconds=round(self._monotonic() - started, 3),
                cleanup_verified=cleanup_verified,
            )

            if result.outcome is ProbeOutcome.VERIFIED:
                verified = target
                evidence = replace(evidence, verified_lower_bound_bytes=verified)
                # Persist the rung before spending anything on the next one.
                self._persist(evidence, SanityStatus.PARTIALLY_VERIFIED, stop)
                if target >= policy_target_bytes:
                    stop = SanityStopReason.POLICY_CAP_REACHED
                    break
                continue

            if result.outcome.bounds_capacity:
                failure_upper = target
                stop = SanityStopReason.CAPACITY_FAILURE
                break
            if result.outcome is ProbeOutcome.UNSUPPORTED:
                stop = SanityStopReason.UNSUPPORTED
                break
            if result.outcome is ProbeOutcome.ABANDONED:
                stop = SanityStopReason.TIME_BUDGET
                break
            stop = SanityStopReason.ERROR
            break

        evidence = replace(
            evidence,
            verified_lower_bound_bytes=verified,
            observed_failure_upper_bytes=failure_upper,
            elapsed_seconds=round(self._monotonic() - started, 3),
            cleanup_verified=cleanup_verified,
        )
        return self._persist(
            evidence,
            _status(verified, failure_upper, policy_target_bytes, stop),
            stop,
        )

    # -- housekeeping ------------------------------------------------------

    def _persist(
        self,
        evidence: StorageSanityEvidence,
        status: SanityStatus,
        stop: SanityStopReason,
    ) -> StorageSanityEvidence:
        recorded = replace(evidence, status=status, stop_reason=stop)
        self._store.put(_record_key(recorded.mount_point), recorded)
        return recorded

    def _remove_orphans(self, directory: Path) -> int:
        """Clear probe artifacts an earlier run left behind.

        `finally` is not enough and the previous implementation proved it:
        its cleanup block was correct and never ran, because the probe
        executed on a daemon thread that shutdown did not await. So recovery
        is a startup problem, not an exception-handling problem.

        Scoped to Kultrun's own probe directory and to positively
        identifiable names. Nothing else is examined, let alone deleted.
        """
        if not directory.is_dir():
            return 0
        removed = 0
        for path in directory.glob(f"{PROBE_PREFIX}*{PROBE_SUFFIX}"):
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
        return removed


def _record_key(mount_point: str) -> str:
    """A stable, filesystem-safe record key for a mount point."""
    cleaned = mount_point.strip("/").replace("/", "-") or "root"
    return f"sanity-{cleaned}"


def _status(
    verified: Maybe[int],
    failure_upper: Maybe[int],
    policy_target_bytes: int,
    stop: SanityStopReason,
) -> SanityStatus:
    """How the evidence stands against the policy decision.

    The ordering matters. A genuine failure below the ceiling contradicts
    policy even if something smaller was verified first — that is the whole
    corrective purpose. A budget running out does not contradict anything.
    """
    if is_resolved(failure_upper) and failure_upper <= policy_target_bytes:
        return SanityStatus.CONTRADICTED
    if is_resolved(verified) and verified >= policy_target_bytes:
        return SanityStatus.POLICY_CAP_VERIFIED
    if stop is SanityStopReason.UNSUPPORTED:
        return SanityStatus.UNSUPPORTED
    if is_resolved(verified):
        return SanityStatus.PARTIALLY_VERIFIED
    return SanityStatus.INCONCLUSIVE


def summarize(evidence: Sequence[StorageSanityEvidence]) -> dict[str, object]:
    """A compact view for the diagnostic surfaces."""
    return {
        entry.mount_point: {
            "status": entry.status.value,
            "stop_reason": entry.stop_reason.value,
            "verified_lower_bound_bytes": entry.verified_lower_bound_bytes,
            "observed_failure_upper_bytes": entry.observed_failure_upper_bytes,
            "policy_target_bytes": entry.policy_target_bytes,
            "observed_at": entry.observed_at.isoformat(),
            "attempts": len(entry.attempts),
            "cleanup_verified": entry.cleanup_verified,
        }
        for entry in evidence
    }
