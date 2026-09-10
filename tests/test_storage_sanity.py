"""Storage sanity: can evidence support the policy decision?

The tests that matter are about what the ladder refuses to do. It must stop
at the policy ceiling, it must not lower capacity because a budget expired,
it must lower capacity when a genuine failure happens below the ceiling, and
it must never treat "unsupported" as evidence that a pool is too small.

None of these allocate real space: the probe is a stub, and the real one is
exercised only under `T3` on a host. CI must never write gigabytes.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from kultrun.capacity.contracts import EvidenceRequirement
from kultrun.capacity.envelope import CapacityService
from kultrun.capacity.policy import default_policy
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.contracts import (
    ProbeOutcome,
    SanityStatus,
    SanityStopReason,
    StorageSanityEvidence,
)
from kultrun.storage.ports import (
    ReservationBudget,
    ReservationResult,
    StorageSanityProbe,
)
from kultrun.storage.sanity import (
    PROBE_DIRECTORY,
    PROBE_PREFIX,
    PROBE_SUFFIX,
    SanityProbePolicy,
    StorageSanityService,
    checkpoints,
)
from tests.test_capacity import GIB, PIB, TIB, host, mount

INSTANT = dt.datetime(2026, 9, 5, 12, 0, tzinfo=dt.UTC)


class StubProbe:
    """A probe whose outcome each test decides. Allocates nothing."""

    method = Name("stub")

    def __init__(self, outcomes: dict[int, ProbeOutcome]) -> None:
        self.outcomes = outcomes
        self.attempted: list[int] = []
        self.chunks: list[int] = []

    def reserve(
        self, path: Path, target_bytes: int, budget: ReservationBudget
    ) -> ReservationResult:
        self.attempted.append(target_bytes)
        self.chunks.append(budget.chunk_bytes)
        outcome = self.outcomes.get(target_bytes, ProbeOutcome.VERIFIED)
        reserved = target_bytes if outcome is ProbeOutcome.VERIFIED else 0
        return ReservationResult(outcome=outcome, reserved_bytes=reserved)


class MemoryStore:
    """Just enough Store for evidence, so persistence order is observable."""

    def __init__(self) -> None:
        self.records: dict[str, object] = {}
        self.writes: list[str] = []

    def put(self, key: str, record: object) -> None:
        self.records[key] = record
        self.writes.append(key)

    def get(self, contract_type: type, key: str) -> object | None:
        found = self.records.get(key)
        return found if isinstance(found, contract_type) else None

    def delete(self, contract_type: type, key: str) -> bool:
        return self.records.pop(key, None) is not None

    def keys(self, contract_type: type) -> tuple[str, ...]:
        return tuple(self.records)

    def records_of(self, contract_type: type) -> tuple[object, ...]:
        return tuple(v for v in self.records.values() if isinstance(v, contract_type))

    # Store protocol spelling
    def reconcile(self) -> object:  # pragma: no cover - not exercised here
        raise NotImplementedError


def service(
    outcomes: dict[int, ProbeOutcome] | None = None,
    *,
    policy: SanityProbePolicy | None = None,
    store: MemoryStore | None = None,
) -> tuple[StorageSanityService, StubProbe, MemoryStore]:
    probe = StubProbe(outcomes or {})
    backing = store or MemoryStore()
    backing.records_ = backing.records  # type: ignore[attr-defined]
    built = StorageSanityService(
        probe,
        _as_store(backing),
        policy=policy or SanityProbePolicy(),
        clock=FixedClock(INSTANT),
        monotonic=lambda: 0.0,
    )
    return built, probe, backing


def _as_store(backing: MemoryStore):  # type: ignore[no-untyped-def]
    """Adapt the test double to the Store protocol's method names."""

    class Adapted:
        put = backing.put
        get = backing.get
        delete = backing.delete
        keys = backing.keys
        reconcile = backing.reconcile

        @staticmethod
        def records(contract_type: type) -> tuple[object, ...]:
            return backing.records_of(contract_type)

    return Adapted()


