"""Pure Capacity derivation. No host I/O and no admission."""

from __future__ import annotations

import hashlib

from machi.capacity.contracts import (
    AcceleratorCapacity,
    AdministratorBound,
    EvidenceStrength,
    MemoryCapacity,
    SonarEvidence,
    SonarStatus,
    SpecialistBound,
    StorageDomainCapacity,
)
from machi.capacity.sonar import not_attempted
from machi.discover.contracts import (
    AcceleratorMemoryTopology,
    AcceleratorObservation,
    MemoryObservation,
)
from machi.discover.mount_contracts import (
    AccessMode,
    MountEntry,
    MountObservation,
    StorageClass,
)
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import (
    NOT_MEASURED,
    NOT_PROVIDED,
    Maybe,
    Unresolved,
    is_resolved,
)
from machi.steward.contracts import OccupancyMap, OwnershipStatus, Reclaimability

_INADEQUATE = frozenset(
    {StorageClass.NETWORK, StorageClass.OVERLAY, StorageClass.UNKNOWN}
)
_EXCLUDED = frozenset({StorageClass.PSEUDO})


def memory_capacity(
    observation: MemoryObservation | None,
    *,
    execution_limit_bytes: Maybe[int],
    reserve_bytes: int,
) -> MemoryCapacity:
    """Hard ceiling is the smallest known hard bound, then the reserve."""
    if reserve_bytes < 0:
        raise ValidationError("memory reserve must not be negative")
    physical: Maybe[int] = (
        observation.physical_total_bytes if observation is not None else NOT_PROVIDED
    )
    bounds = [value for value in (physical,
        execution_limit_bytes) if is_resolved(value)]
    if not bounds:
        return MemoryCapacity(
            physical_bytes=physical,
            execution_limit_bytes=execution_limit_bytes,
            hard_ceiling_bytes=NOT_MEASURED,
            reserve_bytes=reserve_bytes,
            safe_bytes=NOT_MEASURED,
            strength=EvidenceStrength.UNRESOLVED,
            reason="no physical or execution hard bound was observed",
        )
    hard = min(int(value) for value in bounds)
    if reserve_bytes >= hard:
        return MemoryCapacity(
            physical_bytes=physical,
            execution_limit_bytes=execution_limit_bytes,
            hard_ceiling_bytes=hard,
            reserve_bytes=reserve_bytes,
            safe_bytes=Unresolved(
                NOT_MEASURED.reason,
                    "memory reserve is not smaller than the hard ceiling"
            ),
            strength=EvidenceStrength.UNRESOLVED,
            reason="reserve consumes the entire hard ceiling",
        )
    strength = (
        EvidenceStrength.AUTHORITATIVE
        if is_resolved(execution_limit_bytes)
        else EvidenceStrength.REPORTED
    )
    return MemoryCapacity(
        physical_bytes=physical,
        execution_limit_bytes=execution_limit_bytes,
        hard_ceiling_bytes=hard,
        reserve_bytes=reserve_bytes,
        safe_bytes=hard - reserve_bytes,
        strength=strength,
        reason="safe ceiling is the smallest hard bound minus the reserve",
    )


def accelerator_capacity(
    observation: AcceleratorObservation | None,
    *,
    reserve_bytes: int,
) -> tuple[AcceleratorCapacity, ...]:
    """One row per device. Current use stays unresolved at this tier."""
    if reserve_bytes < 0:
        raise ValidationError("accelerator reserve must not be negative")
    if observation is None:
        return ()
    rows: list[AcceleratorCapacity] = []
    for device in observation.devices:
        topology = (
            device.memory_topology.value
            if is_resolved(device.memory_topology)
            else "unresolved"
        )
        unified = (
            is_resolved(device.memory_topology)
            and device.memory_topology is AcceleratorMemoryTopology.UNIFIED
        )
        if unified or not is_resolved(device.memory_total_bytes):
            rows.append(
                AcceleratorCapacity(
                    identity=device.identity,
                    ordinal=device.ordinal,
                    topology=topology,
                    physical_bytes=device.memory_total_bytes,
                    current_used_bytes=NOT_MEASURED,
                    reserve_bytes=reserve_bytes,
                    safe_bytes=NOT_MEASURED,
                    strength=EvidenceStrength.UNRESOLVED,
                    reason=(
                        "unified memory is not a separate accelerator pool"
                        if unified
                        else "dedicated accelerator memory was not reported"
                    ),
                )
            )
            continue
        physical = int(device.memory_total_bytes)
        if reserve_bytes >= physical:
            safe: Maybe[int] = Unresolved(
                NOT_MEASURED.reason, "accelerator reserve is not smaller than the total"
            )
            strength = EvidenceStrength.UNRESOLVED
            reason = "reserve consumes the device total"
        else:
            safe = physical - reserve_bytes
            strength = EvidenceStrength.REPORTED
            reason = "discrete total minus headroom; current use is not proven"
        rows.append(
            AcceleratorCapacity(
                identity=device.identity,
                ordinal=device.ordinal,
                topology=topology,
                physical_bytes=physical,
                current_used_bytes=NOT_MEASURED,
                reserve_bytes=reserve_bytes,
                safe_bytes=safe,
                strength=strength,
                reason=reason,
            )
        )
    return tuple(rows)


