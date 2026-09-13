"""No-op product telemetry exporter. Air-gapped default."""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.vendor.contracts import TelemetryRecord


class DisabledProductTelemetryExporter:
    """Accepts records and discards them. Deployment never depends on this."""

    def export(self, records: Sequence[TelemetryRecord]) -> None:
        del records
