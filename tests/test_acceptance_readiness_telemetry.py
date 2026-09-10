"""Acceptance: Stream A readiness remains correct with Stream B telemetry."""

from __future__ import annotations

import inspect
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.telemetry.sqlite import SQLiteTelemetryStore
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostCapabilities
from kultrun.inference.contracts import InferenceInstance, ObservedState
from kultrun.inference.service import InstanceService
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import (
    _deployment_overview,
    _funnel,
    _model_overview,
    build,
    config_schema,
)
from kultrun.platform.deployment_instance import InstanceView
from kultrun.platform.telemetry_observe import bind_deployment_instance
from kultrun.resource.contracts import ReservationState, WorkloadType
from kultrun.telemetry.privacy import FORBIDDEN_FIELD_TOKENS, forbidden_field_names
from kultrun.telemetry.service import BestEffortRecorder, DisabledRecorder
from tests.test_contracts import host_capabilities
from tests.test_inference_instance import SMALL, _Stack
from tests.test_inference_start_readiness import _other_control_plane
from tests.test_runtime_vllm_inference import _complete_request, _vllm_stack
from tests.test_telemetry import _Boom


def _sqlite(
    tmp_path: Path, clock: Clock
) -> tuple[SQLiteTelemetryStore, BestEffortRecorder]:
    store = SQLiteTelemetryStore.open(
        tmp_path / "telemetry" / "kultrun-telemetry.sqlite3", clock
    )
    return store, BestEffortRecorder(store)


def _bind_start(
    stack: _Stack, tmp_path: Path, recorder: object
) -> object:
    class _Facade:
        def start(
            self,
            instance_id: object,
            host: HostCapabilities,
            *,
            ledger_health: object,
            serving_mode: str = "healthy",
        ) -> InstanceView:
            del host
            found = stack.instances.get(instance_id)  # type: ignore[arg-type]
            assert found is not None
            started = stack.instances.start(
                instance_id,  # type: ignore[arg-type]
                ledger_health=ledger_health,  # type: ignore[arg-type]
                serving_mode=serving_mode,
                launch_request=_complete_request(tmp_path, found),
            )
            return InstanceView(started, "current")

        def stop(self, instance_id: object, host: HostCapabilities) -> InstanceView:
            del host
            return InstanceView(
                stack.instances.stop(instance_id),  # type: ignore[arg-type]
                "current",
            )

    return bind_deployment_instance(_Facade(), recorder, stack.clock)  # type: ignore[arg-type]


def test_observe_persist_defaults_and_readiness_uses_false() -> None:
    signature = inspect.signature(ExecutionService.observe)
    assert signature.parameters["persist"].default is True
    wait_ready = inspect.getsource(InstanceService)
    assert "observe(execution_id, persist=False)" in wait_ready


def test_delayed_ready_with_sqlite_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=0.6, timeout=3.0
    )
    sqlite, recorder = _sqlite(tmp_path, stack.clock)
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    puts = {"execution.handle": 0}
    original = stack.store.put

    def counted(key: str, record: object) -> None:
        kind = getattr(record, "kind", "")
        if kind == "execution.handle":
            puts["execution.handle"] += 1
        original(key, record)

    stack.store.put = counted  # type: ignore[method-assign]
    try:
        view = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        assert view.instance.observed_state is ObservedState.RUNNING
        assert is_resolved(view.instance.pid)
        assert puts["execution.handle"] == 1
        status = recorder.status()
        assert status.deployment_runs >= 1
        assert status.deployment_events >= 1
        assert recorder.last_error is None
    finally:
        stack.instances.stop(instance.instance_id)
        sqlite.close()


def test_high_log_with_sqlite_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, delay=0.0, log_bytes=2 * 1024 * 1024, timeout=5.0
    )
    sqlite, recorder = _sqlite(tmp_path, stack.clock)
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        view = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        assert view.instance.observed_state is ObservedState.RUNNING
        assert recorder.last_error is None
    finally:
        stack.instances.stop(instance.instance_id)
        sqlite.close()


