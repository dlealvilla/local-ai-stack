"""Runtime identity and the launch recipe it produces.

Platform concepts (context, concurrency, memory) are translated here into
an executable plus arguments. Runtime-specific flags stay inside an
adapter; they must not appear as fields on these contracts.

These contracts do not import `execution`. The composition root copies a
launch spec into an `ExecutorSpec`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kultrun.host.contracts import HostId
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class RuntimeCandidateId(EntityId):
    """Identifies one host-driven runtime/executor candidate."""

    prefix = "rtcand"


class ProvisioningPlanId(EntityId):
    """Identifies one runtime provisioning plan."""

    prefix = "rtprov"


class RuntimeInstallationId(EntityId):
    """Identifies one installed runtime environment."""

    prefix = "rtinst"


class CapabilityProfileId(EntityId):
    """Identifies one RuntimeCapabilityProfile."""

    prefix = "rtcap"


class SupportTier(StrEnum):
    """How far this runtime path is a product execution environment."""

    PRODUCT = "product"
    FIXTURE = "fixture"
    REFERENCE = "reference"
    FUTURE = "future"


class CompatibilityClass(StrEnum):
    """Whether a runtime path is plausible on this host. Not eligibility."""

    COMPATIBLE = "compatible"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


class InstallationStatus(StrEnum):
    """Whether files/components exist. Not verification."""

    ABSENT = "absent"
    INSTALLED = "installed"
    FAILED = "failed"


class VerificationStatus(StrEnum):
    """Whether the execution environment has been proven."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    STALE = "stale"


