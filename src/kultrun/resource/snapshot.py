"""Current available capacity: SAFE minus ACTIVE commitments.

ResourceSummary is the repository authority for this view. It is derived
on read and is never persisted as host truth. ResourceManager remains the
final admission authority; this snapshot is planning/advisory.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.resource.contracts import (
    POLICY_VERSION,
    DeviceResourceSummary,
    PoolResourceSummary,
    ReservationId,
    ReservationState,
    ResourceReservation,
    ResourceSummary,
)
from kultrun.resource.ledger import (
    active,
    as_int,
    available_for_new_work,
    device_health,
    reserved_accelerator,
    reserved_incremental_storage,
    reserved_ram,
    reserved_storage,
    reserved_unified,
)

SNAPSHOT_VERSION = "1.6L.0"


def current_capacity_snapshot(
    envelope: CapacityEnvelope,
    reservations: tuple[ResourceReservation, ...],
    *,
    exclude_reservation_id: ReservationId | str | None = None,
    host: HostCapabilities | None = None,
    observed_at: dt.datetime | None = None,
) -> ResourceSummary:
    """Recompute SAFE minus *other* ACTIVE commitments.

    Stored artifacts consume storage via the live free-space authority.
    They do not appear as VRAM commitments.
    """
    excluded = _exclude_token(exclude_reservation_id)
    counted = _without_excluded(reservations, excluded)
    held = active(counted)
    ram_safe = as_int(envelope.memory.safe_bytes)
    ram_reserved = reserved_ram(counted)
    pool_rows = []
    for pool in envelope.pools:
        safe = as_int(pool.space.safe_bytes)
        reserved = reserved_storage(counted, pool.mount_point)
        pool_rows.append(
            PoolResourceSummary(
                mount_point=pool.mount_point,
                quota_identity=NOT_PROVIDED,
                safe_bytes=pool.space.safe_bytes,
                reserved_bytes=reserved,
                available_bytes=available_for_new_work(safe, reserved),
            )
        )
    authorizing = [row for row in pool_rows if as_int(row.safe_bytes) is not None]
    storage_safe: int | None
    storage_source: Maybe[str]
    if len(authorizing) == 1:
        storage_safe = as_int(authorizing[0].safe_bytes)
        storage_source = authorizing[0].mount_point
    else:
        storage_safe, storage_source = None, NOT_PROVIDED
    storage_reserved = reserved_incremental_storage(counted)
    by_host = _accelerator_identity(host)
    devices = []
    for accelerator in envelope.accelerators:
        safe = as_int(accelerator.memory.safe_bytes)
        reserved = reserved_accelerator(counted, accelerator.index)
        vendor, identity = by_host.get(accelerator.index, (NOT_PROVIDED, NOT_PROVIDED))
        devices.append(
            DeviceResourceSummary(
                index=accelerator.index,
                safe_bytes=accelerator.memory.safe_bytes,
                reserved_bytes=reserved,
                available_bytes=available_for_new_work(safe, reserved),
                vendor=vendor,
                device_identity=identity,
            )
        )
    active_ids = tuple(item.reservation_id.value for item in held)
    basis = snapshot_basis(envelope, counted)
    return ResourceSummary(
        host_id=envelope.host_id,
        host_fingerprint=envelope.host_fingerprint,
        health=device_health(envelope, counted),
        policy_version=POLICY_VERSION,
        capacity_policy_version=envelope.policy_version,
        safe_ram_bytes=envelope.memory.safe_bytes,
        reserved_ram_bytes=ram_reserved,
        available_ram_bytes=available_for_new_work(ram_safe, ram_reserved),
        accelerators=tuple(devices),
        reserved_unified_bytes=reserved_unified(counted),
        reserved_incremental_storage_bytes=storage_reserved,
        active_count=len(held),
        serving=False,
        running_instances=0,
        snapshot_basis=basis,
        active_reservation_ids=active_ids,
        excluded_reservation_id=excluded if excluded else NOT_PROVIDED,
        observed_at=observed_at,
        safe_storage_bytes=storage_safe if storage_safe is not None else NOT_PROVIDED,
        available_storage_bytes=available_for_new_work(storage_safe, storage_reserved),
        storage_source=storage_source,
        snapshot_version=SNAPSHOT_VERSION,
        pools=tuple(pool_rows),
    )


def snapshot_basis(
    envelope: CapacityEnvelope,
    reservations: tuple[ResourceReservation, ...],
) -> str:
    """Fingerprint of the facts this view subtracted. Not permanent host truth."""
    held = active(reservations)
    parts = [
        "capacity.snapshot@1",
        SNAPSHOT_VERSION,
        envelope.host_fingerprint,
        envelope.policy_version,
        f"ram:{reserved_ram(reservations)}",
        f"storage:{reserved_incremental_storage(reservations)}",
    ]
    for accelerator in envelope.accelerators:
        parts.append(
            f"gpu{accelerator.index}:"
            f"{reserved_accelerator(reservations, accelerator.index)}"
        )
    parts.append(",".join(sorted(item.reservation_id.value for item in held)))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _exclude_token(value: ReservationId | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, ReservationId):
        return value.value
    return str(value).strip()


def _without_excluded(
    reservations: tuple[ResourceReservation, ...], excluded: str
) -> tuple[ResourceReservation, ...]:
    if not excluded:
        return reservations
    kept = []
    for item in reservations:
        if (
            item.state is ReservationState.ACTIVE
            and item.reservation_id.value == excluded
        ):
            continue
        kept.append(item)
    return tuple(kept)


def _accelerator_identity(
    host: HostCapabilities | None,
) -> dict[int, tuple[Maybe[str], Maybe[str]]]:
    found: dict[int, tuple[Maybe[str], Maybe[str]]] = {}
    if host is None:
        return found
    for accelerator in host.accelerators:
        identity: Maybe[str] = (
            accelerator.model_name
            if is_resolved(accelerator.model_name)
            else NOT_PROVIDED
        )
        found[accelerator.index] = (accelerator.vendor.value, identity)
    return found