def test_never_ready_with_sqlite_persists_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=30.0, timeout=0.4
    )
    sqlite, recorder = _sqlite(tmp_path, stack.clock)
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    started_at = time.monotonic()
    view = bound.start(  # type: ignore[union-attr]
        instance.instance_id,
        host_capabilities(),
        ledger_health=stack.health(),
    )
    assert time.monotonic() - started_at < 2.5
    assert view.instance.observed_state is ObservedState.FAILED
    held = stack.resources.get(reservation.reservation_id)
    assert held is not None
    assert held.state is ReservationState.ACTIVE
    sqlite.close()


def test_telemetry_disk_full_does_not_block_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=0.5, timeout=3.0
    )
    recorder = BestEffortRecorder(_Boom())
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        view = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        assert view.instance.observed_state is ObservedState.RUNNING
        assert recorder.last_error is not None
        assert "disk full" in recorder.last_error
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
    finally:
        stack.instances.stop(instance.instance_id)


def test_inspect_during_starting_with_telemetry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=0.8, timeout=4.0
    )
    sqlite, recorder = _sqlite(tmp_path, stack.clock)
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    seen: list[ObservedState] = []

    def inspect_while_starting() -> None:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            recorded = stack.store.get(InferenceInstance, instance.instance_id.value)
            if (
                recorded is not None
                and recorded.observed_state is ObservedState.STARTING
            ):
                other = _other_control_plane(stack)
                seen.append(other.observe(instance.instance_id).observed_state)
                return
            time.sleep(0.02)

    watcher = threading.Thread(target=inspect_while_starting)
    watcher.start()
    try:
        view = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        watcher.join(timeout=3.0)
        assert view.instance.observed_state is ObservedState.RUNNING
        assert seen == [ObservedState.STARTING]
        other = _other_control_plane(stack)
        lost = other.observe(instance.instance_id)
        assert lost.observed_state is ObservedState.UNKNOWN
        owned = stack.instances.observe(instance.instance_id)
        assert owned.observed_state is ObservedState.RUNNING
    finally:
        watcher.join(timeout=1.0)
        stack.instances.stop(instance.instance_id)
        sqlite.close()


def test_long_run_with_sqlite_stop_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = _vllm_stack(
        tmp_path, monkeypatch, mode="delayed", delay=2.0, timeout=8.0
    )
    sqlite, recorder = _sqlite(tmp_path, stack.clock)
    bound = _bind_start(stack, tmp_path, recorder)
    artifact = stack.stored()
    reservation = stack.reserve(artifact, vram=SMALL)
    instance = stack.instances.create(artifact, reservation, runtime=Name("vllm"))
    try:
        started = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        assert started.instance.observed_state is ObservedState.RUNNING
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            current = stack.instances.observe(started.instance.instance_id)
            assert current.observed_state is ObservedState.RUNNING
            time.sleep(2.0)
        stopped = bound.stop(started.instance.instance_id, host_capabilities())  # type: ignore[union-attr]
        assert stopped.instance.observed_state is ObservedState.STOPPED
        held = stack.resources.get(reservation.reservation_id)
        assert held is not None
        assert held.state is ReservationState.ACTIVE
        restarted = bound.start(  # type: ignore[union-attr]
            instance.instance_id,
            host_capabilities(),
            ledger_health=stack.health(),
        )
        assert restarted.instance.observed_state is ObservedState.RUNNING
        bound.stop(restarted.instance.instance_id, host_capabilities())  # type: ignore[union-attr]
    finally:
        stack.instances.stop(instance.instance_id)
        sqlite.close()


