"""Storage as a set of pools.

A pool is the platform's interpretation of a mount as allocatable,
quota-bounded, fingerprinted capacity. That is a different concept from the
mount facts `host` reports, which is why they have different owners: one is
inspection, the other is the domain against which a mutation is admitted.

Pools are plural from v1 on a reference host that has one. The previous
attempt designed multi-pool storage and never exercised it, and
`docs/ARCHITECTURE.md` Part II §6 makes the general form of that mistake —
assuming one of something there will later be many of — the thing to avoid
at contract-writing time.

The evidence and probing that make a pool's capacity *credible* are Stages
2.2 to 2.4. What exists here is pool identity, which Stage 1.2 needs in
order to speak about storage at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class StoragePoolId(EntityId):
    """Identifies one storage pool."""

    prefix = "pool"


class ProviderClass(StrEnum):
    """What kind of storage backs a pool.

    This drives whether evidence gathered on one pool may be reused on
    another, and whether free-space reporting can be trusted at all —
    network and virtualized volumes reclaim space asynchronously, which is
    how the previous attempt saw a 42,990 MiB deletion return 1.1 GB to
    ``df``.
    """

    LOCAL_DISK = "local_disk"
    NETWORK = "network"
    VIRTUAL = "virtual"
    UNKNOWN = "unknown"


@contract(kind="storage.pool", version=1)
@dataclass(frozen=True, slots=True)
class StoragePool(Contract):
    """One region of storage a mutation can be admitted against."""

    pool_id: StoragePoolId = meaning("platform-minted identity of this pool")
    host_id: HostId = meaning("the host this pool belongs to")
    mount_point: str = meaning("path at which the pool's filesystem is mounted")
    provider_class: ProviderClass = meaning(
        "what backs the pool, which governs whether its evidence is reusable"
    )
    fingerprint: str = meaning(
        "digest of mount identity, filesystem type and quota identity; "
        "evidence is keyed on this and is invalid when it changes"
    )
    generation: int = meaning(
        "advances on every successful mutation, invalidating earlier evidence"
    )
    filesystem_type: Maybe[str] = meaning("filesystem type as reported")
    quota_identity: Maybe[str] = meaning(
        "the quota this pool is bounded by, where one applies; a quota "
        "failure bounds capacity differently from a disk-full failure"
    )


class ProbeOutcome(StrEnum):
    """What one reservation attempt established.

    The classification matters more than it looks. Only ``NO_SPACE`` and
    ``QUOTA_EXCEEDED`` are evidence about capacity; everything else is an
    absence of method or of time. The previous implementation got this right
    and it is the difference between "this pool cannot hold that" and
    "we could not find out".
    """

    #: The filesystem accepted a genuine reservation of the target amount.
    VERIFIED = "verified"
    #: ENOSPC. The pool is exhausted at this size — real capacity evidence.
    NO_SPACE = "no_space"
    #: EDQUOT. An entitlement stopped it — also real capacity evidence.
    QUOTA_EXCEEDED = "quota_exceeded"
    #: EFBIG. A file or platform limit, not a statement about the pool.
    FILE_TOO_LARGE = "file_too_large"
    #: EOPNOTSUPP. No genuine reservation primitive here. **Not** evidence
    #: that the pool is too small.
    UNSUPPORTED = "unsupported"
    #: A budget ran out mid-attempt. Bounded, not complete.
    ABANDONED = "abandoned"
    #: Anything else. Establishes nothing.
    ERROR = "error"

    @property
    def bounds_capacity(self) -> bool:
        """Whether this outcome may establish an upper bound."""
        return self in (ProbeOutcome.NO_SPACE, ProbeOutcome.QUOTA_EXCEEDED)


class SanityStatus(StrEnum):
    """How the empirical evidence stands against the policy decision.

    The question is deliberately narrow: *can evidence support the current
    policy decision?* — never *what is this filesystem's maximum?* On a mount
    advertising half a petabyte the second question has no terminating answer.
    """

    #: No probe has run.
    NOT_CHECKED = "not_checked"
    #: A genuine reservation reached the policy ceiling. Policy confirmed.
    POLICY_CAP_VERIFIED = "policy_cap_verified"
    #: Something was verified, but a budget stopped the ladder below the
    #: ceiling. Useful evidence, and **not** a reason to lower capacity: a
    #: probe that ran out of time proved nothing about the pool's limit.
    PARTIALLY_VERIFIED = "partially_verified"
    #: A genuine space or quota failure occurred below the policy ceiling.
    #: The policy assumption is wrong and capacity must come down.
    CONTRADICTED = "contradicted"
    #: The filesystem offers no genuine reservation primitive, so no
    #: empirical evidence is obtainable here. Policy stands unchanged.
    UNSUPPORTED = "unsupported"
    #: The probe failed for a reason that establishes nothing.
    INCONCLUSIVE = "inconclusive"


class SanityStopReason(StrEnum):
    """Which budget or finding ended the ladder.

    Reported separately because knowing *which* limit stopped a search is
    what tells an operator whether to raise the time budget, the work budget
    or the ceiling — the previous implementation's own conclusion after a
    48-minute search.
    """

    POLICY_CAP_REACHED = "policy_cap_reached"
    CAPACITY_FAILURE = "capacity_failure"
    TIME_BUDGET = "time_budget"
    WORK_BUDGET = "work_budget"
    CHECKPOINT_BUDGET = "checkpoint_budget"
    UNSUPPORTED = "unsupported"
    CANCELLED = "cancelled"
    ERROR = "error"


@contract(kind="storage.probe_attempt", version=1)
@dataclass(frozen=True, slots=True)
class ProbeAttempt(Contract):
    """One rung of the ladder, and what it established."""

    target_bytes: int = meaning("the amount this attempt tried to reserve")
    outcome: ProbeOutcome = meaning("what the attempt established")
    reserved_bytes: int = meaning(
        "how much was genuinely reserved before the attempt ended; an "
        "abandoned attempt still reserved something"
    )
    duration_seconds: float = meaning("how long it took, which is the cost")
    detail: str | None = meaning("the underlying reason, when there was one",
                                 default=None)


@contract(kind="storage.sanity_evidence", version=1)
@dataclass(frozen=True, slots=True)
class StorageSanityEvidence(Contract):
    """Empirical evidence about one pool, as bounds rather than a number.

    Immutable, and scoped so it cannot be reused for a pool it did not
    describe. `docs/PRODUCT_VISION.md` §5.4: facts do not change, policy
    reinterprets them.

    There is deliberately no "actual capacity" field. The conservative
    figure is always the largest verified lower bound — never a midpoint, an
    interpolation, the raw filesystem report or an unverified upper bound.
    """

    mount_point: str = meaning("the pool this describes")
    host_fingerprint: str = meaning(
        "the host it was gathered on; evidence is not portable between hosts"
    )
    pool_fingerprint: str = meaning(
        "the pool's identity, so evidence cannot be reused after the "
        "filesystem underneath it changes"
    )
    probe_policy_version: str = meaning(
        "the probe policy in force, so an old result stays explicable"
    )
    probe_method: Name = meaning("how bytes were reserved")
    status: SanityStatus = meaning("how the evidence stands against policy")
    stop_reason: SanityStopReason = meaning("which budget or finding ended it")
    observed_at: dt.datetime = meaning("when the probe ran, UTC")
    policy_target_bytes: int = meaning(
        "the policy ceiling the probe was asked to support; the ladder never "
        "goes beyond it, because nothing above it can change the decision"
    )
    verified_lower_bound_bytes: Maybe[int] = meaning(
        "the largest amount genuinely reserved. Unresolved when nothing was",
        default=NOT_PROVIDED,
    )
    observed_failure_upper_bytes: Maybe[int] = meaning(
        "the smallest amount that genuinely failed for space or quota. "
        "Unresolved is the normal outcome and is not a gap in the result",
        default=NOT_PROVIDED,
    )
    attempts: tuple[ProbeAttempt, ...] = meaning(
        "every rung, in order, so the conclusion can be argued with",
        default=(),
    )
    total_reserved_bytes: int = meaning(
        "cumulative bytes reserved across the ladder — the probe's real cost",
        default=0,
    )
    elapsed_seconds: float = meaning("wall clock across the whole ladder",
                                     default=0.0)
    cleanup_verified: bool = meaning(
        "whether the probe artifact was confirmed gone. Confirmed by absence "
        "of the path, never by a free-space delta: deleting a 42,990 MiB "
        "probe once returned about 1.1 GB to df immediately",
        default=False,
    )
    orphans_removed: int = meaning(
        "probe artifacts from an earlier interrupted run, cleaned before "
        "this one started", default=0
    )
