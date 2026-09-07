"""How a workload is realized.

`Executor` is the seam. Native process execution is the first and
reference implementation. `ContainerEngine` is the optional container
path; Docker is one adapter behind it, never a generic contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.execution.contracts import (
    ContainerEngineProbe,
    ContainerExecutionConfig,
    ExecutorCapabilityProfile,
    ExecutorHandle,
    ExecutorSpec,
)
from kultrun.execution.engine import (
    ContainerCreateResult,
    ContainerInspection,
    ContainerLogs,
)
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.ids import Name


@runtime_checkable
class Executor(Protocol):
    """Starts, observes and stops processes from a structured spec."""

    @property
    def identity(self) -> Name:
        """Which executor this is, recorded on the handle."""
        ...

    def capabilities(self, host: HostCapabilities) -> ExecutorCapabilityProfile:
        """What this executor can provide on the given host. Does not exec."""
        ...

    def start(self, host_id: HostId, spec: ExecutorSpec) -> ExecutorHandle:
        """Create a process. Must not invoke a shell."""
        ...

    def observe(self, handle: ExecutorHandle) -> ExecutorHandle:
        """Refresh observed state, output and exit code."""
        ...

    def stop(self, handle: ExecutorHandle) -> ExecutorHandle:
        """Ask the process to exit, then force it after the spec's grace."""
        ...


@runtime_checkable
class ContainerEngine(Protocol):
    """Create, inspect, log, stop and remove containers. Not an Executor."""

    @property
    def identity(self) -> Name:
        """Which engine this is, e.g. docker."""
        ...

    def probe(self) -> ContainerEngineProbe:
        """Bounded availability probe. Distinguishes missing binary from daemon."""
        ...

    def create(
        self,
        *,
        name: str,
        config: ContainerExecutionConfig,
        command: tuple[str, ...],
        environment: tuple[str, ...],
        labels: tuple[str, ...],
    ) -> ContainerCreateResult:
        """Create a stopped container. Must not invoke a shell."""
        ...

    def start(self, container_id: str) -> ContainerCreateResult:
        """Start an already-created container."""
        ...

    def inspect(self, container_id: str) -> ContainerInspection | None:
        """Current engine-native state, or None when the id is unknown."""
        ...

    def logs(self, container_id: str, *, limit_bytes: int) -> ContainerLogs:
        """Bounded stdout/stderr from the engine."""
        ...

    def stop(self, container_id: str, *, grace_period_seconds: float) -> None:
        """Ask the container to exit. The executor maps the result."""
        ...

    def kill(self, container_id: str) -> None:
        """Forced stop. Idempotent if already stopped."""
        ...

    def remove(self, container_id: str) -> None:
        """Delete a Kultrun-owned container id. Never a query of all containers."""
        ...
