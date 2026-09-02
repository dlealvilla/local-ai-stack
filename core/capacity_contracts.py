"""Normalized capacity contracts for the capacity/model-optimization work.

AI_DEPLOYMENT_CAPACITY_CONTRACTS_C1

See docs/CAPACITY_ARCHITECTURE.md sections 3, 5 and 37.

This module represents already-validated capacity facts coherently. It is
NOT a second resource calculator:

    core.hardware                        owns detection
    core.capacity_snapshot               owns live observation
    core.resource_capacity               owns vendor-neutral pool identity
    core.resource_safety                 owns protected reserve and
                                         safe-available-before-reservations
    core.resource_reservations           owns managed reservation accounting
    core.storage_capacity_resolution     owns storage evidence and basis
    core.storage_budget                  owns platform storage budget

Every number exposed here is copied from one of those owners. No formula
is reimplemented, and no reported value is ever promoted into a verified
one.

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

    Layer separation is preserved rather than flattened:

        reported_*                              observation
        protected_reserve_bytes                 policy headroom
        safe_available_before_reservations      observation minus headroom
        managed_reserved / safe_available       reservation ledger

    There is no intermediate `effective` value because the existing
    implementation does not calculate one for memory; synthesizing it
    would invent a fact.

    The reservation figures are copied verbatim from the ledger snapshot,
    which already subtracts managed reservations from its own accounting
    capacity. They are never derived from
    `safe_available_before_reservations_bytes`, which would
    double-subtract.
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
    protected_reserve_bytes: int | None
    safe_available_before_reservations_bytes: int | None

    ledger_capacity_bytes: int | None = None
    managed_reserved_bytes: int | None = None
    safe_available_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    memory_pools: tuple[MemoryPoolCapacity, ...]
    storage_pools: tuple[StoragePoolCapacity, ...]
    reservations_applied: bool
    unresolved_pool_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "source": dict(self.source),
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

    ledger_capacity = None
    managed_reserved = None
    safe_available = None

    if reservation_snapshot is not None:
        #
        # Copied verbatim. The ledger's `available` is already
        # `capacities - reserved` against its own managed accounting
        # total, so subtracting reservations again here would
        # double-count them.
        #
        ledger_capacity = _nonnegative_int_or_none(
            (reservation_snapshot.get("capacities") or {}).get(pool_id)
        )
        managed_reserved = _nonnegative_int_or_none(
            (reservation_snapshot.get("reserved") or {}).get(pool_id)
        )
        safe_available = _nonnegative_int_or_none(
            (reservation_snapshot.get("available") or {}).get(pool_id)
        )

    return MemoryPoolCapacity(
        pool_id=pool_id,
        resource_type=pool.get("resource_type"),
        memory_type=pool.get("memory_type"),
        scope=dict(pool.get("scope") or {}),
        reported_total_bytes=_nonnegative_int_or_none(
            capacity.get("total_bytes")
        ),
        reported_used_bytes=_nonnegative_int_or_none(
            capacity.get("used_bytes")
        ),
        reported_available_bytes=_nonnegative_int_or_none(
            capacity.get("available_bytes")
        ),
        safety_resolved=bool(safety.get("resolved", False)),
        safety_reason=safety.get("reason"),
        protected_reserve_bytes=_nonnegative_int_or_none(
            safety.get("protected_reserve_bytes")
        ),
        safe_available_before_reservations_bytes=(
            _nonnegative_int_or_none(
                safety.get(
                    "safe_available_before_reservations_bytes"
                )
            )
        ),
        ledger_capacity_bytes=ledger_capacity,
        managed_reserved_bytes=managed_reserved,
        safe_available_bytes=safe_available,
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
