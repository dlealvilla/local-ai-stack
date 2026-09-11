"""Stage 1.6L — start returns while serving stays up.

Inspect must not clobber STARTING.
"""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path
from typing import TypeVar

import pytest

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.execution.contracts import ExecutionOwnership
from kultrun.execution.service import ExecutionService
from kultrun.inference.contracts import InferenceInstance, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import ReconciliationReport, Store
from kultrun.kernel.schema import Contract
from kultrun.kernel.unresolved import is_resolved
from kultrun.resource.contracts import ReservationState
from tests.test_inference_instance import SMALL, _Stack
from tests.test_runtime_vllm_inference import _complete_request, _vllm_stack

_RecordT = TypeVar("_RecordT", bound=Contract)


class _HangOnHandlePut:
    """Store wrapper: later execution.handle writes block until released."""

    def __init__(self, inner: Store, *, hang_after: int) -> None:
        self._inner = inner
        self._hang_after = hang_after
        self._handle_puts = 0
        self.blocked = threading.Event()
        self.release = threading.Event()

    def put(self, key: str, record: Contract) -> None:
        if record.kind == "execution.handle":
            self._handle_puts += 1
            if self._handle_puts > self._hang_after:
                self.blocked.set()
                self.release.wait(timeout=30)
                return
        self._inner.put(key, record)

    def get(self, contract_type: type[_RecordT], key: str) -> _RecordT | None:
        return self._inner.get(contract_type, key)

    def delete(self, contract_type: type[Contract], key: str) -> bool:
        return self._inner.delete(contract_type, key)

    def keys(self, contract_type: type[Contract]) -> tuple[str, ...]:
        return self._inner.keys(contract_type)

    def records(self, contract_type: type[_RecordT]) -> tuple[_RecordT, ...]:
        return self._inner.records(contract_type)

    def reconcile(self) -> ReconciliationReport:
        return self._inner.reconcile()


def _other_control_plane(stack: _Stack) -> InstanceService:
    return InstanceService(
        stack.store,
        stack.clock,
        stack.inventory,
        stack.resources,
        ExecutionService(NativeProcessExecutor(SystemClock()), stack.store),
        stack.runtimes,
        live_executor="native-process",
    )


def _start_vllm(
    stack: _Stack, tmp_path: Path, instance: InferenceInstance
) -> InferenceInstance:
    return stack.instances.start(
        instance.instance_id,
        ledger_health=stack.health(),
        launch_request=_complete_request(tmp_path, instance),
    )


def test_immediate_ready_returns_while_process_lives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, delay=0.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    try:
        started = _start_vllm(stack, tmp_path, instance)
        elapsed = time.monotonic() - started_at
        assert elapsed < 2.0
        assert started.observed_state is ObservedState.RUNNING
        assert started.ready is True
        assert is_resolved(started.pid)
        os.kill(started.pid, 0)
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
    finally:
        stack.instances.stop(instance.instance_id)


def test_delayed_ready_polls_then_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, mode="delayed", delay=0.6, timeout=3.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = _start_vllm(stack, tmp_path, instance)
        assert started.observed_state is ObservedState.RUNNING
        assert started.ready is True
    finally:
        stack.instances.stop(instance.instance_id)


def test_high_log_volume_does_not_deadlock_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, delay=0.0, log_bytes=2 * 1024 * 1024, timeout=5.0
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = _start_vllm(stack, tmp_path, instance)
        assert started.observed_state is ObservedState.RUNNING
        assert is_resolved(started.pid)
        os.kill(started.pid, 0)
    finally:
        stack.instances.stop(instance.instance_id)


