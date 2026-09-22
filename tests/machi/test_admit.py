"""Admission accounting. No serving and no vendor tools."""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from machi.adapters.admit.log import StoreReservationLog
from machi.adapters.persistence.file_store import FileStore
from machi.admit.contracts import (
    AdmissionDecision,
    AdmissionFailure,
    AdmissionOutcome,
    ReconciliationStatus,
    ReservationRelease,
    ReservationState,
    ResourceReservation,
)
from machi.admit.events import admission_event
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
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ConflictError
from machi.kernel.schema import Contract
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.main import main
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanStatus,
    ResourceRequest,
)

FIXED = FixedClock(dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC))


def _envelope(
    *,
    host: int | object = 100,
    accel: int | object = 100,
    storage: int | object = 100,
    evidence: str = "cev_admit",
    device: str = "accel_0",
    physical: int = 10_000,
) -> CapacityEnvelope:

    return CapacityEnvelope(
        evidence_id=evidence,
        input_token="capacity-admit",
        memory=MemoryCapacity(
            physical_bytes=physical,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=host if isinstance(host, int) else NOT_PROVIDED,
            strength=EvidenceStrength.REPORTED,
            reason="host safe",
        ),
        accelerators=(
            AcceleratorCapacity(
                identity=device,
                ordinal=0,
                topology="discrete",
                physical_bytes=physical,
                current_used_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=accel if isinstance(accel, int) else NOT_PROVIDED,
                strength=EvidenceStrength.REPORTED,
                reason="device safe",
            ),
        )
        if device
        else (),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_admit",
                backing_resolved=True,
                reported_available_bytes=NOT_PROVIDED,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=storage if isinstance(storage, int) else NOT_PROVIDED,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="storage safe",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC),
        provider="native",
    )


def _decision(
    *,
    plan: str = "plan_a",
    token: str = "a" * 32,
    host: int = 40,
    accel: int = 40,
    persistent: int = 10,
    transient: int = 0,
    device: str = "accel_0",
    evidence: str = "cev_admit",
    count: int = 1,
) -> PlanDecision:
    configuration = DeploymentConfiguration(
        plan_id=plan,
        status=PlanStatus.PLANNED,
        model_id="mdl_a",
        artifact_id="mart_a",
        immutable_revision="rev-a",
        foundation_id="fgen_a",
        generation_id="fgen_a",
        capacity_evidence_id=evidence,
        provider="vllm",
        accelerator_count=1,
        accelerator_identity=device,
        context_length=2048,
        concurrency=4,
        dtype="float32",
        quantization="none",
        policy_version="m7.plan.1",
        fingerprint=token,
        settings=(),
    )
    request = ResourceRequest(
        request_id=f"preq_{plan[-8:]}",
        plan_id=plan,
        fingerprint=token,
        foundation_id="fgen_a",
        generation_id="fgen_a",
        capacity_evidence_id=evidence,
        artifact_id="mart_a",
        accelerator_count=count,
        accelerator_memory_bytes=accel,
        host_memory_bytes=host,
        persistent_bytes=persistent,
        transient_bytes=transient,
        cpu_count=1,
    )
    if count != 1:
        request = replace(request, accelerator_count=1)
        configuration = replace(configuration, accelerator_count=1)
    return PlanDecision(
        decision_id=f"pdec_{plan[-8:]}",
        failure=PlanFailure.NONE,
        reason="planned",
        fingerprint=token,
        configuration=configuration,
        request=request,
    )


def _reservation(decision: AdmissionDecision) -> ResourceReservation:
    item = decision.reservation
    assert is_resolved(item)
    return item


def _configuration(decision: PlanDecision) -> DeploymentConfiguration:
    item = decision.configuration
    assert is_resolved(item)
    return item


def _manager(tmp_path: Path) -> ResourceManager:
    store = FileStore(tmp_path)
    return ResourceManager(StoreReservationLog(store))


