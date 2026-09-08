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

from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class RuntimeSupportTier(StrEnum):
    """How far this declared support may be trusted.

    ``TEST_ONLY`` and ``REFERENCE`` must never become production serving
    candidates. ``PRODUCT`` is reserved for later real runtimes.
    ``FUTURE`` is declared but not selectable.
    """

    PRODUCT = "product"
    REFERENCE = "reference"
    TEST_ONLY = "test_only"
    FUTURE = "future"


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
    filesystem_mappings: tuple[str, ...] = meaning(
        "generic filesystem requirements the executor should honour",
        default=(),
    )
    network_bindings: tuple[str, ...] = meaning(
        "generic bind or publish requirements, never a Docker network name",
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
        for mapping in self.filesystem_mappings:
            if not mapping or "\0" in mapping:
                raise ValidationError("filesystem mapping is malformed")
        for binding in self.network_bindings:
            if not binding or "\0" in binding:
                raise ValidationError("network binding is malformed")


@contract(kind="runtime.support_descriptor", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeSupportDescriptor(Contract):
    """Declared, static support. Not installed, not operational, not verified."""

    runtime: Name = meaning("stable runtime identity")
    display_name: str = meaning("human-readable name for consoles")
    support_tier: RuntimeSupportTier = meaning(
        "whether this family is a product candidate or a harness"
    )
    production_candidate: bool = meaning(
        "false for reference and test-only families; they must not be AUTO-selected"
    )
    compatible_executor_types: tuple[Name, ...] = meaning(
        "executor identities this recipe can be handed to"
    )
    descriptor_version: int = meaning("descriptor shape version", default=1)
    supported_os_families: tuple[str, ...] = meaning(
        "operating-system families this family claims, e.g. linux, darwin",
        default=(),
    )
    supported_architectures: tuple[str, ...] = meaning(
        "CPU architectures this family claims, e.g. x86_64, arm64",
        default=(),
    )
    supported_accelerator_families: tuple[str, ...] = meaning(
        "accelerator families this family claims; empty means none required",
        default=(),
    )
    required_features: tuple[str, ...] = meaning(
        "executor features the recipe needs, e.g. structured_argv",
        default=(),
    )
    known_model_architectures: tuple[str, ...] = meaning(
        "model families this runtime claims, when the claim is reliable",
        default=(),
    )
    known_formats: tuple[str, ...] = meaning(
        "artifact formats this runtime claims", default=()
    )
    known_quantizations: tuple[str, ...] = meaning(
        "quantizations this runtime claims", default=()
    )
    known_modalities: tuple[str, ...] = meaning(
        "modalities this runtime claims", default=()
    )
    required_components: tuple[Name, ...] = meaning(
        "packages or binaries that would later be provisioned", default=()
    )
    preferred_version: Maybe[str] = meaning(
        "provisional version token to carry into a candidate; not a solved "
        "or verified pin. Unresolved until a provisioning stage sets one",
        default=NOT_PROVIDED,
    )
    limitations: tuple[str, ...] = meaning("known restrictions", default=())
    evidence: tuple[str, ...] = meaning("where the declaration came from", default=())
    confidence: Confidence = meaning(
        "how much weight a later resolver may place on this declaration",
        default=Confidence.LOW,
    )


@contract(kind="runtime.readiness", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeReadiness(Contract):
    """Runtime-owned answer: is this workload READY?

    Distinct from executor liveness. A live process that has not passed
    its runtime probe is not ready.
    """

    ready: bool = meaning("whether the runtime-specific workload is ready")
    address: Maybe[str] = meaning(
        "bind address when the runtime published one", default=NOT_PROVIDED
    )
    port: Maybe[int] = meaning(
        "bind port when the runtime published one", default=NOT_PROVIDED
    )
    reason: Maybe[str] = meaning(
        "why it is not ready, or how readiness was decided", default=NOT_PROVIDED
    )


class RuntimeCandidateId(EntityId):
    """Deterministic identity of one runtime+executor path on one host."""

    prefix = "rcand"


class CompatibilityClass(StrEnum):
    """Normalized plausibility. Unknown is never Compatible."""

    COMPATIBLE = "compatible"
    CONDITIONAL = "conditional"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


class RuntimeResolverMode(StrEnum):
    """How the resolver chooses which families to evaluate."""

    AUTO = "auto"
    EXPLICIT = "explicit"


class ResolutionReasonCode(StrEnum):
    """Typed reasons. Free text is secondary."""

    HOST_OS_UNSUPPORTED = "host_os_unsupported"
    HOST_ARCH_UNSUPPORTED = "host_arch_unsupported"
    HOST_OS_UNKNOWN = "host_os_unknown"
    HOST_ARCH_UNKNOWN = "host_arch_unknown"
    ACCELERATOR_UNSUPPORTED = "accelerator_unsupported"
    EXECUTOR_UNAVAILABLE = "executor_unavailable"
    EXECUTOR_TYPE_UNSUPPORTED = "executor_type_unsupported"
    EXECUTOR_CAPABILITY_MISSING = "executor_capability_missing"
    EXECUTOR_CAPABILITY_UNKNOWN = "executor_capability_unknown"
    RUNTIME_SUPPORT_UNKNOWN = "runtime_support_unknown"
    REQUIRED_COMPONENT_MISSING = "required_component_missing"
    REQUIRED_COMPONENT_UNKNOWN = "required_component_unknown"
    POLICY_DISALLOWED = "policy_disallowed"
    TEST_ONLY_RUNTIME_EXCLUDED = "test_only_runtime_excluded"
    REFERENCE_RUNTIME_EXCLUDED = "reference_runtime_excluded"
    FUTURE_RUNTIME_EXCLUDED = "future_runtime_excluded"


@contract(kind="runtime.policy", version=1)
@dataclass(frozen=True, slots=True)
class RuntimePolicy(Contract):
    """Bounded resolver controls. Not a policy DSL and not ranking science."""

    mode: RuntimeResolverMode = meaning(
        "AUTO evaluates registered families; EXPLICIT evaluates one request",
        default=RuntimeResolverMode.AUTO,
    )
    requested_runtime: Maybe[str] = meaning(
        "runtime family/provider name in EXPLICIT mode",
        default=NOT_PROVIDED,
    )
    allow_reference_runtimes: bool = meaning(
        "whether REFERENCE-tier families appear in AUTO", default=False
    )
    allow_test_only: bool = meaning(
        "whether TEST_ONLY families appear in AUTO", default=False
    )
    allow_future: bool = meaning(
        "whether FUTURE/unimplemented families appear in AUTO", default=False
    )
    prefer_conditional: bool = meaning(
        "whether a CONDITIONAL path may be the preferred candidate",
        default=False,
    )
    allowed_executor_providers: tuple[str, ...] = meaning(
        "executor identities permitted; empty means no extra filter",
        default=(),
    )
    preferred_executor_order: tuple[str, ...] = meaning(
        "stable preference among otherwise equal executor paths",
        default=("native-process", "container-docker"),
    )
    preferred_runtime_order: tuple[str, ...] = meaning(
        "stable preference among otherwise equal runtime families",
        default=(),
    )

    def __post_init__(self) -> None:
        if self.mode is RuntimeResolverMode.EXPLICIT and not isinstance(
            self.requested_runtime, str
        ):
            raise ValidationError(
                "EXPLICIT mode requires a requested runtime family",
            )
        if (
            isinstance(self.requested_runtime, str)
            and not self.requested_runtime.strip()
        ):
            raise ValidationError("requested runtime must not be empty")


@contract(kind="runtime.candidate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCandidate(Contract):
    """A plausible runtime+executor path. Not installed and not verified."""

    candidate_id: RuntimeCandidateId = meaning(
        "deterministic fingerprint of this path on this host"
    )
    runtime: Name = meaning("runtime family/provider identity, e.g. vllm")
    runtime_family: Name = meaning("runtime family; v0 matches runtime")
    runtime_provider: Name = meaning("runtime provider; v0 matches runtime")
    executor: Name = meaning("executor identity, e.g. native-process")
    executor_type: Name = meaning("generic executor type, e.g. process or container")
    host_id: HostId = meaning("host these facts were judged against")
    compatibility: CompatibilityClass = meaning("normalized plausibility class")
    support_tier: RuntimeSupportTier = meaning(
        "declared support tier from the descriptor"
    )
    reason: str = meaning("human-readable summary of the classification")
    version: Maybe[str] = meaning(
        "preferred/provisional version token; unresolved when unset",
        default=NOT_PROVIDED,
    )
    host_fingerprint: Maybe[str] = meaning(
        "host fingerprint consumed from HostCapabilities",
        default=NOT_PROVIDED,
    )
    reason_codes: tuple[ResolutionReasonCode, ...] = meaning(
        "normalized reasons; empty when the path is cleanly compatible",
        default=(),
    )
    required_executor_capabilities: tuple[str, ...] = meaning(
        "executor features the descriptor asked for", default=()
    )
    matched_executor_capabilities: tuple[str, ...] = meaning(
        "requested features the executor currently reports as supported",
        default=(),
    )
    missing_prerequisites: tuple[str, ...] = meaning(
        "components or capabilities not yet satisfied", default=()
    )
    evidence: tuple[str, ...] = meaning(
        "short provenance; never a vendor object", default=()
    )
    confidence: Confidence = meaning(
        "how much weight a later planner may place on this classification",
        default=Confidence.LOW,
    )
    rank: int = meaning(
        "0 is most preferred among this resolution's ordered candidates",
        default=0,
    )
    policy_mode: RuntimeResolverMode = meaning(
        "resolver mode that produced this evaluation",
        default=RuntimeResolverMode.AUTO,
    )


@contract(kind="runtime.resolution", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeResolution(Contract):
    """One resolver pass. Derived; not durable compatibility truth."""

    host_id: HostId = meaning("host this resolution was computed for")
    policy: RuntimePolicy = meaning("policy that governed this pass")
    candidates: tuple[RuntimeCandidate, ...] = meaning(
        "COMPATIBLE and CONDITIONAL paths, deterministically ranked"
    )
    unsupported: tuple[RuntimeCandidate, ...] = meaning(
        "hard mismatches, including EXPLICIT failures"
    )
    unresolved: tuple[RuntimeCandidate, ...] = meaning(
        "paths that could not be classified because a fact is unknown"
    )
    host_fingerprint: Maybe[str] = meaning(
        "host fingerprint consumed from HostCapabilities",
        default=NOT_PROVIDED,
    )
    preferred_candidate_id: Maybe[str] = meaning(
        "id of the preferred candidate; unresolved when none qualifies",
        default=NOT_PROVIDED,
    )
    excluded_runtimes: tuple[str, ...] = meaning(
        "families omitted by AUTO policy (reference/test/future)",
        default=(),
    )
    notes: tuple[str, ...] = meaning(
        "resolver-level notes, e.g. unknown explicit request",
        default=(),
    )
