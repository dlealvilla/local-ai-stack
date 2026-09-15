"""macOS physical-memory provider (MACHI 2.2.1).

Uses stdlib sysconf page counts. Domain owns ``MemoryObservation``;
this module owns the macOS source. It does not split unified memory
into fake discrete VRAM.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable

from machi.discover.contracts import MemoryObservation, MemorySource
from machi.discover.memory import measured_memory_observation
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import InternalError, ValidationError


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


class MacOSSysconfMemoryProvider:
    """Observe macOS-reported physical/system memory via sysconf."""

    source = MemorySource.SYSCONF

    def __init__(
        self,
        *,
        sysconf: Callable[[str], int] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._sysconf = sysconf
        self._clock = clock or SystemClock()

    def observe(self, when: dt.datetime | None = None) -> MemoryObservation:
        """Read SC_PHYS_PAGES * SC_PAGE_SIZE. Does not allocate buffers."""
        observed_at = when if when is not None else self._clock.now()
        reader = self._sysconf or os.sysconf
        try:
            pages: object = reader("SC_PHYS_PAGES")
            page_size: object = reader("SC_PAGE_SIZE")
        except (ValueError, OSError, AttributeError) as exc:
            raise InternalError(
                "failed to observe physical memory via sysconf",
            ) from exc
        if not isinstance(pages, int) or not isinstance(page_size, int):
            raise ValidationError(
                "sysconf did not return integers",
                pages_type=type(pages).__name__,
                page_size_type=type(page_size).__name__,
            )
        total, raw = physical_total_from_page_counts(pages, page_size)
        return measured_memory_observation(
            total,
            source=self.source,
            raw_total=raw,
            observed_at=observed_at,
        )
