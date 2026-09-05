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

from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, JsonValue, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


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

    os_name: str = meaning(
        "operating system family, normalized: 'linux', 'darwin', 'windows'. "
        "The family is what capability branching keys on; the distribution "
        "is a separate fact"
    )
    os_version: str = meaning("operating system version as reported")
    architecture: Architecture = meaning("processor architecture, normalized")
    kernel_version: Maybe[str] = meaning("kernel version where meaningful")
    virtualized: Maybe[bool] = meaning(
        "whether this is a virtual machine; unknown is common and honest"
    )
    distribution: Maybe[str] = meaning(
        "the distribution or product identifier, where one applies; distinct "
        "from the family because two providers reporting 'linux' and 'ubuntu' "
        "for one field would look like a disagreement",
        default=NOT_PROVIDED,
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
    limit_bytes: Maybe[int] = meaning(
        "the ceiling this execution context may actually use, where the "
        "environment imposes one. Distinct from total: the Stage 1.1 "
        "reference host reports 251.5 GiB of system memory while its "
        "container may use 57.7 GiB, and admitting against the larger "
        "number would get workloads killed",
        default=NOT_PROVIDED,
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


class ProviderStatus(StrEnum):
    """How a discovery provider fared.

    ``PARTIAL`` is separate from ``AVAILABLE`` because a provider that
    answered some questions and not others is not a failure, and treating it
    as one would discard the answers it did give.
    """

    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    MISSING_PREREQUISITE = "missing_prerequisite"


class DeploymentProfile(StrEnum):
    """How much Kultrun actually knows about a host shape.

    Earned from the acceptance level reached on that shape, never declared.
    `docs/PRODUCT_VISION.md` §89.
    """

    CERTIFIED = "certified"
    SUPPORTED = "supported"
    COMPATIBLE = "compatible"
    EXPERIMENTAL = "experimental"
    UNSUPPORTED = "unsupported"


@contract(kind="host.observation", version=1)
@dataclass(frozen=True, slots=True)
class Observation(Contract):
    """One provider's answer about one capability path.

    A provider speaks **paths and JSON-safe values**, never contract types.
    That is what keeps a provider's schema out of the platform: the service
    owns the vocabulary of paths, so no provider can introduce a concept by
    reporting it.
    """

    path: str = meaning(
        "the capability this concerns, as a dotted path such as "
        "'cpu.physical_cores' or 'accelerator.0000:82:00.0.memory_total_bytes'"
    )
    value: JsonValue = meaning("what the provider reported, JSON-safe")
    derivation: Derivation = meaning("how the provider obtained it")
    confidence: Confidence = meaning("how much weight it carries")


@contract(kind="host.provider_report", version=1)
@dataclass(frozen=True, slots=True)
class ProviderReport(Contract):
    """What one provider returned, including having returned nothing.

    A provider that failed still produces a report. "That source was
    unavailable" is a fact an administrator needs, and it is different from
    "this host has no accelerator".
    """

    provider: Name = meaning("which provider this is")
    status: ProviderStatus = meaning("how it fared")
    observed_at: dt.datetime = meaning("when it ran, UTC")
    provider_version: Maybe[str] = meaning(
        "the provider's own version, so an observation is reproducible",
        default=NOT_PROVIDED,
    )
    observations: tuple[Observation, ...] = meaning(
        "what it reported; empty is valid", default=()
    )
    detail: str | None = meaning(
        "why it was unavailable or what it could not answer", default=None
    )


@contract(kind="host.field_provenance", version=1)
@dataclass(frozen=True, slots=True)
class FieldProvenance(Contract):
    """Where one normalized value came from.

    Recorded beside the values rather than wrapping every leaf, keyed by the
    same dotted path. A number with no history cannot be argued with, and
    `docs/PRODUCT_VISION.md` §5.5 requires recommendations to be arguable.
    """

    path: str = meaning("the capability this describes")
    providers: tuple[Name, ...] = meaning(
        "every provider that reported this path, in consultation order"
    )
    accepted_from: Name = meaning("whose value was used")
    derivation: Derivation = meaning("how the accepted value was obtained")
    confidence: Confidence = meaning("how much weight the accepted value carries")


@contract(kind="host.observation_conflict", version=1)
@dataclass(frozen=True, slots=True)
class ObservationConflict(Contract):
    """Two credible providers disagreed and no rule resolved it.

    The value is left unresolved. An unresolved value that says two sources
    disagreed is more useful than a confident value that is wrong, and the
    platform already refuses to authorize against unknowns.
    """

    path: str = meaning("the capability they disagreed about")
    observations: tuple[Observation, ...] = meaning(
        "every competing observation, with its provenance intact"
    )
    resolution: str | None = meaning(
        "the field-specific rule that settled it, when one applied; absent "
        "means the value is unresolved",
        default=None,
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
    profile: DeploymentProfile = meaning(
        "how much Kultrun knows about this host shape, earned from the "
        "acceptance level reached on it",
        default=DeploymentProfile.EXPERIMENTAL,
    )
    provenance: tuple[FieldProvenance, ...] = meaning(
        "where each normalized value came from, by path", default=()
    )
    conflicts: tuple[ObservationConflict, ...] = meaning(
        "paths where providers disagreed; those values are unresolved",
        default=(),
    )
    provider_reports: tuple[ProviderReport, ...] = meaning(
        "which providers were consulted, and how each fared", default=()
    )
