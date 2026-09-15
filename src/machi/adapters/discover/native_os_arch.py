"""Native OS/architecture observer (MACHI 2.1.1).

Reads the current process platform via the Python standard library.
Does not shell out, does not write, and does not mint HostId.
"""

from __future__ import annotations

import platform

from machi.discover.contracts import OSArchitectureObservation
from machi.discover.normalize import NATIVE_OBSERVER, normalize_os_architecture
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import InternalError, ValidationError


class NativeOSArchitectureObserver:
    """Observe this host's OS family and CPU architecture."""

    observer_id = NATIVE_OBSERVER

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def observe(self) -> OSArchitectureObservation:
        """Read platform.system and platform.machine, then normalize."""
        try:
            raw_os: object = platform.system()
            raw_arch: object = platform.machine()
        except Exception as exc:
            raise InternalError(
                "failed to observe operating system or architecture",
            ) from exc
        if not isinstance(raw_os, str) or not isinstance(raw_arch, str):
            raise ValidationError(
                "platform APIs did not return strings",
                raw_os_type=type(raw_os).__name__,
                raw_arch_type=type(raw_arch).__name__,
            )
        return normalize_os_architecture(
            raw_os,
            raw_arch,
            observer=self.observer_id,
            observed_at=self._clock.now(),
        )
