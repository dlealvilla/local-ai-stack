"""Steward port. Adapters read evidence. The domain classifies it."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.steward.contracts import OccupancyMap


@runtime_checkable
class Steward(Protocol):
    """Classify known roots. Must not delete or compute SAFE storage."""

    def assess(self) -> OccupancyMap:
        """Return one occupancy projection."""
        ...
