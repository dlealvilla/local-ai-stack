"""Intel accelerator provider (MACHI 2.3).

Reads host ``xpu-smi discovery`` JSON, with ``xpumcli`` as an alternate
executable for the same Intel SMI family. Domain owns
``AcceleratorObservation``; this module owns Intel source I/O. It does
not install oneAPI, mutate firmware, or treat tiles as top-level devices.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence

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

PROVIDER_ID = "intel"
_XPU_SMI = "xpu-smi"
_XPUMCLI = "xpumcli"
_DISCOVERY_REST = ("discovery", "-j")
_TIMEOUT_SECONDS = 20.0
_MIB_BYTES = 1024 * 1024
_MAX_DEVICES = 64
_NA_TOKENS = frozenset(
    {"", "[n/a]", "n/a", "na", "none", "null", "unknown", "not applicable"}
)
_ALLOC_MARKERS = ("alloc", "allocatable", "max_mem")
_MISSING_MEMORY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "xpu-smi did not report a dedicated memory total",
)
_UNIFIED_MEMORY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "unified topology has no dedicated accelerator memory total",
)


def parse_intel_discovery_json(
    discovery_text: str,
    dump_text: str = "",
) -> tuple[AcceleratorDevice, ...]:
    """Parse Intel SMI discovery JSON into generic devices.

    One ``device_list`` GPU entry is one ``AcceleratorDevice``. Tile counts
    stay in raw evidence. Memory Physical Size is used; Max Mem Alloc Size
    is ignored.
    """
    payload = _load_json(discovery_text, what="xpu-smi discovery")
    entries = _device_entries(payload)
    try:
        memory_by_key = _memory_index(dump_text)
    except ValidationError:
        memory_by_key = {}
    devices: list[AcceleratorDevice] = []
    seen: set[str] = set()
    for ordinal, item in enumerate(entries):
        device = _device_from_entry(item, ordinal=ordinal, memory_by_key=memory_by_key)
        if device.identity in seen:
            raise ValidationError(
                "xpu-smi reported a duplicate device identity",
                identity=device.identity,
            )
        seen.add(device.identity)
        devices.append(device)
    if len(devices) > _MAX_DEVICES:
        raise ValidationError(
            "xpu-smi reported more devices than the observation bound",
            count=len(devices),
        )
    return tuple(devices)


def _load_json(text: str, *, what: str) -> object:
    if not isinstance(text, str):
        raise ValidationError(
            f"{what} JSON must be text",
            actual_type=type(text).__name__,
        )
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{what} JSON is malformed") from exc


def _device_entries(payload: object) -> tuple[Mapping[str, object], ...]:
    items: Sequence[object]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        has_list_key = any(
            str(key).lower() in {"device_list", "devices"} for key in payload
        )
        if has_list_key:
            listed = _get(payload, "device_list", "devices")
            if listed is None:
                items = ()
            elif not isinstance(listed, list):
                raise ValidationError("xpu-smi device_list must be a list")
            else:
                items = listed
        elif _is_gpu_entry(payload):
            items = (payload,)
        else:
            raise ValidationError("xpu-smi discovery JSON is missing device_list")
    else:
        raise ValidationError(
            "xpu-smi discovery JSON must be an object or array",
            actual_type=type(payload).__name__,
        )
    gpus: list[Mapping[str, object]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError(
                "xpu-smi device entries must be objects",
                actual_type=type(item).__name__,
            )
        if not _is_gpu_entry(item):
            continue
        gpus.append(item)
    return tuple(gpus)


def _is_gpu_entry(item: Mapping[str, object]) -> bool:
    kind = _text(_get(item, "device_type", "type")).lower()
    if kind in {"nic", "cpu", "network"}:
        return False
    if kind and kind != "gpu":
        return False
    return any(
        _get(item, name) is not None
        for name in ("device_id", "uuid", "device_name", "pci_bdf_address")
    )


def _memory_index(dump_text: str) -> dict[str, int]:
    stripped = dump_text.strip()
    if not stripped:
        return {}
    if stripped.startswith(("{", "[")):
        return _memory_from_json(stripped)
    return _memory_from_csv(stripped)


def _memory_from_json(text: str) -> dict[str, int]:
    payload = _load_json(text, what="xpu-smi dump")
    entries = _device_entries(payload)
    indexed: dict[str, int] = {}
    for item in entries:
        bytes_total = _physical_bytes(item)
        if bytes_total is None:
            continue
        for key in _entry_keys(item):
            indexed.setdefault(key, bytes_total)
    return indexed


def _memory_from_csv(text: str) -> dict[str, int]:
    rows = tuple(csv.reader(io.StringIO(text), skipinitialspace=True))
    indexed: dict[str, int] = {}
    for raw_row in rows:
        cells = [cell.strip() for cell in raw_row]
        if not any(cells) or _csv_header(cells):
            continue
        if len(cells) < 4:
            raise ValidationError("xpu-smi dump row has the wrong number of fields")
        device_id = cells[0]
        uuid = cells[2]
        memory_text = cells[3]
        mib = _mib_value(memory_text)
        if mib is None:
            continue
        total = mib * _MIB_BYTES
        indexed.setdefault(f"id:{device_id}", total)
        if uuid and not _is_na(uuid):
            indexed.setdefault(f"uuid:{uuid.lower()}", total)
    return indexed


def _csv_header(cells: Sequence[str]) -> bool:
    first = cells[0].lower()
    return first in {"device id", "device_id", "id"} or first.startswith("device")


def _device_from_entry(
    item: Mapping[str, object],
    *,
    ordinal: int,
    memory_by_key: Mapping[str, int],
) -> AcceleratorDevice:
    device_id = _device_id(item)
    identity = _intel_identity(
        item, device_id=device_id if device_id is not None else ordinal
    )
    model_name, model_status = _intel_model(item)
    unified = _looks_integrated(item, model_name)
    memory_total, memory_status, topology, topology_status, device_type, type_status = (
        _intel_memory_and_type(item, memory_by_key=memory_by_key, unified=unified)
    )
    raw = _intel_raw(item, identity=identity, model_name=model_name)
    return AcceleratorDevice(
        ordinal=ordinal,
        vendor=AcceleratorVendor.INTEL,
        vendor_status=ObservationStatus.NORMALIZED,
        model_name=model_name,
        model_status=model_status,
        device_type=device_type,
        device_type_status=type_status,
        memory_topology=topology,
        memory_topology_status=topology_status,
        memory_total_bytes=memory_total,
        memory_total_status=memory_status,
        identity=identity,
        source=AcceleratorSource.XPU_SMI,
        raw=raw,
    )


def _intel_identity(item: Mapping[str, object], *, device_id: int) -> str:
    uuid = _text(_get(item, "uuid"))
    if uuid and not _is_na(uuid):
        if "/" in uuid or "\\" in uuid or " " in uuid:
            raise ValidationError("xpu-smi uuid must be a path-free identity")
        if len(uuid) > 80:
            raise ValidationError("xpu-smi uuid exceeds the identity bound")
        return uuid
    return f"intel-index-{device_id}"


def _intel_model(item: Mapping[str, object]) -> tuple[str, ObservationStatus]:
    token = _text(_get(item, "device_name", "name"))
    if not token or _is_na(token):
        return "", ObservationStatus.UNOBSERVED
    if "/" in token or "\\" in token:
        raise ValidationError("xpu-smi device name must not contain a path")
    if len(token) > 96:
        token = token[:96]
    return token, ObservationStatus.NORMALIZED


def _looks_integrated(item: Mapping[str, object], model_name: str) -> bool:
    del item, model_name
    return False


def _intel_memory_and_type(
    item: Mapping[str, object],
    *,
    memory_by_key: Mapping[str, int],
    unified: bool,
) -> tuple[
    int | Unresolved,
    ObservationStatus,
    AcceleratorMemoryTopology,
    ObservationStatus,
    AcceleratorDeviceType,
    ObservationStatus,
]:
    if unified:
        return (
            _UNIFIED_MEMORY,
            ObservationStatus.UNOBSERVED,
            AcceleratorMemoryTopology.UNIFIED,
            ObservationStatus.NORMALIZED,
            AcceleratorDeviceType.INTEGRATED_GPU,
            ObservationStatus.NORMALIZED,
        )
    bytes_total = _physical_bytes(item)
    if bytes_total is None:
        for key in _entry_keys(item):
            if key in memory_by_key:
                bytes_total = memory_by_key[key]
                break
    if bytes_total is None:
        return (
            _MISSING_MEMORY,
            ObservationStatus.UNOBSERVED,
            AcceleratorMemoryTopology.DISCRETE,
            ObservationStatus.NORMALIZED,
            AcceleratorDeviceType.DISCRETE_GPU,
            ObservationStatus.NORMALIZED,
        )
    return (
        bytes_total,
        ObservationStatus.NORMALIZED,
        AcceleratorMemoryTopology.DISCRETE,
        ObservationStatus.NORMALIZED,
        AcceleratorDeviceType.DISCRETE_GPU,
        ObservationStatus.NORMALIZED,
    )


def _physical_bytes(item: Mapping[str, object]) -> int | None:
    for key, value in item.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in _ALLOC_MARKERS):
            continue
        if lowered in {"memory_physical_size_byte", "memory_physical_size_bytes"}:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError("xpu-smi memory physical size has the wrong type")
            if value <= 0:
                raise ValidationError(
                    "xpu-smi memory physical size must be greater than zero"
                )
            return value
        if (
            lowered
            in {
                "memory_physical_size",
                "memory_physical_size_mib",
                "memory_physical_size_mb",
            }
            or lowered.replace(" ", "") == "memoryphysicalsize"
        ):
            mib = _mib_value(value)
            if mib is None:
                return None
            return mib * _MIB_BYTES
    return None


def _mib_value(value: object) -> int | None:
    if value is None or _is_na(value):
        return None
    if isinstance(value, bool):
        raise ValidationError("xpu-smi memory physical size has the wrong type")
    if isinstance(value, int):
        if value <= 0:
            raise ValidationError(
                "xpu-smi memory physical size must be greater than zero"
            )
        return value
    if isinstance(value, float):
        if value <= 0:
            raise ValidationError(
                "xpu-smi memory physical size must be greater than zero"
            )
        if abs(value - int(value)) > 1e-6:
            raise ValidationError("xpu-smi memory physical size is not a whole MiB")
        return int(value)
    if not isinstance(value, str):
        raise ValidationError("xpu-smi memory physical size has the wrong type")
    token = value.strip().replace(",", "")
    for suffix in ("mib", "mb"):
        if token.lower().endswith(suffix):
            token = token[: -len(suffix)].strip()
            break
    if not token:
        return None
    try:
        number = float(token)
    except ValueError as exc:
        raise ValidationError("xpu-smi memory physical size is not a number") from exc
    if number <= 0:
        raise ValidationError("xpu-smi memory physical size must be greater than zero")
    if abs(number - int(number)) > 1e-6:
        raise ValidationError("xpu-smi memory physical size is not a whole MiB")
    return int(number)


def _intel_raw(item: Mapping[str, object], *, identity: str, model_name: str) -> str:
    pieces: list[str] = []
    device_id = _device_id(item)
    if device_id is not None:
        pieces.append(f"device_id={device_id}")
    if identity:
        pieces.append(f"uuid={identity}")
    if model_name:
        pieces.append(f"name={model_name}")
    bdf = _text(_get(item, "pci_bdf_address", "bdf"))
    if bdf and "/" not in bdf and "\\" not in bdf:
        pieces.append(f"bdf={bdf}")
    tiles = _get(item, "number_of_tiles", "num_tiles", "tiles")
    if tiles is not None and not _is_na(tiles):
        pieces.append(f"tiles={tiles}")
    return ";".join(pieces)[:160]


def _entry_keys(item: Mapping[str, object]) -> tuple[str, ...]:
    keys: list[str] = []
    device_id = _device_id(item)
    if device_id is not None:
        keys.append(f"id:{device_id}")
        keys.append(f"id:{device_id}.0")
    uuid = _text(_get(item, "uuid"))
    if uuid and not _is_na(uuid):
        keys.append(f"uuid:{uuid.lower()}")
    return tuple(keys)


def _device_id(item: Mapping[str, object]) -> int | None:
    value = _get(item, "device_id")
    if value is None or _is_na(value):
        return None
    if isinstance(value, bool):
        raise ValidationError("xpu-smi device_id has the wrong type")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    raise ValidationError("xpu-smi device_id has the wrong type")


def _get(item: Mapping[str, object], *names: str) -> object | None:
    lowered = {str(key).lower(): value for key, value in item.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def _text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str | int | float):
        return str(value).strip()
    return ""


def _is_na(value: object) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in _NA_TOKENS


class IntelAcceleratorProvider:
    """Observe Intel GPUs listed by Intel SMI tooling on Linux."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        discovery_json: str | None = None,
        dump_text: str = "",
        runner: CommandRunner | None = None,
    ) -> None:
        self._discovery_json = discovery_json
        self._dump_text = dump_text
        self._runner = runner or run_command

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        """Intel SMI observation is meaningful on Linux hosts."""
        return (
            os_observation.os_status is ObservationStatus.NORMALIZED
            and is_resolved(os_observation.os_family)
            and os_observation.os_family is OSFamily.LINUX
        )

    def inspect(self) -> ProviderInspectResult:
        """Enumerate Intel GPUs. Missing tooling is unavailable, not zero."""
        if self._discovery_json is not None:
            return self._from_text(self._discovery_json, self._dump_text)
        executable, outcome = self._discover()
        if executable is None:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.UNAVAILABLE,
                    detail="xpu-smi was not found",
                )
            )
        if outcome.timed_out:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail="xpu-smi timed out",
                )
            )
        if outcome.returncode != 0:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=bounded_detail(outcome.stderr) or "xpu-smi exited non-zero",
                )
            )
        return self._from_text(outcome.stdout, "")

    def _discover(self) -> tuple[str | None, CommandOutcome]:
        primary = self._runner((_XPU_SMI, *_DISCOVERY_REST), _TIMEOUT_SECONDS)
        if primary.found:
            return _XPU_SMI, primary
        secondary = self._runner((_XPUMCLI, *_DISCOVERY_REST), _TIMEOUT_SECONDS)
        if secondary.found:
            return _XPUMCLI, secondary
        return None, primary

    def _from_text(self, discovery_text: str, dump_text: str) -> ProviderInspectResult:
        try:
            devices = parse_intel_discovery_json(discovery_text, dump_text)
        except ValidationError as exc:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=bounded_detail(exc.message)
                    or "xpu-smi output was malformed",
                )
            )
        return ProviderInspectResult(
            observed_provider_report(PROVIDER_ID, len(devices)),
            devices,
        )
