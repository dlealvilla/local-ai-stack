"""Native accelerator observer (MACHI 2.3).

Selects applicable implemented providers and combines generic device
observations. Domain owns ``AcceleratorObservation``. NVIDIA and Apple
implementations live in provider modules. Does not compute capacity,
mint HostId, or persist HostProfile.
"""

from __future__ import annotations

from collections.abc import Sequence

from machi.adapters.discover.accelerator_provider import AcceleratorProvider
from machi.adapters.discover.apple_accelerator import AppleAcceleratorProvider
from machi.adapters.discover.native_os_arch import NativeOSArchitectureObserver
from machi.adapters.discover.nvidia_accelerator import NvidiaAcceleratorProvider
from machi.discover.accelerator import (
    NATIVE_OBSERVER,
    accelerator_observation,
    non_observed_provider_report,
)
from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorObservation,
    AcceleratorProviderReport,
    ProviderInspectionStatus,
)
from machi.discover.ports import OSArchitectureObserver
from machi.kernel.clock import Clock, SystemClock


class NativeAcceleratorObserver:
    """Observe accelerators visible to this environment."""

    observer_id = NATIVE_OBSERVER

    def __init__(
        self,
        *,
        os_observer: OSArchitectureObserver | None = None,
        providers: Sequence[AcceleratorProvider] | None = None,
        nvidia_provider: NvidiaAcceleratorProvider | None = None,
        apple_provider: AppleAcceleratorProvider | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._os_observer = os_observer
        self._clock = clock or SystemClock()
        if providers is not None:
            self._providers = tuple(providers)
        else:
            self._providers = (
                nvidia_provider or NvidiaAcceleratorProvider(),
                apple_provider or AppleAcceleratorProvider(),
            )

    def observe(self) -> AcceleratorObservation:
        """Invoke applicable providers and return one generic observation."""
        os_observer = self._os_observer or NativeOSArchitectureObserver(
            clock=self._clock
        )
        os_observation = os_observer.observe()
        when = self._clock.now()
        reports: list[AcceleratorProviderReport] = []
        devices: list[AcceleratorDevice] = []
        for provider in self._providers:
            if not provider.applicable(os_observation):
                reports.append(
                    non_observed_provider_report(
                        provider.provider_id,
                        ProviderInspectionStatus.NOT_APPLICABLE,
                    )
                )
                continue
            result = provider.inspect()
            reports.append(result.report)
            if result.report.status is ProviderInspectionStatus.OBSERVED:
                devices.extend(result.devices)
        return accelerator_observation(
            devices=tuple(devices),
            providers=tuple(reports),
            observed_at=when,
        )
