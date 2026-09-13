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

from kultrun.evidence.contracts import Confidence, Provenance
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
    detail: str | None = meaning(
        "the underlying reason, when there was one", default=None
    )


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
    elapsed_seconds: float = meaning("wall clock across the whole ladder", default=0.0)
    cleanup_verified: bool = meaning(
        "whether the probe artifact was confirmed gone. Confirmed by absence "
        "of the path, never by a free-space delta: deleting a 42,990 MiB "
        "probe once returned about 1.1 GB to df immediately",
        default=False,
    )
    orphans_removed: int = meaning(
        "probe artifacts from an earlier interrupted run, cleaned before "
        "this one started",
        default=0,
    )


# -- ownership ---------------------------------------------------------------


class OwnershipId(EntityId):
    """Identifies one Kultrun-managed storage resource."""

    prefix = "own"


class InstallationGenerationId(EntityId):
    """Identifies one managed installation generation."""

    prefix = "igen"


class ManagedResourceType(StrEnum):
    """What kind of managed root this is. Ownership is at the root, not per file."""

    STATE_ROOT = "state_root"
    RUNTIME_STAGING = "runtime_staging"
    RUNTIME_FINAL = "runtime_final"
    INSTALL_CACHE = "install_cache"
    MODEL_STAGING = "model_staging"
    MODEL_ARTIFACT = "model_artifact"
    DOWNLOAD_CACHE = "download_cache"
    TEMP = "temp"
    TELEMETRY = "telemetry"
    LOGS = "logs"
    GENERATED_CONFIG = "generated_config"
    SONAR_PROBE = "sonar_probe"
    INSTALLATION_GENERATION = "installation_generation"


class LifecycleState(StrEnum):
    """Where a managed resource is in its life."""

    PREPARING = "preparing"
    ACTIVE = "active"
    FAILED = "failed"
    DISPOSABLE = "disposable"
    RETAINED = "retained"
    UNRESOLVED = "unresolved"


class CleanupPolicy(StrEnum):
    """Whether Step 0 may delete this resource when otherwise eligible."""

    DISPOSABLE = "disposable"
    RETAIN = "retain"
    MANUAL = "manual"


class ManagedOccupancyClass(StrEnum):
    """Planning classification of one owned root. Not a second ownership model.

    ACTIVE and REUSABLE occupy bytes that must not be treated as free.
    RECLAIMABLE may be counted as potential post-reclaim capacity on the same
    quota domain after a product-owned delete. UNKNOWN never increases
    capacity.
    """

    ACTIVE = "active"
    REUSABLE = "reusable"
    RECLAIMABLE = "reclaimable"
    PROTECTED = "protected"
    UNKNOWN = "unknown"


class OwnershipConflict(StrEnum):
    """Why automatic deletion is refused."""

    NONE = "none"
    MANIFEST_MISSING = "manifest_missing"
    REGISTRY_MISSING = "registry_missing"
    IDENTITY_MISMATCH = "manifest_registry_mismatch"
    ACTIVE_REFERENCE = "active_reference"
    PROTECTED = "protected"
    LEGACY_UNLABELLED = "legacy_unlabelled"
    PATH_ESCAPE = "path_escape"


LOCAL_OWNER_FILENAME = ".kultrun-owner.json"


@contract(kind="storage.ownership_record", version=1)
@dataclass(frozen=True, slots=True)
class OwnershipRecord(Contract):
    """Positive ownership of one managed root. Dual with the local marker."""

    ownership_id: OwnershipId = meaning("platform-minted identity of this resource")
    host_id: HostId = meaning("host this managed root belongs to")
    resource_type: ManagedResourceType = meaning("kind of managed root")
    managed_root: str = meaning("absolute path of the owned root")
    created_at: dt.datetime = meaning("when ownership was asserted, UTC")
    kultrun_version: str = meaning("Kultrun version that created the resource")
    created_by: str = meaning("always kultrun; never inferred from a path")
    lifecycle_state: LifecycleState = meaning("current lifecycle classification")
    cleanup_policy: CleanupPolicy = meaning("whether Step 0 may delete this root")
    protected: bool = meaning("true when automatic cleanup is forbidden")
    rollback_protected: bool = meaning(
        "true when this generation is retained for rollback"
    )
    evidence_retained: bool = meaning(
        "true when the root is kept as investigation evidence"
    )
    storage_pool_id: Maybe[str] = meaning(
        "StoragePool identity of the quota domain", default=NOT_PROVIDED
    )
    quota_identity: Maybe[str] = meaning(
        "quota domain this root spends from", default=NOT_PROVIDED
    )
    installation_generation_id: Maybe[str] = meaning(
        "generation this root belongs to", default=NOT_PROVIDED
    )
    runtime_installation_id: Maybe[str] = meaning(
        "RuntimeInstallation identity when this is a runtime root",
        default=NOT_PROVIDED,
    )
    artifact_id: Maybe[str] = meaning(
        "ModelArtifact identity when this is an artifact root",
        default=NOT_PROVIDED,
    )
    deployment_id: Maybe[str] = meaning(
        "DeploymentPlan identity when this is bound to a plan",
        default=NOT_PROVIDED,
    )


