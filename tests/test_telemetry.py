"""Phase 0 local telemetry: schema, privacy, append-only history, isolation."""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.telemetry.sqlite import SQLiteTelemetryStore
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.schema import Contract
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.main import build, config_schema, main
from kultrun.platform.requirement import RequirementAssessment, RequirementStatus
from kultrun.platform.telemetry_observe import (
    host_observation,
    model_sizing_observation,
    runtime_memory_observation,
)
from kultrun.resource.contracts import LedgerHealth, ResourceSummary
from kultrun.runtime.contracts import (
    RuntimeMemoryProfile,
    RuntimeMemoryProfileId,
    RuntimeMemoryProfileStatus,
)
from kultrun.telemetry.contracts import (
    CapacitySnapshotObservation,
    DeploymentEventObservation,
    DeploymentEventType,
    DeploymentRunKind,
    DeploymentRunObservation,
    HostObservation,
    ModelSizingObservation,
    ObservationId,
    RuntimeMemoryObservation,
    RuntimeObservation,
    TelemetryEventId,
    TelemetryRunId,
    TelemetrySettings,
    TelemetryStatus,
)
from kultrun.telemetry.privacy import forbidden_field_names
from kultrun.telemetry.service import BestEffortRecorder, resolve_database_path

INSTANT = dt.datetime(2026, 9, 9, 11, 0, tzinfo=dt.UTC)
GIB = 1024**3
STATIC_REQUIREMENT = 11_134_701_404  # ~10.37 GiB
MODEL_LOAD = 10_071_244_472  # ~9.38 GiB
AVAILABLE_KV = -2_555_731_149  # ~-2.38 GiB
DERIVED_NON_KV = STATIC_REQUIREMENT - AVAILABLE_KV  # ~12.75 GiB


def _clock() -> FixedClock:
    return FixedClock(INSTANT)


def _open(tmp_path: Path) -> SQLiteTelemetryStore:
    path = tmp_path / "telemetry" / "kultrun-telemetry.sqlite3"
    return SQLiteTelemetryStore.open(path, _clock())


def _host_row(model_id: str = "qwen2.5-14b-instruct-awq") -> HostObservation:
    from kultrun.host.contracts import (
        Accelerator,
        AcceleratorVendor,
        Architecture,
        CpuFacts,
        ExecutionCapabilities,
        HostCapabilities,
        MemoryFacts,
        NetworkFacts,
        OperatingEnvironment,
    )

    host = HostCapabilities(
        host_id=HostId.generate(),
        fingerprint="fp-test",
        detected_at=INSTANT,
        operating_environment=OperatingEnvironment(
            os_name="linux",
            os_version="24.04",
            architecture=Architecture.X86_64,
            kernel_version=NOT_PROVIDED,
            virtualized=False,
        ),
        cpu=CpuFacts(
            vendor="AuthenticAMD",
            model_name="Test CPU",
            physical_cores=32,
            logical_cores=64,
        ),
        memory=MemoryFacts(
            total_bytes=64 * GIB,
            available_bytes=48 * GIB,
            unified_with_accelerator=False,
            limit_bytes=NOT_PROVIDED,
        ),
        execution=ExecutionCapabilities(
            native_process=True, docker=NOT_PROVIDED, podman=NOT_PROVIDED
        ),
        network=NetworkFacts(
            hostname=NOT_PROVIDED, loopback_address=NOT_PROVIDED, occupied_ports=()
        ),
        accelerators=(
            Accelerator(
                index=0,
                vendor=AcceleratorVendor.NVIDIA,
                model_name="RTX PRO 4500",
                memory_total_bytes=32 * GIB,
                driver_version="580.82.07",
                unified_memory=False,
            ),
        ),
    )
    del model_id
    return host_observation(
        host, observed_at=INSTANT, producer_build_version="0.1.0+test"
    )


