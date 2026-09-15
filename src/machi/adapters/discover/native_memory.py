"""Native physical/system memory observer (MACHI 2.2.1).

Linux reads the kernel memory table. macOS uses stdlib sysconf page
counts. Windows is not implemented. Does not shell out, does not write,
does not compute safe capacity, and does not mint HostId.
"""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Callable
from pathlib import Path

from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.discover.contracts import (
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    OSFamily,
)
from machi.discover.memory import (
    NATIVE_OBSERVER,
    measured_memory_observation,
    parse_linux_memory_table,
    physical_total_from_page_counts,
    unobserved_memory_observation,
)
from machi.discover.ports import OSArchitectureObserver
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import InternalError, ValidationError
from machi.kernel.unresolved import UnresolvedReason, is_resolved

_LINUX_MEMORY_TABLE = Path("/proc/meminfo")


class NativeMemoryObserver:
    """Observe this environment's reported physical/system memory."""

    observer_id = NATIVE_OBSERVER

    def __init__(
        self,
        *,
        os_observer: OSArchitectureObserver | None = None,
        linux_memory_text: str | None = None,
        linux_memory_path: Path | None = None,
        sysconf: Callable[[str], int] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._os_observer = os_observer
        self._linux_memory_text = linux_memory_text
        self._linux_memory_path = linux_memory_path
        self._sysconf = sysconf
        self._clock = clock or SystemClock()

    def observe(self) -> MemoryObservation:
        """Read OS family, then the matching native memory source."""
        os_observer = self._os_observer or NativeOSArchitectureObserver(
            clock=self._clock
        )
        os_observation = os_observer.observe()
        when = self._clock.now()
        if os_observation.os_status is ObservationStatus.UNOBSERVED:
            return unobserved_memory_observation(
                source=MemorySource.UNOBSERVED,
                reason=UnresolvedReason.NOT_MEASURED,
                detail="operating system was not observed",
                observed_at=when,
            )
        if (
            os_observation.os_status is ObservationStatus.UNRECOGNIZED
            or not is_resolved(os_observation.os_family)
        ):
            return unobserved_memory_observation(
                source=MemorySource.UNSUPPORTED,
                reason=UnresolvedReason.UNSUPPORTED,
                detail="operating system has no native memory reader",
                observed_at=when,
            )
        if os_observation.os_family is OSFamily.LINUX:
            return self._observe_linux(when)
        if os_observation.os_family is OSFamily.MACOS:
            return self._observe_sysconf(when)
        return unobserved_memory_observation(
            source=MemorySource.UNSUPPORTED,
            reason=UnresolvedReason.UNSUPPORTED,
            detail="native memory observation is not implemented for windows",
            observed_at=when,
        )

    def _observe_linux(self, when: dt.datetime) -> MemoryObservation:
        text = self._linux_memory_text
        if text is None:
            path = self._linux_memory_path or _LINUX_MEMORY_TABLE
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except FileNotFoundError:
                return unobserved_memory_observation(
                    source=MemorySource.UNOBSERVED,
                    reason=UnresolvedReason.NOT_MEASURED,
                    detail="Linux memory table was not present",
                    observed_at=when,
                )
            except OSError as exc:
                raise InternalError(
                    "failed to observe Linux physical memory",
                ) from exc
        total, raw = parse_linux_memory_table(text)
        return measured_memory_observation(
            total,
            source=MemorySource.LINUX_PROC,
            raw_total=raw,
            observed_at=when,
        )

    def _observe_sysconf(self, when: dt.datetime) -> MemoryObservation:
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
            source=MemorySource.SYSCONF,
            raw_total=raw,
            observed_at=when,
        )
