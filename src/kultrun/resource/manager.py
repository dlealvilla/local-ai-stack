"""Resource Manager: admit now, or do not. No queues, no launch."""

from __future__ import annotations

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import NotFoundError, ValidationError
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import ArtifactState, MemoryPlacement, ModelArtifact
from kultrun.resource.contracts import (
    POLICY_VERSION,
    AdmissionDecision,
    AdmissionReason,
    AdmissionVerdict,
    LedgerHealth,
    RequestId,
    ReservationId,
    ReservationState,
    ResourceRequest,
    ResourceReservation,
    ResourceSummary,
    Workload,
    WorkloadId,
    WorkloadType,
)
from kultrun.resource.ledger import (
    as_int,
    available_for_new_work,
    device_health,
    reserved_accelerator,
    reserved_ram,
    reserved_storage,
    reserved_unified,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.snapshot import current_capacity_snapshot


class ResourceManager:
    """Authoritative admission and reservation ledger. Not a process manager."""

    def __init__(self, store: Store, clock: Clock, lock: AdmissionLock) -> None:
        self._store = store
        self._clock = clock
        self._lock = lock

    def reservations(
        self, *, include_released: bool = False
    ) -> tuple[ResourceReservation, ...]:
        found = []
        for item in self._store.records(ResourceReservation):
            if item.state is ReservationState.RELEASED and not include_released:
                continue
            found.append(item)
        return tuple(found)

    def get(self, reservation_id: ReservationId) -> ResourceReservation | None:
        return self._store.get(ResourceReservation, reservation_id.value)

    def summary(self, envelope: CapacityEnvelope) -> ResourceSummary:
        return self.snapshot(envelope)

    def snapshot(
        self,
        envelope: CapacityEnvelope,
        *,
        exclude_reservation_id: ReservationId | str | None = None,
        host: HostCapabilities | None = None,
    ) -> ResourceSummary:
        """Derived current available capacity. Never stored as host truth."""
        return current_capacity_snapshot(
            envelope,
            self.reservations(include_released=True),
            exclude_reservation_id=exclude_reservation_id,
            host=host,
            observed_at=self._clock.now(),
        )

    def active_reservation_for_plan(
        self, plan_basis: object
    ) -> ResourceReservation | None:
        """ACTIVE grant for this plan, if exactly one matches. Not admission."""
        if not is_resolved(plan_basis) or not isinstance(plan_basis, str):
            return None
        token = plan_basis.strip()
        if not token:
            return None
        matches = [
            item
            for item in self.reservations()
            if item.state is ReservationState.ACTIVE
            and is_resolved(item.plan_fingerprint)
            and item.plan_fingerprint == token
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def admit(
        self,
        request: ResourceRequest,
        envelope: CapacityEnvelope,
        artifact: ModelArtifact | None = None,
    ) -> AdmissionDecision:
        """Check SAFE minus ACTIVE, then persist. One protected operation."""
        with self._lock.hold():
            return self._admit_locked(request, envelope, artifact)

    def release(self, reservation_id: ReservationId) -> ResourceReservation:
        """ACTIVE → RELEASED. Idempotent. Does not stop or delete anything."""
        parsed = ReservationId.parse(reservation_id.value)
        with self._lock.hold():
            found = self.get(parsed)
            if found is None:
                raise NotFoundError("no such reservation", reservation_id=parsed.value)
            if found.state is ReservationState.RELEASED:
                return found
            now = self._clock.now()
            released = ResourceReservation(
                reservation_id=found.reservation_id,
                workload_id=found.workload_id,
                host_id=found.host_id,
                state=ReservationState.RELEASED,
                created_at=found.created_at,
                admitted_vram_bytes=found.admitted_vram_bytes,
                admitted_ram_bytes=found.admitted_ram_bytes,
                admitted_storage_bytes=found.admitted_storage_bytes,
                accelerator_index=found.accelerator_index,
                released_at=now,
                request_id=found.request_id,
                artifact_id=found.artifact_id,
                plan_fingerprint=found.plan_fingerprint,
                admitted_unified_bytes=found.admitted_unified_bytes,
                admitted_cpu=found.admitted_cpu,
                host_fingerprint=found.host_fingerprint,
                capacity_policy_version=found.capacity_policy_version,
                admission_policy_version=found.admission_policy_version,
                safe_ram_at_admission=found.safe_ram_at_admission,
                safe_accelerator_at_admission=found.safe_accelerator_at_admission,
                reserved_ram_before=found.reserved_ram_before,
                reserved_accelerator_before=found.reserved_accelerator_before,
                available_ram_after=found.available_ram_after,
                available_accelerator_after=found.available_accelerator_after,
                release_reason="released",
                estimator_provider=found.estimator_provider,
                logical_name=found.logical_name,
                quantization=found.quantization,
                model_revision=found.model_revision,
                storage_pool_mount=found.storage_pool_mount,
                storage_quota_identity=found.storage_quota_identity,
            )
            self._store.put(released.reservation_id.value, released)
            return released

    def _admit_locked(
        self,
        request: ResourceRequest,
        envelope: CapacityEnvelope,
        artifact: ModelArtifact | None,
    ) -> AdmissionDecision:
        storage_work = request.workload_type in {
            WorkloadType.RUNTIME_PROVISIONING,
            WorkloadType.MODEL_ACQUISITION,
        }
        if not storage_work:
            if artifact is None or request.artifact_id is None:
                raise ValidationError("inference admission requires a stored artifact")
            if artifact.artifact_id != request.artifact_id:
                raise ValidationError(
                    "request artifact does not match inventory artifact"
                )
            if artifact.state is not ArtifactState.STORED:
                return self._decide(
                    request,
                    envelope,
                    AdmissionVerdict.REJECTED,
                    AdmissionReason.ARTIFACT_NOT_STORED,
                    "artifact is not STORED",
                )
        existing = self._active_for_request(request.request_id)
        if existing is not None:
            return AdmissionDecision(
                verdict=AdmissionVerdict.ADMITTED,
                request_id=request.request_id,
                host_id=request.host_id,
                ledger_health=device_health(
                    envelope, self.reservations(include_released=True)
                ),
                reasons=("existing ACTIVE reservation reused",),
                reason_code=AdmissionReason.REUSED.value,
                reservation=existing,
                reused=True,
                serving=False,
            )

        check = self._check(request, envelope)
        if check is not None:
            return check

        now = self._clock.now()
        current = self.reservations(include_released=True)
        ram_reserved = reserved_ram(current)
        acc_index = request.accelerator_index
        acc_reserved = (
            reserved_accelerator(current, acc_index) if acc_index is not None else 0
        )
        ram_safe = as_int(envelope.memory.safe_bytes)
        acc_safe = _device_safe(envelope, acc_index)
        workload = Workload(
            workload_id=WorkloadId.generate(),
            host_id=request.host_id,
            workload_type=request.workload_type or WorkloadType.INFERENCE,
            created_at=now,
            model_id=request.model_id,
        )
        reservation = ResourceReservation(
            reservation_id=ReservationId.generate(),
            workload_id=workload.workload_id,
            host_id=request.host_id,
            state=ReservationState.ACTIVE,
            created_at=now,
            admitted_vram_bytes=request.accelerator_bytes,
            admitted_ram_bytes=request.ram_bytes,
            admitted_storage_bytes=request.incremental_storage_bytes,
            accelerator_index=acc_index,
            request_id=request.request_id,
            artifact_id=request.artifact_id,
            plan_fingerprint=request.plan_fingerprint,
            admitted_unified_bytes=request.unified_bytes,
            admitted_cpu=request.cpu,
            host_fingerprint=envelope.host_fingerprint,
            capacity_policy_version=envelope.policy_version,
            admission_policy_version=POLICY_VERSION,
            safe_ram_at_admission=envelope.memory.safe_bytes,
            safe_accelerator_at_admission=(
                acc_safe if acc_safe is not None else NOT_PROVIDED
            ),
            reserved_ram_before=ram_reserved,
            reserved_accelerator_before=acc_reserved,
            available_ram_after=available_for_new_work(
                ram_safe, ram_reserved + (as_int(request.ram_bytes) or 0)
            ),
            available_accelerator_after=available_for_new_work(
                acc_safe, acc_reserved + (as_int(request.accelerator_bytes) or 0)
            ),
            estimator_provider=request.estimator_provider,
            logical_name=request.logical_name,
            quantization=request.quantization,
            model_revision=request.model_revision,
            storage_pool_mount=request.storage_pool_mount,
            storage_quota_identity=request.storage_quota_identity,
        )
        self._store.put(workload.workload_id.value, workload)
        self._store.put(request.request_id.value, request)
        self._store.put(reservation.reservation_id.value, reservation)
        return AdmissionDecision(
            verdict=AdmissionVerdict.ADMITTED,
            request_id=request.request_id,
            host_id=request.host_id,
            ledger_health=LedgerHealth.WITHIN_CAPACITY,
            reasons=("every load-bearing dimension fits remaining SAFE capacity",),
            reason_code=AdmissionReason.ADMITTED.value,
            reservation=reservation,
            reused=False,
            serving=False,
        )

    def _active_for_request(self, request_id: RequestId) -> ResourceReservation | None:
        for item in self.reservations():
            if item.request_id == request_id and item.state is ReservationState.ACTIVE:
                return item
        return None

    def _check(
        self, request: ResourceRequest, envelope: CapacityEnvelope
    ) -> AdmissionDecision | None:
        current = self.reservations(include_released=True)
        health = device_health(envelope, current)
        if health is LedgerHealth.UNRESOLVED:
            return self._decide(
                request,
                envelope,
                AdmissionVerdict.UNRESOLVED,
                AdmissionReason.UNRESOLVED_SAFE_CAPACITY,
                "load-bearing SAFE capacity is unresolved",
            )

        if request.placement is MemoryPlacement.DISCRETE_GPU:
            if request.accelerator_index is None:
                return self._decide(
                    request,
                    envelope,
                    AdmissionVerdict.UNRESOLVED,
                    AdmissionReason.PLACEMENT_UNDETERMINED,
                    "discrete-GPU placement has no device index",
                )
            if _device_safe(envelope, request.accelerator_index) is None and not any(
                item.index == request.accelerator_index
                for item in envelope.accelerators
            ):
                return self._decide(
                    request,
                    envelope,
                    AdmissionVerdict.REJECTED,
                    AdmissionReason.SELECTED_ACCELERATOR_UNKNOWN,
                    "selected accelerator is not on this host",
                )
        dimensions = _load_bearing(request)
        if not dimensions:
            return self._decide(
                request,
                envelope,
                AdmissionVerdict.UNRESOLVED,
                AdmissionReason.UNRESOLVED_REQUIREMENT,
                "load-bearing resource requirement is unresolved",
            )
        if health is LedgerHealth.OVERCOMMITTED:
            return self._decide(
                request,
                envelope,
                AdmissionVerdict.REJECTED,
                AdmissionReason.LEDGER_OVERCOMMITTED,
                "ledger is OVERCOMMITTED; new admission would increase overcommit",
            )

        for name, needed in dimensions:
            safe, reserved = _safe_and_reserved(name, request, envelope, current)
            if safe is None:
                return self._decide(
                    request,
                    envelope,
                    AdmissionVerdict.UNRESOLVED,
                    AdmissionReason.UNRESOLVED_SAFE_CAPACITY,
                    f"SAFE {name} is unresolved",
                )
            headroom = available_for_new_work(safe, reserved)
            if not isinstance(headroom, int) or needed > headroom:
                reason = (
                    AdmissionReason.INSUFFICIENT_SAFE_RAM
                    if name == "ram"
                    else (
                        AdmissionReason.INSUFFICIENT_SAFE_UNIFIED
                        if name == "unified"
                        else (
                            AdmissionReason.INSUFFICIENT_SAFE_STORAGE
                            if name == "storage"
                            else AdmissionReason.INSUFFICIENT_SAFE_ACCELERATOR
                        )
                    )
                )
                return self._decide(
                    request,
                    envelope,
                    AdmissionVerdict.REJECTED,
                    reason,
                    f"requested {name} {needed} exceeds reservable {headroom}",
                )
        return None

    def _decide(
        self,
        request: ResourceRequest,
        envelope: CapacityEnvelope,
        verdict: AdmissionVerdict,
        reason: AdmissionReason,
        text: str,
    ) -> AdmissionDecision:
        return AdmissionDecision(
            verdict=verdict,
            request_id=request.request_id,
            host_id=request.host_id,
            ledger_health=device_health(
                envelope, self.reservations(include_released=True)
            ),
            reasons=(text,),
            reason_code=reason.value,
            serving=False,
        )


def _load_bearing(request: ResourceRequest) -> list[tuple[str, int]]:
    """Resolved amounts that must fit. CPU and ports are not load-bearing."""
    if request.workload_type in {
        WorkloadType.RUNTIME_PROVISIONING,
        WorkloadType.MODEL_ACQUISITION,
    }:
        storage = as_int(request.incremental_storage_bytes)
        if storage is None:
            return []
        return [("storage", storage)]
    needed: list[tuple[str, int]] = []
    ram = as_int(request.ram_bytes)
    if ram is None:
        return []
    needed.append(("ram", ram))
    if request.placement is MemoryPlacement.DISCRETE_GPU:
        if request.accelerator_index is None:
            return []
        accel = as_int(request.accelerator_bytes)
        if accel is None:
            return []
        needed.append(("accelerator", accel))
    elif request.placement is MemoryPlacement.UNIFIED_MEMORY:
        unified = as_int(request.unified_bytes)
        if unified is None:
            return []
        needed.append(("unified", unified))
    incremental = as_int(request.incremental_storage_bytes)
    if incremental is not None:
        needed.append(("storage", incremental))
    return needed


def _safe_and_reserved(
    name: str,
    request: ResourceRequest,
    envelope: CapacityEnvelope,
    current: tuple[ResourceReservation, ...],
) -> tuple[int | None, int]:
    if name == "ram":
        return as_int(envelope.memory.safe_bytes), reserved_ram(current)
    if name == "unified":
        return None, reserved_unified(current)
    if name == "accelerator":
        index = request.accelerator_index
        if index is None:
            return None, 0
        return _device_safe(envelope, index), reserved_accelerator(current, index)
    if name == "storage":
        mount = (
            request.storage_pool_mount
            if is_resolved(request.storage_pool_mount)
            else None
        )
        if not isinstance(mount, str):
            return None, 0
        return _pool_safe(envelope, mount), reserved_storage(current, mount)
    return None, 0


def _pool_safe(envelope: CapacityEnvelope, mount: str) -> int | None:
    for pool in envelope.pools:
        if pool.mount_point == mount:
            return as_int(pool.space.safe_bytes)
    return None


def _device_safe(envelope: CapacityEnvelope, index: int | None) -> int | None:
    if index is None:
        return None
    for accelerator in envelope.accelerators:
        if accelerator.index == index:
            return as_int(accelerator.memory.safe_bytes)
    return None
