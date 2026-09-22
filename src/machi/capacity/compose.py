"""Compose one CapacityEnvelope from already observed facts."""

from __future__ import annotations

import datetime as dt

from machi.capacity.contracts import (
    AdministratorBound,
    CapacityEnvelope,
    CapacitySettings,
    SonarEvidence,
    SpecialistBound,
)
from machi.capacity.derive import (
    accelerator_capacity,
    input_token,
    memory_capacity,
    storage_domains,
)
from machi.discover.contracts import AcceleratorObservation, MemoryObservation
from machi.discover.mount_contracts import MountObservation
from machi.kernel.unresolved import NOT_MEASURED, Maybe
from machi.steward.contracts import OccupancyMap


def compose_envelope(
    *,
    evidence_id: str,
    memory: MemoryObservation | None = None,
    execution_limit_bytes: Maybe[int] | None = None,
    accelerators: AcceleratorObservation | None = None,
    mounts: MountObservation | None = None,
    occupancy: OccupancyMap | None = None,
    specialists: tuple[SpecialistBound, ...] = (),
    admins: tuple[AdministratorBound, ...] = (),
    sonar_by_domain: dict[str, SonarEvidence] | None = None,
    settings: CapacitySettings,
    observed_at: dt.datetime,
    provider: str,
    input_parts: tuple[str, ...] = (),
) -> CapacityEnvelope:
    """Build one snapshot. Does not discover hardware and does not admit a workload."""
    memory_row = memory_capacity(
        memory,
            execution_limit_bytes=(
                NOT_MEASURED if execution_limit_bytes is None else execution_limit_bytes
            ),
        reserve_bytes=settings.memory_reserve_bytes,
    )
    accelerator_rows = accelerator_capacity(
        accelerators,
        reserve_bytes=settings.accelerator_reserve_bytes,
    )
    storage_rows = storage_domains(
        mounts,
        occupancy,
        specialists=specialists,
        admins=admins,
        sonar_by_domain=sonar_by_domain or {},
        reserve_bytes=settings.storage_reserve_bytes,
        admin_allowed=settings.admin_fallback == "allow",
    )
    parts = input_parts or (evidence_id,)
    return CapacityEnvelope(
        evidence_id=evidence_id,
        input_token=input_token(*parts),
        memory=memory_row,
        accelerators=accelerator_rows,
        storage_domains=storage_rows,
        settings=settings,
        observed_at=observed_at,
        provider=provider,
    )


def is_stale(envelope: CapacityEnvelope, current_token: str) -> bool:
    """True when the inputs no longer match the snapshot a plan would cite."""
    return envelope.input_token != current_token
