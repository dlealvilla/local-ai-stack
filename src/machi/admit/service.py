"""Reserve exactly what a current plan requested. Do not resize it."""

from __future__ import annotations

from dataclasses import dataclass, replace

from machi.admit.contracts import (
    AdmissionDecision,
    AdmissionFailure,
    AdmissionOutcome,
    ReconciliationReport,
    ReconciliationStatus,
    ReservationRelease,
    ReservationState,
    ResourceReservation,
    refused,
)
from machi.admit.identity import release_id, reservation_id
from machi.admit.lock import AdmissionLock, LocalLock
from machi.admit.policy import ACCELERATOR_COUNT, POLICY_VERSION
from machi.admit.ports import ReservationLog
from machi.capacity.contracts import AcceleratorCapacity, CapacityEnvelope
from machi.kernel.errors import ConflictError
from machi.kernel.unresolved import is_resolved
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanStatus,
    ResourceRequest,
)


@dataclass(frozen=True, slots=True)
class _Ledger:
    active: tuple[ResourceReservation, ...]
    held: tuple[ResourceReservation, ...]
    released_ids: frozenset[str]
    malformed: int


class ResourceManager:
    """Single-host admission. The store is the authority, not this object."""

    def __init__(
        self,
        log: ReservationLog,
        lock: AdmissionLock | None = None,
    ) -> None:
        self._log = log
        self._lock = lock if lock is not None else LocalLock()

    def admit(
        self,
        decision: PlanDecision,
        capacity: CapacityEnvelope,
        plan_currency: PlanFailure,
    ) -> AdmissionDecision:
        """Reserve every requested dimension or reserve nothing."""
        with self._lock:
            return self._admit(decision, capacity, plan_currency)

    def release(self, reservation_id_value: str) -> AdmissionDecision:
        """Free one hold. A second release of the same hold converges."""
        with self._lock:
            return self._release(reservation_id_value)

    def get_reservation(self, reservation_id_value: str) -> ResourceReservation | None:
        ledger = self._ledger()
        for item in (*ledger.active, *self._released(ledger)):
            if item.reservation_id == reservation_id_value:
                return item
        return None

    def list_active_reservations(self) -> tuple[ResourceReservation, ...]:
        return self._ledger().active

    def reconcile(self, capacity: CapacityEnvelope) -> ReconciliationReport:
        """Report drift. Do not delete or rewrite holds to hide it."""
        ledger = self._ledger()
        missing = tuple(
            sorted(
                {
                    item.accelerator_identity
                    for item in ledger.active
                    if not _has_device(capacity, item.accelerator_identity)
                }
            )
        )
        over = _overcommitted(ledger.active, capacity)
        if over:
            status = ReconciliationStatus.OVERCOMMITTED
        elif missing or ledger.malformed:
            status = ReconciliationStatus.DEGRADED
        else:
            status = ReconciliationStatus.CONSISTENT
        return ReconciliationReport(
            status=status,
            active_count=len(ledger.active),
            malformed_count=ledger.malformed,
            missing_accelerators=missing,
            overcommitted=over,
            policy_version=POLICY_VERSION,
        )

    def execution_authorized(
        self,
        reservation_id_value: str,
        configuration: DeploymentConfiguration,
    ) -> bool:
        """M9 must call this. A bare plan is not authorization."""
        current = self.get_reservation(reservation_id_value)
        if current is None or current.state is not ReservationState.RESERVED:
            return False
        return (
            current.plan_id == configuration.plan_id
            and current.fingerprint == configuration.fingerprint
            and current.accelerator_identity == configuration.accelerator_identity
        )

    def _admit(
        self,
        decision: PlanDecision,
        capacity: CapacityEnvelope,
        plan_currency: PlanFailure,
    ) -> AdmissionDecision:
        configuration = decision.configuration
        request = decision.request
        if decision.failure is not PlanFailure.NONE or not is_resolved(configuration):
            return refused(
                AdmissionFailure.PLAN_NOT_SUCCESSFUL, "plan was not produced"
            )
        if not is_resolved(request):
            return refused(AdmissionFailure.PLAN_NOT_SUCCESSFUL, "plan has no request")
        if configuration.status is not PlanStatus.PLANNED:
            return refused(AdmissionFailure.PLAN_NOT_SUCCESSFUL, "plan is not planned")
        mismatch = _pair(configuration, request)
        if mismatch is not None:
            return mismatch
        if plan_currency is not PlanFailure.NONE:
            return refused(AdmissionFailure.STALE_PLAN, plan_currency.value)
        if configuration.capacity_evidence_id != capacity.evidence_id:
            return refused(
                AdmissionFailure.STALE_CAPACITY_INPUT,
                "plan cites a different capacity snapshot",
            )
        if request.accelerator_count != ACCELERATOR_COUNT:
            return refused(
                AdmissionFailure.MULTI_ACCELERATOR_ADMISSION_NOT_IMPLEMENTED,
                "only one accelerator can be reserved",
            )
        ledger = self._ledger()
        if _overcommitted(ledger.active, capacity):
            return refused(
                AdmissionFailure.CURRENT_CAPACITY_OVERCOMMITTED,
                "existing holds already exceed safe capacity",
            )
        device = _device(capacity, configuration.accelerator_identity)
        if device is None:
            return refused(
                AdmissionFailure.ACCELERATOR_NOT_PRESENT,
                "planned accelerator is not in this snapshot",
            )
        host = capacity.memory.safe_bytes
        accel = device.safe_bytes
        storage = _storage_ceiling(capacity)
        if not isinstance(host, int) or not isinstance(accel, int):
            return refused(
                AdmissionFailure.CAPACITY_UNRESOLVED, "safe memory is unknown"
            )
        if (request.persistent_bytes or request.transient_bytes) and storage is None:
            return refused(
                AdmissionFailure.CAPACITY_UNRESOLVED,
                "safe storage is unknown",
            )
        sequence = _sequence(ledger, configuration)
        identity = reservation_id(
            plan_id=configuration.plan_id,
            fingerprint=configuration.fingerprint,
            request_id=request.request_id,
            capacity_evidence_id=capacity.evidence_id,
            sequence=sequence,
        )
        for existing in ledger.active:
            if existing.reservation_id == identity:
                return _admitted(existing)
        fit = _fits(
            ledger.active,
            request,
            configuration.accelerator_identity,
            host,
            accel,
            storage,
        )
        if fit is not None:
            return fit
        record = ResourceReservation(
            reservation_id=identity,
            plan_id=configuration.plan_id,
            fingerprint=configuration.fingerprint,
            request_id=request.request_id,
            capacity_evidence_id=capacity.evidence_id,
            accelerator_identity=configuration.accelerator_identity,
            accelerator_memory_bytes=request.accelerator_memory_bytes,
            host_memory_bytes=request.host_memory_bytes,
            persistent_bytes=request.persistent_bytes,
            transient_bytes=request.transient_bytes,
            cpu_count=request.cpu_count,
            policy_version=POLICY_VERSION,
            state=ReservationState.RESERVED,
        )
        try:
            stored, _created = self._log.create(identity, record)
        except ConflictError:
            return refused(
                AdmissionFailure.RESERVATION_CONFLICT,
                "an existing hold does not match this admission",
            )
        if not isinstance(stored, ResourceReservation):
            return refused(
                AdmissionFailure.RESERVATION_STATE_INVALID,
                "store returned an unexpected record",
            )
        return _admitted(stored)

    def _release(self, reservation_id_value: str) -> AdmissionDecision:
        ledger = self._ledger()
        found = None
        for item in ledger.active:
            if item.reservation_id == reservation_id_value:
                found = item
                break
        if found is None:
            for item in self._released(ledger):
                if item.reservation_id == reservation_id_value:
                    return AdmissionDecision(
                        outcome=AdmissionOutcome.RELEASED,
                        failure=AdmissionFailure.NONE,
                        reason="release already recorded",
                        reservation=item,
                    )
            return refused(
                AdmissionFailure.RESERVATION_STATE_INVALID,
                "reservation does not exist",
            )
        release = ReservationRelease(
            release_id=release_id(found.reservation_id),
            reservation_id=found.reservation_id,
            plan_id=found.plan_id,
        )
        self._log.create(release.release_id, release)
        freed = replace(found, state=ReservationState.RELEASED)
        return AdmissionDecision(
            outcome=AdmissionOutcome.RELEASED,
            failure=AdmissionFailure.NONE,
            reason="resources returned to the safe pool",
            reservation=freed,
        )

    def _ledger(self) -> _Ledger:
        records, malformed = self._log.reservations()
        released_ids = frozenset(item.reservation_id for item in self._log.releases())
        active = tuple(
            item
            for item in records
            if item.reservation_id not in released_ids
            and item.state is ReservationState.RESERVED
        )
        return _Ledger(
            active=active,
            held=records,
            released_ids=released_ids,
            malformed=malformed,
        )

    def _released(self, ledger: _Ledger) -> tuple[ResourceReservation, ...]:
        return tuple(
            replace(item, state=ReservationState.RELEASED)
            for item in ledger.held
            if item.reservation_id in ledger.released_ids
        )