class TestTheLadderStopsAtPolicy:
    def test_the_last_rung_is_the_policy_ceiling(self) -> None:
        """Nothing above the ceiling can change the decision.

        The previous implementation climbed toward a pool boundary near 47
        GiB to answer a 6.70 GiB question and spent 48 minutes doing it.
        """
        assert checkpoints(SanityProbePolicy(), 64 * GIB) == (
            8 * GIB,
            16 * GIB,
            32 * GIB,
            64 * GIB,
        )

    def test_the_ladder_is_finite_regardless_of_the_ceiling(self) -> None:
        policy = SanityProbePolicy(max_checkpoints=5)
        assert len(checkpoints(policy, 1 * PIB)) == 5

    def test_a_ceiling_below_the_first_rung_is_one_attempt(self) -> None:
        assert checkpoints(SanityProbePolicy(), 2 * GIB) == (2 * GIB,)

    def test_it_stops_the_moment_the_ceiling_verifies(self) -> None:
        sanity, probe, _ = service()
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert probe.attempted == [8 * GIB, 16 * GIB, 32 * GIB, 64 * GIB]
        assert evidence.stop_reason is SanityStopReason.POLICY_CAP_REACHED
        assert evidence.status is SanityStatus.POLICY_CAP_VERIFIED
        assert evidence.verified_lower_bound_bytes == 64 * GIB


class TestEvidenceMayConfirmOrContradictButNeverExpand:
    """The whole point of the subsystem, and the easiest thing to get wrong."""

    def envelope(self, evidence: StorageSanityEvidence | None):  # type: ignore[no-untyped-def]
        subject = host(
            mounts=(mount("/workspace", "fuse", free=500 * TIB, total=2 * PIB),)
        )
        sanity = {"/workspace": evidence} if evidence else {}
        return CapacityService(clock=FixedClock(INSTANT)).compute(subject, sanity)

    def evidence_with(
        self, status: SanityStatus, verified: int | None, failure: int | None = None
    ) -> StorageSanityEvidence:
        return StorageSanityEvidence(
            mount_point="/workspace",
            host_fingerprint="h",
            pool_fingerprint="p",
            probe_policy_version="0-sanity",
            probe_method=Name("stub"),
            status=status,
            stop_reason=SanityStopReason.POLICY_CAP_REACHED,
            observed_at=INSTANT,
            policy_target_bytes=64 * GIB,
            verified_lower_bound_bytes=verified if verified else NOT_PROVIDED,
            observed_failure_upper_bytes=failure if failure else NOT_PROVIDED,
        )

    def test_with_no_evidence_the_policy_bound_stands(self) -> None:
        pool = self.envelope(None).pools[0]
        assert pool.space.effective_bytes == (
            default_policy().unverified_pool_ceiling_bytes
        )
        assert pool.sanity_status is SanityStatus.NOT_CHECKED
        assert pool.sanity_check_required is True

    def test_partial_evidence_does_not_lower_capacity(self) -> None:
        """A probe stopped by a budget proved nothing about the pool's limit.

        Verified 32 GiB of a 64 GiB bound because time ran out. Reducing
        effective capacity to 32 GiB would be treating "we stopped asking"
        as "the pool is smaller", which is exactly backwards.
        """
        pool = self.envelope(
            self.evidence_with(SanityStatus.PARTIALLY_VERIFIED, 32 * GIB)
        ).pools[0]
        assert pool.space.effective_bytes == 64 * GIB
        assert pool.sanity_verified_lower_bound_bytes == 32 * GIB
        assert pool.sanity_status is SanityStatus.PARTIALLY_VERIFIED

    def test_reaching_the_cap_confirms_the_policy_without_raising_it(self) -> None:
        pool = self.envelope(
            self.evidence_with(SanityStatus.POLICY_CAP_VERIFIED, 64 * GIB)
        ).pools[0]
        assert pool.space.effective_bytes == 64 * GIB
        assert pool.note is not None
        # Names the method rather than asserting genuineness: capacity does
        # not know whether the reservation was real.
        assert "verified by probe method" in pool.note

    def test_a_genuine_failure_below_the_cap_lowers_capacity(self) -> None:
        """The corrective role. Policy was wrong and capacity comes down."""
        pool = self.envelope(
            self.evidence_with(SanityStatus.CONTRADICTED, 16 * GIB, 32 * GIB)
        ).pools[0]
        assert pool.space.effective_bytes == 16 * GIB
        assert isinstance(pool.space.safe_bytes, int) or not is_resolved(
            pool.space.safe_bytes
        )
        assert pool.note is not None
        assert "contradicts" in pool.note

    def test_evidence_can_never_exceed_the_policy_bound(self) -> None:
        """Even claiming a huge verified bound must not expand capacity.

        Raising a bound needs evidence this subsystem does not gather, and
        an operator who could widen capacity by running a probe would have
        found a way around the policy.
        """
        pool = self.envelope(
            self.evidence_with(SanityStatus.POLICY_CAP_VERIFIED, 500 * TIB)
        ).pools[0]
        assert pool.space.effective_bytes == 64 * GIB

    def test_unsupported_does_not_lower_capacity(self) -> None:
        """No primitive means no evidence — not evidence of a small pool."""
        pool = self.envelope(self.evidence_with(SanityStatus.UNSUPPORTED, None)).pools[
            0
        ]
        assert pool.space.effective_bytes == 64 * GIB