@contract(kind="runtime.launch_request", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeLaunchRequest(Contract):
    """What inference asks a runtime to translate. Not argv."""

    instance_id: str = meaning("which InferenceInstance this recipe is for")
    mode: str = meaning(
        "reference serving mode: healthy, exit-immediately, never-ready, "
        "crash-after-ready",
        default="healthy",
    )
    bind_address: str = meaning(
        "loopback address the reference server should bind", default="127.0.0.1"
    )
    artifact_id: Maybe[str] = meaning(
        "stored artifact identity for provenance only", default=NOT_PROVIDED
    )


@contract(kind="runtime.profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeProfile(Contract):
    """What a runtime adapter can do. Not a running process."""

    runtime: Name = meaning("stable runtime identity, e.g. reference-process")
    display_name: str = meaning("human-readable name for consoles")
    executor_kind: Name = meaning(
        "which executor this recipe is intended for, e.g. native-process"
    )
    capabilities: tuple[str, ...] = meaning(
        "generic capability tags; never vendor-specific option names"
    )
    required_components: tuple[Name, ...] = meaning(
        "components this runtime needs, by name; empty if none", default=()
    )


@contract(kind="runtime.launch_spec", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeLaunchSpec(Contract):
    """An executable recipe. Copied into an ExecutorSpec by composition."""

    runtime: Name = meaning("which runtime produced this recipe")
    profile: Name = meaning("which profile it was produced from")
    executable: str = meaning("the program to exec; not a shell line")
    arguments: tuple[str, ...] = meaning("argv after the executable")
    environment: tuple[str, ...] = meaning(
        "extra environment bindings as NAME=value strings", default=()
    )
    working_directory: str | None = meaning(
        "working directory, or the executor's default", default=None
    )
    output_limit_bytes: int = meaning(
        "capture bound the executor should honour", default=16 * 1024
    )
    grace_period_seconds: float = meaning(
        "SIGTERM grace the executor should honour", default=2.0
    )
    device_indexes: tuple[int, ...] = meaning(
        "Kultrun accelerator indexes already chosen; empty in Stage 1.3",
        default=(),
    )

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValidationError("executable must not be empty")
        if "\0" in self.executable:
            raise ValidationError("executable must not contain a NUL")
        if Path(self.executable).name in {
            "sh",
            "bash",
            "zsh",
            "dash",
            "csh",
            "ksh",
            "fish",
        }:
            raise ValidationError(
                "executable must not be a shell; Kultrun does not expose sh -c",
                executable=self.executable,
            )
        for argument in self.arguments:
            if "\0" in argument:
                raise ValidationError("arguments must not contain a NUL")
        for entry in self.environment:
            if "=" not in entry:
                raise ValidationError(
                    "environment entry must be NAME=value",
                    entry=entry,
                )
            name, value = entry.split("=", 1)
            if not name or "\0" in value:
                raise ValidationError(
                    "environment entry is malformed",
                    entry=entry,
                )
        if self.output_limit_bytes < 1:
            raise ValidationError(
                "output limit must be at least one byte",
                output_limit_bytes=self.output_limit_bytes,
            )
        if self.grace_period_seconds <= 0:
            raise ValidationError(
                "grace period must be positive",
                grace_period_seconds=self.grace_period_seconds,
            )
        if any(index < 0 for index in self.device_indexes):
            raise ValidationError("device indexes must be non-negative")


@contract(kind="runtime.policy", version=1)
@dataclass(frozen=True, slots=True)
class RuntimePolicy(Contract):
    """How AUTO runtime selection ranks host-plausible paths."""

    policy_version: str = meaning(
        "which runtime-selection policy produced a candidate ranking",
        default="1.6.0",
    )
    allow_fixture_runtime: bool = meaning(
        "whether a fixture runtime may be AUTO-selected (lab / T2)",
        default=False,
    )
    requested_runtime: Maybe[str] = meaning(
        "explicit runtime family or provider; empty means AUTO",
        default=NOT_PROVIDED,
    )


@contract(kind="runtime.candidate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCandidate(Contract):
    """A plausible execution path. No model is required."""

    candidate_id: RuntimeCandidateId = meaning("minted identity of this candidate")
    runtime_provider: Name = meaning("adapter identity, e.g. vllm or fixture-vllm")
    runtime_family: Name = meaning("platform family, e.g. vllm; eligibility key")
    executor_kind: Name = meaning("intended executor, e.g. native-process")
    host_id: HostId = meaning("host this candidate was evaluated against")
    compatibility: CompatibilityClass = meaning("host/executor plausibility")
    support_tier: SupportTier = meaning("product, fixture, reference, or future")
    preference: int = meaning("lower is preferred among compatible AUTO candidates")
    reason: str = meaning("why this candidate has this compatibility")
    required_backend: Maybe[str] = meaning(
        "expected accelerator/backend, e.g. nvidia-cuda", default=NOT_PROVIDED
    )
    required_components: tuple[str, ...] = meaning(
        "components a provisioner would install", default=()
    )
    confidence: Maybe[str] = meaning("how sure the resolver is", default=NOT_PROVIDED)
    known_limitations: tuple[str, ...] = meaning(
        "honest limits, never invented performance", default=()
    )
    provisioning_available: bool = meaning(
        "whether a provisioner is registered for this path", default=False
    )


@contract(kind="runtime.provisioning_plan", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeProvisioningPlan(Contract):
    """What to install so one runtime path becomes available. Not installed."""

    plan_id: ProvisioningPlanId = meaning("minted identity of this provisioning plan")
    candidate_id: RuntimeCandidateId = meaning("candidate this plan materializes")
    runtime_provider: Name = meaning("adapter that will be provisioned")
    runtime_family: Name = meaning("platform family")
    intended_version: str = meaning("pinned version or range; never latest")
    executor_kind: Name = meaning("executor the installation will use")
    host_id: HostId = meaning("target host")
    required_components: tuple[str, ...] = meaning("packages or components to place")
    installation_strategy: str = meaning(
        "how to place the runtime, e.g. isolated-venv or fixture-marker"
    )
    verification_method: str = meaning("how verification should run afterwards")
    expected_backend: Maybe[str] = meaning(
        "accelerator/backend the verifier should prove", default=NOT_PROVIDED
    )
    target_location: Maybe[str] = meaning(
        "Kultrun-managed environment path when known", default=NOT_PROVIDED
    )


@contract(kind="runtime.installation", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeInstallation(Contract):
    """A placed runtime environment. Installed is not verified."""

    installation_id: RuntimeInstallationId = meaning("minted installation identity")
    runtime_provider: Name = meaning("adapter identity")
    runtime_family: Name = meaning("platform family")
    runtime_version: str = meaning("exact installed version")
    executor_kind: Name = meaning("executor this installation is bound to")
    host_id: HostId = meaning("host the environment lives on")
    status: InstallationStatus = meaning("whether the environment exists")
    location: Maybe[str] = meaning("Kultrun-managed path", default=NOT_PROVIDED)
    installed_at: Maybe[str] = meaning(
        "UTC timestamp when installation succeeded", default=NOT_PROVIDED
    )
    provenance: tuple[str, ...] = meaning("how it was placed", default=())
    failure_reason: Maybe[str] = meaning(
        "typed install failure", default=NOT_PROVIDED
    )
    provisioning_plan_id: Maybe[str] = meaning(
        "plan that produced this installation", default=NOT_PROVIDED
    )


@contract(kind="runtime.capability_profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCapabilityProfile(Contract):
    """What a verified (or failed) execution environment can support.

    Operational verification and versioned support metadata are both
    recorded. A tiny validation workload does not imply every architecture
    works. This is not a capacity estimate.
    """

    profile_id: CapabilityProfileId = meaning("minted profile identity")
    installation_id: RuntimeInstallationId = meaning("installation this evidence is of")
    runtime_provider: Name = meaning("adapter identity")
    runtime_family: Name = meaning("platform family used for eligibility")
    runtime_version: str = meaning("exact runtime version verified")
    executor_kind: Name = meaning("executor used during verification")
    host_id: HostId = meaning("host the evidence belongs to")
    host_fingerprint: str = meaning("host identity the fingerprint includes")
    status: VerificationStatus = meaning("verified, failed, unverified, or stale")
    support_tier: SupportTier = meaning(
        "whether this may authorize executable selection"
    )
    verification_method: str = meaning("how operational proof was obtained")
    verification_fingerprint: str = meaning(
        "identity of runtime/executor/accelerator/driver; not free capacity"
    )
    supported_architectures: tuple[str, ...] = meaning(
        "architectures this runtime version claims; empty means unstated"
    )
    verified_at: Maybe[str] = meaning(
        "UTC timestamp of last verification", default=NOT_PROVIDED
    )
    verification_confidence: Maybe[str] = meaning(
        "confidence of the operational proof", default=NOT_PROVIDED
    )
    supported_formats: tuple[str, ...] = meaning(
        "artifact formats; empty means unstated", default=()
    )
    supported_quantizations: tuple[str, ...] = meaning(
        "quantizations; empty means unstated", default=()
    )
    supported_modalities: tuple[str, ...] = meaning(
        "modalities; empty means unstated", default=()
    )
    supported_accelerator_types: tuple[str, ...] = meaning(
        "accelerator families, e.g. nvidia", default=()
    )
    usable_devices: tuple[int, ...] = meaning(
        "Kultrun accelerator indexes visible to the runtime", default=()
    )
    streaming_capability: Maybe[bool] = meaning(
        "whether streaming is claimed", default=NOT_PROVIDED
    )
    tensor_parallel_capability: Maybe[bool] = meaning(
        "whether tensor parallel is claimed", default=NOT_PROVIDED
    )
    lora_capability: Maybe[bool] = meaning(
        "whether LoRA/adapters are claimed", default=NOT_PROVIDED
    )
    verified_accelerator_access: Maybe[bool] = meaning(
        "operational proof that the expected accelerator is visible",
        default=NOT_PROVIDED,
    )
    verified_engine_initialization: Maybe[bool] = meaning(
        "operational proof that the engine initialized", default=NOT_PROVIDED
    )
    verified_readiness: Maybe[bool] = meaning(
        "operational proof that readiness succeeded", default=NOT_PROVIDED
    )
    known_limitations: tuple[str, ...] = meaning(
        "honest limits from verification or support metadata", default=()
    )
    evidence: tuple[str, ...] = meaning("bounded verification evidence", default=())
    failure_reason: Maybe[str] = meaning(
        "why verification failed or became stale", default=NOT_PROVIDED
    )
    capability_schema_version: str = meaning(
        "version of the support-metadata table", default="1.6.0"
    )
