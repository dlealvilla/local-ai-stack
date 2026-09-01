"""Single-host Resource Manager v1.

AI_DEPLOYMENT_PHASE9_RESOURCE_MANAGER_V1

The Resource Manager owns dynamic workload state and coordinates:

planning -> admission -> reservation -> runtime start -> tracking
tracking -> runtime stop -> state removal -> reservation release

It does not own:
- Phase 8 capacity estimation;
- hardware discovery;
- Docker mechanics;
- vLLM mechanics;
- Platform API routes.

Those remain behind replaceable interfaces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from core.resource_reservations import (
    AdmissionDecision,
    ReservationDeniedError,
    ResourceReservationLedger,
)


ResourceMap = dict[str, int]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResourceManagerError(RuntimeError):
    pass


class UnknownModelError(ResourceManagerError):
    pass


class WorkloadConflictError(ResourceManagerError):
    pass


class WorkloadNotFoundError(ResourceManagerError):
    pass


class RuntimeStartError(ResourceManagerError):
    pass


class RuntimeStopError(ResourceManagerError):
    pass


class WorkloadStateStore(Protocol):
    def load(self) -> list["WorkloadRecord"]:
        ...

    def save(
        self,
        workloads: Iterable["WorkloadRecord"],
    ) -> None:
        ...


class ResourcePlanningProvider(Protocol):
    def build_view(self) -> Mapping[str, Any]:
        ...


class WorkloadRuntime(Protocol):
    def start(
        self,
        *,
        workload_id: str,
        model_id: str,
        metadata: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        ...

    def stop(
        self,
        *,
        workload_id: str,
        model_id: str,
        runtime_state: Mapping[str, Any],
    ) -> None:
        ...


@dataclass(frozen=True)
class WorkloadRecord:
    workload_id: str
    model_id: str
    status: str
    reservation_id: str
    requirements: ResourceMap
    requirement_basis: str
    created_at_utc: str
    updated_at_utc: str
    runtime_state: dict[str, Any] = field(
        default_factory=dict
    )
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "WorkloadRecord":
        return cls(
            workload_id=str(value["workload_id"]),
            model_id=str(value["model_id"]),
            status=str(value["status"]),
            reservation_id=str(value["reservation_id"]),
            requirements={
                str(key): int(amount)
                for key, amount in dict(
                    value["requirements"]
                ).items()
            },
            requirement_basis=str(
                value["requirement_basis"]
            ),
            created_at_utc=str(
                value["created_at_utc"]
            ),
            updated_at_utc=str(
                value["updated_at_utc"]
            ),
            runtime_state=dict(
                value.get("runtime_state")
                or {}
            ),
            metadata=dict(
                value.get("metadata")
                or {}
            ),
        )


class ResourceManager:
    """Single logical owner for Phase 9 workload mutations."""

    def __init__(
        self,
        *,
        ledger: ResourceReservationLedger,
        planning_provider: ResourcePlanningProvider,
        runtime: WorkloadRuntime,
        state_store: WorkloadStateStore | None = None,
    ) -> None:
        self._lock = RLock()
        self._ledger = ledger
        self._planning_provider = planning_provider
        self._runtime = runtime
        self._state_store = state_store
        self._workloads: dict[str, WorkloadRecord] = {}

        if self._state_store is not None:
            for workload in self._state_store.load():
                if workload.workload_id in self._workloads:
                    raise WorkloadConflictError(
                        "duplicate workload in persistent state: "
                        f"{workload.workload_id}"
                    )

                self._workloads[
                    workload.workload_id
                ] = workload

    def _persist_unlocked(self) -> None:
        if self._state_store is None:
            return

        self._state_store.save(
            sorted(
                self._workloads.values(),
                key=lambda value: value.workload_id,
            )
        )

    def _planning_view_unlocked(
        self,
    ) -> Mapping[str, Any]:
        view = self._planning_provider.build_view()

        if not isinstance(view, Mapping):
            raise ResourceManagerError(
                "planning provider returned a non-mapping view"
            )

        capacities = view.get("capacities")

        if not isinstance(capacities, Mapping):
            raise ResourceManagerError(
                "planning view has no capacities mapping"
            )

        observed_capacities = {
            str(key): int(value)
            for key, value in capacities.items()
        }

        ledger_snapshot = self._ledger.snapshot()

        if ledger_snapshot.reservations:
            # Planning capacities represent currently observed safe
            # availability. The reservation ledger owns total managed
            # accounting capacity and subtracts managed reservations
            # itself.
            #
            # Therefore, while reservations exist, add those managed
            # reservations back to the live observation before using
            # it as ledger total capacity. Never increase an already
            # established total while reservations exist: this keeps
            # the refresh conservative if another/external workload
            # consumes resources or if a reservation has not yet been
            # physically consumed.
            current_capacities = (
                ledger_snapshot.capacities
            )
            reserved = ledger_snapshot.reserved

            refreshed_capacities = {}

            resource_names = (
                set(observed_capacities)
                | set(reserved)
            )

            for resource_name in resource_names:
                observed_available = int(
                    observed_capacities.get(
                        resource_name,
                        0,
                    )
                )

                managed_reserved = int(
                    reserved.get(
                        resource_name,
                        0,
                    )
                )

                inferred_total = (
                    observed_available
                    + managed_reserved
                )

                previous_total = (
                    current_capacities.get(
                        resource_name
                    )
                )

                if previous_total is None:
                    refreshed_capacities[
                        resource_name
                    ] = inferred_total
                else:
                    refreshed_capacities[
                        resource_name
                    ] = min(
                        int(previous_total),
                        inferred_total,
                    )

            self._ledger.set_capacities(
                refreshed_capacities
            )
        else:
            self._ledger.set_capacities(
                observed_capacities
            )

        return view

    def _model_resolution_unlocked(
        self,
        model_id: str,
        view: Mapping[str, Any],
    ) -> tuple[ResourceMap, str, dict[str, Any]]:
        resolutions = view.get(
            "requirement_resolutions_by_model"
        )

        if not isinstance(resolutions, Mapping):
            raise ResourceManagerError(
                "planning view has no requirement resolutions"
            )

        resolution = resolutions.get(model_id)

        if not isinstance(resolution, Mapping):
            raise UnknownModelError(
                f"model has no resolved planning record: {model_id}"
            )

        if resolution.get("resolved") is not True:
            raise ResourceManagerError(
                f"model requirement is unresolved: {model_id}"
            )

        requirements = resolution.get(
            "requirements"
        )

        if not isinstance(requirements, Mapping):
            raise ResourceManagerError(
                f"model has no requirements mapping: {model_id}"
            )

        normalized: ResourceMap = {
            str(key): int(value)
            for key, value in requirements.items()
            if int(value) > 0
        }

        if not normalized:
            raise ResourceManagerError(
                f"model has no positive requirements: {model_id}"
            )

        basis = str(
            resolution.get("basis")
            or "unknown"
        )

        return (
            normalized,
            basis,
            dict(resolution),
        )

    def preview_start(
        self,
        model_id: str,
    ) -> dict[str, Any]:
        model_id = str(model_id).strip()

        if not model_id:
            raise ValueError(
                "model_id cannot be empty"
            )

        with self._lock:
            view = self._planning_view_unlocked()

            (
                requirements,
                basis,
                resolution,
            ) = self._model_resolution_unlocked(
                model_id,
                view,
            )

            decision = self._ledger.evaluate(
                requirements
            )

            return {
                "model_id": model_id,
                "requirements": requirements,
                "requirement_basis": basis,
                "requirement_resolution":
                    resolution,
                "admission":
                    decision.to_dict(),
            }

    def start_model(
        self,
        model_id: str,
        *,
        workload_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> WorkloadRecord:
        model_id = str(model_id).strip()

        if not model_id:
            raise ValueError(
                "model_id cannot be empty"
            )

        resolved_workload_id = (
            str(workload_id).strip()
            if workload_id is not None
            else f"{model_id}:{uuid4()}"
        )

        if not resolved_workload_id:
            raise ValueError(
                "workload_id cannot be empty"
            )

        with self._lock:
            if resolved_workload_id in self._workloads:
                raise WorkloadConflictError(
                    "workload already exists: "
                    f"{resolved_workload_id}"
                )

            view = self._planning_view_unlocked()

            (
                requirements,
                basis,
                resolution,
            ) = self._model_resolution_unlocked(
                model_id,
                view,
            )

            # Reservation is the commit point before runtime mutation.
            reservation = self._ledger.reserve(
                resolved_workload_id,
                requirements,
                metadata={
                    "model_id": model_id,
                    "requirement_basis": basis,
                },
            )

            now = _utc_now()

            record = WorkloadRecord(
                workload_id=resolved_workload_id,
                model_id=model_id,
                status="starting",
                reservation_id=
                    reservation.reservation_id,
                requirements=dict(requirements),
                requirement_basis=basis,
                created_at_utc=now,
                updated_at_utc=now,
                metadata={
                    **dict(metadata or {}),
                    "requirement_resolution":
                        resolution,
                },
            )

            self._workloads[
                resolved_workload_id
            ] = record

            try:
                self._persist_unlocked()
            except Exception:
                del self._workloads[
                    resolved_workload_id
                ]

                self._ledger.release(
                    reservation.reservation_id
                )

                raise

            try:
                runtime_state = self._runtime.start(
                    workload_id=
                        resolved_workload_id,
                    model_id=model_id,
                    metadata=dict(metadata or {}),
                )
            except Exception as exc:
                del self._workloads[
                    resolved_workload_id
                ]

                try:
                    self._persist_unlocked()
                finally:
                    self._ledger.release(
                        reservation.reservation_id
                    )

                raise RuntimeStartError(
                    f"runtime failed to start "
                    f"{resolved_workload_id}: {exc}"
                ) from exc

            running = replace(
                record,
                status="running",
                updated_at_utc=_utc_now(),
                runtime_state=dict(
                    runtime_state or {}
                ),
            )

            self._workloads[
                resolved_workload_id
            ] = running

            # If this persistence fails, DO NOT release the reservation:
            # the workload may genuinely be running. Failing safe means
            # retaining its resource claim for later reconciliation.
            self._persist_unlocked()

            return running

    def stop_workload(
        self,
        workload_id: str,
    ) -> WorkloadRecord:
        workload_id = str(workload_id).strip()

        if not workload_id:
            raise ValueError(
                "workload_id cannot be empty"
            )

        with self._lock:
            existing = self._workloads.get(
                workload_id
            )

            if existing is None:
                raise WorkloadNotFoundError(
                    f"unknown workload: {workload_id}"
                )

            previous = existing

            stopping = replace(
                existing,
                status="stopping",
                updated_at_utc=_utc_now(),
            )

            self._workloads[
                workload_id
            ] = stopping

            self._persist_unlocked()

            try:
                self._runtime.stop(
                    workload_id=workload_id,
                    model_id=existing.model_id,
                    runtime_state=dict(
                        existing.runtime_state
                    ),
                )
            except Exception as exc:
                self._workloads[
                    workload_id
                ] = previous

                self._persist_unlocked()

                raise RuntimeStopError(
                    f"runtime failed to stop "
                    f"{workload_id}: {exc}"
                ) from exc

            # Runtime is now stopped. Remove workload state first.
            # If persistence fails, retain the reservation: stale reservation
            # is safer than accidental oversubscription.
            del self._workloads[
                workload_id
            ]

            try:
                self._persist_unlocked()
            except Exception:
                self._workloads[
                    workload_id
                ] = stopping

                raise

            released = self._ledger.release(
                existing.reservation_id
            )

            if released is None:
                raise ResourceManagerError(
                    "runtime stopped but reservation was missing: "
                    f"{existing.reservation_id}"
                )

            return replace(
                stopping,
                status="stopped",
                updated_at_utc=_utc_now(),
            )

    def workload(
        self,
        workload_id: str,
    ) -> WorkloadRecord | None:
        with self._lock:
            return self._workloads.get(
                workload_id
            )

    def workloads(
        self,
    ) -> tuple[WorkloadRecord, ...]:
        with self._lock:
            return tuple(
                sorted(
                    self._workloads.values(),
                    key=lambda value:
                        value.workload_id,
                )
            )

    def snapshot(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            return {
                "workloads": [
                    workload.to_dict()
                    for workload in self.workloads()
                ],
                "resources":
                    self._ledger.snapshot().to_dict(),
            }