@contract(kind="storage.installation_generation", version=1)
@dataclass(frozen=True, slots=True)
class InstallationGeneration(Contract):
    """One managed generation: runtime, staging, caches, config references.

    A seam, not an installer. Prepare / verify / promote / rollback GC come later.
    """

    generation_id: InstallationGenerationId = meaning("identity of this generation")
    host_id: HostId = meaning("host this generation was created on")
    created_at: dt.datetime = meaning("when the generation was opened, UTC")
    lifecycle_state: LifecycleState = meaning("preparing, active, failed, or retained")
    rollback_protected: bool = meaning("true while a prior generation must be kept")
    ownership_ids: tuple[str, ...] = meaning(
        "owned roots that belong to this generation", default=()
    )


# -- evidence ----------------------------------------------------------------


class StorageEvidenceStatus(StrEnum):
    """How storage evidence may be used. Names the authorization class."""

    AUTHORITATIVE = "authoritative"
    CORROBORATED = "corroborated"
    PROBED = "probed"
    BOUNDED = "bounded"
    CONTRADICTED = "contradicted"
    UNRESOLVED = "unresolved"


class StorageFailureCode(StrEnum):
    """Normalized write failures. Not installer flavour text."""

    STORAGE_QUOTA_EXCEEDED = "storage_quota_exceeded"
    STORAGE_SPACE_EXHAUSTED = "storage_space_exhausted"
    STORAGE_PERMISSION_DENIED = "storage_permission_denied"
    STORAGE_IO_FAILURE = "storage_io_failure"
    STORAGE_UNRESOLVED = "storage_unresolved"


class ManagedPathPurpose(StrEnum):
    """Why a managed path exists. Used to bind paths to pools."""

    STATE_ROOT = "state_root"
    RUNTIME_STAGING = "runtime_staging"
    RUNTIME_FINAL = "runtime_final"
    INSTALL_CACHE = "install_cache"
    MODEL_STAGING = "model_staging"
    MODEL_FINAL = "model_final"
    DOWNLOAD_CACHE = "download_cache"
    TEMP = "temp"
    TELEMETRY = "telemetry"
    LOGS = "logs"


@contract(kind="storage.capacity_evidence", version=1)
@dataclass(frozen=True, slots=True)
class StorageCapacityEvidence(Contract):
    """Normalized capacity evidence for one pool. Capacity consumes this as data."""

    host_id: HostId = meaning("host this evidence was gathered on")
    mount_point: str = meaning("pool mount this describes")
    quota_identity: Maybe[str] = meaning("quota domain, when known")
    pool_fingerprint: str = meaning("pool identity; invalid when the mount changes")
    observed_at: dt.datetime = meaning("when this evidence was produced, UTC")
    status: StorageEvidenceStatus = meaning("authorization class of this evidence")
    confidence: Confidence = meaning("how much weight this evidence carries")
    provenance: Provenance = meaning("who produced it, when, under which policy")
    reported_available_bytes: Maybe[int] = meaning(
        "generic filesystem-reported free space; never authorizes alone",
        default=NOT_PROVIDED,
    )
    declared_available_bytes: Maybe[int] = meaning(
        "strongest native/declared available figure, when one exists",
        default=NOT_PROVIDED,
    )
    probe_available_bytes: Maybe[int] = meaning(
        "technology-specific probe available figure, when one ran",
        default=NOT_PROVIDED,
    )
    hard_maximum_bytes: Maybe[int] = meaning(
        "smallest known hard entitlement; a probe may not exceed it",
        default=NOT_PROVIDED,
    )
    operational_available_bytes: Maybe[int] = meaning(
        "available after arbitration, before Kultrun headroom; not SAFE",
        default=NOT_PROVIDED,
    )
    authorizing_available_bytes: Maybe[int] = meaning(
        "the only figure ResourceManager may spend; unresolved is not zero",
        default=NOT_PROVIDED,
    )
    belief_bound_bytes: Maybe[int] = meaning(
        "heuristic ceiling for display; never authorizing SAFE",
        default=NOT_PROVIDED,
    )
    native_source: Maybe[str] = meaning(
        "declared/native source identity", default=NOT_PROVIDED
    )
    probe_name: Maybe[str] = meaning(
        "technology probe that ran, if any", default=NOT_PROVIDED
    )
    probe_available: bool = meaning("whether a compatible probe existed", default=False)
    probe_executed: bool = meaning("whether that probe actually ran", default=False)
    disagreement_ratio: Maybe[float] = meaning(
        "abs(native-probe)/max(native,probe) when both exist", default=NOT_PROVIDED
    )
    selected_reason: str = meaning("why the operational value was chosen", default="")
    administrator_bound_bytes: Maybe[int] = meaning(
        "manual bound; never overrides a smaller hard or empirical failure",
        default=NOT_PROVIDED,
    )
    accounted_managed_bytes: Maybe[int] = meaning(
        "platform-managed bytes on this pool when authorizing remaining "
        "was last characterized; used to refresh remaining without "
        "discarding the characterization",
        default=NOT_PROVIDED,
    )


