"""Pure memory observation helpers (MACHI 2.2.1).

Domain owns the generic ``MemoryObservation`` factories. Concrete
Linux/macOS/Windows readers live in adapters. This module does not
read the host, does not call platform APIs, and does not compute
safe allocatable memory.
"""

from __future__ import annotations

import datetime as dt

from machi.discover.contracts import (
    MemoryObservation,
    MemorySource,
    ObservationStatus,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_MEASURED, Unresolved, UnresolvedReason

NATIVE_OBSERVER = "native"


def measured_memory_observation(
    total_bytes: int,
    *,
    source: MemorySource,
    raw_total: str,
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> MemoryObservation:
    """Build a measured physical/system memory observation."""
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    return MemoryObservation(
        physical_total_bytes=total_bytes,
        physical_total_status=ObservationStatus.NORMALIZED,
        source=source,
        raw_total=raw_total,
        observed_at=when,
        observer=observer,
    )


def unobserved_memory_observation(
    *,
    source: MemorySource,
    reason: UnresolvedReason,
    detail: str,
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> MemoryObservation:
    """Build a truthful non-measurement. Never substitutes zero bytes."""
    if source not in {MemorySource.UNOBSERVED, MemorySource.UNSUPPORTED}:
        raise ValidationError(
            "unobserved memory requires an unobserved or unsupported source",
            source=source.value,
        )
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    unresolved: Unresolved = (
        NOT_MEASURED
        if reason is UnresolvedReason.NOT_MEASURED
        else Unresolved(reason, detail)
    )
    return MemoryObservation(
        physical_total_bytes=unresolved,
        physical_total_status=ObservationStatus.UNOBSERVED,
        source=source,
        raw_total="",
        observed_at=when,
        observer=observer,
    )
