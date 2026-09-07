"""How a workload is realized.

`Executor` is the seam. Native process execution is the first and
reference implementation. `ContainerEngine` is declared so an OCI adapter
is later an implementation rather than a redesign — it is unimplemented.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.execution.contracts import (
    ExecutorCapabilityProfile,
    ExecutorHandle,
    ExecutorSpec,
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
    """Optional container path. Not implemented in Stage 1.3."""

    @property
    def identity(self) -> Name:
        """Which engine this would be."""
        ...