def storage_domains(
    mounts: MountObservation | None,
    occupancy: OccupancyMap | None,
    *,
    specialists: tuple[SpecialistBound, ...],
    admins: tuple[AdministratorBound, ...],
    sonar_by_domain: dict[str, SonarEvidence],
    reserve_bytes: int,
    admin_allowed: bool,
) -> tuple[StorageDomainCapacity, ...]:
    """Group by backing identity. Do not add available bytes across mounts."""
    if mounts is None:
        return ()
    groups = _groups(mounts)
    rows: list[StorageDomainCapacity] = []
    for domain_id, members in groups.items():
        resolved_backing = members[0][0]
        usable = _usable(members)
        reported = _min_available(members) if usable else NOT_MEASURED
        specialist = _specialist(domain_id, specialists)
        sonar = sonar_by_domain.get(domain_id, not_attempted())
        protected, reclaimable = _occupancy(domain_id, occupancy, resolved_backing)
        hard, strength, reason = _select_hard(
            reported=reported,
            specialist=specialist,
            sonar=sonar,
            admin=_admin(domain_id, admins) if admin_allowed else None,
            usable=usable,
        )
        safe = _after_reserve(hard, reserve_bytes)
        potential = _potential(safe, reclaimable)
        rows.append(
            StorageDomainCapacity(
                domain_id=domain_id,
                backing_resolved=resolved_backing,
                reported_available_bytes=reported,
                specialist_remaining_bytes=specialist
                if specialist is not None
                else NOT_PROVIDED,
                hard_bound_bytes=hard,
                reserve_bytes=reserve_bytes,
                safe_bytes=safe,
                protected_occupancy_bytes=protected,
                reclaimable_bytes=reclaimable,
                potential_after_reclaim_bytes=potential,
                usable=usable,
                strength=strength,
                sonar=sonar,
                reason=reason,
            )
        )
    return tuple(rows)


def domain_needs_sonar(mounts: MountObservation, domain_id: str) -> bool:
    """Ordinary local evidence does not require a write. Overlay, network,
        and unread quota do."""
    from machi.discover.mount_contracts import QuotaEvidenceStatus

    for resolved, entry in _groups(mounts).get(domain_id, []):
        del resolved
        if entry.storage_class in _INADEQUATE:
            return True
        if entry.quota.status is QuotaEvidenceStatus.UNAVAILABLE:
            return True
    return False


def input_token(*parts: str) -> str:
    """Stable token for the facts this envelope consumed."""
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]


def _groups(mounts: MountObservation) -> dict[str, list[tuple[bool, MountEntry]]]:
    grouped: dict[str, list[tuple[bool, MountEntry]]] = {}
    for entry in mounts.entries:
        if entry.storage_class in _EXCLUDED:
            continue
        if is_resolved(entry.backing_store_id):
            grouped.setdefault(str(entry.backing_store_id), []).append((True, entry))
        else:
            grouped.setdefault(entry.mount_id, []).append((False, entry))
    return grouped


def _usable(members: list[tuple[bool, MountEntry]]) -> bool:
    for _resolved, entry in members:
        if entry.access_mode is AccessMode.READ_ONLY:
            return False
        if entry.storage_class in _EXCLUDED:
            return False
    return True


def _min_available(members: list[tuple[bool, MountEntry]]) -> Maybe[int]:
    values = [
        int(entry.reported_capacity.available_bytes)
        for _resolved, entry in members
        if is_resolved(entry.reported_capacity.available_bytes)
    ]
    if not values:
        return NOT_MEASURED
    return min(values)


