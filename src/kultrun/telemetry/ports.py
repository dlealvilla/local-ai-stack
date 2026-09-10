"""The telemetry recording seam.

A small typed port. Not an event bus. Implementations live in
``adapters/telemetry``. Callers receive this port; they never see sqlite.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class TelemetryRecorder(Protocol):
    """Append-only operational evidence. Never an execution authority."""

    def record_host_observation(self, observation: HostObservation) -> None:
        """Persist one Host Discovery copy."""
        ...

    def record_runtime_observation(self, observation: RuntimeObservation) -> None:
        """Persist one foundation / verification copy."""
        ...

    def record_capacity_snapshot(self, snapshot: CapacitySnapshotObservation) -> None:
        """Persist one CurrentCapacitySnapshot copy."""
        ...

    def record_model_sizing(self, observation: ModelSizingObservation) -> None:
        """Persist one candidate-sizing copy."""
        ...

    def record_runtime_memory_profile(
        self, observation: RuntimeMemoryObservation
    ) -> None:
        """Persist one analytical RuntimeMemoryProfile copy."""
        ...

    def start_deployment_run(self, run: DeploymentRunObservation) -> None:
        """Insert a run that has begun."""
        ...

    def record_deployment_event(self, event: DeploymentEventObservation) -> None:
        """Persist one lifecycle milestone."""
        ...

    def finish_deployment_run(self, run: DeploymentRunObservation) -> None:
        """Complete a started run. Does not delete or rewrite other runs."""
        ...

    def status(self) -> TelemetryStatus:
        """Counts and schema version. Never a query console."""
        ...
