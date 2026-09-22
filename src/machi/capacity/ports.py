"""Capacity ports. Adapters own host writes and cgroup reads."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.capacity.contracts import CapacityEnvelope


@runtime_checkable
class CapacityEvaluator(Protocol):
    """Derive one envelope. Must not admit, place, or tune a runtime."""

    def evaluate(self) -> CapacityEnvelope:
        """Return one capacity snapshot."""
        ...
