"""AMD accelerator provider (MACHI 2.3).

Reads host ``amd-smi`` JSON. Domain owns ``AcceleratorObservation``;
this module owns AMD source I/O. It does not install ROCm, mutate
partition or firmware state, import ``amdsmi``, or compute safe VRAM.

Memory-unit rule ``amd-smi-mb-mib-as-2-20-bytes-v1``: ``amd-smi static
--json`` reports Instinct VRAM as a whole number with unit ``MB`` or
``MiB``. Those values are treated as binary 2^20-byte units, matching
observed MI300X JSON (196592 MB for 192 GiB HBM). Decimal SI megabytes
are not inferred. Unsupported units fail closed.

Topology rule ``mi300a-or-apu-unified-hbm-discrete-v1``: MI300A / APU
tokens are unified with unresolved dedicated memory even when HBM is
reported. HBM/GDDR without those tokens is discrete. Unknown stays
unresolved; a memory number is not enough to infer discrete.
"""

from __future__ import annotations

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

PROVIDER_ID = "amd"
_AMD_SMI = "amd-smi"
LIST_ARGV = (_AMD_SMI, "list", "--json")
STATIC_ARGV = (_AMD_SMI, "static", "--asic", "--vram", "--bus", "--json")
TIMEOUT_SECONDS = 20.0
MEMORY_UNIT_RULE = "amd-smi-mb-mib-as-2-20-bytes-v1"
TOPOLOGY_RULE = "mi300a-or-apu-unified-hbm-discrete-v1"
_MIB_BYTES = 1024 * 1024
_GIB_BYTES = 1024 * 1024 * 1024
_MAX_DEVICES = 64
_READ_ONLY_SUBCOMMANDS = frozenset({"list", "static"})
_MUTATING_TOKENS = frozenset(
    {
        "set",
        "reset",
        "partition",
        "firmware",
        "power",
        "clock",
        "process",
        "kill",
        "config",
    }
)
_NA_TOKENS = frozenset(
    {
        "",
        "[n/a]",
        "n/a",
        "na",
        "none",
        "null",
        "not applicable",
        "not available",
        "unknown",
    }
)
_UNIFIED_TYPES = frozenset(
    {
        "ddr",
        "ddr4",
        "ddr5",
        "lpddr",
        "lpddr4",
        "lpddr4x",
        "lpddr5",
        "lpddr5x",
    }
)
_DISCRETE_TYPES = frozenset(
    {
        "hbm",
        "hbm2",
        "hbm2e",
        "hbm3",
        "hbm3e",
        "gddr",
        "gddr6",
        "gddr6x",
        "gddr7",
    }
)
_UNIFIED_MEMORY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "unified topology has no dedicated accelerator memory total",
)
_MISSING_MEMORY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "amd-smi did not report a dedicated memory total",
)
_UNKNOWN_TOPOLOGY = Unresolved(
    UnresolvedReason.NOT_MEASURED,
    "amd-smi did not establish memory topology",
)


def assert_read_only_amd_argv(argv: Sequence[str]) -> None:
    """Reject mutating or non-JSON amd-smi invocations."""
    if not argv or argv[0] != _AMD_SMI:
        raise ValidationError("AMD inspect argv must start with amd-smi")
    if len(argv) < 2 or argv[1] not in _READ_ONLY_SUBCOMMANDS:
        raise ValidationError("AMD inspect argv is not a read-only subcommand")
    if "--json" not in argv:
        raise ValidationError("AMD inspect argv must request JSON")
    tokens = {part.lower().lstrip("-") for part in argv[1:]}
    if tokens & _MUTATING_TOKENS:
        raise ValidationError("AMD inspect argv must not mutate the device")


