"""SAFE minus ACTIVE reservations. Available for new work is never negative."""

from __future__ import annotations

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import MemoryPlacement
from kultrun.resource.contracts import (
    AdmissionReason,
    LedgerHealth,
    ReservationState,
    ResourceReservation,
    ResourceSummary,
)

_ACTIVE = ReservationState.ACTIVE


def as_int(value: object) -> int | None:
    """Resolved int, or None. Unresolved is not zero."""
    if is_resolved(value) and isinstance(value, int):
        return value
    return None


def available_for_new_work(safe: int | None, reserved: int) -> Maybe[int]:
    """SAFE - reserved, floored at 0. Unresolved SAFE stays unresolved."""
    if safe is None:
        return NOT_PROVIDED
    remaining = safe - reserved
    return 0 if remaining < 0 else remaining


def deficit(safe: int | None, reserved: int) -> int:
    """How far ACTIVE exceeds SAFE, when it does. Never advertised as available."""
    if safe is None:
        return 0
    return max(0, reserved - safe)


def active(
    reservations: tuple[ResourceReservation, ...],
) -> tuple[ResourceReservation, ...]:
    return tuple(item for item in reservations if item.state is _ACTIVE)


def reserved_ram(reservations: tuple[ResourceReservation, ...]) -> int:
    total = 0
    for item in active(reservations):
        amount = as_int(item.admitted_ram_bytes)
        if amount is not None:
            total += amount
    return total


def reserved_unified(reservations: tuple[ResourceReservation, ...]) -> int:
    total = 0
    for item in active(reservations):
        amount = as_int(item.admitted_unified_bytes)
        if amount is not None:
            total += amount
    return total


def reserved_incremental_storage(reservations: tuple[ResourceReservation, ...]) -> int:
    total = 0
    for item in active(reservations):
        amount = as_int(item.admitted_storage_bytes)
        if amount is not None:
            total += amount
    return total


def reserved_accelerator(
    reservations: tuple[ResourceReservation, ...], index: int
) -> int:
    """One device only. Never a sum across GPUs."""
    total = 0
    for item in active(reservations):
        if item.accelerator_index != index:
            continue
        amount = as_int(item.admitted_vram_bytes)
        if amount is not None:
            total += amount
    return total


def device_health(
    envelope: CapacityEnvelope, reservations: tuple[ResourceReservation, ...]
) -> LedgerHealth:
    """WITHIN / OVERCOMMITTED / UNRESOLVED from current SAFE minus ACTIVE."""
    ram_safe = as_int(envelope.memory.safe_bytes)
    if ram_safe is None:
        return LedgerHealth.UNRESOLVED
    if reserved_ram(reservations) > ram_safe:
        return LedgerHealth.OVERCOMMITTED
    for accelerator in envelope.accelerators:
        safe = as_int(accelerator.memory.safe_bytes)
        if safe is None:
            continue
        if reserved_accelerator(reservations, accelerator.index) > safe:
            return LedgerHealth.OVERCOMMITTED
    return LedgerHealth.WITHIN_CAPACITY


def summarize(
    envelope: CapacityEnvelope, reservations: tuple[ResourceReservation, ...]
) -> ResourceSummary:
    """Recompute availability. Do not persist these numbers as authority."""
    from kultrun.resource.snapshot import current_capacity_snapshot

    return current_capacity_snapshot(envelope, reservations)


def insufficient_reason(
    placement: MemoryPlacement, dimension: str
) -> AdmissionReason:
    if dimension == "ram":
        return AdmissionReason.INSUFFICIENT_SAFE_RAM
    if dimension == "unified":
        return AdmissionReason.INSUFFICIENT_SAFE_UNIFIED
    if placement is MemoryPlacement.DISCRETE_GPU:
        return AdmissionReason.INSUFFICIENT_SAFE_ACCELERATOR
    return AdmissionReason.INSUFFICIENT_SAFE_ACCELERATOR