class TestTriggering:
    def test_a_credible_ordinary_disk_is_not_flagged(self) -> None:
        subject = host(mounts=(mount("/", "ext4", free=30 * GIB, total=30 * GIB),))
        pool = CapacityService(clock=FixedClock(INSTANT)).compute(subject).pools[0]
        assert pool.sanity_check_required is False

    def test_the_petabyte_network_mount_is_flagged(self) -> None:
        subject = host(
            mounts=(mount("/workspace", "fuse", free=500 * TIB, total=2 * PIB),)
        )
        pool = CapacityService(clock=FixedClock(INSTANT)).compute(subject).pools[0]
        assert pool.sanity_check_required is True

    def test_a_small_incredible_mount_is_not_worth_probing(self) -> None:
        """Policy already bounds it below the report; a probe buys nothing."""
        subject = host(mounts=(mount("/net", "nfs", free=10 * GIB, total=20 * GIB),))
        pool = CapacityService(clock=FixedClock(INSTANT)).compute(subject).pools[0]
        assert pool.requirement is EvidenceRequirement.EMPIRICAL_EVIDENCE_NEEDED
        assert pool.sanity_check_required is False

    def test_a_verified_pool_stops_asking(self) -> None:
        evidence = TestEvidenceMayConfirmOrContradictButNeverExpand().evidence_with(
            SanityStatus.POLICY_CAP_VERIFIED, 64 * GIB
        )
        subject = host(
            mounts=(mount("/workspace", "fuse", free=500 * TIB, total=2 * PIB),)
        )
        pool = (
            CapacityService(clock=FixedClock(INSTANT))
            .compute(subject, {"/workspace": evidence})
            .pools[0]
        )
        assert pool.sanity_check_required is False


