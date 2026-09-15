"""Internal accelerator provider seam (MACHI 2.3).

This is adapter-local orchestration glue, not a product plugin
framework. Domain code continues to consume ``AcceleratorObserver``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorProviderReport,
    OSArchitectureObservation,
    ProviderInspectionStatus,
)
from machi.kernel.errors import ValidationError


@runtime_checkable
class AcceleratorProvider(Protocol):
    """One vendor/source implementation behind NativeAcceleratorObserver."""

    provider_id: str

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        """True when this provider is meaningful for the observed host."""
        ...

    def inspect(self) -> ProviderInspectResult:
        """Observe devices. Must not mutate the host."""
        ...


class ProviderInspectResult:
    """Devices only accompany a successful ``observed`` inspection."""

    def __init__(
        self,
        report: AcceleratorProviderReport,
        devices: tuple[AcceleratorDevice, ...] = (),
    ) -> None:
        if report.status is ProviderInspectionStatus.OBSERVED:
            if report.device_count != len(devices):
                raise ValidationError(
                    "observed inspect result must match report device_count",
                    provider=report.provider,
                    reported=report.device_count,
                    devices=len(devices),
                )
        elif devices:
            raise ValidationError(
                "non-observed inspect result cannot emit devices",
                provider=report.provider,
                status=report.status.value,
            )
        self.report = report
        self.devices = devices