def parse_amd_smi_json(
    list_text: str,
    static_text: str = "",
) -> tuple[AcceleratorDevice, ...]:
    """Parse ``amd-smi list`` and optional ``static`` JSON into devices.

    CPU entries are ignored. Duplicate GPU identities fail closed.
    Unknown VRAM units fail closed. APU/MI300A stays unified without a
    dedicated total.
    """
    listed = _gpu_objects(_load_json(list_text, what="amd-smi list"), what="list")
    static_items: tuple[Mapping[str, object], ...] = ()
    if static_text.strip():
        static_items = _gpu_objects(
            _load_json(static_text, what="amd-smi static"),
            what="static",
        )
    static_by_key = _index_entries(static_items)
    devices: list[AcceleratorDevice] = []
    seen: set[str] = set()
    for ordinal, item in enumerate(listed):
        static_item = _lookup_static(item, static_by_key)
        merged = _merge_maps(item, static_item)
        device = _device_from_entry(merged, ordinal=ordinal)
        if device.identity in seen:
            raise ValidationError(
                "amd-smi reported a duplicate device identity",
                identity=device.identity,
            )
        seen.add(device.identity)
        devices.append(device)
    if len(devices) > _MAX_DEVICES:
        raise ValidationError(
            "amd-smi reported more devices than the observation bound",
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


def _gpu_objects(payload: object, *, what: str) -> tuple[Mapping[str, object], ...]:
    entries = _collection(payload, what=what)
    gpus: list[Mapping[str, object]] = []
    for item in entries:
        if not isinstance(item, dict):
            raise ValidationError(
                f"amd-smi {what} entries must be objects",
                actual_type=type(item).__name__,
            )
        if _is_cpu_entry(item) and not _is_gpu_entry(item):
            continue
        if not _is_gpu_entry(item):
            continue
        gpus.append(item)
    return tuple(gpus)


def _collection(payload: object, *, what: str) -> Sequence[object]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValidationError(
            f"amd-smi {what} JSON must be an object or array",
            actual_type=type(payload).__name__,
        )
    for key in ("gpu", "gpu_data", "gpus", "gpu_list", "devices"):
        value = _get(payload, key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and _is_gpu_entry(value):
            return (value,)
    if _is_gpu_entry(payload) or _is_cpu_entry(payload):
        return (payload,)
    cpu = _get(payload, "cpu") or _get(payload, "cpu_data")
    if isinstance(cpu, list) and not any(
        _get(payload, key) for key in ("gpu", "gpu_data", "gpus")
    ):
        return cpu
    raise ValidationError(f"amd-smi {what} JSON is missing GPU entries")


def _is_cpu_entry(item: Mapping[str, object]) -> bool:
    return _get(item, "cpu", "cpu_id") is not None


def _is_gpu_entry(item: Mapping[str, object]) -> bool:
    if _get(item, "gpu", "gpu_id") is not None:
        return True
    if _nested(item, "asic") is not None or _nested(item, "vram") is not None:
        return True
    return _get(item, "uuid") is not None and _bdf(item) is not None


def _index_entries(
    items: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for item in items:
        for key in _entry_keys(item):
            indexed.setdefault(key, item)
    return indexed


def _lookup_static(
    item: Mapping[str, object],
    indexed: Mapping[str, Mapping[str, object]],
) -> Mapping[str, object] | None:
    for key in _entry_keys(item):
        found = indexed.get(key)
        if found is not None:
            return found
    return None


def _entry_keys(item: Mapping[str, object]) -> tuple[str, ...]:
    keys: list[str] = []
    gpu_id = _gpu_index(item)
    if gpu_id is not None:
        keys.append(f"gpu:{gpu_id}")
    uuid = _uuid(item)
    if uuid:
        keys.append(f"uuid:{uuid.lower()}")
    bdf = _bdf(item)
    if bdf:
        keys.append(f"bdf:{bdf.lower()}")
    return tuple(keys)


def _merge_maps(
    listed: Mapping[str, object],
    static_item: Mapping[str, object] | None,
) -> dict[str, object]:
    merged = dict(listed)
    if static_item is None:
        return merged
    for key, value in static_item.items():
        if key not in merged or merged[key] in (None, "", []):
            merged[key] = value
            continue
        listed_value = merged[key]
        if isinstance(listed_value, dict) and isinstance(value, dict):
            nested = dict(listed_value)
            nested.update(value)
            merged[key] = nested
    return merged


def _device_from_entry(
    item: Mapping[str, object], *, ordinal: int
) -> AcceleratorDevice:
    gpu_id = _gpu_index(item)
    identity = _amd_identity(item, gpu_id=gpu_id if gpu_id is not None else ordinal)
    model_name, model_status = _amd_model(item)
    topology, topology_status, device_type, type_status = _amd_topology(
        item, model_name
    )
    memory_total, memory_status = _amd_memory(item, topology=topology)
    raw = _amd_raw(item, gpu_id=gpu_id, identity=identity, model_name=model_name)
    return AcceleratorDevice(
        ordinal=ordinal,
        vendor=AcceleratorVendor.AMD,
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
        source=AcceleratorSource.AMD_SMI,
        raw=raw,
    )


def _amd_identity(item: Mapping[str, object], *, gpu_id: int) -> str:
    uuid = _uuid(item)
    if uuid:
        if "/" in uuid or "\\" in uuid or " " in uuid:
            raise ValidationError("amd-smi uuid must be a path-free identity")
        if len(uuid) > 80:
            raise ValidationError("amd-smi uuid exceeds the identity bound")
        return uuid
    return f"amd-index-{gpu_id}"


def _amd_model(item: Mapping[str, object]) -> tuple[str, ObservationStatus]:
    asic = _nested(item, "asic")
    board = _nested(item, "board")
    candidates = (
        _text(_get(asic, "market_name") if isinstance(asic, dict) else None),
        _text(_get(board, "product_name") if isinstance(board, dict) else None),
        _text(_get(item, "market_name", "product_name", "name")),
    )
    for token in candidates:
        if not token:
            continue
        if "/" in token or "\\" in token:
            raise ValidationError("amd-smi model must not contain a path")
        if len(token) > 96:
            token = token[:96]
        return token, ObservationStatus.NORMALIZED
    return "", ObservationStatus.UNOBSERVED


def _amd_topology(
    item: Mapping[str, object], model_name: str
) -> tuple[
    AcceleratorMemoryTopology | Unresolved,
    ObservationStatus,
    AcceleratorDeviceType | Unresolved,
    ObservationStatus,
]:
    vram = _nested(item, "vram")
    vram_type = ""
    if isinstance(vram, dict):
        vram_type = _text(_get(vram, "type")).lower().replace(" ", "")
    blob = f"{model_name} {vram_type}".lower()
    if "mi300a" in blob or _has_apu_token(model_name) or vram_type in _UNIFIED_TYPES:
        return (
            AcceleratorMemoryTopology.UNIFIED,
            ObservationStatus.NORMALIZED,
            AcceleratorDeviceType.INTEGRATED_GPU,
            ObservationStatus.NORMALIZED,
        )
    if vram_type in _DISCRETE_TYPES or _looks_discrete_instinct(model_name):
        return (
            AcceleratorMemoryTopology.DISCRETE,
            ObservationStatus.NORMALIZED,
            AcceleratorDeviceType.DISCRETE_GPU,
            ObservationStatus.NORMALIZED,
        )
    return (
        _UNKNOWN_TOPOLOGY,
        ObservationStatus.UNOBSERVED,
        Unresolved(
            UnresolvedReason.NOT_MEASURED,
            "amd-smi did not establish device type",
        ),
        ObservationStatus.UNOBSERVED,
    )


def _amd_memory(
    item: Mapping[str, object],
    *,
    topology: AcceleratorMemoryTopology | Unresolved,
) -> tuple[int | Unresolved, ObservationStatus]:
    if is_resolved(topology) and topology is AcceleratorMemoryTopology.UNIFIED:
        return _UNIFIED_MEMORY, ObservationStatus.UNOBSERVED
    if not (is_resolved(topology) and topology is AcceleratorMemoryTopology.DISCRETE):
        return _MISSING_MEMORY, ObservationStatus.UNOBSERVED
    vram = _nested(item, "vram")
    if not isinstance(vram, dict):
        return _MISSING_MEMORY, ObservationStatus.UNOBSERVED
    size = _get(vram, "size")
    if size is None or _is_na(size):
        return _MISSING_MEMORY, ObservationStatus.UNOBSERVED
    return _convert_vram_size(size), ObservationStatus.NORMALIZED


def _convert_vram_size(size: object) -> int:
    if isinstance(size, bool):
        raise ValidationError("amd-smi vram size has the wrong type")
    if isinstance(size, int):
        return _require_positive_bytes(size * _MIB_BYTES)
    if isinstance(size, float):
        if size != int(size):
            raise ValidationError("amd-smi vram size is not a whole number")
        return _require_positive_bytes(int(size) * _MIB_BYTES)
    if isinstance(size, str):
        token, unit = _split_size_text(size)
        return _scale_vram(token, unit)
    if isinstance(size, dict):
        value = _get(size, "value")
        unit = _text(_get(size, "unit"))
        if value is None or _is_na(value):
            raise ValidationError("amd-smi vram size is missing a value")
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise ValidationError("amd-smi vram size value has the wrong type")
        if isinstance(value, str):
            number, parsed_unit = _split_size_text(value)
            return _scale_vram(number, parsed_unit or unit)
        if isinstance(value, float) and value != int(value):
            raise ValidationError("amd-smi vram size is not a whole number")
        return _scale_vram(int(value), unit)
    raise ValidationError("amd-smi vram size has the wrong type")


def _split_size_text(text: str) -> tuple[int, str]:
    token = text.strip()
    if _is_na(token):
        raise ValidationError("amd-smi vram size is missing")
    parts = token.replace(",", "").split()
    if not parts:
        raise ValidationError("amd-smi vram size is missing")
    if not parts[0].replace(".", "", 1).isdigit():
        raise ValidationError("amd-smi vram size is not a number")
    number = float(parts[0])
    if number != int(number):
        raise ValidationError("amd-smi vram size is not a whole number")
    unit = parts[1] if len(parts) > 1 else "MB"
    return int(number), unit


def _scale_vram(value: int, unit: str) -> int:
    normalized = unit.strip().lower().replace(" ", "")
    if normalized in {"", "mb", "mib"}:
        return _require_positive_bytes(value * _MIB_BYTES)
    if normalized in {"gb", "gib"}:
        return _require_positive_bytes(value * _GIB_BYTES)
    if normalized in {"b", "byte", "bytes"}:
        return _require_positive_bytes(value)
    raise ValidationError("amd-smi vram unit is not supported", unit=unit)


def _require_positive_bytes(total: int) -> int:
    if total <= 0:
        raise ValidationError(
            "amd-smi vram size must be greater than zero",
            total=total,
        )
    return total


def _amd_raw(
    item: Mapping[str, object],
    *,
    gpu_id: int | None,
    identity: str,
    model_name: str,
) -> str:
    pieces: list[str] = []
    if gpu_id is not None:
        pieces.append(f"gpu={gpu_id}")
    if identity.startswith("amd-index-"):
        pieces.append(f"id={identity}")
    elif identity:
        pieces.append(f"uuid={identity}")
    if model_name:
        pieces.append(f"name={model_name}")
    bdf = _bdf(item)
    if bdf and "/" not in bdf and "\\" not in bdf:
        pieces.append(f"bdf={bdf}")
    vram = _nested(item, "vram")
    if isinstance(vram, dict):
        vram_type = _text(_get(vram, "type"))
        if vram_type:
            pieces.append(f"vram.type={vram_type}")
        size = _get(vram, "size")
        if isinstance(size, dict):
            value = _get(size, "value")
            unit = _text(_get(size, "unit"))
            if value is not None and not _is_na(value):
                pieces.append(f"vram.size={value}{unit}")
        elif size is not None and not _is_na(size) and not isinstance(size, dict):
            pieces.append(f"vram.size={size}")
    raw = ";".join(pieces)
    return raw[:160]


def _gpu_index(item: Mapping[str, object]) -> int | None:
    value = _get(item, "gpu", "gpu_id")
    if value is None or _is_na(value):
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.isdigit():
            return int(value)
        raise ValidationError("amd-smi gpu index has the wrong type")
    return value


def _uuid(item: Mapping[str, object]) -> str:
    token = _text(_get(item, "uuid", "hip_uuid"))
    return "" if _is_na(token) else token


def _bdf(item: Mapping[str, object]) -> str | None:
    bus = _nested(item, "bus")
    token = _text(_get(item, "bdf"))
    if not token and isinstance(bus, dict):
        token = _text(_get(bus, "bdf"))
    return None if not token or _is_na(token) else token


def _nested(item: Mapping[str, object], name: str) -> object | None:
    return _get(item, name)


def _get(item: Mapping[str, object] | None, *names: str) -> object | None:
    if item is None:
        return None
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


def _has_apu_token(model_name: str) -> bool:
    tokens = {part for part in model_name.lower().replace("_", " ").split() if part}
    return "apu" in tokens


def _looks_discrete_instinct(model_name: str) -> bool:
    lowered = model_name.lower()
    return "instinct" in lowered and "mi300a" not in lowered


class AmdAcceleratorProvider:
    """Observe AMD GPUs assigned to this Linux execution context."""

    provider_id = PROVIDER_ID

    def __init__(
        self,
        *,
        list_json: str | None = None,
        static_json: str | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self._list_json = list_json
        self._static_json = static_json
        self._runner = runner or run_command

    def applicable(self, os_observation: OSArchitectureObservation) -> bool:
        """AMD SMI observation is meaningful on Linux hosts."""
        return (
            os_observation.os_status is ObservationStatus.NORMALIZED
            and is_resolved(os_observation.os_family)
            and os_observation.os_family is OSFamily.LINUX
        )

    def inspect(self) -> ProviderInspectResult:
        """Enumerate AMD GPUs. Missing tooling is unavailable, not zero."""
        if self._list_json is not None:
            return self._from_json(self._list_json, self._static_json or "")
        list_outcome = self._run(LIST_ARGV)
        if not list_outcome.found:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.UNAVAILABLE,
                    detail="amd-smi was not found",
                )
            )
        if list_outcome.timed_out:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail="amd-smi timed out",
                )
            )
        if list_outcome.returncode != 0:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=bounded_detail(list_outcome.stderr)
                    or "amd-smi exited non-zero",
                )
            )
        static_text = ""
        try:
            listed = _gpu_objects(
                _load_json(list_outcome.stdout, what="amd-smi list"),
                what="list",
            )
        except ValidationError as exc:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=(
                        bounded_detail(exc.message) or "amd-smi output was malformed"
                    ),
                )
            )
        if listed:
            static_outcome = self._run(STATIC_ARGV)
            if (
                static_outcome.found
                and not static_outcome.timed_out
                and static_outcome.returncode == 0
            ):
                static_text = static_outcome.stdout
        return self._from_json(list_outcome.stdout, static_text)

    def _run(self, argv: Sequence[str]) -> CommandOutcome:
        assert_read_only_amd_argv(argv)
        return self._runner(argv, TIMEOUT_SECONDS)

    def _from_json(self, list_text: str, static_text: str) -> ProviderInspectResult:
        try:
            devices = parse_amd_smi_json(list_text, static_text)
        except ValidationError as exc:
            return ProviderInspectResult(
                non_observed_provider_report(
                    PROVIDER_ID,
                    ProviderInspectionStatus.FAILED,
                    detail=(
                        bounded_detail(exc.message) or "amd-smi output was malformed"
                    ),
                )
            )
        return ProviderInspectResult(
            observed_provider_report(PROVIDER_ID, len(devices)),
            devices,
        )