@contract(kind="storage.administrator_bound", version=1)
@dataclass(frozen=True, slots=True)
class AdministratorCapacityBound(Contract):
    """Last-resort administrator-declared available writable bytes for one pool.

    Used only when native, specialist, and Sonar cannot establish authorizing
    capacity. Weaker than a smaller hard entitlement or empirical failure.
    Identity-keyed: host, mount, fingerprint, and quota must still match.
    """

    host_id: HostId = meaning("host this bound was recorded on")
    mount_point: str = meaning("pool mount this bound describes")
    quota_identity: Maybe[str] = meaning("quota domain, when known")
    pool_fingerprint: str = meaning("pool identity; invalid when the mount changes")
    available_bytes: int = meaning(
        "administrator-declared available writable bytes; last-resort "
        "evidence, never stronger than a smaller hard or empirical bound"
    )
    observed_at: dt.datetime = meaning(
        "when the administrator supplied this value, UTC"
    )
    provenance: Provenance = meaning("who recorded it, when, under which policy")


@contract(kind="storage.requirement", version=1)
@dataclass(frozen=True, slots=True)
class StorageRequirement(Contract):
    """What a mutation would cost on one pool. Conservative bound admits."""

    confidence: Confidence = meaning("how much weight this requirement carries")
    persistent_bytes: Maybe[int] = meaning(
        "bytes expected to remain after success", default=NOT_PROVIDED
    )
    peak_transient_bytes: Maybe[int] = meaning(
        "staging/workspace peak above persistent", default=NOT_PROVIDED
    )
    cache_bytes: Maybe[int] = meaning(
        "install/download cache if Kultrun-owned", default=NOT_PROVIDED
    )
    reserve_bytes: Maybe[int] = meaning(
        "emergency headroom this operation must leave", default=NOT_PROVIDED
    )
    required_peak_free_bytes: Maybe[int] = meaning(
        "conservative peak free space required before mutation",
        default=NOT_PROVIDED,
    )
    mount_point: Maybe[str] = meaning("destination pool mount", default=NOT_PROVIDED)
    quota_identity: Maybe[str] = meaning(
        "destination quota domain", default=NOT_PROVIDED
    )
    source: Maybe[str] = meaning(
        "how this requirement was produced", default=NOT_PROVIDED
    )
    notes: tuple[str, ...] = meaning("short factual notes", default=())


@contract(kind="storage.managed_path", version=1)
@dataclass(frozen=True, slots=True)
class ManagedPathBinding(Contract):
    """One significant path bound to a pool. Not a capacity claim."""

    host_id: HostId = meaning("host this path belongs to")
    purpose: ManagedPathPurpose = meaning("why this path exists")
    path: str = meaning("absolute path")
    mount_point: Maybe[str] = meaning(
        "StoragePool mount that contains it", default=NOT_PROVIDED
    )
    quota_identity: Maybe[str] = meaning(
        "quota domain it spends from", default=NOT_PROVIDED
    )
    ownership_id: Maybe[str] = meaning(
        "ownership record, when asserted", default=NOT_PROVIDED
    )
    persistent: bool = meaning(
        "true when the path is expected to survive restart", default=True
    )


