"""Native filesystem/mount observer (MACHI 2.4.1).

Selects a concrete OS mount provider. Domain owns ``MountObservation``.
Linux and macOS implementations live in provider modules. Windows is
explicitly unsupported. Does not change mounts, walk customer trees, or
compute SAFE storage.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from machi.adapters.discover.linux_mount import LinuxMountProvider, StatVfs
from machi.adapters.discover.macos_mount import MacOSMountProvider, MacOSMountRecord
from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.discover.contracts import ObservationStatus, OSFamily
from machi.discover.mount_contracts import (
    MountObservation,
    MountObservationSettings,
    MountSettingProvenance,
    WriteProbePolicy,
)
from machi.discover.mounts import (
    DEFAULT_WRITE_PROBE_MAX_BYTES,
    NATIVE_OBSERVER,
    default_mount_settings,
    unobserved_mount_observation,
)
from machi.discover.ports import OSArchitectureObserver
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.unresolved import UnresolvedReason, is_resolved


class NativeMountObserver:
    """Observe this environment's filesystem/mount topology."""

    observer_id = NATIVE_OBSERVER

    def __init__(
        self,
        *,
        os_observer: OSArchitectureObserver | None = None,
        settings: MountObservationSettings | None = None,
        write_probe_policy: WriteProbePolicy | None = None,
        write_probe_max_bytes: int | None = None,
        linux_mountinfo_text: str | None = None,
        linux_mountinfo_path: Path | None = None,
        linux_statvfs: StatVfs | None = None,
        macos_records: Sequence[MacOSMountRecord] | None = None,
        linux_provider: LinuxMountProvider | None = None,
        macos_provider: MacOSMountProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._os_observer = os_observer
        self._clock = clock or SystemClock()
        if settings is not None:
            self._settings = settings
        else:
            policy = write_probe_policy or WriteProbePolicy.DISABLED
            provenance = (
                MountSettingProvenance.ADMINISTRATOR
                if write_probe_policy is not None
                else MountSettingProvenance.PRODUCT_DEFAULT
            )
            max_bytes = (
                DEFAULT_WRITE_PROBE_MAX_BYTES
                if write_probe_max_bytes is None
                else write_probe_max_bytes
            )
            self._settings = default_mount_settings(
                write_probe_policy=policy,
                write_probe_max_bytes=max_bytes,
                write_probe_provenance=provenance,
            )
        self._linux_provider = linux_provider or LinuxMountProvider(
            mountinfo_text=linux_mountinfo_text,
            mountinfo_path=linux_mountinfo_path,
            statvfs=linux_statvfs,
            clock=clock,
        )
        self._macos_provider = macos_provider or MacOSMountProvider(
            records=macos_records,
            clock=clock,
        )

    def observe(self) -> MountObservation:
        """Read OS family, then the matching native mount provider."""
        os_observer = self._os_observer or NativeOSArchitectureObserver(
            clock=self._clock
        )
        os_observation = os_observer.observe()
        when = self._clock.now()
        settings = self._settings
        if os_observation.os_status is ObservationStatus.UNOBSERVED:
            return unobserved_mount_observation(
                settings=settings,
                reason=UnresolvedReason.NOT_MEASURED,
                detail="operating system was not observed",
                provider="native",
                observed_at=when,
            )
        if (
            os_observation.os_status is ObservationStatus.UNRECOGNIZED
            or not is_resolved(os_observation.os_family)
        ):
            return unobserved_mount_observation(
                settings=settings,
                reason=UnresolvedReason.UNSUPPORTED,
                detail="operating system has no native mount reader",
                provider="native",
                observed_at=when,
            )
        if os_observation.os_family is OSFamily.LINUX:
            return self._linux_provider.observe(settings, when)
        if os_observation.os_family is OSFamily.MACOS:
            return self._macos_provider.observe(settings, when)
        return unobserved_mount_observation(
            settings=settings,
            reason=UnresolvedReason.UNSUPPORTED,
            detail="native mount observation is not implemented for windows",
            os_family=OSFamily.WINDOWS,
            provider="windows",
            observed_at=when,
        )
