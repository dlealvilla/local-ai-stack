"""Native physical/system memory observer (MACHI 2.2.1).

Selects a concrete OS memory provider. Domain owns the observation
contract. Linux, macOS, and (deferred) Windows implementations live
in provider modules. Does not shell out, write, compute safe capacity,
or mint HostId.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from machi.adapters.discover.linux_proc_memory import LinuxProcMemoryProvider
from machi.adapters.discover.macos_sysconf_memory import MacOSSysconfMemoryProvider
from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.discover.contracts import (
    MemoryObservation,
    MemorySource,
    ObservationStatus,
    OSFamily,
)
from machi.discover.memory import NATIVE_OBSERVER, unobserved_memory_observation
from machi.discover.ports import OSArchitectureObserver
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.unresolved import UnresolvedReason, is_resolved


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
        linux_provider: LinuxProcMemoryProvider | None = None,
        macos_provider: MacOSSysconfMemoryProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._os_observer = os_observer
        self._linux_provider = linux_provider or LinuxProcMemoryProvider(
            memory_text=linux_memory_text,
            memory_path=linux_memory_path,
            clock=clock,
        )
        self._macos_provider = macos_provider or MacOSSysconfMemoryProvider(
            sysconf=sysconf,
            clock=clock,
        )
        self._clock = clock or SystemClock()

    def observe(self) -> MemoryObservation:
        """Read OS family, then the matching native memory provider."""
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
            return self._linux_provider.observe(when)
        if os_observation.os_family is OSFamily.MACOS:
            return self._macos_provider.observe(when)
        return unobserved_memory_observation(
            source=MemorySource.UNSUPPORTED,
            reason=UnresolvedReason.UNSUPPORTED,
            detail="native memory observation is not implemented for windows",
            observed_at=when,
        )