def test_never_ready_timeout_persists_failure_and_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=30.0, timeout=0.4
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    failed = _start_vllm(stack, tmp_path, instance)
    elapsed = time.monotonic() - started_at
    assert elapsed < 2.5
    assert failed.observed_state is ObservedState.FAILED
    assert "timeout" in str(failed.failure_reason)
    stored = stack.store.get(InferenceInstance, instance.instance_id.value)
    assert stored is not None
    assert stored.observed_state is ObservedState.FAILED
    held = stack.resources.get(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE
    live = [
        item
        for item in stack.executions.list()
        if item.observed_state.value == "running"
        and item.ownership is ExecutionOwnership.OWNED
    ]
    assert live == []


def test_process_exit_before_ready_fails_without_waiting_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="exit-immediately", timeout=5.0
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    failed = _start_vllm(stack, tmp_path, instance)
    assert time.monotonic() - started_at < 2.0
    assert failed.observed_state is ObservedState.FAILED
    assert "exited" in str(failed.failure_reason)
    held = stack.resources.get(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE


def test_ready_then_process_dies_reconciles_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, delay=0.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = _start_vllm(stack, tmp_path, instance)
        assert is_resolved(started.pid)
        os.kill(started.pid, signal.SIGTERM)
        time.sleep(0.2)
        crashed = stack.instances.observe(started.instance_id)
        assert crashed.observed_state is ObservedState.FAILED
    finally:
        stack.instances.stop(instance.instance_id)


def test_handle_put_hang_does_not_block_ready_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, delay=0.0, timeout=2.0)
    hung = _HangOnHandlePut(stack.store, hang_after=1)
    executor = NativeProcessExecutor(SystemClock())
    executions = ExecutionService(executor, hung)
    stack.executions = executions
    stack.instances = InstanceService(
        hung,
        stack.clock,
        stack.inventory,
        stack.resources,
        executions,
        stack.runtimes,
        startup_timeout=2.0,
        live_executor="native-process",
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started_at = time.monotonic()
        started = _start_vllm(stack, tmp_path, instance)
        assert time.monotonic() - started_at < 2.0
        assert started.observed_state is ObservedState.RUNNING
        assert not hung.blocked.is_set()
    finally:
        hung.release.set()
        stack.instances.stop(instance.instance_id)


def test_inspect_during_starting_does_not_prevent_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=0.8, timeout=4.0
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    seen: list[ObservedState] = []

    def inspect_while_starting() -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
            starting = (
                recorded is not None
                and recorded.observed_state is ObservedState.STARTING
            )
            if starting:
                other = _other_control_plane(stack)
                seen.append(other.observe(instance.instance_id).observed_state)
                return
            time.sleep(0.02)

    watcher = threading.Thread(target=inspect_while_starting)
    watcher.start()
    try:
        started = _start_vllm(stack, tmp_path, instance)
        watcher.join(timeout=3.0)
        assert started.observed_state is ObservedState.RUNNING
        assert seen == [ObservedState.STARTING]
        persisted = stack.store.get(InferenceInstance, instance.instance_id.value)
        assert persisted is not None
        assert persisted.observed_state is ObservedState.RUNNING
    finally:
        watcher.join(timeout=1.0)
        stack.instances.stop(instance.instance_id)


def test_separate_process_inspect_after_running_reacquires_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, delay=0.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = _start_vllm(stack, tmp_path, instance)
        assert started.observed_state is ObservedState.RUNNING
        other = _other_control_plane(stack)
        seen = other.observe(started.instance_id)
        assert seen.observed_state is ObservedState.RUNNING
        owned = stack.instances.observe(started.instance_id)
        assert owned.observed_state is ObservedState.RUNNING
        assert other.blocks_release(reservation.reservation_id)
    finally:
        stack.instances.stop(instance.instance_id)


def test_idempotent_start_and_two_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, delay=0.0)
    first_art = stack.stored(name="one")
    second_art = stack.stored(name="two")
    first_res = stack.reserve(first_art, vram=SMALL)
    second_res = stack.reserve(second_art, vram=SMALL)
    first = stack.instances.create(first_art, first_res, runtime=Name("vllm"))
    second = stack.instances.create(second_art, second_res, runtime=Name("vllm"))
    try:
        running = _start_vllm(stack, tmp_path, first)
        again = _start_vllm(stack, tmp_path, first)
        assert again.pid == running.pid
        assert again.execution_id == running.execution_id
        other = _start_vllm(stack, tmp_path, second)
        assert other.instance_id != running.instance_id
        assert other.pid != running.pid
        assert other.observed_state is ObservedState.RUNNING
    finally:
        stack.instances.stop(first.instance_id)
        stack.instances.stop(second.instance_id)


def test_start_while_starting_does_not_launch_second_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=0.8, timeout=4.0
    )
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    first: list[InferenceInstance] = []

    def launch() -> None:
        first.append(_start_vllm(stack, tmp_path, instance))

    worker = threading.Thread(target=launch)
    worker.start()
    seen_starting = False
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
        if (
            recorded is not None
            and recorded.observed_state is ObservedState.STARTING
        ):
            seen_starting = True
            break
        time.sleep(0.02)
    try:
        assert seen_starting
        again = _start_vllm(stack, tmp_path, instance)
        worker.join(timeout=4.0)
        assert not worker.is_alive()
        assert first
        assert first[0].observed_state is ObservedState.RUNNING
        assert again.observed_state in {
            ObservedState.STARTING,
            ObservedState.RUNNING,
        }
        assert again.execution_id == first[0].execution_id
        live = [
            item
            for item in stack.executions.list()
            if item.observed_state.value == "running"
            and item.ownership is ExecutionOwnership.OWNED
        ]
        assert len(live) == 1
    finally:
        worker.join(timeout=1.0)
        stack.instances.stop(instance.instance_id)


def test_long_run_observe_stop_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(tmp_path, monkeypatch, mode="delayed", delay=2.0, timeout=8.0)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = _start_vllm(stack, tmp_path, instance)
        assert started.observed_state is ObservedState.RUNNING
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            current = stack.instances.observe(started.instance_id)
            assert current.observed_state is ObservedState.RUNNING
            time.sleep(2.0)
        other = _other_control_plane(stack)
        seen = other.observe(started.instance_id)
        assert seen.observed_state is ObservedState.RUNNING
        assert stack.instances.observe(started.instance_id).observed_state is (
            ObservedState.RUNNING
        )
        stopped = other.stop(started.instance_id)
        assert stopped.observed_state is ObservedState.STOPPED
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
        restarted = _start_vllm(stack, tmp_path, instance)
        assert restarted.observed_state is ObservedState.RUNNING
        assert restarted.reservation_id == reservation.reservation_id
        stack.instances.stop(restarted.instance_id)
    finally:
        stack.instances.stop(instance.instance_id)