def test_admit_binds_the_plan_and_does_not_serve(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    decision = _decision()
    admitted = manager.admit(decision, _envelope(), PlanFailure.NONE)
    assert admitted.outcome is AdmissionOutcome.ADMITTED
    reservation = admitted.reservation
    assert is_resolved(reservation)
    assert reservation.state is ReservationState.RESERVED
    assert reservation.plan_id == "plan_a"
    assert reservation.accelerator_identity == "accel_0"
    assert reservation.policy_version == "m8.admit.1"
    assert manager.execution_authorized(
        reservation.reservation_id, _configuration(decision)
    )
    event = admission_event(admitted, plan_id="plan_a", clock=FIXED)
    assert event.event_type.value == "admit.completed"
    assert "/" not in str(event.payload)
    assert not (tmp_path / "serving_instance").exists()


def test_repeat_admission_does_not_double_count(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    capacity = _envelope()
    decision = _decision(host=40, accel=40)
    first = manager.admit(decision, capacity, PlanFailure.NONE)
    second = manager.admit(decision, capacity, PlanFailure.NONE)
    assert _reservation(first).reservation_id == _reservation(second).reservation_id
    assert len(manager.list_active_reservations()) == 1


def test_aggregate_host_memory_refuses_the_overflow(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    capacity = _envelope(host=100, accel=1000)
    assert (
        manager.admit(
            _decision(plan="plan_a", token="a" * 32, host=40),
            capacity,
            PlanFailure.NONE,
        ).outcome
        is AdmissionOutcome.ADMITTED
    )
    assert (
        manager.admit(
            _decision(plan="plan_b", token="b" * 32, host=30),
            capacity,
            PlanFailure.NONE,
        ).outcome
        is AdmissionOutcome.ADMITTED
    )
    overflow = manager.admit(
        _decision(plan="plan_c", token="c" * 32, host=31),
        capacity,
        PlanFailure.NONE,
    )
    assert overflow.failure is AdmissionFailure.INSUFFICIENT_HOST_MEMORY
    assert len(manager.list_active_reservations()) == 2


def test_accelerator_budget_is_not_pooled(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    capacity = _envelope(host=1000, accel=50)
    assert (
        manager.admit(
            _decision(plan="plan_a", token="a" * 32, accel=40, host=10),
            capacity,
            PlanFailure.NONE,
        ).outcome
        is AdmissionOutcome.ADMITTED
    )
    refused = manager.admit(
        _decision(plan="plan_b", token="b" * 32, accel=20, host=10),
        capacity,
        PlanFailure.NONE,
    )
    assert refused.failure is AdmissionFailure.INSUFFICIENT_ACCELERATOR_CAPACITY


def test_host_memory_is_distinct_from_accelerator_memory(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    refused = manager.admit(
        _decision(host=60, accel=10),
        _envelope(host=50, accel=1000, physical=10_000),
        PlanFailure.NONE,
    )
    assert refused.failure is AdmissionFailure.INSUFFICIENT_HOST_MEMORY
    assert not manager.list_active_reservations()


def test_storage_dimensions_are_checked_separately(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    persistent = manager.admit(
        _decision(persistent=60, transient=0, host=10, accel=10),
        _envelope(storage=50, host=100, accel=100),
        PlanFailure.NONE,
    )
    assert persistent.failure is AdmissionFailure.INSUFFICIENT_PERSISTENT_STORAGE
    transient = manager.admit(
        _decision(
            plan="plan_t",
            token="t" * 32,
            persistent=10,
            transient=50,
            host=10,
            accel=10,
        ),
        _envelope(storage=50, host=100, accel=100),
        PlanFailure.NONE,
    )
    assert transient.failure is AdmissionFailure.INSUFFICIENT_TRANSIENT_STORAGE


def test_release_is_idempotent_and_frees_capacity(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    capacity = _envelope(host=100, accel=100)
    admitted = manager.admit(_decision(host=80, accel=80), capacity, PlanFailure.NONE)
    reservation = admitted.reservation
    assert is_resolved(reservation)
    first = manager.release(reservation.reservation_id)
    second = manager.release(reservation.reservation_id)
    assert first.outcome is AdmissionOutcome.RELEASED
    assert second.outcome is AdmissionOutcome.RELEASED
    released = manager.get_reservation(reservation.reservation_id)
    assert released is not None
    assert released.state is ReservationState.RELEASED
    assert manager.list_active_reservations() == ()
    nxt = manager.admit(
        _decision(plan="plan_b", token="b" * 32, host=80, accel=80),
        capacity,
        PlanFailure.NONE,
    )
    assert nxt.outcome is AdmissionOutcome.ADMITTED
    assert not manager.execution_authorized(
        reservation.reservation_id, _configuration(_decision())
    )


def test_stale_plan_and_mismatch_consume_nothing(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    stale = manager.admit(_decision(), _envelope(), PlanFailure.STALE_MODEL_INPUT)
    assert stale.failure is AdmissionFailure.STALE_PLAN
    assert "stale_model_input" in stale.reason
    other = _envelope(evidence="cev_other")
    changed = manager.admit(_decision(evidence="cev_admit"), other, PlanFailure.NONE)
    assert changed.failure is AdmissionFailure.STALE_CAPACITY_INPUT
    mixed = _decision()
    current = mixed.request
    assert is_resolved(current)
    mixed = replace(
        mixed,
        request=replace(current, plan_id="plan_other", fingerprint="b" * 32),
    )
    assert manager.admit(mixed, _envelope(), PlanFailure.NONE).failure is (
        AdmissionFailure.PLAN_REQUEST_MISMATCH
    )
    assert manager.list_active_reservations() == ()


def test_missing_accelerator_is_not_replaced(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    refused = manager.admit(
        _decision(device="accel_missing"),
        _envelope(device="accel_0"),
        PlanFailure.NONE,
    )
    assert refused.failure is AdmissionFailure.ACCELERATOR_NOT_PRESENT
    assert manager.list_active_reservations() == ()


def test_unresolved_safe_bytes_are_not_zero(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    refused = manager.admit(_decision(), _envelope(host=NOT_PROVIDED), PlanFailure.NONE)
    assert refused.failure is AdmissionFailure.CAPACITY_UNRESOLVED


def test_shrink_is_reported_and_blocks_new_admission(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    admitted = manager.admit(
        _decision(host=40, accel=40), _envelope(host=100, accel=100), PlanFailure.NONE
    )
    shrunk = _envelope(host=30, accel=100)
    report = manager.reconcile(shrunk)
    assert report.status is ReconciliationStatus.OVERCOMMITTED
    assert "host_memory" in report.overcommitted
    assert len(manager.list_active_reservations()) == 1
    blocked = manager.admit(
        _decision(plan="plan_b", token="b" * 32, host=1, accel=1),
        shrunk,
        PlanFailure.NONE,
    )
    assert blocked.failure is AdmissionFailure.CURRENT_CAPACITY_OVERCOMMITTED
    assert (
        _reservation(admitted).reservation_id
        == manager.list_active_reservations()[0].reservation_id
    )


def test_recreation_keeps_the_hold(tmp_path: Path) -> None:
    first = _manager(tmp_path)
    admitted = first.admit(_decision(host=80), _envelope(host=100), PlanFailure.NONE)
    second = _manager(tmp_path)
    assert len(second.list_active_reservations()) == 1
    repeat = second.admit(_decision(host=80), _envelope(host=100), PlanFailure.NONE)
    assert _reservation(repeat).reservation_id == _reservation(admitted).reservation_id
    conflict = second.admit(
        _decision(plan="plan_b", token="b" * 32, host=30),
        _envelope(host=100),
        PlanFailure.NONE,
    )
    assert conflict.failure is AdmissionFailure.INSUFFICIENT_HOST_MEMORY


def test_concurrent_admits_cannot_oversubscribe(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    capacity = _envelope(host=100, accel=1000)
    barrier = threading.Barrier(2)
    results: list[AdmissionFailure] = []

    def worker(plan: str, token: str) -> None:
        barrier.wait()
        outcome = manager.admit(
            _decision(plan=plan, token=token, host=60, accel=10),
            capacity,
            PlanFailure.NONE,
        )
        results.append(outcome.failure)

    threads = [
        threading.Thread(target=worker, args=("plan_a", "a" * 32)),
        threading.Thread(target=worker, args=("plan_b", "b" * 32)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(AdmissionFailure.NONE) == 1
    assert (
        sum(item.host_memory_bytes for item in manager.list_active_reservations()) == 60
    )


def test_malformed_record_is_reported_not_repaired(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.admit(_decision(), _envelope(), PlanFailure.NONE)
    kind = tmp_path / "admit.reservation"
    (kind / "broken.json").write_text("{", encoding="utf-8")
    report = manager.reconcile(_envelope())
    assert report.malformed_count == 1
    assert report.status is ReconciliationStatus.DEGRADED
    assert len(manager.list_active_reservations()) == 1


def test_store_conflict_refuses_without_consuming_capacity() -> None:
    class _ConflictLog:
        def create(self, key: str, record: Contract) -> tuple[Contract, bool]:
            raise ConflictError("stored record already exists and does not match")

        def reservations(self) -> tuple[tuple[ResourceReservation, ...], int]:
            return (), 0

        def releases(self) -> tuple[ReservationRelease, ...]:
            return ()

    decision = ResourceManager(_ConflictLog()).admit(
        _decision(),
        _envelope(),
        PlanFailure.NONE,
    )
    assert decision.failure is AdmissionFailure.RESERVATION_CONFLICT
    assert not is_resolved(decision.reservation)


def test_inspect_prints_a_hold_without_serving(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manager = _manager(tmp_path)
    admitted = manager.admit(_decision(), _envelope(), PlanFailure.NONE)
    reservation = _reservation(admitted)
    assert main(["admit", "inspect", "--store-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert reservation.reservation_id in out
    assert "state    reserved" in out
    assert "plan     plan_a" in out
    assert "device   accel_0" in out
    assert "reconcile capacity_required" in out
    assert "api_server" not in out
    assert main(["admit", "policy"]) == 0
