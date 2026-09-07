"""The runtime seam.

Named `InferenceRuntime` in `docs/ARCHITECTURE.md`. Stage 1.3 implements
the port with a reference process adapter that is not an LLM runtime.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
)


@runtime_checkable
class InferenceRuntime(Protocol):
    """Translates a profile into a structured launch recipe."""

    @property
    def identity(self) -> Name:
        """Stable runtime name."""
        ...

    def profile(self) -> RuntimeProfile:
        """What this adapter can do."""
        ...

    def support(self) -> RuntimeSupportDescriptor:
        """Declared static support. Not proof that anything is installed."""
        ...

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        """Produce the recipe. Must not start a process."""
        ...

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
    ) -> RuntimeReadiness:
        """Runtime-owned READY probe. Must not signal or kill a process."""
        ...
