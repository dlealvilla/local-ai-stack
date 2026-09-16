"""Pure accelerator observation helpers (MACHI 2.3).

Domain owns generic ``AcceleratorObservation`` factories. Concrete
vendor readers live in adapters. This module does not read the host,
does not call vendor tools, and does not compute safe GPU memory.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import replace

from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorObservation,
    AcceleratorProviderReport,
    ObservationStatus,
    ProviderInspectionStatus,
)
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_MEASURED

NATIVE_OBSERVER = "native"


def with_ordinal(device: AcceleratorDevice, ordinal: int) -> AcceleratorDevice:
    """Return a copy of ``device`` at a new observation ordinal."""
    return replace(device, ordinal=ordinal)


def number_devices(
    devices: tuple[AcceleratorDevice, ...],
) -> tuple[AcceleratorDevice, ...]:
    """Assign contiguous 0-based ordinals after provider results are combined."""
    return tuple(with_ordinal(device, index) for index, device in enumerate(devices))


def accelerator_observation(
    *,
    devices: tuple[AcceleratorDevice, ...],
    providers: tuple[AcceleratorProviderReport, ...],
    observer: str = NATIVE_OBSERVER,
    observed_at: dt.datetime | None = None,
    clock: Clock | None = None,
) -> AcceleratorObservation:
    """Build one generic observation from provider reports and devices."""
    when = observed_at if observed_at is not None else (clock or SystemClock()).now()
    numbered = number_devices(devices)
    observed = any(
        report.status is ProviderInspectionStatus.OBSERVED for report in providers
    )
    return AcceleratorObservation(
        devices=numbered,
        providers=providers,
        status=(
            ObservationStatus.NORMALIZED if observed else ObservationStatus.UNOBSERVED
        ),
        observed_at=when,
        observer=observer,
    )


def observed_provider_report(
    provider: str,
    device_count: int,
    *,
    detail: str = "",
) -> AcceleratorProviderReport:
    """Record a successful inspection, including a truthful zero-device result."""
    if device_count < 0:
        raise ValidationError(
            "observed provider device_count must not be negative",
            provider=provider,
        )
    return AcceleratorProviderReport(
        provider=provider,
        status=ProviderInspectionStatus.OBSERVED,
        detail=detail,
        device_count=device_count,
    )


def non_observed_provider_report(
    provider: str,
    status: ProviderInspectionStatus,
    *,
    detail: str = "",
) -> AcceleratorProviderReport:
    """Record not-applicable, unavailable, unsupported, or failed inspection."""
    if status is ProviderInspectionStatus.OBSERVED:
        raise ValidationError(
            "observed provider reports must use observed_provider_report",
            provider=provider,
        )
    return AcceleratorProviderReport(
        provider=provider,
        status=status,
        detail=detail,
        device_count=NOT_MEASURED,
    )
