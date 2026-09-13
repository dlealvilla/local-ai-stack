"""Outbound telemetry port. Implementations live in adapters/telemetry."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from kultrun.vendor.contracts import TelemetryRecord


@runtime_checkable
class ProductTelemetryExporter(Protocol):
    """Single outbound product-telemetry seam.

    Must not block a mutating path. A failed export is dropped and counted,
    never retried onto inference or deployment.
    """

    def export(self, records: Sequence[TelemetryRecord]) -> None:
        """Accept sanitized records. Must not raise into the caller."""
        ...
