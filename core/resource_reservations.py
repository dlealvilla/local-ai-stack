"""Resource reservation domain for the single-host Resource Manager.

AI_DEPLOYMENT_PHASE9_RESOURCE_RESERVATIONS_V1

Core owns the reservation concepts. Storage/persistence implementations live
behind ReservationStore adapters.

This module intentionally does not depend on:
- Docker;
- vLLM;
- NVIDIA/CUDA;
- the Platform API;
- model inventory;
- the Capacity Planner implementation.

Resource pools are identified by stable string keys, allowing later support
for system RAM, dedicated VRAM, unified memory, CPU, accelerators, or other
host resources without redesigning the ledger.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4


ResourceMap = dict[str, int]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_nonnegative_resources(
    resources: Mapping[str, int],
    *,
    field_name: str,
) -> ResourceMap:
    normalized: ResourceMap = {}

    for raw_name, raw_value in resources.items():
        name = str(raw_name).strip()

        if not name:
            raise ValueError(f"{field_name} contains an empty resource name")

        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise TypeError(
                f"{field_name}[{name!r}] must be an integer number of units"
            )

        if raw_value < 0:
            raise ValueError(
                f"{field_name}[{name!r}] cannot be negative"
            )

        normalized[name] = raw_value

    return normalized


def _normalize_positive_resources(
    resources: Mapping[str, int],
    *,
    field_name: str,
) -> ResourceMap:
    normalized = _normalize_nonnegative_resources(
        resources,
        field_name=field_name,
    )

    positive = {
        name: value
        for name, value in normalized.items()
        if value > 0
    }

    if not positive:
        raise ValueError(f"{field_name} must request at least one resource")

    return positive


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str
    requested: ResourceMap
    available: ResourceMap
    deficits: ResourceMap = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReservationRecord:
    reservation_id: str
    workload_id: str
    resources: ResourceMap
    created_at_utc: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReservationRecord":
        return cls(
            reservation_id=str(value["reservation_id"]),
            workload_id=str(value["workload_id"]),
            resources=_normalize_positive_resources(
                dict(value["resources"]),
                field_name="resources",
            ),
            created_at_utc=str(value["created_at_utc"]),
            metadata=dict(value.get("metadata") or {}),
        )


@dataclass(frozen=True)
class ReservationSnapshot:
    capacities: ResourceMap
    reserved: ResourceMap
    available: ResourceMap
    reservations: tuple[ReservationRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capacities": dict(self.capacities),
            "reserved": dict(self.reserved),
            "available": dict(self.available),
            "reservations": [
                reservation.to_dict()
                for reservation in self.reservations
            ],
        }


class ReservationStore(Protocol):
    """Persistence boundary owned by core and implemented by adapters."""

    def load(self) -> list[ReservationRecord]:
        ...

    def save(self, reservations: Iterable[ReservationRecord]) -> None:
        ...


class ReservationError(RuntimeError):
    pass


class ReservationConflictError(ReservationError):
    pass


class ReservationDeniedError(ReservationError):
    def __init__(self, decision: AdmissionDecision):
        self.decision = decision
        super().__init__(decision.reason)


class ResourceReservationLedger:
    """Thread-safe single-owner resource reservation ledger.

    The ledger prevents admitted reservations from exceeding the capacities
    supplied to it. It deliberately does not discover capacities itself.

    Cross-process scheduling is intentionally outside this class. Phase 9's
    ResourceManager is expected to be the single logical owner of mutations.
    """

    def __init__(
        self,
        capacities: Mapping[str, int],
        *,
        store: ReservationStore | None = None,
    ) -> None:
        self._lock = RLock()
        self._store = store
        self._capacities = _normalize_nonnegative_resources(
            capacities,
            field_name="capacities",
        )
        self._reservations: dict[str, ReservationRecord] = {}

        if self._store is not None:
            for reservation in self._store.load():
                if reservation.reservation_id in self._reservations:
                    raise ReservationConflictError(
                        "duplicate reservation id in persistent store: "
                        f"{reservation.reservation_id}"
                    )

                if self._find_by_workload_unlocked(
                    reservation.workload_id
                ) is not None:
                    raise ReservationConflictError(
                        "duplicate workload id in persistent store: "
                        f"{reservation.workload_id}"
                    )

                self._reservations[
                    reservation.reservation_id
                ] = reservation

    @property
    def capacities(self) -> ResourceMap:
        with self._lock:
            return dict(self._capacities)

    def set_capacities(self, capacities: Mapping[str, int]) -> None:
        """Refresh observed safe capacities without mutating reservations."""

        normalized = _normalize_nonnegative_resources(
            capacities,
            field_name="capacities",
        )

        with self._lock:
            self._capacities = normalized

    def _find_by_workload_unlocked(
        self,
        workload_id: str,
    ) -> ReservationRecord | None:
        for reservation in self._reservations.values():
            if reservation.workload_id == workload_id:
                return reservation

        return None

    def reservation_for_workload(
        self,
        workload_id: str,
    ) -> ReservationRecord | None:
        workload_id = str(workload_id).strip()

        if not workload_id:
            raise ValueError("workload_id cannot be empty")

        with self._lock:
            return self._find_by_workload_unlocked(workload_id)

    def total_reserved(self) -> ResourceMap:
        with self._lock:
            totals: ResourceMap = {
                name: 0
                for name in self._capacities
            }

            for reservation in self._reservations.values():
                for name, value in reservation.resources.items():
                    totals[name] = totals.get(name, 0) + value

            return totals

    def available_resources(self) -> ResourceMap:
        with self._lock:
            reserved = self.total_reserved()

            names = set(self._capacities) | set(reserved)

            return {
                name: self._capacities.get(name, 0)
                - reserved.get(name, 0)
                for name in sorted(names)
            }

    def evaluate(
        self,
        requested: Mapping[str, int],
    ) -> AdmissionDecision:
        normalized = _normalize_positive_resources(
            requested,
            field_name="requested",
        )

        with self._lock:
            available = self.available_resources()

            deficits: ResourceMap = {}

            for name, request_value in normalized.items():
                available_value = available.get(name, 0)

                if request_value > available_value:
                    deficits[name] = request_value - available_value

            if deficits:
                return AdmissionDecision(
                    allowed=False,
                    reason="insufficient_safe_resource_capacity",
                    requested=dict(normalized),
                    available=dict(available),
                    deficits=deficits,
                )

            return AdmissionDecision(
                allowed=True,
                reason="admitted",
                requested=dict(normalized),
                available=dict(available),
                deficits={},
            )

    def reserve(
        self,
        workload_id: str,
        resources: Mapping[str, int],
        *,
        metadata: Mapping[str, Any] | None = None,
        reservation_id: str | None = None,
    ) -> ReservationRecord:
        workload_id = str(workload_id).strip()

        if not workload_id:
            raise ValueError("workload_id cannot be empty")

        normalized_resources = _normalize_positive_resources(
            resources,
            field_name="resources",
        )

        with self._lock:
            existing = self._find_by_workload_unlocked(workload_id)

            if existing is not None:
                raise ReservationConflictError(
                    f"workload already has a reservation: {workload_id}"
                )

            decision = self.evaluate(normalized_resources)

            if not decision.allowed:
                raise ReservationDeniedError(decision)

            resolved_reservation_id = (
                str(reservation_id).strip()
                if reservation_id is not None
                else str(uuid4())
            )

            if not resolved_reservation_id:
                raise ValueError("reservation_id cannot be empty")

            if resolved_reservation_id in self._reservations:
                raise ReservationConflictError(
                    "reservation id already exists: "
                    f"{resolved_reservation_id}"
                )

            record = ReservationRecord(
                reservation_id=resolved_reservation_id,
                workload_id=workload_id,
                resources=dict(normalized_resources),
                created_at_utc=_utc_now(),
                metadata=dict(metadata or {}),
            )

            self._reservations[record.reservation_id] = record

            try:
                self._persist_unlocked()
            except Exception:
                del self._reservations[record.reservation_id]
                raise

            return record

    def release(
        self,
        reservation_id: str,
    ) -> ReservationRecord | None:
        reservation_id = str(reservation_id).strip()

        if not reservation_id:
            raise ValueError("reservation_id cannot be empty")

        with self._lock:
            removed = self._reservations.pop(
                reservation_id,
                None,
            )

            if removed is None:
                return None

            try:
                self._persist_unlocked()
            except Exception:
                self._reservations[removed.reservation_id] = removed
                raise

            return removed

    def release_workload(
        self,
        workload_id: str,
    ) -> ReservationRecord | None:
        workload_id = str(workload_id).strip()

        if not workload_id:
            raise ValueError("workload_id cannot be empty")

        with self._lock:
            existing = self._find_by_workload_unlocked(workload_id)

            if existing is None:
                return None

            return self.release(existing.reservation_id)

    def reconcile(
        self,
        active_workload_ids: Iterable[str],
    ) -> list[ReservationRecord]:
        """Release reservations whose workloads are no longer active.

        This is intentionally conservative: reconciliation only removes stale
        reservations. Discovery/adoption of unreserved live workloads belongs
        in the future ResourceManager reconciliation layer.
        """

        active = {
            str(workload_id).strip()
            for workload_id in active_workload_ids
            if str(workload_id).strip()
        }

        with self._lock:
            stale = [
                reservation
                for reservation in self._reservations.values()
                if reservation.workload_id not in active
            ]

            if not stale:
                return []

            original = dict(self._reservations)

            for reservation in stale:
                del self._reservations[reservation.reservation_id]

            try:
                self._persist_unlocked()
            except Exception:
                self._reservations = original
                raise

            return stale

    def snapshot(self) -> ReservationSnapshot:
        with self._lock:
            reservations = tuple(
                sorted(
                    self._reservations.values(),
                    key=lambda value: value.reservation_id,
                )
            )

            return ReservationSnapshot(
                capacities=dict(self._capacities),
                reserved=self.total_reserved(),
                available=self.available_resources(),
                reservations=reservations,
            )

    def _persist_unlocked(self) -> None:
        if self._store is None:
            return

        self._store.save(
            sorted(
                self._reservations.values(),
                key=lambda value: value.reservation_id,
            )
        )
