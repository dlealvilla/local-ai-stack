"""The runtime seam.

Named `InferenceRuntime` in `docs/ARCHITECTURE.md`. Stage 1.3 implements
the port with a reference process adapter that is not an LLM runtime.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import RuntimeLaunchSpec, RuntimeProfile


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

    def launch_spec(self) -> RuntimeLaunchSpec:
        """Produce the recipe. Must not start a process."""
        ...