def _sizing(model_id: str, estimated: int) -> ModelSizingObservation:
    assessment = RequirementAssessment(
        model_id=model_id,
        logical_name=model_id,
        requirement_status=RequirementStatus.READY,
        eligibility_status="eligible",
        runtime="vllm",
        runtime_version="0.28.0",
        profile_id="rcap_test",
        view_id="emv_test",
        view_status="current",
        selection_mode="auto",
        selected_candidate_id=None,
        requirement=None,
        basis="basis",
        reasons=(),
        capacity_assessed=True,
        capacity_fit="feasible",
        capacity_verdict="feasible",
        required_ram_bytes=8 * GIB,
        required_vram_bytes=estimated,
        safe_ram_bytes=64 * GIB,
        safe_vram_bytes=32 * GIB,
        source_ref="Qwen/Qwen2.5-14B-Instruct-AWQ",
        source_revision="rev1",
        evaluation=None,
        snapshot_basis="snap-1",
    )
    row = model_sizing_observation(assessment, observed_at=INSTANT)
    return ModelSizingObservation(
        observation_id=row.observation_id,
        observed_at=row.observed_at,
        model_id=model_id,
        source_model_ref=row.source_model_ref,
        revision=row.revision,
        runtime="vllm",
        runtime_version="0.28.0",
        factual_weight_bytes=5_570_747_392,
        estimator_mode="auto",
        estimator_provider="llmfit",
        estimator_version="1.1.14",
        estimated_minimum_vram_bytes=4_745_308_256,
        estimated_recommended_vram_bytes=7_623_046_144,
        estimated_kv_bytes=469_762_048,
        estimated_runtime_overhead_bytes=1_073_741_824,
        estimated_final_requirement_bytes=estimated,
        required_ram_bytes=8 * GIB,
        confidence="medium",
        deep_feasibility_result="feasible",
        capacity_basis="snap-1",
    )


def _t3_profile() -> RuntimeMemoryObservation:
    profile = RuntimeMemoryProfile(
        profile_id=RuntimeMemoryProfileId.generate(),
        status=RuntimeMemoryProfileStatus.FAILED,
        basis_fingerprint="exec-basis",
        class_key="v1|vllm|0.28.0|native-process|ok|blackwell|qwen2|awq|8192|1",
        source_model_id="qwen2.5-14b-instruct-awq",
        runtime="vllm",
        host_id=HostId.generate(),
        host_fingerprint="fp-t3",
        measured_at=INSTANT,
        confidence=Confidence.UNKNOWN,
        probe_budget_bytes=STATIC_REQUIREMENT,
        vllm_model_load_bytes=MODEL_LOAD,
        vllm_available_kv_bytes=AVAILABLE_KV,
        derived_non_kv_bytes=DERIVED_NON_KV,
        static_requirement_bytes=STATIC_REQUIREMENT,
        static_weight_component=5_570_747_392,
        static_kv_component=469_762_048,
        failure_reason="calibrated_insufficient_vram",
    )
    return runtime_memory_observation(
        profile,
        gpu_model="RTX PRO 4500",
        gpu_architecture="blackwell",
        calibrated_required_vram_bytes=DERIVED_NON_KV,
        measurement_quality="negative_available_kv",
    )


class _Boom:
    def record_host_observation(self, observation: HostObservation) -> None:
        raise OSError("disk full")

    def record_runtime_observation(self, observation: RuntimeObservation) -> None:
        raise OSError("disk full")

    def record_capacity_snapshot(self, snapshot: CapacitySnapshotObservation) -> None:
        raise OSError("disk full")

    def record_model_sizing(self, observation: ModelSizingObservation) -> None:
        raise OSError("disk full")

    def record_runtime_memory_profile(
        self, observation: RuntimeMemoryObservation
    ) -> None:
        raise OSError("disk full")

    def start_deployment_run(self, run: DeploymentRunObservation) -> None:
        raise OSError("disk full")

    def record_deployment_event(self, event: DeploymentEventObservation) -> None:
        raise OSError("disk full")

    def finish_deployment_run(self, run: DeploymentRunObservation) -> None:
        raise OSError("disk full")

    def status(self) -> TelemetryStatus:
        raise OSError("disk full")


def test_default_path_is_under_state_root(tmp_path: Path) -> None:
    settings = TelemetrySettings()
    path = resolve_database_path(tmp_path / "state", settings)
    assert path == tmp_path / "state" / "telemetry" / "kultrun-telemetry.sqlite3"


def test_migration_sql_is_package_data() -> None:
    from importlib.resources import files

    sql = (
        files("kultrun.telemetry")
        .joinpath("migrations", "001_initial.sql")
        .read_text(encoding="utf-8")
    )
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
    assert "CREATE TABLE IF NOT EXISTS host_observation" in sql


