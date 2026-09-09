"""SQLite implementation of TelemetryRecorder.

Creates ``<state_root>/telemetry/kultrun-telemetry.sqlite3``, applies
versioned migrations, and inserts append-only rows. Domain services never
see this type.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path

from kultrun.kernel.clock import Clock, SystemClock
from kultrun.telemetry.contracts import (
    CapacitySnapshotObservation,
    DeploymentEventObservation,
    DeploymentRunObservation,
    HostObservation,
    ModelSizingObservation,
    RuntimeMemoryObservation,
    RuntimeObservation,
    TelemetryStatus,
)

_MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "initial operational metadata", "001_initial.sql"),
)


def _migration_sql(filename: str) -> str:
    """Read a shipped migration from package data, not the source tree."""
    return (
        files("kultrun.telemetry")
        .joinpath("migrations", filename)
        .read_text(encoding="utf-8")
    )


def _iso(value: object) -> str | None:
    if value is None:
        return None
    rendered = getattr(value, "isoformat", None)
    if callable(rendered):
        return str(rendered())
    return str(value)


def _ident(value: object) -> str | None:
    if value is None:
        return None
    token = getattr(value, "value", value)
    if token is None:
        return None
    return str(token)


def _enum(value: object) -> str | None:
    if value is None:
        return None
    token = getattr(value, "value", value)
    return str(token)


class SQLiteTelemetryStore:
    """File-backed local telemetry. Not a control-plane store."""

    def __init__(self, path: Path, clock: Clock | None = None) -> None:
        self._path = Path(path)
        self._clock = clock or SystemClock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row
        self._configure()
        self._migrate()

    @classmethod
    def open(cls, path: Path, clock: Clock | None = None) -> SQLiteTelemetryStore:
        """Create or reopen the database and apply missing migrations."""
        return cls(path, clock)

    @property
    def path(self) -> Path:
        """Resolved sqlite file."""
        return self._path

    def close(self) -> None:
        """Release the connection."""
        self._connection.close()

    def record_host_observation(self, observation: HostObservation) -> None:
        self._insert(
            """
            INSERT INTO host_observation (
                observation_id, observed_at, host_id, host_fingerprint,
                duration_ms, os_name, os_version, architecture, cpu_vendor,
                cpu_model, cpu_physical_cores, cpu_logical_cores,
                ram_total_bytes, ram_available_bytes, ram_limit_bytes,
                storage_mount_point, storage_total_bytes, storage_free_bytes,
                accelerator_count, gpu_index, gpu_vendor, gpu_model,
                gpu_architecture, gpu_total_bytes, driver_version,
                producer_build_version
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                observation.observation_id.value,
                _iso(observation.observed_at),
                observation.host_id.value,
                observation.host_fingerprint,
                observation.duration_ms,
                observation.os_name,
                observation.os_version,
                observation.architecture,
                observation.cpu_vendor,
                observation.cpu_model,
                observation.cpu_physical_cores,
                observation.cpu_logical_cores,
                observation.ram_total_bytes,
                observation.ram_available_bytes,
                observation.ram_limit_bytes,
                observation.storage_mount_point,
                observation.storage_total_bytes,
                observation.storage_free_bytes,
                observation.accelerator_count,
                observation.gpu_index,
                observation.gpu_vendor,
                observation.gpu_model,
                observation.gpu_architecture,
                observation.gpu_total_bytes,
                observation.driver_version,
                observation.producer_build_version,
            ),
        )

    def record_runtime_observation(self, observation: RuntimeObservation) -> None:
        self._insert(
            """
            INSERT INTO runtime_observation (
                observation_id, observed_at, host_id, host_fingerprint,
                duration_ms, foundation_id, selection_mode, runtime,
                runtime_version, executor, installation_id,
                capability_profile_id, verification_status, foundation_role
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                observation.observation_id.value,
                _iso(observation.observed_at),
                _ident(observation.host_id),
                observation.host_fingerprint,
                observation.duration_ms,
                observation.foundation_id,
                observation.selection_mode,
                observation.runtime,
                observation.runtime_version,
                observation.executor,
                observation.installation_id,
                observation.capability_profile_id,
                observation.verification_status,
                observation.foundation_role,
            ),
        )

    def record_capacity_snapshot(self, snapshot: CapacitySnapshotObservation) -> None:
        self._insert(
            """
            INSERT INTO capacity_snapshot (
                snapshot_id, observed_at, host_id, host_fingerprint,
                safe_vram_bytes, committed_vram_bytes, available_vram_bytes,
                safe_ram_bytes, committed_ram_bytes, available_ram_bytes,
                available_storage_bytes, active_reservation_count,
                basis_fingerprint, accelerator_index
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                snapshot.snapshot_id.value,
                _iso(snapshot.observed_at),
                _ident(snapshot.host_id),
                snapshot.host_fingerprint,
                snapshot.safe_vram_bytes,
                snapshot.committed_vram_bytes,
                snapshot.available_vram_bytes,
                snapshot.safe_ram_bytes,
                snapshot.committed_ram_bytes,
                snapshot.available_ram_bytes,
                snapshot.available_storage_bytes,
                snapshot.active_reservation_count,
                snapshot.basis_fingerprint,
                snapshot.accelerator_index,
            ),
        )

    def record_model_sizing(self, observation: ModelSizingObservation) -> None:
        self._insert(
            """
            INSERT INTO model_sizing_observation (
                observation_id, observed_at, duration_ms, model_id,
                source_model_ref, revision, architecture, quantization,
                runtime, runtime_version, requested_context, concurrency,
                factual_weight_bytes, estimator_mode, estimator_provider,
                estimator_version, estimated_minimum_vram_bytes,
                estimated_recommended_vram_bytes, estimated_kv_bytes,
                estimated_runtime_overhead_bytes,
                estimated_final_requirement_bytes, required_ram_bytes,
                required_storage_bytes, confidence, cheap_filter_result,
                deep_feasibility_result, capacity_basis
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                observation.observation_id.value,
                _iso(observation.observed_at),
                observation.duration_ms,
                observation.model_id,
                observation.source_model_ref,
                observation.revision,
                observation.architecture,
                observation.quantization,
                observation.runtime,
                observation.runtime_version,
                observation.requested_context,
                observation.concurrency,
                observation.factual_weight_bytes,
                observation.estimator_mode,
                observation.estimator_provider,
                observation.estimator_version,
                observation.estimated_minimum_vram_bytes,
                observation.estimated_recommended_vram_bytes,
                observation.estimated_kv_bytes,
                observation.estimated_runtime_overhead_bytes,
                observation.estimated_final_requirement_bytes,
                observation.required_ram_bytes,
                observation.required_storage_bytes,
                observation.confidence,
                observation.cheap_filter_result,
                observation.deep_feasibility_result,
                observation.capacity_basis,
            ),
        )

    def record_runtime_memory_profile(
        self, observation: RuntimeMemoryObservation
    ) -> None:
        self._insert(
            """
            INSERT INTO runtime_memory_profile (
                observation_id, measured_at, profile_id, model_id, revision,
                architecture, quantization, host_id, host_fingerprint,
                gpu_model, gpu_architecture, runtime, runtime_version,
                capability_profile_id, context_tokens, concurrency,
                probe_budget_bytes, factual_weight_bytes,
                estimated_static_requirement_bytes, estimated_kv_bytes,
                measured_model_load_bytes, measured_available_kv_bytes,
                measured_peak_gpu_bytes, derived_non_kv_bytes,
                derived_runtime_extra_bytes, calibrated_required_vram_bytes,
                profile_status, confidence, measurement_quality,
                failure_reason, class_key, basis_fingerprint
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                observation.observation_id.value,
                _iso(observation.measured_at),
                observation.profile_id,
                observation.model_id,
                observation.revision,
                observation.architecture,
                observation.quantization,
                _ident(observation.host_id),
                observation.host_fingerprint,
                observation.gpu_model,
                observation.gpu_architecture,
                observation.runtime,
                observation.runtime_version,
                observation.capability_profile_id,
                observation.context_tokens,
                observation.concurrency,
                observation.probe_budget_bytes,
                observation.factual_weight_bytes,
                observation.estimated_static_requirement_bytes,
                observation.estimated_kv_bytes,
                observation.measured_model_load_bytes,
                observation.measured_available_kv_bytes,
                observation.measured_peak_gpu_bytes,
                observation.derived_non_kv_bytes,
                observation.derived_runtime_extra_bytes,
                observation.calibrated_required_vram_bytes,
                observation.profile_status,
                observation.confidence,
                observation.measurement_quality,
                observation.failure_reason,
                observation.class_key,
                observation.basis_fingerprint,
            ),
        )

    def start_deployment_run(self, run: DeploymentRunObservation) -> None:
        self._insert(
            """
            INSERT INTO deployment_run (
                deployment_run_id, started_at, kind, ended_at, duration_ms,
                host_id, selected_model, selected_revision, runtime,
                runtime_version, executor, plan_id, artifact_id,
                reservation_id, instance_id, state, failure_reason_code
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            self._run_values(run),
        )

    def record_deployment_event(self, event: DeploymentEventObservation) -> None:
        self._insert(
            """
            INSERT INTO deployment_event (
                event_id, occurred_at, event_type, correlation_id, status,
                duration_ms
            ) VALUES (?,?,?,?,?,?)
            """,
            (
                event.event_id.value,
                _iso(event.occurred_at),
                _enum(event.event_type),
                event.correlation_id,
                event.status,
                event.duration_ms,
            ),
        )

    def finish_deployment_run(self, run: DeploymentRunObservation) -> None:
        """Update the same run's end fields. Other historical runs stay intact."""
        existing = self._connection.execute(
            "SELECT 1 FROM deployment_run WHERE deployment_run_id = ?",
            (run.deployment_run_id.value,),
        ).fetchone()
        if existing is None:
            self.start_deployment_run(run)
            return
        self._connection.execute(
            """
            UPDATE deployment_run
            SET ended_at = ?, duration_ms = ?, state = ?,
                failure_reason_code = ?, selected_model = COALESCE(?, selected_model),
                reservation_id = COALESCE(?, reservation_id),
                instance_id = COALESCE(?, instance_id)
            WHERE deployment_run_id = ?
            """,
            (
                _iso(run.ended_at),
                run.duration_ms,
                run.state,
                run.failure_reason_code,
                run.selected_model,
                run.reservation_id,
                run.instance_id,
                run.deployment_run_id.value,
            ),
        )
        self._connection.commit()

    def status(self) -> TelemetryStatus:
        version = self._connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        return TelemetryStatus(
            enabled=True,
            available=True,
            database_path=str(self._path),
            applied_version=int(version) if version is not None else None,
            host_observations=self._count("host_observation"),
            runtime_observations=self._count("runtime_observation"),
            capacity_snapshots=self._count("capacity_snapshot"),
            model_sizing_observations=self._count("model_sizing_observation"),
            runtime_memory_profiles=self._count("runtime_memory_profile"),
            deployment_runs=self._count("deployment_run"),
            deployment_events=self._count("deployment_event"),
        )

    def _configure(self) -> None:
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA busy_timeout = 5000")

    def _migrate(self) -> None:
        applied = self._applied_versions()
        for version, description, filename in _MIGRATIONS:
            if version in applied:
                continue
            sql = _migration_sql(filename)
            self._connection.executescript(sql)
            self._connection.execute(
                """
                INSERT INTO schema_migrations (version, applied_at, description)
                VALUES (?, ?, ?)
                """,
                (version, _iso(self._clock.now()), description),
            )
            self._connection.commit()

    def _applied_versions(self) -> set[int]:
        found = self._connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'schema_migrations'
            """
        ).fetchone()
        if found is None:
            return set()
        return {
            int(row[0])
            for row in self._connection.execute("SELECT version FROM schema_migrations")
        }

    def _insert(self, sql: str, values: Iterable[object]) -> None:
        self._connection.execute(sql, tuple(values))
        self._connection.commit()

    def _count(self, table: str) -> int:
        row = self._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])

    def _run_values(self, run: DeploymentRunObservation) -> tuple[object, ...]:
        return (
            run.deployment_run_id.value,
            _iso(run.started_at),
            _enum(run.run_kind),
            _iso(run.ended_at),
            run.duration_ms,
            _ident(run.host_id),
            run.selected_model,
            run.selected_revision,
            run.runtime,
            run.runtime_version,
            run.executor,
            run.plan_id,
            run.artifact_id,
            run.reservation_id,
            run.instance_id,
            run.state,
            run.failure_reason_code,
        )