def _admitted(reservation: ResourceReservation) -> AdmissionDecision:
    return AdmissionDecision(
        outcome=AdmissionOutcome.ADMITTED,
        failure=AdmissionFailure.NONE,
        reason="resources reserved",
        reservation=reservation,
    )


def _pair(
    configuration: DeploymentConfiguration,
    request: ResourceRequest,
) -> AdmissionDecision | None:
    if (
        configuration.plan_id != request.plan_id
        or configuration.fingerprint != request.fingerprint
    ):
        return refused(
            AdmissionFailure.PLAN_REQUEST_MISMATCH, "request does not match the plan"
        )
    if (
        configuration.artifact_id != request.artifact_id
        or configuration.generation_id != request.generation_id
        or configuration.capacity_evidence_id != request.capacity_evidence_id
        or configuration.foundation_id != request.foundation_id
    ):
        return refused(
            AdmissionFailure.PLAN_CONFIGURATION_MISMATCH,
            "request bindings do not match the configuration",
        )
    return None


def _fits(
    active: tuple[ResourceReservation, ...],
    request: ResourceRequest,
    accelerator_identity: str,
    host_safe: int,
    accelerator_safe: int,
    storage_safe: int | None,
) -> AdmissionDecision | None:
    host_used = sum(item.host_memory_bytes for item in active)
    if host_used + request.host_memory_bytes > host_safe:
        return refused(
            AdmissionFailure.INSUFFICIENT_HOST_MEMORY, "host safe memory is short"
        )
    accel_used = sum(
        item.accelerator_memory_bytes
        for item in active
        if item.accelerator_identity == accelerator_identity
    )
    if accel_used + request.accelerator_memory_bytes > accelerator_safe:
        return refused(
            AdmissionFailure.INSUFFICIENT_ACCELERATOR_CAPACITY,
            "accelerator safe memory is short",
        )
    if storage_safe is None:
        return None
    used = sum(item.persistent_bytes + item.transient_bytes for item in active)
    remaining = storage_safe - used
    if request.persistent_bytes > remaining:
        return refused(
            AdmissionFailure.INSUFFICIENT_PERSISTENT_STORAGE,
            "safe storage cannot hold the persistent request",
        )
    if request.persistent_bytes + request.transient_bytes > remaining:
        return refused(
            AdmissionFailure.INSUFFICIENT_TRANSIENT_STORAGE,
            "safe storage cannot hold the transient request",
        )
    return None