def test_database_is_created_under_state_root(tmp_path: Path) -> None:
    store = _open(tmp_path)
    expected = tmp_path / "telemetry" / "kultrun-telemetry.sqlite3"
    assert store.path == expected
    assert expected.is_file()
    status = store.status()
    assert status.applied_version == 1
    store.close()


def test_migration_is_idempotent_and_preserves_rows(tmp_path: Path) -> None:
    first = _open(tmp_path)
    first.record_host_observation(_host_row())
    assert first.status().host_observations == 1
    first.close()
    second = _open(tmp_path)
    assert second.status().applied_version == 1
    assert second.status().host_observations == 1
    versions = second._connection.execute(
        "SELECT version FROM schema_migrations"
    ).fetchall()
    assert [row[0] for row in versions] == [1]
    second.close()


def test_sizing_is_append_only_for_the_same_model(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.record_model_sizing(_sizing("qwen2.5-14b-instruct-awq", STATIC_REQUIREMENT))
    store.record_model_sizing(_sizing("qwen2.5-14b-instruct-awq", DERIVED_NON_KV))
    assert store.status().model_sizing_observations == 2
    rows = store._connection.execute(
        "SELECT estimated_final_requirement_bytes FROM model_sizing_observation"
        " ORDER BY observation_id"
    ).fetchall()
    values = {row[0] for row in rows}
    assert values == {STATIC_REQUIREMENT, DERIVED_NON_KV}
    store.close()


def test_telemetry_contracts_are_metadata_only() -> None:
    offenders: list[str] = []
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
        assert issubclass(item, Contract)
        found = forbidden_field_names(item)
        offenders.extend(f"{item.__name__}.{name}" for name in found)
    assert offenders == []


def test_host_observation_copies_discovery_facts(tmp_path: Path) -> None:
    store = _open(tmp_path)
    row = _host_row()
    store.record_host_observation(row)
    loaded = store._connection.execute(
        "SELECT os_name, gpu_model, gpu_total_bytes, ram_total_bytes"
        " FROM host_observation"
    ).fetchone()
    assert loaded[0] == "linux"
    assert loaded[1] == "RTX PRO 4500"
    assert loaded[2] == 32 * GIB
    assert loaded[3] == 64 * GIB
    store.close()


def test_capacity_snapshot_does_not_recalculate(tmp_path: Path) -> None:
    store = _open(tmp_path)
    snapshot = ResourceSummary(
        host_id=HostId.generate(),
        host_fingerprint="fp-cap",
        health=LedgerHealth.WITHIN_CAPACITY,
        policy_version="capacity.v1",
        capacity_policy_version="capacity.v1",
        safe_ram_bytes=48 * GIB,
        reserved_ram_bytes=2 * GIB,
        available_ram_bytes=46 * GIB,
        snapshot_basis="snap-auth",
        active_count=1,
        observed_at=INSTANT,
        available_storage_bytes=200 * GIB,
    )
    from kultrun.platform.telemetry_observe import capacity_snapshot_observation

    copied = capacity_snapshot_observation(snapshot, observed_at=INSTANT)
    store.record_capacity_snapshot(copied)
    loaded = store._connection.execute(
        "SELECT safe_ram_bytes, committed_ram_bytes, available_ram_bytes,"
        " basis_fingerprint FROM capacity_snapshot"
    ).fetchone()
    assert loaded[0] == 48 * GIB
    assert loaded[1] == 2 * GIB
    assert loaded[2] == 46 * GIB
    assert loaded[3] == "snap-auth"
    store.close()


def test_sizing_keeps_factual_and_estimated_apart(tmp_path: Path) -> None:
    store = _open(tmp_path)
    store.record_model_sizing(_sizing("qwen2.5-14b-instruct-awq", STATIC_REQUIREMENT))
    loaded = store._connection.execute(
        "SELECT factual_weight_bytes, estimated_minimum_vram_bytes,"
        " estimated_kv_bytes, estimated_final_requirement_bytes"
        " FROM model_sizing_observation"
    ).fetchone()
    assert loaded[0] == 5_570_747_392
    assert loaded[1] == 4_745_308_256
    assert loaded[2] == 469_762_048
    assert loaded[3] == STATIC_REQUIREMENT
    assert loaded[0] != loaded[3]
    store.close()


def test_runtime_memory_persists_the_t3_failure_shape(tmp_path: Path) -> None:
    store = _open(tmp_path)
    row = _t3_profile()
    store.record_runtime_memory_profile(row)
    loaded = store._connection.execute(
        "SELECT estimated_static_requirement_bytes, measured_model_load_bytes,"
        " measured_available_kv_bytes, derived_non_kv_bytes,"
        " calibrated_required_vram_bytes, profile_status, failure_reason"
        " FROM runtime_memory_profile"
    ).fetchone()
    assert loaded[0] == STATIC_REQUIREMENT
    assert loaded[1] == MODEL_LOAD
    assert loaded[2] == AVAILABLE_KV
    assert loaded[2] < 0
    assert loaded[3] == DERIVED_NON_KV
    assert loaded[4] is not None
    assert loaded[4] > STATIC_REQUIREMENT
    assert loaded[5] == "failed"
    assert loaded[6] == "calibrated_insufficient_vram"
    store.close()


def test_deployment_run_and_events_persist(tmp_path: Path) -> None:
    store = _open(tmp_path)
    run_id = TelemetryRunId.generate()
    store.start_deployment_run(
        DeploymentRunObservation(
            deployment_run_id=run_id,
            started_at=INSTANT,
            run_kind=DeploymentRunKind.DEPLOYMENT,
            host_id=HostId.generate(),
            selected_model="qwen2.5-14b-instruct-awq",
            runtime="vllm",
            state="started",
        )
    )
    store.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=INSTANT,
            event_type=DeploymentEventType.RUNTIME_LAUNCH_STARTED,
            correlation_id=run_id.value,
            status="started",
        )
    )
    store.finish_deployment_run(
        DeploymentRunObservation(
            deployment_run_id=run_id,
            started_at=INSTANT,
            ended_at=INSTANT,
            duration_ms=1200,
            state="failed",
            failure_reason_code="readiness_timeout",
        )
    )
    status = store.status()
    assert status.deployment_runs == 1
    assert status.deployment_events == 1
    ended = store._connection.execute(
        "SELECT state, duration_ms, failure_reason_code FROM deployment_run"
    ).fetchone()
    assert ended[0] == "failed"
    assert ended[1] == 1200
    assert ended[2] == "readiness_timeout"
    store.close()