def _platform(tmp_path: Path, *, enabled: bool) -> object:
    configuration = config_schema().load(
        {
            "platform": {"state_root": str(tmp_path / "state")},
            "telemetry": {"enabled": enabled},
        }
    )
    return build(
        configuration,
        fixture=fixtures.DEFAULT_SHAPE,
        acquisition_adapter="fixture",
    )


def _funnel_key(platform: object) -> tuple[object, ...]:
    result = _funnel(platform, persist=True)
    host = platform.hosts.current  # type: ignore[attr-defined]
    overview = _deployment_overview(platform, persist=False)
    selection = _model_overview(platform)
    members = tuple(
        sorted(
            (
                item.model_id,
                item.required_vram_bytes,
                item.validation_status,
            )
            for item in result.available.members
        )
    )
    feasible = tuple(sorted(item.model_id for item in result.estimated_feasible))
    plan = overview.plan
    selected = selection.selection.selected_model_id
    selected_id = selected if is_resolved(selected) else None
    return (
        host.fingerprint,
        result.available.available_count,
        result.available.estimated_feasible_count,
        members,
        feasible,
        None if plan is None else plan.model_id.value,
        None if plan is None else plan.expected_vram_bytes,
        selected_id,
    )


def test_funnel_equivalent_with_and_without_telemetry(tmp_path: Path) -> None:
    disabled = _platform(tmp_path / "noop", enabled=False)
    sqlite = _platform(tmp_path / "sqlite", enabled=True)
    assert isinstance(disabled.telemetry, DisabledRecorder)  # type: ignore[attr-defined]
    left = _funnel_key(disabled)
    right = _funnel_key(sqlite)
    assert left == right
    database = tmp_path / "sqlite" / "state" / "telemetry" / "kultrun-telemetry.sqlite3"
    assert database.is_file()


def test_sqlite_schema_and_integrity_have_no_customer_content(
    tmp_path: Path,
) -> None:
    from kultrun.telemetry.contracts import (
        CapacitySnapshotObservation,
        DeploymentEventObservation,
        DeploymentRunObservation,
        HostObservation,
        ModelSizingObservation,
        RuntimeMemoryObservation,
        RuntimeObservation,
        TelemetrySettings,
    )

    for item in (
        HostObservation,
        RuntimeObservation,
        CapacitySnapshotObservation,
        ModelSizingObservation,
        RuntimeMemoryObservation,
        DeploymentRunObservation,
        DeploymentEventObservation,
        TelemetrySettings,
    ):
        assert forbidden_field_names(item) == ()
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "fresh")}}
    )
    platform = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
    _funnel(platform, persist=True)
    database = tmp_path / "fresh" / "telemetry" / "kultrun-telemetry.sqlite3"
    assert database.is_file()
    connection = sqlite3.connect(database)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        assert integrity == ("ok",)
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()
        assert version == (1,)
        offenders: list[str] = []
        for (table,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ):
            for row in connection.execute(f"PRAGMA table_info({table})"):
                name = str(row[1]).lower()
                if name in FORBIDDEN_FIELD_TOKENS:
                    offenders.append(f"{table}.{row[1]}")
                    continue
                for token in FORBIDDEN_FIELD_TOKENS:
                    if token in name.split("_"):
                        offenders.append(f"{table}.{row[1]}")
                        break
        assert offenders == []
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "host_observation",
                "runtime_observation",
                "capacity_snapshot",
                "model_sizing_observation",
                "runtime_memory_profile",
                "deployment_run",
                "deployment_event",
            )
        }
        assert counts["host_observation"] >= 1
        assert counts["capacity_snapshot"] >= 1
        assert counts["model_sizing_observation"] >= 1
        print("FRESH SQLITE COUNTS", counts)
    finally:
        connection.close()


def test_evaluation_probe_workload_is_not_inference() -> None:
    assert WorkloadType.EVALUATION.value == "evaluation"
    assert WorkloadType.INFERENCE.value == "inference"
    assert WorkloadType.EVALUATION is not WorkloadType.INFERENCE
