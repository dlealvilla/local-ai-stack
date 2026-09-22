"""Admit one in-memory plan from the installed package. No server."""

from __future__ import annotations

import datetime as dt
import tempfile
from pathlib import Path

from machi.adapters.admit.lock import FileAdmissionLock
from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.persistence.file_store import FileStore
from machi.admit.contracts import AdmissionFailure, ReservationState
from machi.admit.service import ResourceManager
from machi.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceStrength,
    MemoryCapacity,
    StorageDomainCapacity,
)
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import not_attempted
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanStatus,
    ResourceRequest,
)

FIXED = dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC)


def _envelope() -> CapacityEnvelope:
    return CapacityEnvelope(
        evidence_id="cev_prove",
        input_token="capacity-prove",
        memory=MemoryCapacity(
            physical_bytes=NOT_PROVIDED,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=100,
            strength=EvidenceStrength.REPORTED,
            reason="fixture host",
        ),
        accelerators=(
            AcceleratorCapacity(
                identity="accel_prove",
                ordinal=0,
                topology="discrete",
                physical_bytes=NOT_PROVIDED,
                current_used_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=100,
                strength=EvidenceStrength.REPORTED,
                reason="fixture device",
            ),
        ),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_prove",
                backing_resolved=True,
                reported_available_bytes=NOT_PROVIDED,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=100,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="fixture storage",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED,
        provider="native",
    )


def _decision() -> PlanDecision:
    token = "a" * 32
    configuration = DeploymentConfiguration(
        plan_id="plan_prove",
        status=PlanStatus.PLANNED,
        model_id="mdl_prove",
        artifact_id="mart_prove",
        immutable_revision="commit-prove",
        foundation_id="fgen_prove",
        generation_id="fgen_prove",
        capacity_evidence_id="cev_prove",
        provider="vllm",
        accelerator_count=1,
        accelerator_identity="accel_prove",
        context_length=2048,
        concurrency=4,
        dtype="float32",
        quantization="none",
        policy_version="m7.plan.1",
        fingerprint=token,
        settings=(),
    )
    request = ResourceRequest(
        request_id="preq_prove",
        plan_id="plan_prove",
        fingerprint=token,
        foundation_id="fgen_prove",
        generation_id="fgen_prove",
        capacity_evidence_id="cev_prove",
        artifact_id="mart_prove",
        accelerator_count=1,
        accelerator_memory_bytes=40,
        host_memory_bytes=40,
        persistent_bytes=10,
        transient_bytes=0,
        cpu_count=1,
    )
    return PlanDecision(
        decision_id="pdec_prove",
        failure=PlanFailure.NONE,
        reason="planned",
        fingerprint=token,
        configuration=configuration,
        request=request,
    )


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="machi-admit-"))
    store = FileStore(root)
    manager = ResourceManager(StoreReservationLog(store), FileAdmissionLock(root))
    capacity = _envelope()
    decision = _decision()
    first = manager.admit(decision, capacity, PlanFailure.NONE)
    if first.failure is not AdmissionFailure.NONE or not is_resolved(first.reservation):
        raise SystemExit(f"admit refused: {first.failure.value}")
    identity = first.reservation.reservation_id
    if first.reservation.state is not ReservationState.RESERVED:
        raise SystemExit("reservation was not reserved")
    second = manager.admit(decision, capacity, PlanFailure.NONE)
    if not is_resolved(second.reservation):
        raise SystemExit("repeat admission lost the reservation")
    if second.reservation.reservation_id != identity:
        raise SystemExit("repeat admission created another hold")
    if len(manager.list_active_reservations()) != 1:
        raise SystemExit("repeat admission consumed capacity twice")
    released = manager.release(identity)
    if released.failure is not AdmissionFailure.NONE:
        raise SystemExit(f"release failed: {released.failure.value}")
    again = manager.release(identity)
    if again.failure is not AdmissionFailure.NONE:
        raise SystemExit("repeated release did not converge")
    if manager.list_active_reservations():
        raise SystemExit("release did not free the hold")
    third = manager.admit(decision, capacity, PlanFailure.NONE)
    if third.failure is not AdmissionFailure.NONE or not is_resolved(third.reservation):
        raise SystemExit("freed capacity was not admissible again")
    if third.reservation.reservation_id == identity:
        raise SystemExit("a new hold reused the released reservation id")
    print(f"admit_ok {identity}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
