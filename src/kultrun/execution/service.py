"""In-memory live processes plus persisted handles.

The adapter owns Popen objects. This service owns identity, persistence
and the restart story: a handle whose process we can no longer prove is
ours becomes UNVERIFIED and is never signalled.
"""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.execution.contracts import (
    ExecutionId,
    ExecutionOwnership,
    ExecutionState,
    ExecutorCapabilityProfile,
    ExecutorHandle,
    ExecutorSpec,
)
from kultrun.execution.ports import Executor
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.persistence import Store


class ExecutionService:
    """Start, observe, stop. Collections are plural."""

    def __init__(self, executor: Executor, store: Store) -> None:
        self._executor = executor
        self._store = store

    def capabilities(self, host: HostCapabilities) -> ExecutorCapabilityProfile:
        """Current-host capability evidence from the wired executor."""
        return self._executor.capabilities(host)

    def start(self, host_id: HostId, spec: ExecutorSpec) -> ExecutorHandle:
        """Launch and persist. Returns the live owned handle."""
        handle = self._executor.start(host_id, spec)
        self._store.put(handle.execution_id.value, handle)
        return handle

    def list(self) -> tuple[ExecutorHandle, ...]:
        """Every persisted execution, observed against live state."""
        return tuple(
            self.observe(record.execution_id)
            for record in self._store.records(ExecutorHandle)
        )

    def observe(
        self, execution_id: ExecutionId, *, persist: bool = True
    ) -> ExecutorHandle:
        """Refresh one execution. Unknown ids fail closed.

        Readiness polling passes persist=False so a growing stdout capture
        cannot fsync the store on every tick and miss the startup deadline.
        """
        recorded = self._store.get(ExecutorHandle, execution_id.value)
        if recorded is None:
            raise NotFoundError("no such execution", execution_id=execution_id.value)
        refreshed = self._executor.observe(recorded)
        if persist and refreshed != recorded:
            self._store.put(execution_id.value, refreshed)
        return refreshed

    def stop(self, execution_id: ExecutionId) -> ExecutorHandle:
        """Stop one owned execution. Unverified processes are not signalled."""
        handle = self.observe(execution_id, persist=False)
        if handle.ownership is not ExecutionOwnership.OWNED:
            return handle
        if handle.observed_state in (ExecutionState.EXITED, ExecutionState.FAILED):
            return handle
        stopped = self._executor.stop(handle)
        self._store.put(execution_id.value, stopped)
        return stopped

    def stop_all_running(self) -> tuple[ExecutorHandle, ...]:
        """Stop every owned running execution. Used by the reference console."""
        stopped: list[ExecutorHandle] = []
        for handle in self.list():
            if (
                handle.ownership is ExecutionOwnership.OWNED
                and handle.observed_state
                in (
                    ExecutionState.RUNNING,
                    ExecutionState.STARTING,
                    ExecutionState.STOPPING,
                )
            ):
                stopped.append(self.stop(handle.execution_id))
        return tuple(stopped)

    def reconcile(self) -> str:
        """On startup: drop claims we cannot prove. Do not kill strangers.

        Returns a fact string; grading belongs to the composition root.
        """
        leftovers = 0
        for recorded in self._store.records(ExecutorHandle):
            observed = self._executor.observe(recorded)
            if observed.ownership is ExecutionOwnership.UNVERIFIED:
                leftovers += 1
            if observed != recorded:
                self._store.put(recorded.execution_id.value, observed)
        if leftovers:
            return f"{leftovers} unverified process(es) left unclaimed"
        return "no unverified processes"

    def unverified_count(self) -> int:
        """How many records name a PID we will not claim."""
        return sum(
            1
            for handle in self._store.records(ExecutorHandle)
            if handle.ownership is ExecutionOwnership.UNVERIFIED
        )


def running_owned(handles: Sequence[ExecutorHandle]) -> tuple[ExecutorHandle, ...]:
    """The subset that is ours and still running."""
    return tuple(
        handle
        for handle in handles
        if handle.ownership is ExecutionOwnership.OWNED
        and handle.observed_state in (ExecutionState.RUNNING, ExecutionState.STARTING)
    )