def _overcommitted(
    active: tuple[ResourceReservation, ...],
    capacity: CapacityEnvelope,
) -> tuple[str, ...]:
    found: list[str] = []
    host = capacity.memory.safe_bytes
    if isinstance(host, int) and sum(item.host_memory_bytes for item in active) > host:
        found.append("host_memory")
    by_device: dict[str, int] = {}
    for item in active:
        by_device[item.accelerator_identity] = (
            by_device.get(item.accelerator_identity, 0) + item.accelerator_memory_bytes
        )
    for identity, used in by_device.items():
        device = _device(capacity, identity)
        if (
            device is not None
            and isinstance(device.safe_bytes, int)
            and used > device.safe_bytes
        ):
            found.append("accelerator_memory")
            break
    ceiling = _storage_ceiling(capacity)
    storage_used = sum(item.persistent_bytes + item.transient_bytes for item in active)
    if ceiling is not None and storage_used > ceiling:
        found.append("storage")
    return tuple(found)


def _device(capacity: CapacityEnvelope, identity: str) -> AcceleratorCapacity | None:
    for device in capacity.accelerators:
        if device.identity == identity:
            return device
    return None


def _has_device(capacity: CapacityEnvelope, identity: str) -> bool:
    return _device(capacity, identity) is not None


def _storage_ceiling(capacity: CapacityEnvelope) -> int | None:
    """Largest single usable domain. Pools are not added together."""
    found: list[int] = []
    for domain in capacity.storage_domains:
        if domain.usable and isinstance(domain.safe_bytes, int):
            found.append(domain.safe_bytes)
    if not found:
        return None
    return max(found)


def _sequence(ledger: _Ledger, configuration: DeploymentConfiguration) -> int:
    return sum(
        1
        for item in ledger.held
        if item.reservation_id in ledger.released_ids
        and item.plan_id == configuration.plan_id
        and item.fingerprint == configuration.fingerprint
        and item.capacity_evidence_id == configuration.capacity_evidence_id
    )
