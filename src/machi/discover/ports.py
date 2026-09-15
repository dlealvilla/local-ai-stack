"""Replaceable Discover observer ports (MACHI 2.1.1 / 2.2.1).

Core owns observation contracts. Adapters interrogate the host.
Composition selects adapters. This is not a probe engine.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.discover.contracts import MemoryObservation, OSArchitectureObservation


@runtime_checkable
class OSArchitectureObserver(Protocol):
    """Something that can observe OS family and CPU architecture."""

    def observe(self) -> OSArchitectureObservation:
        """Return one observation. Must not mutate the host."""
        ...


@runtime_checkable
class MemoryObserver(Protocol):
    """Something that can observe reported physical/system memory."""

    def observe(self) -> MemoryObservation:
        """Return one observation. Must not mutate the host or compute capacity."""
        ...
