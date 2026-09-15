"""Linux physical-memory provider (MACHI 2.2.1).

Reads the kernel memory table. Domain owns ``MemoryObservation``;
this module owns the Linux source. It does not compute capacity.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from machi.discover.contracts import MemoryObservation, MemorySource
from machi.discover.memory import (
    measured_memory_observation,
    unobserved_memory_observation,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import InternalError, ValidationError
from machi.kernel.unresolved import UnresolvedReason

_LINUX_MEMORY_TABLE = Path("/proc/meminfo")
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


class LinuxProcMemoryProvider:
    """Observe Linux-reported physical/system memory from the kernel table."""

    source = MemorySource.LINUX_PROC

    def __init__(
        self,
        *,
        memory_text: str | None = None,
        memory_path: Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._memory_text = memory_text
        self._memory_path = memory_path
        self._clock = clock or SystemClock()

    def observe(self, when: dt.datetime | None = None) -> MemoryObservation:
        """Read MemTotal. Missing table is unobserved, never zero."""
        observed_at = when if when is not None else self._clock.now()
        text = self._memory_text
        if text is None:
            path = self._memory_path or _LINUX_MEMORY_TABLE
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                return unobserved_memory_observation(
                    source=MemorySource.UNOBSERVED,
                    reason=UnresolvedReason.NOT_MEASURED,
                    detail="Linux memory table was not present",
                    observed_at=observed_at,
                )
            except OSError as exc:
                raise InternalError(
                    "failed to observe Linux physical memory",
                ) from exc
        total, raw = parse_linux_memory_table(text)
        return measured_memory_observation(
            total,
            source=self.source,
            raw_total=raw,
            observed_at=observed_at,
        )
