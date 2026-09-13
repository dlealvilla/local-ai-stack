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
    run_id: Maybe[str] = meaning(
        "DeploymentRun identity when the fact was correlated", default=NOT_PROVIDED
    )
    executor: Maybe[str] = meaning(
        "executor class, when the fact recorded one", default=NOT_PROVIDED
    )
    support_tier: Maybe[str] = meaning(
        "product maturity of a foundation family", default=NOT_PROVIDED
    )
    profile: Maybe[str] = meaning("minimum host profile identity", default=NOT_PROVIDED)
    possibility: Maybe[str] = meaning(
        "coarse host possibility, never verified", default=NOT_PROVIDED
    )
    requires_reclamation: Maybe[str] = meaning(
        "whether PASS depended on planned reclaim", default=NOT_PROVIDED
    )
    byte_band: Maybe[str] = meaning(
        "coarse capacity or footprint band, never an exact path",
        default=NOT_PROVIDED,
    )
    discovered: Maybe[str] = meaning(
        "runtime or model funnel discovered count", default=NOT_PROVIDED
    )
    product_selectable: Maybe[str] = meaning(
        "runtime funnel product-selectable count", default=NOT_PROVIDED
    )
    host_compatible: Maybe[str] = meaning(
        "runtime funnel host-compatible count", default=NOT_PROVIDED
    )
    executor_compatible: Maybe[str] = meaning(
        "runtime funnel executor-compatible count", default=NOT_PROVIDED
    )
    capacity_feasible: Maybe[str] = meaning(
        "runtime funnel capacity-feasible count", default=NOT_PROVIDED
    )
    cleanup_lifecycle: Maybe[str] = meaning(
        "whether cleanup ran for lifecycle hygiene", default=NOT_PROVIDED
    )
    cleanup_capacity: Maybe[str] = meaning(
        "whether cleanup was also required for capacity", default=NOT_PROVIDED
    )