def _specialist(domain_id: str, specialists: tuple[SpecialistBound, ...]) -> int | None:
    matches = [item for item in specialists if item.backing_store_id == domain_id]
    if not matches:
        return None
    return min(item.remaining_bytes for item in matches)


def _admin(domain_id: str, admins: tuple[AdministratorBound, ...]) -> int | None:
    matches = [item for item in admins if item.domain_id == domain_id]
    if not matches:
        return None
    return min(item.bound_bytes for item in matches)


def _occupancy(
    domain_id: str, occupancy: OccupancyMap | None, backing_resolved: bool
) -> tuple[Maybe[int], Maybe[int]]:
    if occupancy is None or not backing_resolved:
        return NOT_PROVIDED, NOT_PROVIDED
    protected = 0
    reclaimable = 0
    saw = False
    for resource in occupancy.resources:
        if resource.ownership is not OwnershipStatus.VERIFIED_MACHI_OWNED:
            continue
        if not is_resolved(resource.backing_store_id):
            continue
        if str(resource.backing_store_id) != domain_id:
            continue
        if not is_resolved(resource.size_bytes):
            return NOT_MEASURED, NOT_MEASURED
        saw = True
        size = int(resource.size_bytes)
        if resource.reclaimability is Reclaimability.RECLAIMABLE:
            reclaimable += size
        else:
            protected += size
    if not saw:
        return 0, 0
    return protected, reclaimable


def _select_hard(
    *,
    reported: Maybe[int],
    specialist: int | None,
    sonar: SonarEvidence,
    admin: int | None,
    usable: bool,
) -> tuple[Maybe[int], EvidenceStrength, str]:
    if not usable:
        return (
            NOT_MEASURED,
            EvidenceStrength.UNRESOLVED,
            "read-only or excluded storage is not a planning domain",
        )
    candidates: list[tuple[int, EvidenceStrength, str]] = []
    if is_resolved(reported):
        candidates.append(
            (int(reported), EvidenceStrength.REPORTED,
                "filesystem-reported available bytes")
        )
    if specialist is not None:
        candidates.append(
            (
                specialist,
                EvidenceStrength.SPECIALIST,
                "specialist remaining entitlement is a hard bound",
            )
        )
    contradicted = sonar.status is SonarStatus.CONTRADICTED
    if contradicted and is_resolved(sonar.proven_lower_bytes):
        candidates.append(
            (
                int(sonar.proven_lower_bytes),
                EvidenceStrength.EMPIRICALLY_PROVEN,
                "sonar hard failure is below the reported available bytes",
            )
        )
    elif (
        sonar.status is SonarStatus.CORROBORATED
        and is_resolved(reported)
        and is_resolved(sonar.proven_lower_bytes)
        and int(sonar.proven_lower_bytes) > int(reported)
    ):
        # A larger write must not raise the reported ceiling.
        pass
    if not candidates and admin is not None:
        return (
            admin,
            EvidenceStrength.ADMINISTRATOR_BOUNDED,
            "administrator bound used because no harder evidence exists",
        )
    if not candidates:
        return (
            NOT_MEASURED,
            EvidenceStrength.UNRESOLVED,
            "no trustworthy storage bound was established",
        )
    hard, strength, reason = min(candidates, key=lambda item: item[0])
    if admin is not None and admin < hard:
        return (
            admin,
            EvidenceStrength.ADMINISTRATOR_BOUNDED,
            "administrator bound is smaller than the other evidence",
        )
    corroborated = sonar.status is SonarStatus.CORROBORATED
    if corroborated and strength is EvidenceStrength.REPORTED:
        reason = "sonar corroborated the reported ceiling and did not replace it"
    return hard, strength, reason


def _after_reserve(hard: Maybe[int], reserve: int) -> Maybe[int]:
    if not is_resolved(hard):
        return NOT_MEASURED
    if reserve >= int(hard):
        return Unresolved(NOT_MEASURED.reason,
            "storage reserve is not smaller than the hard bound")
    return int(hard) - reserve


def _potential(safe: Maybe[int], reclaimable: Maybe[int]) -> Maybe[int]:
    if not is_resolved(safe) or not is_resolved(reclaimable):
        return NOT_MEASURED
    return int(safe) + int(reclaimable)
