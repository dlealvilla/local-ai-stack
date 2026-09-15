"""NVIDIA accelerator provider (MACHI 2.3).

Reads ``nvidia-smi`` machine-readable CSV. Domain owns
``AcceleratorObservation``; this module owns NVIDIA source I/O.
It does not install drivers, change MIG/persistence, allocate
workloads, or compute safe VRAM.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

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

PROVIDER_ID = "nvidia"
_NVIDIA_SMI = "nvidia-smi"
_QUERY_FIELDS = ("index", "uuid", "name", "memory.total")
_NVIDIA_ARGV = (
    _NVIDIA_SMI,
    f"--query-gpu={','.join(_QUERY_FIELDS)}",
    "--format=csv,noheader,nounits",
)
_TIMEOUT_SECONDS = 8.0
_MIB_BYTES = 1024 * 1024
_NA_TOKENS = frozenset({"", "[n/a]", "n/a", "na"})


def parse_nvidia_smi_csv(text: str) -> tuple[AcceleratorDevice, ...]:
    """Parse ``nvidia-smi`` CSV into generic devices.

    Memory values are MiB and convert as integer ``value * 1024 * 1024``.
    Unknown memory stays Unresolved, never zero. Malformed rows fail closed
    rather than dropping a GPU.
    """
    if not isinstance(text, str):
        raise ValidationError(
            "nvidia-smi CSV must be text",
            actual_type=type(text).__name__,
        )
    stripped = text.strip()
    if not stripped:
        return ()
    rows = tuple(csv.reader(io.StringIO(stripped), skipinitialspace=True))
    devices: list[AcceleratorDevice] = []
    seen_indexes: set[int] = set()
    for raw_row in rows:
        cells = [cell.strip() for cell in raw_row]
        if not any(cells):
            continue
        device = _device_from_row(cells, ordinal=len(devices))
        if device.identity in {item.identity for item in devices}:
            raise ValidationError(
                "nvidia-smi reported a duplicate device identity",
                identity=device.identity,
            )
        nvidia_index = _row_index(cells)
        if nvidia_index in seen_indexes:
            raise ValidationError(
                "nvidia-smi reported a duplicate GPU index",
                index=nvidia_index,
            )
        seen_indexes.add(nvidia_index)
        devices.append(device)
    return tuple(devices)


def _row_index(cells: Sequence[str]) -> int:
    if len(cells) != len(_QUERY_FIELDS):
        raise ValidationError(
            "nvidia-smi row has the wrong number of fields",
            count=len(cells),
        )
    index_text = cells[0]
    if not index_text.isdigit():
        raise ValidationError(
            "nvidia-smi index is not an integer",
            raw=index_text,
        )
    return int(index_text)


def _device_from_row(cells: Sequence[str], *, ordinal: int) -> AcceleratorDevice:
    index = _row_index(cells)
    uuid = cells[1]
    name = cells[2]
    memory_text = cells[3]
    identity = _nvidia_identity(index=index, uuid=uuid)
    memory_total, memory_status = _nvidia_memory(memory_text)
    model_name, model_status = _nvidia_model(name)
    raw = _nvidia_raw(
        index=index,
        uuid=uuid,
        name=name,
        memory_text=memory_text,
    )
    return AcceleratorDevice(
        ordinal=ordinal,
        vendor=AcceleratorVendor.NVIDIA,
        vendor_status=ObservationStatus.NORMALIZED,
        model_name=model_name,
        model_status=model_status,
        device_type=AcceleratorDeviceType.DISCRETE_GPU,
        device_type_status=ObservationStatus.NORMALIZED,
        memory_topology=AcceleratorMemoryTopology.DISCRETE,
        memory_topology_status=ObservationStatus.NORMALIZED,
        memory_total_bytes=memory_total,
        memory_total_status=memory_status,
        identity=identity,
        source=AcceleratorSource.NVIDIA_SMI,
        raw=raw,
    )


def _nvidia_identity(*, index: int, uuid: str) -> str:
    token = uuid.strip()
    if _is_na(token):
        return f"nvidia-index-{index}"
    if "/" in token or "\\" in token or " " in token:
        raise ValidationError(
            "nvidia-smi uuid must be a path-free identity",
            raw=token,
        )
    if len(token) > 80:
        raise ValidationError("nvidia-smi uuid exceeds the identity bound")
    return token


def _nvidia_model(name: str) -> tuple[str, ObservationStatus]:
    token = name.strip()
    if _is_na(token):
        return "", ObservationStatus.UNOBSERVED
    if "/" in token or "\\" in token:
        raise ValidationError("nvidia-smi name must not contain a path")
    if len(token) > 96:
        token = token[:96]
    return token, ObservationStatus.NORMALIZED


def _nvidia_memory(text: str) -> tuple[int | Unresolved, ObservationStatus]:
    token = text.strip()
    if _is_na(token):
        return (
            Unresolved(
                UnresolvedReason.NOT_MEASURED,
                "nvidia-smi did not report a dedicated memory total",
            ),
            ObservationStatus.UNOBSERVED,
        )
    if not token.isdigit():
        raise ValidationError(
            "nvidia-smi memory.total is not an integer",
            raw=token,
        )
    mib = int(token)
    if mib <= 0:
        raise ValidationError(
            "nvidia-smi memory.total must be greater than zero",
            raw=token,
        )
    return mib * _MIB_BYTES, ObservationStatus.NORMALIZED


def _nvidia_raw(*, index: int, uuid: str, name: str, memory_text: str) -> str:
    uuid_part = uuid.strip() if not _is_na(uuid) else ""
    name_part = name.strip() if not _is_na(name) else ""
    pieces = [f"index={index}"]
    if uuid_part and "/" not in uuid_part and "\\" not in uuid_part:
        pieces.append(f"uuid={uuid_part}")
    if name_part and "/" not in name_part and "\\" not in name_part:
        pieces.append(f"name={name_part}")
    if memory_text.strip() and "/" not in memory_text:
        pieces.append(f"memory.total={memory_text.strip()}")
    raw = ";".join(pieces)
    return raw[:160]


def _is_na(value: str) -> bool:
    return value.strip().lower() in _NA_TOKENS


class NvidiaAcceleratorProvider:
    """Observe NVIDIA GPUs assigned to this execution context."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        csv_text: str | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self._csv_text = csv_text
        self._runner = runner or run_command

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        """NVIDIA tooling may exist on Linux, macOS, or Windows hosts."""
        if os_observation.os_status is ObservationStatus.UNOBSERVED:
            return True
        if not is_resolved(os_observation.os_family):
            return True
        return os_observation.os_family in {
            OSFamily.LINUX,
            OSFamily.MACOS,
            OSFamily.WINDOWS,
        }

    def inspect(self) -> ProviderInspectResult:
        """Enumerate NVIDIA devices. Missing tooling is unavailable, not zero."""
        if self._csv_text is not None:
            return self._from_csv(self._csv_text)
        outcome = self._runner(_NVIDIA_ARGV, _TIMEOUT_SECONDS)
        return self._from_outcome(outcome)

    def _from_outcome(self, outcome: CommandOutcome) -> ProviderInspectResult:
        if not outcome.found:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.UNAVAILABLE,
                    detail="nvidia-smi was not found",
                )
            )
        if outcome.timed_out:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail="nvidia-smi timed out",
                )
            )
        if outcome.returncode != 0:
            detail = bounded_detail(outcome.stderr) or "nvidia-smi exited non-zero"
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=detail,
                )
            )
        return self._from_csv(outcome.stdout)

    def _from_csv(self, text: str) -> ProviderInspectResult:
        try:
            devices = parse_nvidia_smi_csv(text)
        except ValidationError as exc:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=bounded_detail(exc.message)
                    or "nvidia-smi output was malformed",
                )
            )
        return ProviderInspectResult(
            observed_provider_report(PROVIDER_ID, len(devices)),
            devices,
        )
