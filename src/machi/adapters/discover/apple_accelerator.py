"""Apple accelerator provider (MACHI 2.3).

Reads ``system_profiler SPDisplaysDataType -json``. Domain owns
``AcceleratorObservation``; this module owns the Apple source.
It does not treat system RAM as dedicated VRAM and does not require
PCI identity.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from machi.adapters.discover.accelerator_provider import ProviderInspectResult
from machi.adapters.discover.command import (
    CommandOutcome,
    CommandRunner,
    bounded_detail,
    run_command,
)
from machi.discover.accelerator import (
    non_observed_provider_report,
    observed_provider_report,
)
from machi.discover.contracts import (
    AcceleratorDevice,
    AcceleratorDeviceType,
    AcceleratorMemoryTopology,
    AcceleratorSource,
    AcceleratorVendor,
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
    ProviderInspectionStatus,
)
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import Unresolved, UnresolvedReason, is_resolved

PROVIDER_ID = "apple"
_SYSTEM_PROFILER = "system_profiler"
_APPLE_ARGV = (_SYSTEM_PROFILER, "SPDisplaysDataType", "-json")
_TIMEOUT_SECONDS = 45.0
_SLUG = re.compile(r"[^a-z0-9]+")
_UNIFIED_MEMORY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "unified topology has no dedicated accelerator memory total",
)


def parse_apple_displays_json(text: str) -> tuple[AcceleratorDevice, ...]:
    """Parse ``system_profiler`` JSON into Apple accelerator devices.

    Only Apple GPUs are emitted. Unified topology never carries a fake
    dedicated memory total. Non-Apple GPUs on macOS are skipped, which
    is a successful empty Apple inspection when none remain.
    """
    if not isinstance(text, str):
        raise ValidationError(
            "Apple displays JSON must be text",
            actual_type=type(text).__name__,
        )
    try:
        payload: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("Apple displays JSON is malformed") from exc
    if not isinstance(payload, dict):
        raise ValidationError("Apple displays JSON must be an object")
    entries = payload.get("SPDisplaysDataType")
    if entries is None:
        raise ValidationError("SPDisplaysDataType is missing")
    if not isinstance(entries, list):
        raise ValidationError("SPDisplaysDataType must be a list")
    devices: list[AcceleratorDevice] = []
    used_identities: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValidationError("SPDisplaysDataType entries must be objects")
        if not _is_apple_gpu(item):
            continue
        identity = _unique_identity(_apple_identity(item), used_identities)
        used_identities.add(identity)
        devices.append(_device_from_item(item, ordinal=len(devices), identity=identity))
    return tuple(devices)


def _is_apple_gpu(item: Mapping[str, object]) -> bool:
    device_type = str(item.get("sppci_device_type", "")).strip().lower()
    if device_type and "gpu" not in device_type:
        return False
    vendor = str(item.get("spdisplays_vendor", "")).strip().lower()
    model = str(item.get("sppci_model", "")).strip().lower()
    if "apple" in vendor:
        return True
    return model.startswith("apple")


def _device_from_item(
    item: Mapping[str, object], *, ordinal: int, identity: str
) -> AcceleratorDevice:
    model = str(item.get("sppci_model", "")).strip()
    if "/" in model or "\\" in model:
        raise ValidationError("Apple GPU model must not contain a path")
    if model:
        model_name, model_status = model, ObservationStatus.NORMALIZED
    else:
        model_name, model_status = "", ObservationStatus.UNOBSERVED
    vendor_raw = str(item.get("spdisplays_vendor", "")).strip()
    bus = str(item.get("sppci_bus", "")).strip()
    raw = _apple_raw(model=model, vendor=vendor_raw, bus=bus)
    return AcceleratorDevice(
        ordinal=ordinal,
        vendor=AcceleratorVendor.APPLE,
        vendor_status=ObservationStatus.NORMALIZED,
        model_name=model_name,
        model_status=model_status,
        device_type=AcceleratorDeviceType.INTEGRATED_GPU,
        device_type_status=ObservationStatus.NORMALIZED,
        memory_topology=AcceleratorMemoryTopology.UNIFIED,
        memory_topology_status=ObservationStatus.NORMALIZED,
        memory_total_bytes=_UNIFIED_MEMORY,
        memory_total_status=ObservationStatus.UNOBSERVED,
        identity=identity,
        source=AcceleratorSource.APPLE_DISPLAYS,
        raw=raw,
    )


def _apple_identity(item: Mapping[str, object]) -> str:
    model = str(item.get("sppci_model", "")).strip()
    slug = _SLUG.sub("-", model.lower()).strip("-")
    return slug or "apple-gpu"


def _unique_identity(base: str, used: set[str]) -> str:
    if base not in used:
        return base
    suffix = 1
    while f"{base}-{suffix}" in used:
        suffix += 1
    return f"{base}-{suffix}"


def _apple_raw(*, model: str, vendor: str, bus: str) -> str:
    pieces: list[str] = []
    if model and "/" not in model and "\\" not in model:
        pieces.append(f"sppci_model={model}")
    if vendor and "/" not in vendor and "\\" not in vendor:
        pieces.append(f"spdisplays_vendor={vendor}")
    if bus and "/" not in bus and "\\" not in bus:
        pieces.append(f"sppci_bus={bus}")
    return ";".join(pieces)[:160]


class AppleAcceleratorProvider:
    """Observe Apple GPUs on macOS. Not applicable on other OS families."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        displays_json: str | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self._displays_json = displays_json
        self._runner = runner or run_command

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        """Apple accelerator observation is meaningful only on macOS."""
        return (
            os_observation.os_status is ObservationStatus.NORMALIZED
            and is_resolved(os_observation.os_family)
            and os_observation.os_family is OSFamily.MACOS
        )

    def inspect(self) -> ProviderInspectResult:
        """Enumerate Apple GPUs. Missing tooling is unavailable, not zero."""
        if self._displays_json is not None:
            return self._from_json(self._displays_json)
        outcome = self._runner(_APPLE_ARGV, _TIMEOUT_SECONDS)
        return self._from_outcome(outcome)

    def _from_outcome(self, outcome: CommandOutcome) -> ProviderInspectResult:
        if not outcome.found:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.UNAVAILABLE,
                    detail="system_profiler was not found",
                )
            )
        if outcome.timed_out:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail="system_profiler timed out",
                )
            )
        if outcome.returncode != 0:
            detail = bounded_detail(outcome.stderr) or "system_profiler exited non-zero"
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=detail,
                )
            )
        return self._from_json(outcome.stdout)

    def _from_json(self, text: str) -> ProviderInspectResult:
        try:
            devices = parse_apple_displays_json(text)
        except ValidationError as exc:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=bounded_detail(exc.message)
                    or "system_profiler output was malformed",
                )
            )
        return ProviderInspectResult(
            observed_provider_report(PROVIDER_ID, len(devices)),
            devices,
        )
