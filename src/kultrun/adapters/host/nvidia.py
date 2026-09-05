"""The NVIDIA supplement — smallest vendor interface that closes a real gap.

**Why it exists.** The Stage 1.1 spike found that hwloc on the reference
host reports an NVIDIA device's presence and nothing about its memory: the
Ubuntu build carries no NVML plugin, so the device is a PCI entry with DRM
render nodes. Accelerator memory and driver version are exactly what Stage
1.2 needs in order to compute a safe VRAM layer. The gap is measured, not
predicted, and this provider is the smallest thing that closes it.

**Why it is authoritative for accelerator presence.** hwloc found four
NVIDIA display devices on the reference host; this provider found one. The
other three are physically present and not assigned to this container.
Trusting the enumeration would have claimed four times the accelerator
memory that exists — a capacity error no unit test could have caught. So
this provider answers True to `reports_accelerator_assignment`.

That is a **field-specific** rule justified by a measurement, not a general
"vendor beats hwloc" precedence. hwloc remains authoritative for CPU
topology, and a disagreement about anything else still surfaces as a
conflict.

**No NVIDIA vocabulary leaves this file.** Values are normalized onto
platform capability paths, and nothing downstream learns that NVML, CUDA or
`nvidia-smi` exist. A device is identified by its PCI bus address — a stable
host-scoped attribute — never by a provider-local handle or index.
"""

from __future__ import annotations

from typing import Final

from kultrun.adapters.host import _process
from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import Observation, ProviderReport, ProviderStatus
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe

PROVIDER: Final = Name("nvidia")

#: Queried fields, in order. `pci.bus_id` is first because it is the key the
#: platform identifies a device by.
_FIELDS: Final = (
    "pci.bus_id",
    "name",
    "memory.total",
    "driver_version",
)

_MIB: Final = 1024 * 1024


class NvidiaProvider:
    """Observes assigned NVIDIA accelerators through the vendor CLI."""

    provider = PROVIDER

    def __init__(self, clock: Clock | None = None, *, csv: str | None = None) -> None:
        self._clock = clock or SystemClock()
        self._csv = csv  # supplied when replaying a captured fixture

    @property
    def reports_accelerator_assignment(self) -> bool:
        """True: this reports devices assigned to this execution context."""
        return True

    def observe(self) -> ProviderReport:
        if self._csv is not None:
            return self._report(self._csv, NOT_PROVIDED, ProviderStatus.PARTIAL)

        if _process.which("nvidia-smi") is None:
            # A host with no NVIDIA tooling is not a host with no accelerator.
            # The platform must still be described, so this is a fact rather
            # than a failure, and affected values stay unresolved.
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.UNAVAILABLE,
                observed_at=self._clock.now(),
                detail="nvidia-smi not on PATH; accelerator detail unresolved",
            )

        version = self._version()
        result = _process.run(
            [
                "nvidia-smi",
                f"--query-gpu={','.join(_FIELDS)}",
                "--format=csv,noheader,nounits",
            ]
        )
        if not result.usable:
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.FAILED,
                observed_at=self._clock.now(),
                provider_version=version,
                detail=result.detail,
            )
        return self._report(result.stdout, version, ProviderStatus.PARTIAL)

    def _report(
        self, csv: str, version: Maybe[str], status: ProviderStatus
    ) -> ProviderReport:
        observations = tuple(_observe(csv))
        return ProviderReport(
            provider=PROVIDER,
            status=status if observations else ProviderStatus.AVAILABLE,
            observed_at=self._clock.now(),
            provider_version=version,
            observations=observations,
            detail=(
                "accelerator identity, memory and driver for devices assigned "
                "to this context"
            ),
        )

    def _version(self) -> Maybe[str]:
        result = _process.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        )
        if not result.usable:
            return NOT_PROVIDED
        first = result.stdout.strip().splitlines()
        return first[0].strip() if first else NOT_PROVIDED


def _observe(csv: str) -> list[Observation]:
    found: list[Observation] = []
    for line in csv.strip().splitlines():
        cells = [cell.strip() for cell in line.split(",")]
        if len(cells) != len(_FIELDS):
            continue
        bus, name, memory_mib, driver = cells
        key = _normalize_bus(bus)
        if not key:
            continue

        def measured(field: str, value: object, key: str = key) -> None:
            found.append(
                Observation(
                    path=f"accelerator.{key}.{field}",
                    value=value,  # type: ignore[arg-type]
                    derivation=Derivation.MEASURED,
                    confidence=Confidence.HIGH,
                )
            )

        measured("vendor", "nvidia")
        if name:
            measured("model_name", name)
        if memory_mib.isdigit():
            measured("memory_total_bytes", int(memory_mib) * _MIB)
        if driver:
            measured("driver_version", driver)
        # A discrete NVIDIA accelerator has its own memory. Recording this
        # explicitly is what lets a unified-memory host be represented
        # differently rather than being forced into a discrete-GPU shape.
        measured("unified_memory", False)
    return found


def _normalize_bus(bus: str) -> str:
    """Normalize `00000000:82:00.0` to the `0000:82:00.0` form hwloc uses.

    The two tools spell the same address differently. Normalizing here is
    what allows the service to recognise that they are describing one device
    rather than two — and doing it in the adapter keeps the vendor's
    spelling out of the platform.
    """
    stripped = bus.strip().lower()
    if not stripped:
        return ""
    parts = stripped.split(":")
    if len(parts) == 3:
        domain, bus_id, rest = parts
        return f"{int(domain, 16):04x}:{bus_id}:{rest}"
    return stripped


def build(clock: Clock | None = None) -> NvidiaProvider:
    """Factory for the adapter registry."""
    return NvidiaProvider(clock)


def replay(csv: str, clock: Clock | None = None) -> NvidiaProvider:
    """Replay a captured provider fixture through the real parsing path."""
    return NvidiaProvider(clock, csv=csv)
