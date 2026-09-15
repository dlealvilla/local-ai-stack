"""Replaceable OS/architecture observation port (MACHI 2.1.1).

Core owns the observation contract. Adapters interrogate the host.
Composition selects the adapter. This is not a probe engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.discover.contracts import OSArchitectureObservation


@runtime_checkable
class OSArchitectureObserver(Protocol):
    """Something that can observe OS family and CPU architecture."""

    def observe(self) -> OSArchitectureObservation:
        """Return one observation. Must not mutate the host."""
        ...
