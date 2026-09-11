"""Runtime identity and the launch recipe it produces.

Platform concepts (context, concurrency, memory) are translated here into
an executable plus arguments. Runtime-specific flags stay inside an
adapter; they must not appear as fields on these contracts.

These contracts do not import `execution`. The composition root copies a
launch spec into an `ExecutorSpec`.
"""

from __future__ import annotations

import datetime as dt
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
    interpreter: Maybe[str] = meaning(
        "exact runtime interpreter from the verified installation; never PATH python",
        default=NOT_PROVIDED,
    )
    model_path: Maybe[str] = meaning(
        "local stored artifact directory; never a Hub repository id",
        default=NOT_PROVIDED,
    )
    served_model: Maybe[str] = meaning(
        "deterministic served-model identity derived from the plan",
        default=NOT_PROVIDED,
    )
    bind_port: Maybe[int] = meaning(
        "allocated loopback port for this instance", default=NOT_PROVIDED
    )
    context_tokens: Maybe[int] = meaning(
        "plan-resolved context length; unresolved means runtime default",
        default=NOT_PROVIDED,
    )
    concurrency: Maybe[int] = meaning(
        "plan-resolved runtime concurrency; unresolved means runtime default",
        default=NOT_PROVIDED,
    )
    accelerator_index: int | None = meaning(
        "selected accelerator index; none means not a discrete GPU placement",
        default=None,
    )
    quantization: Maybe[str] = meaning(
        "plan-required quantization; omitted when the plan did not require one",
        default=NOT_PROVIDED,
    )
    installation_id: Maybe[str] = meaning(
        "verified RuntimeInstallation identity this recipe must use",
        default=NOT_PROVIDED,
    )
    runtime_version: Maybe[str] = meaning(
        "plan runtime version this recipe must honour", default=NOT_PROVIDED
    )
    reserved_accelerator_bytes: Maybe[int] = meaning(
        "admitted accelerator memory from the ACTIVE reservation; "
        "unresolved means no reservation-derived GPU budget",
        default=NOT_PROVIDED,
    )
    accelerator_memory_total_bytes: Maybe[int] = meaning(
        "installed memory of the selected accelerator from host facts; "
        "never a SAFE layer and never a runtime default",
        default=NOT_PROVIDED,
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
    served_models: tuple[str, ...] = meaning(
        "identities the runtime reports as loaded; empty until probed",
        default=(),
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


class RuntimeProvisioningPlanId(EntityId):
    """Deterministic identity of one exact intended install."""

    prefix = "rplan"


class RuntimeInstallationId(EntityId):
    """Deterministic identity of the installation produced by one plan."""

    prefix = "rinst"


class InstallationStatus(StrEnum):
    """Package lifecycle only. Not verified, ready, or running."""

    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"


@contract(kind="runtime.provisioning_component", version=1)
@dataclass(frozen=True, slots=True)
class ProvisioningComponent(Contract):
    """One package Kultrun intends to install. Not a pip command line."""

    category: str = meaning("component category, e.g. python-package")
    name: Name = meaning("package or binary name, e.g. vllm")
    version: str = meaning("exact version pin")
    source: str = meaning("package source identity, e.g. pypi")
    installer: str = meaning("installer mechanism name, e.g. pip")


@contract(kind="runtime.provisioning_plan", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeProvisioningPlan(Contract):
    """Exact intended install. Immutable once persisted. Not verified."""

    plan_id: RuntimeProvisioningPlanId = meaning(
        "fingerprint of this exact intended install"
    )
    candidate_id: RuntimeCandidateId = meaning("RuntimeCandidate this plan came from")
    runtime: Name = meaning("runtime family/provider identity")
    runtime_family: Name = meaning("runtime family; v0 matches runtime")
    runtime_provider: Name = meaning("runtime provider; v0 matches runtime")
    runtime_version: str = meaning("exact version pin, never latest")
    executor: Name = meaning("executor identity this install is for")
    host_id: HostId = meaning("host this plan was made for")
    host_fingerprint: str = meaning("host fingerprint at plan creation")
    python_version: str = meaning("required Python version, e.g. 3.12")
    installation_root: str = meaning("destination relative to the Kultrun state root")
    installer: str = meaning("installer name, e.g. pip")
    installer_mechanism: str = meaning(
        "how isolation is realized, e.g. python-venv-pip"
    )
    plan_fingerprint: str = meaning("full SHA-256 of the identity material")
    created_at: dt.datetime = meaning("when the plan was first persisted, UTC")
    python_executable: Maybe[str] = meaning(
        "host interpreter used to create the venv, when known",
        default=NOT_PROVIDED,
    )
    components: tuple[ProvisioningComponent, ...] = meaning(
        "packages this plan will install", default=()
    )
    required_prerequisites: tuple[str, ...] = meaning(
        "facts that must hold before install", default=()
    )
    unresolved_prerequisites: tuple[str, ...] = meaning(
        "required facts that were unknown at plan time", default=()
    )
    provenance: tuple[str, ...] = meaning(
        "short lineage; never a vendor object", default=()
    )
    storage_mount: Maybe[str] = meaning(
        "destination pool for this install", default=NOT_PROVIDED
    )
    persistent_bytes: Maybe[int] = meaning(
        "estimated persistent runtime footprint", default=NOT_PROVIDED
    )
    peak_transient_bytes: Maybe[int] = meaning(
        "staging peak above persistent", default=NOT_PROVIDED
    )
    cache_bytes: Maybe[int] = meaning(
        "managed install cache; zero when --no-cache-dir", default=NOT_PROVIDED
    )
    required_peak_free_bytes: Maybe[int] = meaning(
        "conservative peak free space required before realize",
        default=NOT_PROVIDED,
    )


@contract(kind="runtime.installation", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeInstallation(Contract):
    """Receipt that packages were installed. Not a capability profile."""

    installation_id: RuntimeInstallationId = meaning(
        "fingerprint of the install produced by one plan"
    )
    plan_id: RuntimeProvisioningPlanId = meaning("plan that produced this install")
    candidate_id: RuntimeCandidateId = meaning("candidate the plan was made from")
    runtime: Name = meaning("runtime family/provider identity")
    runtime_family: Name = meaning("runtime family; v0 matches runtime")
    runtime_provider: Name = meaning("runtime provider; v0 matches runtime")
    runtime_version: str = meaning("exact version that was requested")
    executor: Name = meaning("executor identity this install is for")
    host_id: HostId = meaning("host the install was performed on")
    host_fingerprint: str = meaning("host fingerprint recorded on the plan")
    status: InstallationStatus = meaning("installing, installed, or failed")
    installation_root: str = meaning(
        "final destination relative to the Kultrun state root"
    )
    installer: str = meaning("installer name, e.g. pip")
    package_source: str = meaning("package source identity, e.g. pypi")
    created_at: dt.datetime = meaning("when the install record was created, UTC")
    attempt_count: int = meaning("how many explicit provision attempts", default=1)
    python_executable: Maybe[str] = meaning(
        "python inside the isolated environment", default=NOT_PROVIDED
    )
    python_version: Maybe[str] = meaning(
        "python version inside the isolated environment", default=NOT_PROVIDED
    )
    installer_version: Maybe[str] = meaning(
        "installer version string when captured", default=NOT_PROVIDED
    )
    provenance_manifest_path: Maybe[str] = meaning(
        "installer report path relative to the state root", default=NOT_PROVIDED
    )
    provenance_manifest_sha256: Maybe[str] = meaning(
        "SHA-256 of the installer report", default=NOT_PROVIDED
    )
    resolved_runtime_version: Maybe[str] = meaning(
        "top-level package metadata version after install", default=NOT_PROVIDED
    )
    started_at: dt.datetime | None = meaning(
        "when the current attempt began", default=None
    )
    completed_at: dt.datetime | None = meaning(
        "when the current attempt finished", default=None
    )
    last_failure_code: Maybe[str] = meaning(
        "normalized failure code when status is failed", default=NOT_PROVIDED
    )
    last_failure_message: Maybe[str] = meaning(
        "short failure detail; not a traceback dump", default=NOT_PROVIDED
    )
    installed_bytes: Maybe[int] = meaning(
        "measured persistent bytes of the installed tree; unknown is not zero",
        default=NOT_PROVIDED,
    )


class RuntimeCapabilityProfileId(EntityId):
    """Deterministic identity of the current profile for one installation."""

    prefix = "rcap"


class VerificationStatus(StrEnum):
    """Effective runtime verification state. Not installation status."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"
    STALE = "stale"


class VerificationReasonCode(StrEnum):
    """Normalized verification failures. Not installer or resolver codes."""

    INSTALLATION_NOT_INSTALLED = "installation_not_installed"
    INSTALLATION_PATH_MISSING = "installation_path_missing"
    PYTHON_EXECUTABLE_MISSING = "python_executable_missing"
    PYTHON_PROBE_FAILED = "python_probe_failed"
    RUNTIME_PACKAGE_MISSING = "runtime_package_missing"
    RUNTIME_VERSION_MISMATCH = "runtime_version_mismatch"
    RUNTIME_IMPORT_FAILED = "runtime_import_failed"
    BACKEND_IMPORT_FAILED = "backend_import_failed"
    EXECUTOR_UNAVAILABLE = "executor_unavailable"
    PROBE_TIMEOUT = "probe_timeout"
    PROBE_EXIT_NONZERO = "probe_exit_nonzero"
    PROBE_OUTPUT_INVALID = "probe_output_invalid"
    ACCELERATOR_NOT_VISIBLE = "accelerator_not_visible"
    ACCELERATOR_IDENTITY_MISMATCH = "accelerator_identity_mismatch"
    BACKEND_ACCELERATOR_UNAVAILABLE = "backend_accelerator_unavailable"
    ACCELERATOR_OPERATION_FAILED = "accelerator_operation_failed"
    DRIVER_BACKEND_INCOMPATIBLE = "driver_backend_incompatible"
    VERIFICATION_BASIS_CHANGED = "verification_basis_changed"


_PROBE_SHELL_NAMES = frozenset({"sh", "bash", "zsh", "dash", "csh", "ksh", "fish"})


@contract(kind="runtime.verification_check", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeVerificationCheck(Contract):
    """One bounded check inside a verification attempt."""

    name: str = meaning("stable check identity, e.g. runtime_import")
    outcome: str = meaning("pass or fail")
    detail: str = meaning("short factual detail; never a traceback dump", default="")


@contract(kind="runtime.verification_basis", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeVerificationBasis(Contract):
    """Material facts a previous verification may still apply to.

    Capacity, load, and free-space figures are not part of this basis.
    """

    host_id: HostId = meaning("host these facts were taken from")
    installation_id: RuntimeInstallationId = meaning(
        "installation this basis is bound to"
    )
    installation_root: str = meaning("final install path relative to the state root")
    runtime: Name = meaning("runtime family/provider identity")
    runtime_version: str = meaning("exact installed runtime version pin")
    python_executable: str = meaning("isolated runtime interpreter path")
    python_version: str = meaning("isolated runtime Python version token")
    executor: Name = meaning("executor identity used for the probe")
    executor_type: str = meaning("generic executor type, e.g. process")
    executor_available: bool = meaning("whether that executor is currently available")
    os_family: str = meaning("host OS family, e.g. linux")
    architecture: str = meaning("host architecture, e.g. x86_64")
    accelerator_vendor: str = meaning("primary accelerator vendor, or none")
    accelerator_model: str = meaning("primary accelerator model, or none")
    accelerator_count: int = meaning("visible accelerator count")
    driver_version: str = meaning("primary accelerator driver version, or none")
    fingerprint: str = meaning("SHA-256 of the canonical material above")


@contract(kind="runtime.verification_probe", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeVerificationProbe(Contract):
    """Executor-neutral one-shot probe. Copied into an ExecutorSpec."""

    executable: str = meaning("program to exec; not a shell line")
    arguments: tuple[str, ...] = meaning(
        "argv after the executable; each element is one argument"
    )
    environment: tuple[str, ...] = meaning(
        "extra environment bindings as NAME=value strings", default=()
    )
    timeout_seconds: float = meaning("how long the probe may run", default=180.0)
    output_limit_bytes: int = meaning(
        "stdout and stderr are each truncated at this size", default=32 * 1024
    )

    def __post_init__(self) -> None:
        if not self.executable.strip():
            raise ValidationError("probe executable must not be empty")
        if "\0" in self.executable:
            raise ValidationError("probe executable must not contain a NUL")
        if Path(self.executable).name in _PROBE_SHELL_NAMES:
            raise ValidationError(
                "probe executable must not be a shell",
                executable=self.executable,
            )
        for argument in self.arguments:
            if "\0" in argument:
                raise ValidationError("probe arguments must be NUL-free strings")
        if self.timeout_seconds <= 0:
            raise ValidationError("probe timeout must be positive")
        if self.output_limit_bytes < 1:
            raise ValidationError("probe output limit must be at least one byte")


@contract(kind="runtime.capability_profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCapabilityProfile(Contract):
    """Host-specific observed runtime capability. Not declared support."""

    profile_id: RuntimeCapabilityProfileId = meaning(
        "fingerprint of the current profile for one installation"
    )
    installation_id: RuntimeInstallationId = meaning(
        "installation this profile describes"
    )
    plan_id: RuntimeProvisioningPlanId = meaning("plan that produced the install")
    candidate_id: RuntimeCandidateId = meaning("candidate the plan was made from")
    runtime: Name = meaning("runtime family/provider identity")
    runtime_family: Name = meaning("runtime family; v0 matches runtime")
    runtime_provider: Name = meaning("runtime provider; v0 matches runtime")
    runtime_version: str = meaning("exact runtime version observed or requested")
    executor: Name = meaning("executor identity this profile is bound to")
    executor_type: str = meaning("generic executor type, e.g. process")
    host_id: HostId = meaning("host these facts were verified against")
    status: VerificationStatus = meaning("unverified, verified, failed, or stale")
    verification_basis_fingerprint: str = meaning(
        "fingerprint of the material basis used for this profile"
    )
    verifier_provider: Name = meaning("which verifier adapter produced this profile")
    verifier_schema: str = meaning("verifier/schema token, e.g. 1")
    created_at: dt.datetime = meaning("when this profile record was first written")
    last_attempted_at: dt.datetime = meaning("when a probe last ran, UTC")
    attempt_count: int = meaning("how many explicit probes have run", default=0)
    verification_basis: RuntimeVerificationBasis | None = meaning(
        "material basis captured with the last attempt", default=None
    )
    verified_at: dt.datetime | None = meaning(
        "when required checks last passed", default=None
    )
    python_executable: Maybe[str] = meaning(
        "isolated runtime interpreter path", default=NOT_PROVIDED
    )
    python_version: Maybe[str] = meaning(
        "Python version observed during verification", default=NOT_PROVIDED
    )
    runtime_package_version: Maybe[str] = meaning(
        "runtime package metadata version observed during verification",
        default=NOT_PROVIDED,
    )
    backend: Maybe[str] = meaning(
        "backend identity observed during verification, e.g. torch",
        default=NOT_PROVIDED,
    )
    backend_version: Maybe[str] = meaning(
        "backend version observed during verification", default=NOT_PROVIDED
    )
    backend_accelerator_available: Maybe[bool] = meaning(
        "whether the runtime backend reported an accelerator device",
        default=NOT_PROVIDED,
    )
    backend_accelerator_runtime_version: Maybe[str] = meaning(
        "accelerator runtime version reported by the backend", default=NOT_PROVIDED
    )
    device_count: Maybe[int] = meaning(
        "accelerator devices visible inside the runtime", default=NOT_PROVIDED
    )
    devices: tuple[str, ...] = meaning(
        "observed accelerator names; never a vendor object", default=()
    )
    accelerator_operation: Maybe[str] = meaning(
        "tiny accelerator operation outcome: pass, fail, or skip",
        default=NOT_PROVIDED,
    )
    checks: tuple[RuntimeVerificationCheck, ...] = meaning(
        "bounded verification checks from the last attempt", default=()
    )
    reason_codes: tuple[VerificationReasonCode, ...] = meaning(
        "normalized failure reasons; empty when verified", default=()
    )
    diagnostic_summary: str = meaning(
        "bounded stdout/stderr or failure summary; never a full log",
        default="",
    )
    evidence_digest: Maybe[str] = meaning(
        "SHA-256 of the structured probe payload when one existed",
        default=NOT_PROVIDED,
    )
    last_failure_code: Maybe[str] = meaning(
        "normalized failure code when status is failed", default=NOT_PROVIDED
    )
    last_failure_message: Maybe[str] = meaning(
        "short failure detail; not a traceback dump", default=NOT_PROVIDED
    )
    probe_exit_code: Maybe[int] = meaning(
        "probe process exit code when one was observed", default=NOT_PROVIDED
    )


class FoundationSelectionId(EntityId):
    """Deterministic identity of the current foundation selection on one host."""

    prefix = "fsel"


class FoundationSelectionMode(StrEnum):
    """Product selection mode. Not RuntimePolicy AUTO/EXPLICIT coverage."""

    AUTO = "auto"
    MANUAL = "manual"


class FoundationConfidence(StrEnum):
    """How far a path may be trusted. Provisionable is not executable."""

    BLOCKED = "blocked"
    PROVISIONABLE = "provisionable"
    VERIFIED_EXECUTABLE = "verified_executable"


@contract(kind="runtime.foundation_selection", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSelection(Contract):
    """Recommended versus selected foundation. Not a ranking engine."""

    selection_id: FoundationSelectionId = meaning(
        "fingerprint of the current selection record for one host"
    )
    host_id: HostId = meaning("host this selection applies to")
    selection_mode: FoundationSelectionMode = meaning(
        "AUTO follows the current recommendation; MANUAL holds another "
        "provisionable candidate. Not RuntimePolicy.mode"
    )
    created_at: dt.datetime = meaning("when this selection record was first written")
    selected_at: dt.datetime = meaning("when the current selection last changed")
    recommended_candidate_id: Maybe[str] = meaning(
        "current pre-provision recommendation; unresolved when none exists",
        default=NOT_PROVIDED,
    )
    selected_candidate_id: Maybe[str] = meaning(
        "candidate AUTO or MANUAL chose; unresolved when none exists",
        default=NOT_PROVIDED,
    )
    generation: int = meaning(
        "increments when the selected candidate changes", default=1
    )
    downstream_stale: bool = meaning(
        "true after a selection change until later stages recompute",
        default=False,
    )
    stale_domains: tuple[str, ...] = meaning(
        "derived domains that must not be trusted after a selection change",
        default=(),
    )


class RuntimeFamily(StrEnum):
    """Intended serving-foundation families. Identity is not executability."""

    VLLM = "vllm"
    LLAMA_CPP = "llama.cpp"
    MLX = "mlx"


class HostStorageClass(StrEnum):
    """Preference size class. Not feasibility and not ResourceManager admission."""

    CONSTRAINED = "constrained"
    COMFORTABLE = "comfortable"
    UNRESOLVED = "unresolved"


class FoundationPreferenceOutcome(StrEnum):
    """Whether product preference could name a feasible candidate."""

    RECOMMENDED = "recommended"
    BLOCKED = "blocked"


class FoundationTransitionKind(StrEnum):
    """Same-family model switch is not a foundation rebootstrap."""

    NONE = "none"
    MODEL_SWITCH = "model_switch"
    FOUNDATION_REBOOTSTRAP = "foundation_rebootstrap"


class FoundationTransitionAction(StrEnum):
    """Required orchestration steps. Not a hot runtime swap."""

    STOP_LIVE_INFERENCE = "stop_live_inference"
    RELEASE_RESERVATIONS = "release_reservations"
    SELECT_FOUNDATION = "select_foundation"
    REALIZE_OR_REUSE_INSTALLATION = "realize_or_reuse_installation"
    VERIFY_RUNTIME = "verify_runtime"
    RECOMPUTE_DOWNSTREAM = "recompute_downstream"
    FRESH_DEPLOYMENT_PLAN = "fresh_deployment_plan"
    FRESH_RESOURCE_REQUEST = "fresh_resource_request"
    RESOURCE_MANAGER_ADMISSION = "resource_manager_admission"
    LAUNCH_INFERENCE_INSTANCE = "launch_inference_instance"


_GIB = 1024**3


@contract(kind="runtime.preference_policy", version=1)
@dataclass(frozen=True, slots=True)
class RuntimePreferencePolicy(Contract):
    """Product foundation preference. Ranking, not admission.

    Used only after hard feasibility has already removed infeasible families.
    """

    comfortable_storage_bytes: int = meaning(
        "SAFE storage at or above this figure prefers vLLM when both vLLM "
        "and llama.cpp are feasible; below it prefers llama.cpp. Not a "
        "feasibility threshold and not the 32 GiB Sonar tier",
        default=64 * _GIB,
    )
    policy_version: str = meaning(
        "preference policy identity recorded on decisions",
        default="1.6R0.0-runtime-breadth",
    )

    def __post_init__(self) -> None:
        if self.comfortable_storage_bytes < 1:
            raise ValidationError(
                "comfortable storage preference must be positive",
                comfortable_storage_bytes=self.comfortable_storage_bytes,
            )


@contract(kind="runtime.preference_decision", version=1)
@dataclass(frozen=True, slots=True)
class FoundationPreferenceDecision(Contract):
    """Derived product recommendation. Not persisted and not admission."""

    host_id: HostId = meaning("host these families were judged against")
    outcome: FoundationPreferenceOutcome = meaning(
        "recommended when a feasible family was chosen; blocked otherwise"
    )
    apple_silicon: bool = meaning("whether Apple Silicon policy applied")
    storage_class: HostStorageClass = meaning(
        "constrained, comfortable, or unresolved SAFE storage"
    )
    recommended_family: Maybe[str] = meaning(
        "chosen family identity; unresolved when blocked", default=NOT_PROVIDED
    )
    recommended_candidate_id: Maybe[str] = meaning(
        "chosen RuntimeCandidate; unresolved when blocked", default=NOT_PROVIDED
    )
    feasible_families: tuple[str, ...] = meaning(
        "hard-feasible family identities in input order", default=()
    )
    reasons: tuple[str, ...] = meaning("typed preference reasons", default=())
    policy_version: str = meaning(
        "preference policy that produced this decision",
        default="1.6R0.0-runtime-breadth",
    )
    comfortable_storage_bytes: int = meaning(
        "configured preference band used for this decision",
        default=64 * _GIB,
    )


@contract(kind="runtime.foundation_transition", version=1)
@dataclass(frozen=True, slots=True)
class FoundationTransition(Contract):
    """Derived switch contract. Not a live process mutation."""

    host_id: HostId = meaning("host this transition would apply to")
    transition_kind: FoundationTransitionKind = meaning(
        "none, same-family model switch, or foundation rebootstrap"
    )
    from_family: Maybe[str] = meaning(
        "currently selected family; unresolved when none", default=NOT_PROVIDED
    )
    to_family: Maybe[str] = meaning(
        "requested family; unresolved when none", default=NOT_PROVIDED
    )
    from_candidate_id: Maybe[str] = meaning(
        "currently selected candidate", default=NOT_PROVIDED
    )
    to_candidate_id: Maybe[str] = meaning("requested candidate", default=NOT_PROVIDED)
    production_executable: bool = meaning(
        "true only when the target is a verified executable foundation",
        default=False,
    )
    required_actions: tuple[str, ...] = meaning(
        "orchestration steps that must complete before serving the target",
        default=(),
    )
    reusable: tuple[str, ...] = meaning(
        "state that may be reused when still fresh", default=()
    )
    must_recompute: tuple[str, ...] = meaning(
        "derived state that must not be reused after this transition",
        default=(),
    )
    reasons: tuple[str, ...] = meaning("why this classification was chosen", default=())


class EligibleModelViewId(EntityId):
    """Deterministic identity of one derived eligible-model view."""

    prefix = "emv"


class RuntimeEligibilityStatus(StrEnum):
    """Per-model runtime compatibility. Unknown is never eligible."""

    ELIGIBLE = "eligible"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"


class EligibleViewStatus(StrEnum):
    """Whether this derived view may be treated as current authority."""

    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class EligibilityReasonCode(StrEnum):
    """Factual eligibility reasons. Free text is secondary."""

    UNSUPPORTED_ARCHITECTURE = "unsupported_architecture"
    UNSUPPORTED_ARTIFACT_FORMAT = "unsupported_artifact_format"
    UNSUPPORTED_QUANTIZATION = "unsupported_quantization"
    UNSUPPORTED_PRECISION = "unsupported_precision"
    UNSUPPORTED_MODALITY = "unsupported_modality"
    UNSUPPORTED_RUNTIME = "unsupported_runtime"
    RUNTIME_VERSION_UNSUPPORTED = "runtime_version_unsupported"
    BACKEND_MISMATCH = "backend_mismatch"
    REQUIRED_MODEL_METADATA_MISSING = "required_model_metadata_missing"
    COMPATIBILITY_UNRESOLVED = "compatibility_unresolved"
    FOUNDATION_STALE = "foundation_stale"
    RUNTIME_CAPABILITY_STALE = "runtime_capability_stale"
    RUNTIME_CAPABILITY_UNVERIFIED = "runtime_capability_unverified"
    SELECTED_FOUNDATION_MISSING = "selected_foundation_missing"
    PROFILE_INSTALLATION_MISMATCH = "profile_installation_mismatch"


@contract(kind="runtime.eligible_model_candidate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeEligibleModelCandidate(Contract):
    """One catalog model judged against the selected verified foundation.

    Derived. Not catalog metadata and not an inventory mutation.
    """

    model_id: str = meaning("catalog model identity this judgement applies to")
    logical_name: str = meaning("catalog logical name; not an eligibility stamp")
    status: RuntimeEligibilityStatus = meaning(
        "eligible, blocked, or unresolved for this foundation"
    )
    reason_codes: tuple[EligibilityReasonCode, ...] = meaning(
        "typed reasons; empty only when eligible", default=()
    )
    reasons: tuple[str, ...] = meaning(
        "short factual notes; never a traceback", default=()
    )
    architecture: Maybe[str] = meaning(
        "architecture copied from catalog facts", default=NOT_PROVIDED
    )
    quantization: Maybe[str] = meaning(
        "quantization copied from catalog facts", default=NOT_PROVIDED
    )
    family: Maybe[str] = meaning(
        "family copied from catalog facts", default=NOT_PROVIDED
    )


@contract(kind="runtime.eligible_model_view", version=1)
@dataclass(frozen=True, slots=True)
class EligibleModelView(Contract):
    """Derived runtime/model compatibility for the selected foundation.

    Not persisted. Recomputed. Does not mutate ModelMetadata or inventory.
    """

    view_id: EligibleModelViewId = meaning(
        "fingerprint of this derived view for one host and foundation basis"
    )
    host_id: HostId = meaning("host this view was computed for")
    status: EligibleViewStatus = meaning(
        "current, stale, or unavailable; only current is authoritative"
    )
    evaluated_at: dt.datetime = meaning("when this derived view was computed, UTC")
    selection_mode: Maybe[str] = meaning(
        "AUTO or MANUAL from FoundationSelection; unresolved when none",
        default=NOT_PROVIDED,
    )
    recommended_candidate_id: Maybe[str] = meaning(
        "current recommendation; never used in place of selected",
        default=NOT_PROVIDED,
    )
    selected_candidate_id: Maybe[str] = meaning(
        "selected foundation this view is bound to", default=NOT_PROVIDED
    )
    runtime: Maybe[str] = meaning(
        "selected runtime family identity", default=NOT_PROVIDED
    )
    runtime_version: Maybe[str] = meaning(
        "selected runtime version pin or observed version", default=NOT_PROVIDED
    )
    executor: Maybe[str] = meaning(
        "executor identity of the selected installation", default=NOT_PROVIDED
    )
    installation_id: Maybe[str] = meaning(
        "matching RuntimeInstallation identity", default=NOT_PROVIDED
    )
    profile_id: Maybe[str] = meaning(
        "matching RuntimeCapabilityProfile identity", default=NOT_PROVIDED
    )
    profile_status: Maybe[str] = meaning(
        "effective verification status of that profile", default=NOT_PROVIDED
    )
    foundation_stale: bool = meaning(
        "FoundationSelection.downstream_stale at computation time",
        default=False,
    )
    reason_codes: tuple[EligibilityReasonCode, ...] = meaning(
        "why this view is not current, when it is not", default=()
    )
    eligible_count: int = meaning("how many catalog models are ELIGIBLE", default=0)
    blocked_count: int = meaning("how many catalog models are BLOCKED", default=0)
    unresolved_count: int = meaning("how many catalog models are UNRESOLVED", default=0)
    candidates: tuple[RuntimeEligibleModelCandidate, ...] = meaning(
        "per-model judgements; empty when the view is unavailable",
        default=(),
    )


class RuntimeMemoryProfileId(EntityId):
    """Identity of one measured runtime-memory profile."""

    prefix = "rmp"


class RuntimeMemoryProfileStatus(StrEnum):
    """Whether this profile captured usable memory facts."""

    MEASURED = "measured"
    UNRESOLVED = "unresolved"
    FAILED = "failed"


class RuntimeValidationStatus(StrEnum):
    """How a candidate's final requirement was validated. Not ranking."""

    MEASURED_RUNTIME = "measured_runtime"
    CALIBRATED_FROM_HIGH_PRESSURE_SENTINEL = "calibrated_from_high_pressure_sentinel"
    CACHED_RUNTIME_CALIBRATION = "cached_runtime_calibration"
    UNRESOLVED = "unresolved"


@contract(kind="runtime.memory_profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeMemoryProfile(Contract):
    """Measured native-runtime memory evidence. Not selection or admission.

    Host- and runtime-specific. Capacity changes do not invalidate a profile
    whose execution basis is unchanged.
    """

    profile_id: RuntimeMemoryProfileId = meaning("identity of this measured profile")
    status: RuntimeMemoryProfileStatus = meaning(
        "measured when B and K were captured; failed/unresolved otherwise"
    )
    basis_fingerprint: str = meaning(
        "material execution basis this profile is valid for"
    )
    class_key: str = meaning("runtime-memory validation class this sentinel represents")
    source_model_id: str = meaning("sentinel model that was probed")
    runtime: str = meaning("runtime family, e.g. vllm")
    host_id: HostId = meaning("host these facts were measured on")
    host_fingerprint: str = meaning("host fingerprint at measurement")
    measured_at: dt.datetime = meaning("when these facts were captured, UTC")
    confidence: Confidence = meaning(
        "HIGH when measured; UNKNOWN when the profile is not usable"
    )
    source_revision: Maybe[str] = meaning(
        "exact artifact revision probed", default=NOT_PROVIDED
    )
    runtime_version: Maybe[str] = meaning("exact runtime version", default=NOT_PROVIDED)
    executor: Maybe[str] = meaning(
        "executor identity used for the probe", default=NOT_PROVIDED
    )
    capability_profile_id: Maybe[str] = meaning(
        "RuntimeCapabilityProfile this probe was bound to", default=NOT_PROVIDED
    )
    accelerator_index: int | None = meaning("device the probe reserved", default=None)
    accelerator_architecture: Maybe[str] = meaning(
        "selected accelerator architecture/model basis", default=NOT_PROVIDED
    )
    model_architecture: Maybe[str] = meaning(
        "model architecture family", default=NOT_PROVIDED
    )
    quantization: Maybe[str] = meaning(
        "quantization family probed", default=NOT_PROVIDED
    )
    context_tokens: Maybe[int] = meaning(
        "context the probe assumed", default=NOT_PROVIDED
    )
    concurrency: Maybe[int] = meaning(
        "concurrency assumption the probe used", default=NOT_PROVIDED
    )
    kv_dtype: Maybe[str] = meaning("KV/cache dtype when known", default=NOT_PROVIDED)
    probe_budget_bytes: Maybe[int] = meaning(
        "admitted SAFE VRAM budget B for this probe", default=NOT_PROVIDED
    )
    vllm_model_load_bytes: Maybe[int] = meaning(
        "runtime-reported model-load memory, when captured", default=NOT_PROVIDED
    )
    vllm_available_kv_bytes: Maybe[int] = meaning(
        "runtime-reported available KV cache memory K; may be negative",
        default=NOT_PROVIDED,
    )
    derived_non_kv_bytes: Maybe[int] = meaning(
        "B minus K; usable even when K is negative", default=NOT_PROVIDED
    )
    derived_runtime_extra_bytes: Maybe[int] = meaning(
        "non-KV minus model-load when both are valid", default=NOT_PROVIDED
    )
    runtime_extra_floor_bytes: Maybe[int] = meaning(
        "conservative runtime-extra floor transferred to same-class members",
        default=NOT_PROVIDED,
    )
    runtime_extra_ratio: Maybe[float] = meaning(
        "runtime-extra / model-load when that ratio is valid", default=NOT_PROVIDED
    )
    static_requirement_bytes: Maybe[int] = meaning(
        "static estimated-feasible total at probe time", default=NOT_PROVIDED
    )
    static_weight_component: Maybe[int] = meaning(
        "static base-model component at probe time", default=NOT_PROVIDED
    )
    static_kv_component: Maybe[int] = meaning(
        "static KV component at probe time", default=NOT_PROVIDED
    )
    static_runtime_overhead: Maybe[int] = meaning(
        "static runtime-overhead component at probe time", default=NOT_PROVIDED
    )
    notes: tuple[str, ...] = meaning("short factual notes; never raw logs", default=())
    failure_reason: Maybe[str] = meaning(
        "why the probe produced no usable profile, when it did not",
        default=NOT_PROVIDED,
    )
