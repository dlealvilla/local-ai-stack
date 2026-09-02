"""Normalized capacity contracts for the capacity/model-optimization work.

AI_DEPLOYMENT_CAPACITY_CONTRACTS_C1_C2

See docs/CAPACITY_ARCHITECTURE.md sections 3, 4, 5, 29 and 37.

This module represents already-validated capacity facts coherently. It is
NOT a second resource calculator:

    core.hardware                        owns detection
    core.capacity_snapshot               owns live observation
    core.resource_capacity               owns vendor-neutral pool identity
    core.resource_safety                 owns protected reserve and
                                         safe-available-before-reservations
    core.resource_reservations           owns managed reservation accounting
    core.storage_capacity_resolution     owns storage evidence, basis
                                         and storage headroom policy
    core.storage_budget                  owns platform storage budget

Every number exposed here is copied from one of those owners. No formula
is reimplemented, and no reported value is ever promoted into a verified
one.

The one derived field is `unmanaged_usage_bytes`, which merely labels
observed usage and feeds no safety decision. It stays unset whenever the
attribution is not derivable.

Normalization receives already-established evidence. Nothing in this
module reads /proc, NVML, the filesystem, configuration or a reservation
store, so the contracts stay pure and testable.

No caller consumes these contracts yet. Deleting this module restores the
exact predecessor behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


CAPACITY_CONTRACTS_SCHEMA_VERSION = 1


#
# The logical identity of the single storage pool the platform currently
# manages. Real multi-pool hosts will derive identities from storage
# identity semantics; until then, two configured paths that resolve to the
# same underlying storage must never be presented as two pools.
#
PLATFORM_DATA_STORAGE_POOL_ID = "storage:platform_data"


def _nonnegative_int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None

    value = int(value)

    if value < 0:
        return None

    return value


# ---------------------------------------------------------------------------
# HeadroomPolicy
# ---------------------------------------------------------------------------
#
# Policy is an INPUT; a protected byte figure is an OUTPUT. Keeping them
# apart is what later allows administrator overrides, policy versioning,
# optimization profiles and explainability.
#
# Every value here is read from the authoritative policy owner
# (core.resource_safety for memory, storage capacity resolution's
# allocation policy for storage). Nothing is defaulted or hard-coded, so
# an administrator override of the underlying policy is reflected
# automatically and this layer can never disagree with the calculation
# that actually applied.
#


@dataclass(frozen=True)
class MemoryHeadroomPolicy:
    """Configured headroom for one memory architecture.

    Either a proportional/floor pair, for architectures whose accounting
    is resolved, or a `strategy` naming why the architecture fails
    closed. Unified memory can share physical bytes with system RAM, so
    it carries a strategy rather than a fraction.
    """

    memory_type: str
    reserve_fraction: float | None
    minimum_reserve_bytes: int | None
    strategy: str | None

    @property
    def resolved(self) -> bool:
        return self.reserve_fraction is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StorageHeadroomPolicy:
    """Configured storage headroom, owned by storage capacity resolution."""

    protected_free_fraction: float | None
    minimum_reserve_bytes: int | None
    warning_free_fraction: float | None
    platform_allocation_percent: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HeadroomPolicy:
    """The configured safety inputs that produced an envelope.

    `cpu` is deliberately absent rather than empty. The source detects
    CPU model and core count but has no cgroup quota, no cpuset
    effective-core resolution and no CPU reserve policy, so there is no
    CPU headroom to represent. See `CpuCapacityStatus`.
    """

    schema_version: int
    memory: tuple[MemoryHeadroomPolicy, ...]
    storage: StorageHeadroomPolicy | None

    def for_memory_type(
        self,
        memory_type: str | None,
    ) -> MemoryHeadroomPolicy | None:
        for policy in self.memory:
            if policy.memory_type == memory_type:
                return policy

        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory": [
                policy.to_dict()
                for policy in self.memory
            ],
            "storage": (
                self.storage.to_dict()
                if self.storage is not None
                else None
            ),
        }


@dataclass(frozen=True)
class CpuCapacityStatus:
    """Why no CPU capacity figures appear in the envelope.

    CPU capability is known; CPU capacity policy is not yet resolved.
    This is a schema-level hook so the distinction is explicit instead
    of looking like an oversight, and it carries no numeric values.
    """

    capability_known: bool
    effective_capacity_available: bool
    headroom_policy_available: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CPU_CAPACITY_POLICY_UNRESOLVED = CpuCapacityStatus(
    capability_known=True,
    effective_capacity_available=False,
    headroom_policy_available=False,
    reason="cpu_capacity_policy_not_yet_resolved",
)


def build_headroom_policy(
    *,
    resource_safety: Mapping[str, Any],
    storage_plan: Mapping[str, Any] | None = None,
) -> HeadroomPolicy:
    """Normalize the configured safety policy that produced the outputs.

    `resource_safety["policy"]` is the authoritative memory policy that
    `build_resource_safety` actually applied, so reading it here cannot
    drift from the calculation. Storage policy comes from the capacity
    resolution's `allocation_policy`, with the administrator allocation
    percentage from the platform budget.
    """

    resource_safety = _require_mapping(
        resource_safety,
        name="resource_safety",
    )

    policy = resource_safety.get("policy") or {}

    memory_policies = []

    for memory_type in sorted(policy):
        entry = policy.get(memory_type) or {}

        if not isinstance(entry, Mapping):
            continue

        fraction = entry.get("reserve_fraction")

        memory_policies.append(
            MemoryHeadroomPolicy(
                memory_type=memory_type,
                reserve_fraction=(
                    float(fraction)
                    if isinstance(fraction, (int, float))
                    and not isinstance(fraction, bool)
                    else None
                ),
                minimum_reserve_bytes=_nonnegative_int_or_none(
                    entry.get("minimum_reserve_bytes")
                ),
                strategy=entry.get("strategy"),
            )
        )

    storage_policy = None

    if storage_plan is not None:
        storage_plan = _require_mapping(
            storage_plan,
            name="storage_plan",
        )

        allocation_policy = (
            (storage_plan.get("capacity") or {}).get(
                "allocation_policy"
            )
            or {}
        )
        budget = storage_plan.get("platform_budget") or {}

        allocation_percent = budget.get(
            "platform_allocation_percent"
        )

        storage_policy = StorageHeadroomPolicy(
            protected_free_fraction=allocation_policy.get(
                "protected_free_fraction"
            ),
            minimum_reserve_bytes=_nonnegative_int_or_none(
                allocation_policy.get("minimum_reserve_bytes")
            ),
            warning_free_fraction=allocation_policy.get(
                "warning_free_fraction"
            ),
            platform_allocation_percent=(
                float(allocation_percent)
                if isinstance(allocation_percent, (int, float))
                and not isinstance(allocation_percent, bool)
                else None
            ),
        )

    return HeadroomPolicy(
        schema_version=CAPACITY_CONTRACTS_SCHEMA_VERSION,
        memory=tuple(memory_policies),
        storage=storage_policy,
    )


# ---------------------------------------------------------------------------
# HostCapabilityProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceleratorCapability:
    """Relatively stable capability facts for one accelerator.

    `memory_type` is the classification owned by core.resource_capacity:
    `dedicated_vram`, `unified_memory` or the fail-closed
    `accelerator_memory`. It is what distinguishes dedicated from unified
    memory, and it must not be inferred here.
    """

    pool_id: str
    index: int
    vendor: str | None
    name: str | None
    memory_type: str | None
    memory_total_bytes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StoragePoolCapability:
    """Identity and capability metadata for one storage pool."""

    pool_id: str
    path: str | None
    provider: str | None
    reported_scope: str | None
    quota_known: bool | None

    # Populated only when the caller supplies storage identity evidence
    # from core.storage_capacity_cache.inspect_storage_identity. This
    # module never performs the stat itself.
    device_id: int | None = None
    mount_source: str | None = None
    filesystem_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostCapabilityProfile:
    """What the host is, as distinct from what is momentarily free.

    Deliberately absent, because no current detector provides them:

    - host fingerprint. No host-identity concept exists in the source
      yet; storage identity is currently the only fingerprint available
      and it belongs to the storage pool.
    - accelerator compute capability and architecture. `nvidia-smi` is
      queried for name, memory.total and memory.free only.
    - effective CPU limits. Only model and core count are detected, so
      no cgroup/quota-corrected value exists to represent.

    Point-in-time state (live availability, usage, reservations) belongs
    to CapacityEnvelope, not here.
    """

    schema_version: int
    operating_system: str | None
    architecture: str | None
    cpu_model: str | None
    cpu_cores: int | None
    ram_total_bytes: int | None
    accelerators: tuple[AcceleratorCapability, ...]
    storage_pools: tuple[StoragePoolCapability, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operating_system": self.operating_system,
            "architecture": self.architecture,
            "cpu_model": self.cpu_model,
            "cpu_cores": self.cpu_cores,
            "ram_total_bytes": self.ram_total_bytes,
            "accelerators": [
                accelerator.to_dict()
                for accelerator in self.accelerators
            ],
            "storage_pools": [
                pool.to_dict()
                for pool in self.storage_pools
            ],
        }


# ---------------------------------------------------------------------------
# CapacityEnvelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryPoolCapacity:
    """Current safe state of one memory pool.

    Field names state the actual mathematics, because the distinction
    below is easy to get wrong and expensive when wrong:

        reported_total_bytes
            observed pool size.

        reported_available_bytes
            observed free bytes. This ALREADY reflects any managed
            workload that is physically consuming memory.

        protected_reserve_bytes
            min(total, max(fraction * total, minimum)), calculated by
            core.resource_safety from the headroom policy.

        observed_safe_available_bytes
            max(0, reported_available - protected_reserve), calculated
            by core.resource_safety. It is a LIVE OBSERVATION minus
            headroom, not a pool total: if a managed workload is running,
            its consumption is already subtracted here.

        reconstructed_safe_pool_capacity_bytes
            the reservation ledger's accounting capacity for the pool,
            which ResourceManager reconstructs as
            min(previous_total, observed_safe + managed_reserved) so the
            figure means "safe pool total including what is reserved".

        managed_reserved_bytes
            the ledger's current reservation total.

        safe_available_for_additional_workload_bytes
            the ledger's own `available`, i.e. reconstructed capacity
            minus managed reservations. This is the answer to "how much
            can another workload receive".

    Subtracting `managed_reserved_bytes` from
    `observed_safe_available_bytes` is the double-subtraction bug: for a
    workload that is already consuming memory, the reservation would be
    removed twice. All three reservation figures are therefore copied
    verbatim from the ledger snapshot and never recomputed here.

    There is no `effective_total_bytes`: the existing implementation
    calculates no intermediate effective value for memory, and inventing
    one would fabricate a fact.
    """

    pool_id: str
    resource_type: str | None
    memory_type: str | None
    scope: dict[str, Any]

    reported_total_bytes: int | None
    reported_used_bytes: int | None
    reported_available_bytes: int | None

    safety_resolved: bool
    safety_reason: str | None
    headroom_policy_key: str | None
    protected_reserve_bytes: int | None
    observed_safe_available_bytes: int | None

    unmanaged_usage_bytes: int | None = None
    unmanaged_usage_basis: str | None = None

    reconstructed_safe_pool_capacity_bytes: int | None = None
    managed_reserved_bytes: int | None = None
    safe_available_for_additional_workload_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def explain(self) -> list[dict[str, Any]]:
        """The accounting chain, in order, with the owner of each figure."""

        stages = [
            (
                "reported_total",
                self.reported_total_bytes,
                "capacity_snapshot",
            ),
            (
                "reported_available",
                self.reported_available_bytes,
                "capacity_snapshot",
            ),
            (
                "protected_reserve",
                self.protected_reserve_bytes,
                "resource_safety",
            ),
            (
                "observed_safe_available",
                self.observed_safe_available_bytes,
                "resource_safety",
            ),
            (
                "reconstructed_safe_pool_capacity",
                self.reconstructed_safe_pool_capacity_bytes,
                "reservation_ledger",
            ),
            (
                "managed_reserved",
                self.managed_reserved_bytes,
                "reservation_ledger",
            ),
            (
                "safe_available_for_additional_workload",
                self.safe_available_for_additional_workload_bytes,
                "reservation_ledger",
            ),
        ]

        return [
            {
                "stage": stage,
                "value_bytes": value,
                "owner": owner,
            }
            for stage, value, owner in stages
        ]


@dataclass(frozen=True)
class StoragePoolCapacity:
    """Current safe state of one storage pool.

    The reported/verified distinction is the critical invariant here. A
    pool may simultaneously report hundreds of terabytes free and have no
    verified capacity at all, in which case every safe figure stays
    `None`. Normalization must never resolve that tension in favour of
    the reported number.
    """

    pool_id: str
    path: str | None
    provider: str | None

    reported_total_bytes: int | None
    reported_free_bytes: int | None
    reported_scope: str | None
    reported_accepted_as_capacity_evidence: bool

    verified_remaining_bytes: int | None
    verified_effective_total_bytes: int | None
    verified_lower_bound_bytes: int | None
    observed_upper_failure_bytes: int | None
    capacity_basis: str | None
    capacity_confidence: str | None
    capacity_source: str | None
    evidence_cache_valid: bool | None

    protected_reserve_bytes: int | None
    safe_allocatable_bytes: int | None

    platform_used_bytes: int | None
    available_for_new_platform_bytes: int | None
    budget_resolved: bool
    budget_reason: str | None
    budget_basis: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def explain(self) -> list[dict[str, Any]]:
        """The storage chain from reported signal to allocatable budget.

        `reported_*` deliberately appears first and is deliberately not
        an input to anything below it. On a provider-backed volume it is
        recorded and rejected, so a pool can report terabytes free while
        every figure below stays `None`.
        """

        stages = [
            (
                "reported_free",
                self.reported_free_bytes,
                "capacity_snapshot",
            ),
            (
                "verified_lower_bound",
                self.verified_lower_bound_bytes,
                "storage_capacity_resolution",
            ),
            (
                "observed_upper_failure",
                self.observed_upper_failure_bytes,
                "storage_capacity_resolution",
            ),
            (
                "verified_remaining",
                self.verified_remaining_bytes,
                "storage_capacity_resolution",
            ),
            (
                "protected_reserve",
                self.protected_reserve_bytes,
                "storage_capacity_resolution",
            ),
            (
                "safe_allocatable",
                self.safe_allocatable_bytes,
                "storage_capacity_resolution",
            ),
            (
                "available_for_new_platform",
                self.available_for_new_platform_bytes,
                "storage_budget",
            ),
        ]

        return [
            {
                "stage": stage,
                "value_bytes": value,
                "owner": owner,
            }
            for stage, value, owner in stages
        ]


@dataclass(frozen=True)
class CapacityEnvelope:
    """One coherent answer to "what can be safely allocated right now".

    Accelerators and storage are collections, not scalars, even on a host
    with one GPU and one pool.

    No CPU pool is present: `core.resource_capacity` normalizes memory
    pools only, so there is no CPU capacity, headroom or safe figure to
    represent. CPU core count lives in HostCapabilityProfile.
    """

    schema_version: int
    generated_at: str | None
    source: dict[str, Any]
    headroom_policy: HeadroomPolicy
    cpu_capacity_status: CpuCapacityStatus
    memory_pools: tuple[MemoryPoolCapacity, ...]
    storage_pools: tuple[StoragePoolCapacity, ...]
    reservations_applied: bool
    unresolved_pool_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source": dict(self.source),
            "headroom_policy": self.headroom_policy.to_dict(),
            "cpu_capacity_status": (
                self.cpu_capacity_status.to_dict()
            ),
            "memory_pools": [
                pool.to_dict()
                for pool in self.memory_pools
            ],
            "storage_pools": [
                pool.to_dict()
                for pool in self.storage_pools
            ],
            "reservations_applied": self.reservations_applied,
            "unresolved_pool_ids": list(self.unresolved_pool_ids),
        }

    def policy_for(
        self,
        pool_id: str,
    ) -> MemoryHeadroomPolicy | None:
        """The headroom policy that produced this pool's protected reserve."""

        pool = self.memory_pool(pool_id)

        if pool is None:
            return None

        return self.headroom_policy.for_memory_type(
            pool.headroom_policy_key
        )

    def memory_pool(self, pool_id: str) -> MemoryPoolCapacity | None:
        for pool in self.memory_pools:
            if pool.pool_id == pool_id:
                return pool

        return None

    def storage_pool(self, pool_id: str) -> StoragePoolCapacity | None:
        for pool in self.storage_pools:
            if pool.pool_id == pool_id:
                return pool

        return None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _require_mapping(value: Any, *, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")

    return value


def _accelerator_pools(resource_capacity: Mapping[str, Any]):
    for pool in resource_capacity.get("resource_pools") or []:
        if not isinstance(pool, Mapping):
            continue

        scope = pool.get("scope") or {}

        if scope.get("kind") == "accelerator":
            yield pool, scope


def build_host_capability_profile(
    *,
    capacity_snapshot: Mapping[str, Any],
    resource_capacity: Mapping[str, Any],
    storage_plan: Mapping[str, Any] | None = None,
    storage_identity: Mapping[str, Any] | None = None,
) -> HostCapabilityProfile:
    """Normalize stable host capability facts already established elsewhere.

    `capacity_snapshot` supplies host, CPU, RAM and accelerator
    observation. `resource_capacity` supplies the accelerator memory-type
    classification and pool identity. `storage_plan` and
    `storage_identity`, when supplied, supply storage-pool identity.
    """

    capacity_snapshot = _require_mapping(
        capacity_snapshot,
        name="capacity_snapshot",
    )
    resource_capacity = _require_mapping(
        resource_capacity,
        name="resource_capacity",
    )

    host = capacity_snapshot.get("host") or {}
    memory = capacity_snapshot.get("memory") or {}
    snapshot_storage = capacity_snapshot.get("storage") or {}

    accelerators = []

    for pool, scope in _accelerator_pools(resource_capacity):
        capacity = pool.get("capacity") or {}

        accelerators.append(
            AcceleratorCapability(
                pool_id=str(pool.get("pool_id")),
                index=int(scope.get("accelerator_index")),
                vendor=scope.get("vendor"),
                name=scope.get("name"),
                memory_type=pool.get("memory_type"),
                memory_total_bytes=_nonnegative_int_or_none(
                    capacity.get("total_bytes")
                ),
            )
        )

    storage_pools: list[StoragePoolCapability] = []

    if storage_plan is not None:
        storage_plan = _require_mapping(
            storage_plan,
            name="storage_plan",
        )

        capacity = storage_plan.get("capacity") or {}
        usage = storage_plan.get("platform_usage") or {}
        identity = storage_identity or {}

        storage_pools.append(
            StoragePoolCapability(
                pool_id=PLATFORM_DATA_STORAGE_POOL_ID,
                path=usage.get("data_root")
                or snapshot_storage.get("path"),
                provider=capacity.get("provider"),
                reported_scope=snapshot_storage.get("scope"),
                quota_known=snapshot_storage.get("quota_known"),
                device_id=identity.get("device_id"),
                mount_source=identity.get("mount_source"),
                filesystem_type=identity.get("filesystem_type"),
            )
        )

    return HostCapabilityProfile(
        schema_version=CAPACITY_CONTRACTS_SCHEMA_VERSION,
        operating_system=host.get("operating_system"),
        architecture=host.get("architecture"),
        cpu_model=host.get("cpu_model"),
        cpu_cores=host.get("cpu_cores"),
        ram_total_bytes=_nonnegative_int_or_none(
            memory.get("total_bytes")
        ),
        accelerators=tuple(accelerators),
        storage_pools=tuple(storage_pools),
    )


def _build_memory_pool(
    pool: Mapping[str, Any],
    *,
    reservation_snapshot: Mapping[str, Any] | None,
) -> MemoryPoolCapacity:
    capacity = pool.get("capacity") or {}
    safety = pool.get("safety") or {}

    pool_id = str(pool.get("pool_id"))

    reconstructed_capacity = None
    managed_reserved = None
    safe_available = None

    if reservation_snapshot is not None:
        #
        # Copied verbatim. The ledger's `available` is already
        # `capacities - reserved` against its own reconstructed
        # accounting total, so subtracting reservations again here would
        # double-count them.
        #
        reconstructed_capacity = _nonnegative_int_or_none(
            (reservation_snapshot.get("capacities") or {}).get(pool_id)
        )
        managed_reserved = _nonnegative_int_or_none(
            (reservation_snapshot.get("reserved") or {}).get(pool_id)
        )
        safe_available = _nonnegative_int_or_none(
            (reservation_snapshot.get("available") or {}).get(pool_id)
        )

    #
    # Observed usage can only be attributed to unmanaged consumers when
    # nothing is managed. A reservation is an entitlement rather than a
    # measurement, so once one exists the split between managed and
    # unmanaged consumption is not derivable from these inputs and must
    # not be guessed.
    #
    reported_used = _nonnegative_int_or_none(
        capacity.get("used_bytes")
    )

    unmanaged_usage = None
    unmanaged_usage_basis = "managed_reservation_state_unknown"

    if reservation_snapshot is not None:
        if managed_reserved:
            unmanaged_usage_basis = (
                "not_derivable_with_active_reservations"
            )

        else:
            unmanaged_usage = reported_used
            unmanaged_usage_basis = (
                "all_observed_usage_unmanaged"
            )

    return MemoryPoolCapacity(
        pool_id=pool_id,
        resource_type=pool.get("resource_type"),
        memory_type=pool.get("memory_type"),
        scope=dict(pool.get("scope") or {}),
        reported_total_bytes=_nonnegative_int_or_none(
            capacity.get("total_bytes")
        ),
        reported_used_bytes=reported_used,
        reported_available_bytes=_nonnegative_int_or_none(
            capacity.get("available_bytes")
        ),
        safety_resolved=bool(safety.get("resolved", False)),
        safety_reason=safety.get("reason"),
        headroom_policy_key=pool.get("memory_type"),
        protected_reserve_bytes=_nonnegative_int_or_none(
            safety.get("protected_reserve_bytes")
        ),
        observed_safe_available_bytes=(
            _nonnegative_int_or_none(
                safety.get(
                    "safe_available_before_reservations_bytes"
                )
            )
        ),
        unmanaged_usage_bytes=unmanaged_usage,
        unmanaged_usage_basis=unmanaged_usage_basis,
        reconstructed_safe_pool_capacity_bytes=(
            reconstructed_capacity
        ),
        managed_reserved_bytes=managed_reserved,
        safe_available_for_additional_workload_bytes=(
            safe_available
        ),
    )


def _reported_filesystem_accepted(
    capacity: Mapping[str, Any],
) -> bool:
    """Whether any filesystem-reported figure was accepted as evidence.

    On a shared or provider-backed volume the filesystem figure is
    recorded but rejected, which is precisely why it must not become a
    verified capacity.
    """

    for evidence in capacity.get("evidence") or []:
        if not isinstance(evidence, Mapping):
            continue

        if evidence.get("source") in {
            "filesystem_free",
            "filesystem_statvfs",
        }:
            if evidence.get("accepted") is True:
                return True

    return False


def _build_storage_pool(
    *,
    storage_plan: Mapping[str, Any],
    capacity_snapshot: Mapping[str, Any],
) -> StoragePoolCapacity:
    capacity = storage_plan.get("capacity") or {}
    resolved = capacity.get("resolved") or {}
    consensus = capacity.get("consensus") or {}
    allocation_policy = capacity.get("allocation_policy") or {}
    budget = storage_plan.get("platform_budget") or {}
    usage = storage_plan.get("platform_usage") or {}
    cache = storage_plan.get("capacity_cache") or {}
    snapshot_storage = capacity_snapshot.get("storage") or {}

    return StoragePoolCapacity(
        pool_id=PLATFORM_DATA_STORAGE_POOL_ID,
        path=usage.get("data_root") or snapshot_storage.get("path"),
        provider=capacity.get("provider"),
        reported_total_bytes=_nonnegative_int_or_none(
            snapshot_storage.get("total_bytes")
        ),
        reported_free_bytes=_nonnegative_int_or_none(
            snapshot_storage.get("free_bytes")
        ),
        reported_scope=snapshot_storage.get("scope"),
        reported_accepted_as_capacity_evidence=(
            _reported_filesystem_accepted(capacity)
        ),
        verified_remaining_bytes=_nonnegative_int_or_none(
            resolved.get("remaining_bytes")
        ),
        verified_effective_total_bytes=_nonnegative_int_or_none(
            resolved.get("effective_total_bytes")
        ),
        verified_lower_bound_bytes=_nonnegative_int_or_none(
            consensus.get("strongest_verified_lower_bound_bytes")
        ),
        observed_upper_failure_bytes=_nonnegative_int_or_none(
            consensus.get("smallest_observed_upper_failure_bytes")
        ),
        capacity_basis=resolved.get("basis"),
        capacity_confidence=resolved.get("confidence"),
        capacity_source=storage_plan.get("capacity_source"),
        evidence_cache_valid=cache.get("valid"),
        protected_reserve_bytes=_nonnegative_int_or_none(
            allocation_policy.get("reserve_bytes")
        ),
        safe_allocatable_bytes=_nonnegative_int_or_none(
            allocation_policy.get("safe_allocatable_bytes")
        ),
        platform_used_bytes=_nonnegative_int_or_none(
            budget.get("platform_used_bytes")
        ),
        available_for_new_platform_bytes=_nonnegative_int_or_none(
            budget.get("available_for_new_platform_bytes")
        ),
        budget_resolved=bool(budget.get("resolved", False)),
        budget_reason=budget.get("reason"),
        budget_basis=budget.get("basis"),
    )


def build_capacity_envelope(
    *,
    capacity_snapshot: Mapping[str, Any],
    resource_safety: Mapping[str, Any],
    storage_plan: Mapping[str, Any] | None = None,
    reservation_snapshot: Mapping[str, Any] | None = None,
) -> CapacityEnvelope:
    """Normalize the current safe resource state from existing outputs.

    `resource_safety` is the authority for memory headroom and
    safe-available-before-reservations. `storage_plan` is the authority
    for storage evidence, basis and platform budget.
    `reservation_snapshot`, when supplied, is a
    `ResourceReservationLedger.snapshot().to_dict()` and is the authority
    for managed reservation accounting.

    Omitting `reservation_snapshot` means reservation state is unknown,
    reported as `reservations_applied = False` with the reservation
    figures left unset. It does not mean zero reservations exist.
    """

    capacity_snapshot = _require_mapping(
        capacity_snapshot,
        name="capacity_snapshot",
    )
    resource_safety = _require_mapping(
        resource_safety,
        name="resource_safety",
    )

    if reservation_snapshot is not None:
        reservation_snapshot = _require_mapping(
            reservation_snapshot,
            name="reservation_snapshot",
        )

    memory_pools = [
        _build_memory_pool(
            pool,
            reservation_snapshot=reservation_snapshot,
        )
        for pool in resource_safety.get("resource_pools") or []
        if isinstance(pool, Mapping)
    ]

    storage_pools: list[StoragePoolCapacity] = []

    if storage_plan is not None:
        storage_pools.append(
            _build_storage_pool(
                storage_plan=_require_mapping(
                    storage_plan,
                    name="storage_plan",
                ),
                capacity_snapshot=capacity_snapshot,
            )
        )

    source = {
        "capacity_snapshot_schema_version": (
            capacity_snapshot.get("schema_version")
        ),
        "resource_safety_schema_version": (
            resource_safety.get("schema_version")
        ),
        "storage_planning_schema_version": (
            storage_plan.get("schema_version")
            if storage_plan is not None
            else None
        ),
    }

    return CapacityEnvelope(
        schema_version=CAPACITY_CONTRACTS_SCHEMA_VERSION,
        generated_at=capacity_snapshot.get("generated_at"),
        source=source,
        headroom_policy=build_headroom_policy(
            resource_safety=resource_safety,
            storage_plan=storage_plan,
        ),
        cpu_capacity_status=CPU_CAPACITY_POLICY_UNRESOLVED,
        memory_pools=tuple(memory_pools),
        storage_pools=tuple(storage_pools),
        reservations_applied=reservation_snapshot is not None,
        unresolved_pool_ids=tuple(
            str(pool_id)
            for pool_id in (
                resource_safety.get("unresolved_pool_ids") or []
            )
        ),
    )
