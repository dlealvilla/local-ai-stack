"""Durable deployment-run correlation. Not a workflow engine.

One record per state root. Independent CLI processes read the same
identity and stamp OperationalFact.correlation_id so a journey can be
reconstructed without a second analytics bus.
"""

from __future__ import annotations

from dataclasses import dataclass

from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import PersistenceError, PreconditionFailedError
from kultrun.kernel.persistence import Store
from kultrun.platform.contracts import (
    DeploymentRun,
    DeploymentRunId,
    DeploymentRunStatus,
)

#: Singleton key under which the current journey is stored.
RUN_KEY = "current"


@dataclass(frozen=True, slots=True)
class RunLoad:
    """Outcome of ensuring the current deployment run exists."""

    run: DeploymentRun
    created: bool


class DeploymentRunStore:
    """Reads and writes the single current DeploymentRun record."""

    def __init__(self, store: Store, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._loaded: DeploymentRun | None = None

    def current(self) -> DeploymentRun | None:
        """Loaded run, or the stored current record if startup has not bound."""
        if self._loaded is not None:
            return self._loaded
        try:
            existing = self._store.get(DeploymentRun, RUN_KEY)
        except PersistenceError as error:
            raise PreconditionFailedError(
                "deployment run exists but cannot be read; refusing to mint "
                "a new correlation identity over it",
                reason=str(error),
            ) from error
        if existing is not None:
            self._loaded = existing
        return existing

    def ensure(self, host_id: HostId, kultrun_build: str) -> RunLoad:
        """Reuse the current run, or mint one for this state root."""
        existing = self.current()
        if existing is not None:
            return RunLoad(run=existing, created=False)
        created = DeploymentRun(
            run_id=DeploymentRunId.generate(),
            host_id=host_id,
            started_at=self._clock.now(),
            status=DeploymentRunStatus.IN_PROGRESS,
            kultrun_build=kultrun_build,
        )
        self._store.put(RUN_KEY, created)
        self._loaded = created
        return RunLoad(run=created, created=True)

    def mark_failed(self) -> None:
        """Record that this journey ended in a known product failure."""
        current = self.current()
        if current is None or current.status is DeploymentRunStatus.FAILED:
            return
        from dataclasses import replace

        updated = replace(current, status=DeploymentRunStatus.FAILED)
        self._store.put(RUN_KEY, updated)
        self._loaded = updated

    def mark_completed(self) -> None:
        """Record a successful end of this journey."""
        current = self.current()
        if current is None:
            return
        from dataclasses import replace

        updated = replace(current, status=DeploymentRunStatus.COMPLETED)
        self._store.put(RUN_KEY, updated)
        self._loaded = updated