@contract(kind="storage.probe_report", version=1)
@dataclass(frozen=True, slots=True)
class ProbeReport(Contract):
    """Whether a technology probe existed, ran, and what it measured."""

    probe_name: str = meaning("registered probe identity")
    technology: str = meaning("storage technology this probe addresses")
    compatible: bool = meaning("true when supports() matched this environment")
    available: bool = meaning("true when the probe's method can actually run")
    executed: bool = meaning("true when probe() was invoked")
    available_bytes: Maybe[int] = meaning(
        "available writable bytes the probe measured", default=NOT_PROVIDED
    )
    hard_maximum_bytes: Maybe[int] = meaning(
        "hard entitlement the probe observed, if any", default=NOT_PROVIDED
    )
    detail: str = meaning("why it ran, skipped, or failed", default="")


@contract(kind="storage.cleanup_report", version=1)
@dataclass(frozen=True, slots=True)
class CleanupReport(Contract):
    """Outcome of Step 0. Absence of deletion is not a failure."""

    host_id: HostId = meaning("host that was inventoried")
    inspected: int = meaning("managed roots considered")
    removed: int = meaning("roots actually deleted")
    bytes_removed: int = meaning("bytes removed, best effort")
    unresolved: tuple[str, ...] = meaning("roots that must not be deleted", default=())
    protected: tuple[str, ...] = meaning(
        "active, rollback, or evidence roots", default=()
    )
    legacy_unlabelled: tuple[str, ...] = meaning(
        "kultrun-looking paths without positive ownership", default=()
    )
    rediscovery_required: bool = meaning("always true after Step 0", default=True)


@contract(kind="storage.empirical_evidence", version=1)
@dataclass(frozen=True, slots=True)
class EmpiricalProbeEvidence(Contract):
    """Bounded real-write search result. Evidence, not a selection."""

    host_id: HostId = meaning("host the probe ran on")
    mount_point: str = meaning("pool that was probed")
    target_path: str = meaning("directory the probe file lived on")
    max_probe_bytes: int = meaning("configured exploration ceiling")
    bytes_physically_written: int = meaning("bytes actually written before cleanup")
    search_granularity_bytes: int = meaning("smallest step the search used")
    probe_ceiling_reached: bool = meaning(
        "true when the ceiling was hit without a capacity failure"
    )
    confidence: Confidence = meaning("weight of this empirical bound")
    provenance: Provenance = meaning("probe identity and time")
    cleanup_success: bool = meaning("true when the owned probe file was confirmed gone")
    verified_lower_bound_bytes: Maybe[int] = meaning(
        "largest successful real write", default=NOT_PROVIDED
    )
    observed_failure_upper_bytes: Maybe[int] = meaning(
        "smallest size that failed for space or quota", default=NOT_PROVIDED
    )
    failure_code: Maybe[str] = meaning(
        "STORAGE_QUOTA_EXCEEDED / STORAGE_SPACE_EXHAUSTED when observed",
        default=NOT_PROVIDED,
    )
    failure_errno: Maybe[int] = meaning(
        "underlying errno when a write failed", default=NOT_PROVIDED
    )
    elapsed_seconds: float = meaning("wall clock of the search", default=0.0)
    interrupted: bool = meaning("true when cancelled or timed out", default=False)
    algorithm_version: Maybe[str] = meaning(
        "Sonar tree identity, e.g. sonar-v2-tree", default=NOT_PROVIDED
    )
    payload_version: Maybe[str] = meaning(
        "deterministic payload generator identity", default=NOT_PROVIDED
    )
    completed_tier_units: tuple[int, ...] = meaning(
        "official fsynced checkpoints in abstract units", default=()
    )
    committed_bytes: int = meaning("largest completed checkpoint in bytes", default=0)
    run_state: Maybe[str] = meaning(
        "running, complete, interrupted_recovered, cleanup_failed, very_low",
        default=NOT_PROVIDED,
    )
    reserve_established: bool = meaning(
        "true when the owned emergency reserve was fully written", default=False
    )
    reserve_released: bool = meaning(
        "true when the reserve file was removed or never held", default=False
    )
    quota_identity: Maybe[str] = meaning(
        "quota domain this probe consumed", default=NOT_PROVIDED
    )
    pool_fingerprint: Maybe[str] = meaning(
        "pool identity at probe start; must still match at finalize",
        default=NOT_PROVIDED,
    )
    probe_id: Maybe[str] = meaning(
        "identity of this empirical run", default=NOT_PROVIDED
    )
    attempted_tier_units: tuple[int, ...] = meaning(
        "logical tree targets requested, in order", default=()
    )
    additional_bytes_last: int = meaning(
        "additional bytes written by the last grow", default=0
    )
    corroboration: Maybe[str] = meaning(
        "confirmed_bracketed, not_contradicted, lower_only, "
        "inconclusive, limited, contradicted; unset for full-tree runs",
        default=NOT_PROVIDED,
    )
    specialist_candidate_bytes: Maybe[int] = meaning(
        "specialist figure after smaller hard bounds, when corroborating",
        default=NOT_PROVIDED,
    )