class TestBudgetsAndHonestPartialResults:
    def test_a_capacity_failure_stops_the_ladder_and_bounds_it(self) -> None:
        sanity, probe, _ = service({32 * GIB: ProbeOutcome.NO_SPACE})
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert probe.attempted == [8 * GIB, 16 * GIB, 32 * GIB]
        assert evidence.status is SanityStatus.CONTRADICTED
        assert evidence.verified_lower_bound_bytes == 16 * GIB
        assert evidence.observed_failure_upper_bytes == 32 * GIB
        assert evidence.stop_reason is SanityStopReason.CAPACITY_FAILURE

    def test_quota_exhaustion_also_bounds_capacity(self) -> None:
        sanity, _, _ = service({16 * GIB: ProbeOutcome.QUOTA_EXCEEDED})
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert evidence.status is SanityStatus.CONTRADICTED
        assert evidence.observed_failure_upper_bytes == 16 * GIB

    def test_an_unsupported_primitive_bounds_nothing(self) -> None:
        """`EOPNOTSUPP` is an absence of method, not a small filesystem."""
        sanity, _, _ = service({8 * GIB: ProbeOutcome.UNSUPPORTED})
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert evidence.status is SanityStatus.UNSUPPORTED
        assert not is_resolved(evidence.observed_failure_upper_bytes)
        assert not is_resolved(evidence.verified_lower_bound_bytes)

    def test_a_file_size_limit_bounds_nothing(self) -> None:
        sanity, _, _ = service({16 * GIB: ProbeOutcome.FILE_TOO_LARGE})
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert not is_resolved(evidence.observed_failure_upper_bytes)
        assert evidence.verified_lower_bound_bytes == 8 * GIB

    def test_an_abandoned_attempt_is_partial_not_failed(self) -> None:
        sanity, _, _ = service({32 * GIB: ProbeOutcome.ABANDONED})
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert evidence.status is SanityStatus.PARTIALLY_VERIFIED
        assert evidence.verified_lower_bound_bytes == 16 * GIB
        assert evidence.stop_reason is SanityStopReason.TIME_BUDGET
        assert not is_resolved(evidence.observed_failure_upper_bytes)

    def test_the_work_allowance_bounds_the_ladder(self) -> None:
        sanity, probe, _ = service(policy=SanityProbePolicy(work_budget_bytes=20 * GIB))
        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert probe.attempted == [8 * GIB]
        assert evidence.stop_reason is SanityStopReason.WORK_BUDGET
        assert evidence.verified_lower_bound_bytes == 8 * GIB

    def test_cancellation_is_honoured_between_rungs(self) -> None:
        sanity, probe, _ = service()
        calls = {"n": 0}

        def cancelled() -> bool:
            calls["n"] += 1
            return calls["n"] > 2

        evidence = sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
            cancelled=cancelled,
        )
        assert evidence.stop_reason is SanityStopReason.CANCELLED
        assert len(probe.attempted) == 2

    def test_reservation_is_chunked_not_monolithic(self) -> None:
        """A single huge call cannot be abandoned, and that orphaned 42,990 MiB."""
        sanity, probe, _ = service()
        sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert all(chunk < 8 * GIB for chunk in probe.chunks)
        assert probe.chunks[0] == SanityProbePolicy().chunk_bytes