def test_sqlite_failure_does_not_corrupt_the_domain_fact() -> None:
    host_id = HostId.generate()
    recorder = BestEffortRecorder(_Boom())
    observation = HostObservation(
        observation_id=ObservationId.generate(),
        observed_at=INSTANT,
        host_id=host_id,
        host_fingerprint="fp",
    )
    recorder.record_host_observation(observation)
    assert recorder.last_error is not None
    assert "disk full" in recorder.last_error
    assert host_id.value.startswith("host_")
    assert recorder.status().last_error is not None


def test_product_startup_writes_local_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "state"
    configuration = config_schema().load({"platform": {"state_root": str(root)}})
    platform = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
    database = root / "telemetry" / "kultrun-telemetry.sqlite3"
    assert database.is_file()
    status = platform.telemetry.status()
    assert status.enabled is True
    assert status.applied_version == 1
    assert status.host_observations >= 1
    assert status.capacity_snapshots >= 1
    from kultrun.main import _funnel

    _funnel(platform, persist=True)
    after = platform.telemetry.status()
    assert after.model_sizing_observations >= 1
    assert after.deployment_events >= 1
    connection = sqlite3.connect(database)
    print("DB path", database)
    print("schema version", after.applied_version)
    for table in (
        "host_observation",
        "runtime_observation",
        "capacity_snapshot",
        "model_sizing_observation",
        "runtime_memory_profile",
        "deployment_run",
        "deployment_event",
    ):
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table} {count}")
        row = connection.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
        print(f"latest {table}", row)
    connection.close()
    captured = capsys.readouterr()
    assert "host_observation" in captured.out


def test_cli_telemetry_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
    monkeypatch.setenv("KULTRUN_RUNTIME_PROVISIONER", "fixture")
    monkeypatch.setenv("KULTRUN_RUNTIME_VERIFIER", "fixture")
    assert main(["telemetry", "status"]) == 0
    printed = capsys.readouterr().out
    assert "Enabled: true" in printed
    assert "kultrun-telemetry.sqlite3" in printed
    assert "Schema version: 1" in printed
    assert "Host observations:" in printed