@contract(kind="storage.low_space_guidance", version=1)
@dataclass(frozen=True, slots=True)
class LowSpaceGuidance(Contract):
    """Administrator guidance when authorizing storage is too small to deploy."""

    host_id: HostId = meaning("host this guidance is for")
    mount_point: str = meaning("constrained storage domain")
    quota_identity: Maybe[str] = meaning("quota domain, when known")
    authorizing_available_bytes: Maybe[int] = meaning(
        "what Kultrun can currently establish"
    )
    threshold_bytes: int = meaning("policy threshold that triggered guidance")
    cleaned_bytes: int = meaning("owned disposable bytes Step 0 removed")
    message: str = meaning("what the administrator is asked to do")
    rediscovery_required: bool = meaning("true; the next attempt must rediscover")


@contract(kind="storage.managed_occupancy_item", version=1)
@dataclass(frozen=True, slots=True)
class ManagedOccupancyItem(Contract):
    """One dual-owned root as occupancy. Not an admission and not a path guess."""

    ownership_id: OwnershipId = meaning("registry identity of this root")
    resource_type: ManagedResourceType = meaning("kind of managed root")
    occupancy_class: ManagedOccupancyClass = meaning(
        "active, reusable, reclaimable, protected, or unknown"
    )
    managed_root: str = meaning("absolute owned root; local operational path")
    occupied_bytes: int = meaning("best-effort tree size; unknown occupancy is omitted")
    mount_point: Maybe[str] = meaning("StoragePool mount this root spends from")
    quota_identity: Maybe[str] = meaning("quota domain, when known")
    pool_fingerprint: Maybe[str] = meaning("pool identity when bound")
    reason: str = meaning("why this class was assigned", default="")


@contract(kind="storage.pool_occupancy", version=1)
@dataclass(frozen=True, slots=True)
class PoolOccupancy(Contract):
    """Per-pool occupancy totals. Reclaimable is not currently free."""

    mount_point: str = meaning("StoragePool mount")
    quota_identity: Maybe[str] = meaning("quota domain, when known")
    pool_fingerprint: Maybe[str] = meaning("pool identity when bound")
    active_bytes: int = meaning("bytes required by a live workload or current install")
    reusable_bytes: int = meaning("bytes that satisfy the next foundation/model")
    reclaimable_bytes: int = meaning(
        "inactive owned bytes that a planned reclaim may release"
    )
    protected_bytes: int = meaning("owned bytes retained on purpose")
    unknown_bytes: int = meaning("unproven occupancy; never added to potential")


@contract(kind="storage.reclaim_action", version=1)
@dataclass(frozen=True, slots=True)
class ReclaimAction(Contract):
    """One planned delete. Execution re-validates ownership immediately before."""

    ownership_id: OwnershipId = meaning("root proposed for deletion")
    resource_type: ManagedResourceType = meaning("kind of managed root")
    expected_bytes: int = meaning("tree size at plan time")
    mount_point: str = meaning("quota domain mount")
    reason: str = meaning("why this root was classified reclaimable")


@contract(kind="storage.reclaim_plan", version=1)
@dataclass(frozen=True, slots=True)
class StorageReclaimPlan(Contract):
    """Pre-provision reclaim on one quota domain. Not a serving DeploymentPlan."""

    mount_point: str = meaning("destination pool")
    expected_bytes: int = meaning("sum of planned deletes")
    actions: tuple[ReclaimAction, ...] = meaning("ordered deletes")


@contract(kind="storage.reclaim_result", version=1)
@dataclass(frozen=True, slots=True)
class StorageReclaimResult(Contract):
    """What a planned reclaim actually released. Expected is not actual."""

    mount_point: str = meaning("destination pool")
    expected_bytes: int = meaning("planned release")
    actual_bytes: int = meaning("bytes observed gone after delete")
    removed: int = meaning("roots actually deleted")
    rediscovery_required: bool = meaning(
        "true; capacity must be recomputed", default=True
    )
    blocked: tuple[str, ...] = meaning("roots refused at execute time", default=())
