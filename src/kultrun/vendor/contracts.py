"""Vendor configuration and the sanitized telemetry record.

The exporter port lives beside these contracts. The disabled adapter is the
only implementation in this stage: air-gapped operation is the default.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


@contract(kind="config.vendor", version=1)
@dataclass(frozen=True, slots=True)
class TelemetrySettings(Contract):
    """Outbound product-telemetry controls. Off by default.

    Enabling this section does not by itself send anything: an exporter
    adapter must still be wired, and a failed or absent exporter must never
    block inference or deployment.
    """

    enabled: bool = meaning(
        "whether the installation may offer operational metadata to an exporter",
        default=False,
    )
    export_operational_metadata: bool = meaning(
        "whether sanitized operational facts may be queued for export; "
        "never includes prompts, responses, or documents",
        default=False,
    )


@contract(kind="vendor.telemetry_record", version=1)
@dataclass(frozen=True, slots=True)
class TelemetryRecord(Contract):
    """Sanitized operational metadata. Never customer content."""

    occurred_at: dt.datetime = meaning("when the fact happened, UTC")
    event_type: str = meaning("stable dotted operational event name")
    outcome: str = meaning("pass, fail, unresolved, info, or blocked")
    stage: str = meaning("deployment column")
    kultrun_build: Maybe[str] = meaning("build id when known", default=NOT_PROVIDED)
    os_name: Maybe[str] = meaning("OS family", default=NOT_PROVIDED)
    architecture: Maybe[str] = meaning("CPU architecture", default=NOT_PROVIDED)
    storage_technology: Maybe[str] = meaning(
        "filesystem family, when the fact is about storage", default=NOT_PROVIDED
    )
    runtime: Maybe[str] = meaning(
        "runtime family, when applicable", default=NOT_PROVIDED
    )
    model: Maybe[str] = meaning(
        "catalog logical name, never generated text", default=NOT_PROVIDED
    )
    reason_code: Maybe[str] = meaning("typed product reason", default=NOT_PROVIDED)
    latency_ms: Maybe[int] = meaning(
        "latency when the fact recorded one", default=NOT_PROVIDED
    )
    error_class: Maybe[str] = meaning(
        "error class, never an exception body", default=NOT_PROVIDED
    )
