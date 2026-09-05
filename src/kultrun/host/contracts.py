"""What the machine is, as reported.

The field set is transcribed from `docs/PRODUCT_VISION.md` §8 rather than
invented, which is why a contract this detailed is not speculation. Stage
1.1 builds the detector that populates it and earns the `L2` evidence;
this stage fixes the shape it must produce.

Three properties are load-bearing and cheap now:

- **Everything is `Maybe[...]`** except what is structurally certain. A CPU
  whose core count could not be read has an unknown core count, not zero.
- **Accelerators and mounts are plural from v1**, on a host that will
  usually have one of each. `docs/ARCHITECTURE.md` Part II §6: this is what
  keeps Milestone 14 an extension rather than a rewrite.
- **`host_id` is on the record.** Same reason.

Nothing here interprets. Every value carries basis *reported*, and the
free space on a mount is a fact about a filesystem, not a permission to
write to it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


class HostId(EntityId):
    """Identifies one host. Present on every host-scoped contract."""

    prefix = "host"


class Architecture(StrEnum):
    """Processor architecture, normalized away from platform spellings."""

    X86_64 = "x86_64"
    ARM64 = "arm64"
    UNKNOWN = "unknown"


class AcceleratorVendor(StrEnum):
    """Accelerator families the platform branches on."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    APPLE = "apple"
    UNKNOWN = "unknown"


@contract(kind="host.operating_environment", version=1)
@dataclass(frozen=True, slots=True)
class OperatingEnvironment(Contract):
    """The operating system and how it is hosted."""

    os_name: str = meaning("operating system, normalized")
    os_version: str = meaning("operating system version as reported")
    architecture: Architecture = meaning("processor architecture, normalized")
    kernel_version: Maybe[str] = meaning("kernel version where meaningful")
    virtualized: Maybe[bool] = meaning(
        "whether this is a virtual machine; unknown is common and honest"
    )


@contract(kind="host.cpu", version=1)
@dataclass(frozen=True, slots=True)
class CpuFacts(Contract):
    """Processor facts, as reported."""

    vendor: Maybe[str] = meaning("processor vendor")
    model_name: Maybe[str] = meaning("processor model as reported")
    physical_cores: Maybe[int] = meaning("physical core count")
    logical_cores: Maybe[int] = meaning("logical processor count including threads")


@contract(kind="host.memory", version=1)
@dataclass(frozen=True, slots=True)
class MemoryFacts(Contract):
    """System memory, as reported.

    ``unified_with_accelerator`` matters more than it looks: on Apple
    Silicon, system and accelerator memory are the same pool, so treating
    them as separate budgets would double-count. Where this is unknown the
    platform fails closed rather than assuming they are separate.
    """

    total_bytes: Maybe[int] = meaning("installed system memory")
    available_bytes: Maybe[int] = meaning("memory free at detection time")
    unified_with_accelerator: Maybe[bool] = meaning(
        "whether system and accelerator memory are one pool"
    )


@contract(kind="host.accelerator", version=1)
@dataclass(frozen=True, slots=True)
class Accelerator(Contract):
    """One accelerator device.

    Per-device, never aggregated. Summing memory across devices is only
    valid where the interconnect genuinely permits it, which is a capacity
    judgement and does not belong in a reported fact.
    """

    index: int = meaning("device ordinal on this host")
    vendor: AcceleratorVendor = meaning("accelerator family, normalized")
    model_name: Maybe[str] = meaning("device model as reported")
    memory_total_bytes: Maybe[int] = meaning("device memory installed")
    driver_version: Maybe[str] = meaning("driver version, for compatibility checks")
    unified_memory: Maybe[bool] = meaning(
        "whether this device shares the system memory pool"
    )


@contract(kind="host.mount", version=1)
@dataclass(frozen=True, slots=True)
class MountFacts(Contract):
    """One filesystem mount, as reported.

    These are inspection facts. The platform's interpretation of a mount as
    allocatable capacity is a `StoragePool`, owned by `storage`, and raw
    free space here may never authorize a mutation. The previous attempt saw
    a filesystem advertise roughly 239 TB free while a 6.70 GiB install was
    correctly refused.
    """

    mount_point: str = meaning("path at which the filesystem is mounted")
    device: Maybe[str] = meaning("backing device as reported")
    filesystem_type: Maybe[str] = meaning("filesystem type")
    total_bytes: Maybe[int] = meaning("filesystem size as reported")
    free_bytes: Maybe[int] = meaning(
        "free space as reported; may be displayed, never authorizes"
    )


@contract(kind="host.execution", version=1)
@dataclass(frozen=True, slots=True)
class ExecutionCapabilities(Contract):
    """How workloads can be run on this host.

    Native process execution is first class and is therefore a plain bool:
    if the platform is running, it can start a process. Everything else is
    `Maybe[...]`, because absence of evidence for Docker is not evidence of
    absence.
    """

    native_process: bool = meaning("native process execution, always available")
    docker: Maybe[bool] = meaning("whether a usable Docker daemon is present")
    podman: Maybe[bool] = meaning("whether Podman is present")


@contract(kind="host.network", version=1)
@dataclass(frozen=True, slots=True)
class NetworkFacts(Contract):
    """Networking facts needed to place services."""

    hostname: Maybe[str] = meaning("host name as reported")
    loopback_address: Maybe[str] = meaning("address the control plane binds to")
    occupied_ports: tuple[int, ...] = meaning(
        "ports already in use, so the platform does not collide with them",
        default=(),
    )


@contract(kind="host.capabilities", version=1)
@dataclass(frozen=True, slots=True)
class HostCapabilities(Contract):
    """The normalized description of one host.

    Stable regardless of how it was detected, which is what allows a
    synthetic fixture for an unsupported host shape to exercise the same
    capability branching as a real one.
    """

    host_id: HostId = meaning("platform-minted identity of this host")
    fingerprint: str = meaning(
        "digest of the stable facts; the key by which cached evidence is "
        "later judged reusable"
    )
    detected_at: dt.datetime = meaning("when detection ran, UTC")
    operating_environment: OperatingEnvironment = meaning("OS and virtualization")
    cpu: CpuFacts = meaning("processor facts")
    memory: MemoryFacts = meaning("system memory facts")
    execution: ExecutionCapabilities = meaning("how workloads can be run here")
    network: NetworkFacts = meaning("networking facts")
    accelerators: tuple[Accelerator, ...] = meaning(
        "every accelerator, per device and never aggregated", default=()
    )
    mounts: tuple[MountFacts, ...] = meaning(
        "every relevant filesystem mount", default=()
    )
