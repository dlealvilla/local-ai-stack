"""Pure memory observation helpers (MACHI 2.2.1).

Adapters supply Linux proc-table text or sysconf page counts.
This module does not read the host, does not call platform APIs, and
does not compute safe allocatable memory.
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

_KIB_BYTES = 1024
_MEMTOTAL = "MemTotal"


def parse_linux_memory_table(text: str) -> tuple[int, str]:
    """Return (bytes, compact raw line) from a Linux memory table.

    Linux reports kB as KiB. Conversion is integer ``value * 1024``.
    """
    if not isinstance(text, str):
        raise ValidationError(
            "Linux memory table must be text",
            actual_type=type(text).__name__,
        )
    matched: str | None = None
    number: str | None = None
    unit: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, rest = stripped.partition(":")
        if separator != ":" or key.strip() != _MEMTOTAL:
            continue
        fields = rest.split()
        if len(fields) < 2:
            raise ValidationError(
                "MemTotal is missing a unit",
                what="physical_total_bytes",
            )
        number, unit = fields[0], fields[1]
        matched = f"{_MEMTOTAL}: {number} {unit}"
        break
    if matched is None or number is None or unit is None:
        raise ValidationError(
            "MemTotal is missing",
            what="physical_total_bytes",
        )
    if not number.isdigit():
        raise ValidationError(
            "MemTotal is not an integer",
            what="physical_total_bytes",
            raw=number,
        )
    if unit != "kB":
        raise ValidationError(
            "MemTotal unit is not kB",
            what="physical_total_bytes",
            unit=unit,
        )
    total = int(number) * _KIB_BYTES
    if total <= 0:
        raise ValidationError(
            "MemTotal must be greater than zero",
            what="physical_total_bytes",
            total=total,
        )
    return total, matched


def physical_total_from_page_counts(
    pages: object, page_size: object
) -> tuple[int, str]:
    """Convert sysconf page counts into integer bytes."""
    if not isinstance(pages, int) or not isinstance(page_size, int):
        raise ValidationError(
            "sysconf page counts must be integers",
            pages_type=type(pages).__name__,
            page_size_type=type(page_size).__name__,
        )
    if pages <= 0 or page_size <= 0:
        raise ValidationError(
            "sysconf physical memory is not positive",
            pages=pages,
            page_size=page_size,
        )
    total = pages * page_size
    raw = f"SC_PHYS_PAGES={pages};SC_PAGE_SIZE={page_size}"
    return total, raw


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