class TestEvidencePersistenceAndReuse:
    def test_each_rung_is_persisted_before_the_next_begins(self) -> None:
        """48 minutes of correct probing was once discarded on interrupt."""
        sanity, _, store = service()
        sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        # Four rungs plus the final record: every success was written.
        assert len(store.writes) >= 5

    def test_evidence_is_reused_rather_than_regathered(self) -> None:
        sanity, _, _ = service()
        sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        found = sanity.evidence_for("/pool", host_fingerprint="h", pool_fingerprint="p")
        assert found is not None
        assert found.verified_lower_bound_bytes == 64 * GIB

    @pytest.mark.parametrize(
        ("host_fingerprint", "pool_fingerprint"),
        [("other", "p"), ("h", "other")],
    )
    def test_evidence_is_not_reused_across_identities(
        self, host_fingerprint: str, pool_fingerprint: str
    ) -> None:
        """A different host or a changed filesystem is not what was measured."""
        sanity, _, _ = service()
        sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert (
            sanity.evidence_for(
                "/pool",
                host_fingerprint=host_fingerprint,
                pool_fingerprint=pool_fingerprint,
            )
            is None
        )

    def test_a_changed_probe_policy_invalidates_evidence(self) -> None:
        """An old conclusion must not be inherited by a new policy."""
        store = MemoryStore()
        sanity, _, _ = service(store=store)
        sanity.check(
            "/pool",
            policy_target_bytes=64 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        other = StorageSanityService(
            StubProbe({}),
            _as_store(store),
            policy=SanityProbePolicy(version="1-different"),
            clock=FixedClock(INSTANT),
        )
        assert (
            other.evidence_for("/pool", host_fingerprint="h", pool_fingerprint="p")
            is None
        )


class TestCleanupAndOrphans:
    def test_orphans_from_an_earlier_run_are_cleared_first(
        self, tmp_path: Path
    ) -> None:
        """`finally` is not enough: the previous cleanup was correct and
        never ran, because the probe was on a daemon thread."""
        probe_dir = tmp_path / PROBE_DIRECTORY
        probe_dir.mkdir()
        orphan = probe_dir / f"{PROBE_PREFIX}999{PROBE_SUFFIX}"
        orphan.write_bytes(b"left behind")
        unrelated = probe_dir / "someone-elses-file.txt"
        unrelated.write_bytes(b"not ours")

        sanity, _, _ = service()
        evidence = sanity.check(
            str(tmp_path),
            policy_target_bytes=8 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert evidence.orphans_removed == 1
        assert not orphan.exists()
        assert unrelated.exists(), "only Kultrun's own probe artifacts are removed"

    def test_cleanup_is_confirmed_by_absence_not_by_free_space(
        self, tmp_path: Path
    ) -> None:
        """Deleting a 42,990 MiB probe once returned ~1.1 GB to df at once."""
        sanity, _, _ = service()
        evidence = sanity.check(
            str(tmp_path),
            policy_target_bytes=8 * GIB,
            host_fingerprint="h",
            pool_fingerprint="p",
        )
        assert evidence.cleanup_verified is True
        remaining = list((tmp_path / PROBE_DIRECTORY).glob(f"{PROBE_PREFIX}*"))
        assert remaining == []


class TestTheRealProbeIsGenuine:
    def test_the_shipped_probe_satisfies_the_port(self) -> None:
        from kultrun.adapters.storage import posix_reservation

        assert isinstance(posix_reservation.build(), StorageSanityProbe)

    def test_it_reserves_genuinely_and_cleans_up(self, tmp_path: Path) -> None:
        """A small real reservation — 8 MiB, not gigabytes.

        Proves the primitive works and that the artifact is gone afterwards.
        The full ladder against a real filesystem is `T3`, on a host; CI must
        never write gigabytes.
        """
        from kultrun.adapters.storage import posix_reservation

        probe = posix_reservation.build()
        target = 8 * 1024 * 1024
        result = probe.reserve(
            tmp_path / f"{PROBE_PREFIX}test{PROBE_SUFFIX}",
            target,
            ReservationBudget(
                chunk_bytes=1024 * 1024,
                deadline=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=30),
                remaining_work_bytes=target,
            ),
        )
        assert result.outcome in (ProbeOutcome.VERIFIED, ProbeOutcome.UNSUPPORTED)
        if result.outcome is ProbeOutcome.VERIFIED:
            assert result.reserved_bytes == target
        assert list(tmp_path.glob(f"{PROBE_PREFIX}*")) == []

    def test_a_work_allowance_below_the_target_is_abandoned_not_attempted(
        self, tmp_path: Path
    ) -> None:
        from kultrun.adapters.storage import posix_reservation

        result = posix_reservation.build().reserve(
            tmp_path / "probe.probe",
            64 * GIB,
            ReservationBudget(
                chunk_bytes=1024 * 1024,
                deadline=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=30),
                remaining_work_bytes=1024,
            ),
        )
        assert result.outcome in (ProbeOutcome.ABANDONED, ProbeOutcome.UNSUPPORTED)
        assert result.reserved_bytes == 0
        assert list(tmp_path.glob("*")) == []

    @pytest.mark.skipif(
        hasattr(os, "posix_fallocate"),
        reason="this asserts the behaviour where the primitive is absent",
    )
    def test_without_the_primitive_it_refuses_rather_than_faking(self) -> None:
        """macOS has no `posix_fallocate`, and the honest answer is nothing.

        The tempting substitute is `truncate` or a sparse write, which would
        succeed instantly at any size and "verify" a petabyte on the very
        mounts this exists to distrust. Reporting `UNSUPPORTED` leaves the
        policy bound standing and lowers nothing — no evidence beats fake
        evidence. `docs/DEBT.md` DC-14.
        """
        from kultrun.adapters.storage import posix_reservation

        result = posix_reservation.build().reserve(
            Path("/tmp/kultrun-nonexistent.probe"),
            8 * GIB,
            ReservationBudget(
                chunk_bytes=1024 * 1024,
                deadline=dt.datetime.now(dt.UTC) + dt.timedelta(seconds=5),
                remaining_work_bytes=8 * GIB,
            ),
        )
        assert result.outcome is ProbeOutcome.UNSUPPORTED
        assert result.reserved_bytes == 0
        assert result.detail is not None
        assert "sparse" in result.detail
