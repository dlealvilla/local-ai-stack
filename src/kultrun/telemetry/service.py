"""Best-effort telemetry wrapper and path resolution.

The adapter opens sqlite. This module never imports sqlite types. A write
failure is recorded and swallowed so the control plane fact remains valid.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from kultrun.kernel.unresolved import is_resolved
from kultrun.telemetry.contracts import (
    CapacitySnapshotObservation,
    DeploymentEventObservation,
    DeploymentRunObservation,
    HostObservation,
    ModelSizingObservation,
    RuntimeMemoryObservation,
    RuntimeObservation,
    TelemetrySettings,
    TelemetryStatus,
)
from kultrun.telemetry.ports import TelemetryRecorder

TELEMETRY_DIRECTORY = "telemetry"
TELEMETRY_FILENAME = "kultrun-telemetry.sqlite3"


def resolve_database_path(state_root: Path, settings: TelemetrySettings) -> Path:
    """State-root default, or the explicit test override."""
    configured = settings.database_path
    if is_resolved(configured) and configured.strip():
        return Path(configured).expanduser().resolve()
    return (
        Path(state_root).expanduser().resolve()
        / TELEMETRY_DIRECTORY
        / TELEMETRY_FILENAME
    )


class DisabledRecorder:
    """No database. Used when telemetry is off or failed to open."""

    def __init__(
        self,
        *,
        enabled: bool,
        database_path: str | None = None,
        last_error: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._database_path = database_path
        self._last_error = last_error

    def record_host_observation(self, observation: HostObservation) -> None:
        del observation

    def record_runtime_observation(self, observation: RuntimeObservation) -> None:
        del observation

    def record_capacity_snapshot(self, snapshot: CapacitySnapshotObservation) -> None:
        del snapshot

    def record_model_sizing(self, observation: ModelSizingObservation) -> None:
        del observation

    def record_runtime_memory_profile(
        self, observation: RuntimeMemoryObservation
    ) -> None:
        del observation

    def start_deployment_run(self, run: DeploymentRunObservation) -> None:
        del run

    def record_deployment_event(self, event: DeploymentEventObservation) -> None:
        del event

    def finish_deployment_run(self, run: DeploymentRunObservation) -> None:
        del run

    def status(self) -> TelemetryStatus:
        return TelemetryStatus(
            enabled=self._enabled,
            available=False,
            database_path=self._database_path,
            applied_version=None,
            last_error=self._last_error,
        )


class BestEffortRecorder:
    """Swallow persistence errors. Never invent a successful write."""

    def __init__(self, inner: TelemetryRecorder) -> None:
        self._inner = inner
        self._last_error: str | None = None

    @property
    def last_error(self) -> str | None:
        """Most recent swallowed persistence failure."""
        return self._last_error

    def record_host_observation(self, observation: HostObservation) -> None:
        self._run(lambda: self._inner.record_host_observation(observation))

    def record_runtime_observation(self, observation: RuntimeObservation) -> None:
        self._run(lambda: self._inner.record_runtime_observation(observation))

    def record_capacity_snapshot(self, snapshot: CapacitySnapshotObservation) -> None:
        self._run(lambda: self._inner.record_capacity_snapshot(snapshot))

    def record_model_sizing(self, observation: ModelSizingObservation) -> None:
        self._run(lambda: self._inner.record_model_sizing(observation))

    def record_runtime_memory_profile(
        self, observation: RuntimeMemoryObservation
    ) -> None:
        self._run(lambda: self._inner.record_runtime_memory_profile(observation))

    def start_deployment_run(self, run: DeploymentRunObservation) -> None:
        self._run(lambda: self._inner.start_deployment_run(run))

    def record_deployment_event(self, event: DeploymentEventObservation) -> None:
        self._run(lambda: self._inner.record_deployment_event(event))

    def finish_deployment_run(self, run: DeploymentRunObservation) -> None:
        self._run(lambda: self._inner.finish_deployment_run(run))

    def status(self) -> TelemetryStatus:
        try:
            reported = self._inner.status()
        except Exception as error:  # telemetry must not raise to callers
            self._last_error = str(error)
            return TelemetryStatus(
                enabled=True,
                available=False,
                last_error=self._last_error,
            )
        if self._last_error is None:
            return reported
        return TelemetryStatus(
            enabled=reported.enabled,
            available=reported.available,
            database_path=reported.database_path,
            applied_version=reported.applied_version,
            last_error=self._last_error,
            host_observations=reported.host_observations,
            runtime_observations=reported.runtime_observations,
            capacity_snapshots=reported.capacity_snapshots,
            model_sizing_observations=reported.model_sizing_observations,
            runtime_memory_profiles=reported.runtime_memory_profiles,
            deployment_runs=reported.deployment_runs,
            deployment_events=reported.deployment_events,
        )

    def _run(self, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as error:
            self._last_error = str(error)
