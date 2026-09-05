"""hwloc — the general topology provider.

**What the Stage 1.1 spike established on the reference host**, hwloc
2.10.0 from Ubuntu 24.04's `apt`:

*Answers well:* CPU vendor and model, socket, core and thread counts, cache
hierarchy, NUMA nodes, total memory (`local_memory` on the NUMA node), and
the PCI tree including which devices exist.

*Does not answer:* accelerator memory, driver version, operating-system
release, filesystem mounts. The Ubuntu build ships no CUDA or NVML plugin,
so an NVIDIA device appears as a PCI device with a vendor identifier and
DRM render nodes, and nothing about its memory.

That is not a defect. hwloc's own documentation states that platforms "will
only report a subset" of its information, and its accelerator
interoperability is largely about *locality* rather than device detail. The
gaps are why two small supplements exist, and the fact that hwloc is
excellent at what it does is why Kultrun does not write topology
enumeration.

**It reports the physical bus, not this container's allocation.** On the
reference host hwloc found four NVIDIA display devices where one was
assigned. It therefore answers False to `reports_accelerator_assignment`,
and the service treats its device list as evidence rather than as the set of
accelerators Kultrun may use.

Parsed from `lstopo-no-graphics --output-format xml`, which is documented
stable output, rather than through a C binding — no compiled dependency, and
the raw XML is what the provider fixture captures.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Final

from kultrun.adapters.host import _process
from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import (
    Observation,
    ProviderReport,
    ProviderStatus,
)
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe

PROVIDER: Final = Name("hwloc")

#: PCI class 0x0300 is a display controller. An accelerator that presents as
#: something else is not recognised here, and is left to a vendor provider.
_DISPLAY_CLASS: Final = "0300"

#: PCI vendor identifiers of **compute accelerator** vendors, mapped to the
#: platform's normalized vocabulary.
#:
#: A display-class device whose vendor is not here is not asserted to be an
#: accelerator. That distinction was measured rather than assumed: the Stage
#: 1.1 reference host carries an ASPEED management VGA (`1a03`) alongside its
#: NVIDIA devices, as most servers do. Treating every display controller as
#: an accelerator would give a CPU-only host one phantom accelerator with an
#: unknown vendor and unknown memory — on the shape where a false accelerator
#: is most likely to go unnoticed.
#:
#: Devices that are filtered out are not lost: the raw topology is what the
#: provider fixture captures, so the full truth remains inspectable.
_PCI_VENDORS: Final = {
    "10de": "nvidia",
    "1002": "amd",
    "8086": "intel",
    "106b": "apple",
}


class HwlocProvider:
    """Observes CPU topology, memory and the PCI tree through hwloc."""

    provider = PROVIDER

    def __init__(self, clock: Clock | None = None, *, xml: str | None = None) -> None:
        self._clock = clock or SystemClock()
        self._xml = xml  # supplied when replaying a captured fixture

    @property
    def reports_accelerator_assignment(self) -> bool:
        """False: hwloc reads the machine's bus, not this context's allocation."""
        return False

    def observe(self) -> ProviderReport:
        version, document = self._read()
        if document is None:
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.UNAVAILABLE,
                observed_at=self._clock.now(),
                provider_version=version,
                detail=self._detail,
            )
        try:
            root = ET.fromstring(document)  # output of a local, trusted tool
        except ET.ParseError as error:
            return ProviderReport(
                provider=PROVIDER,
                status=ProviderStatus.FAILED,
                observed_at=self._clock.now(),
                provider_version=version,
                detail=f"lstopo XML did not parse: {error}",
            )
        return ProviderReport(
            provider=PROVIDER,
            status=ProviderStatus.PARTIAL,
            observed_at=self._clock.now(),
            provider_version=version,
            observations=tuple(_observe(root)),
            detail=(
                "topology and PCI presence only; accelerator memory, driver "
                "version, OS release and mounts are not hwloc's to report"
            ),
        )

    # -- reading -----------------------------------------------------------

    _detail: str | None = None

    def _read(self) -> tuple[Maybe[str], str | None]:
        if self._xml is not None:
            return NOT_PROVIDED, self._xml
        version = self._version()
        result = _process.run(["lstopo-no-graphics", "--output-format", "xml"])
        if not result.usable:
            self._detail = result.detail
            return version, None
        return version, result.stdout

    def _version(self) -> Maybe[str]:
        result = _process.run(["hwloc-info", "--version"])
        if not result.usable:
            return NOT_PROVIDED
        # "hwloc-info 2.10.0"
        parts = result.stdout.strip().split()
        return parts[-1] if parts else NOT_PROVIDED


def _observe(root: ET.Element) -> list[Observation]:
    """Map the hwloc topology onto Kultrun capability paths."""
    found: list[Observation] = []

    def measured(path: str, value: object) -> None:
        found.append(
            Observation(
                path=path,
                value=value,  # type: ignore[arg-type]
                derivation=Derivation.MEASURED,
                confidence=Confidence.HIGH,
            )
        )

    machine = root.find(".//object[@type='Machine']")
    if machine is not None:
        for info in machine.findall("info"):
            name, value = info.get("name"), info.get("value")
            if name == "hwlocVersion" or value is None:
                continue
            if name == "Architecture":
                measured("operating_environment.architecture", value)
            elif name == "OSName":
                measured("operating_environment.os_name", value.lower())
            elif name == "OSRelease":
                measured("operating_environment.kernel_version", value)
            elif name == "HostName":
                measured("network.hostname", value)

    packages = root.findall(".//object[@type='Package']")
    for package in packages:
        for info in package.findall("info"):
            if info.get("name") == "CPUVendor" and info.get("value"):
                measured("cpu.vendor", info.get("value"))
            elif info.get("name") == "CPUModel" and info.get("value"):
                measured("cpu.model_name", info.get("value"))
        break  # one representative package; heterogeneous CPUs are deferred

    cores = root.findall(".//object[@type='Core']")
    units = root.findall(".//object[@type='PU']")
    if cores:
        measured("cpu.physical_cores", len(cores))
    if units:
        measured("cpu.logical_cores", len(units))

    total = 0
    for node in root.findall(".//object[@type='NUMANode']"):
        local = node.get("local_memory")
        if local is not None and local.isdigit():
            total += int(local)
    if total:
        measured("memory.total_bytes", total)

    for device in root.findall(".//object[@type='PCIDev']"):
        pci_type = device.get("pci_type") or ""
        bus = device.get("pci_busid")
        if bus is None or not pci_type.startswith(_DISPLAY_CLASS):
            continue
        vendor = _PCI_VENDORS.get(_vendor_id(pci_type))
        if vendor is None:
            # A display controller from a non-accelerator vendor: onboard or
            # management video, not something a workload can be admitted to.
            continue
        measured(f"accelerator.{bus}.vendor", vendor)
    return found


def _vendor_id(pci_type: str) -> str:
    """Extract the PCI vendor id from `0300 [10de:2c31] [10de:2051] a1`."""
    start = pci_type.find("[")
    if start == -1:
        return ""
    return pci_type[start + 1 : start + 5]


def build(clock: Clock | None = None) -> HwlocProvider:
    """Factory for the adapter registry."""
    return HwlocProvider(clock)


def replay(xml: str, clock: Clock | None = None) -> HwlocProvider:
    """Replay a captured provider fixture through the real parsing path."""
    return HwlocProvider(clock, xml=xml)

