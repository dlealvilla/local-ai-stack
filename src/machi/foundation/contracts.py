"""Foundation contracts (MACHI 5).

Native managed vLLM is the primary engine. Ollama is a separate engine
with its own recipe. These records do not choose a model, admit a
workload, or start a server.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

_TOKEN_MAX = 80
_REASON_MAX = 240
_LIBRARY_MAX = 512
_MAX_SETTINGS = 24


class FoundationFamily(StrEnum):
    """Serving family. Not an ontology."""

    DIRECT = "direct"


class FoundationEngine(StrEnum):
    """Engine selected for this foundation. vLLM stays the primary engine."""

    VLLM = "vllm"
    OLLAMA = "ollama"


class ExecutorKind(StrEnum):
    """How the managed environment is created. Containers are deferred."""

    NATIVE_PROCESS = "native_process"


class AcceleratorBackend(StrEnum):
    """GPU software stack for the vLLM build."""

    CUDA = "cuda"
    ROCM = "rocm"


class ProvisionMode(StrEnum):
    """Inspection does not mutate. Provision is explicit."""

    INSPECT_ONLY = "inspect_only"
    PLAN_ONLY = "plan_only"
    PROVISION = "provision"


class SupportState(StrEnum):
    """Whether this host can hold a foundation. Not an admission verdict."""

    SUPPORTED = "supported"
    CONDITIONALLY_SUPPORTED = "conditionally_supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    BLOCKED_BY_PREREQUISITE = "blocked_by_prerequisite"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    PROVISIONING_FAILED = "provisioning_failed"
    VERIFICATION_FAILED = "verification_failed"
    READY = "ready"
    RECONCILE_REQUIRED = "reconcile_required"


class FailureCode(StrEnum):
    """Typed foundation failure. Not a shell exit code."""

    NONE = "none"
    HOST_UNSUPPORTED = "host_unsupported"
    ACCELERATOR_UNSUPPORTED = "accelerator_unsupported"
    DRIVER_OR_BACKEND_INCOMPATIBLE = "driver_or_backend_incompatible"
    PREREQUISITE_BLOCKED = "prerequisite_blocked"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    PYTHON_PROVISION_FAILED = "python_provision_failed"
    PACKAGE_RESOLUTION_FAILED = "package_resolution_failed"
    PACKAGE_DOWNLOAD_FAILED = "package_download_failed"
    PACKAGE_INSTALL_FAILED = "package_install_failed"
    VERIFICATION_FAILED = "verification_failed"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    UNEXPECTED = "unexpected"
    PROMOTED_UNREGISTERED = "promoted_unregistered"


class FeatureState(StrEnum):
    """How a capability was established. Docs are not verification."""

    DECLARED_BY_VERSION = "declared_by_version"
    DISCOVERED = "discovered"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"
    UNSUPPORTED = "unsupported"


class SettingProvenance(StrEnum):
    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR = "administrator"


class SettingSupport(StrEnum):
    SUPPORTED = "supported"


@contract(kind="foundation.setting", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSetting(Contract):
    """One inspectable Foundation knob."""

    name: str = meaning("dotted setting name")
    value: str = meaning("current value as text")
    provenance: SettingProvenance = meaning("who selected this value")
    reason: str = meaning("why this value is in force")
    allowed_values: str = meaning("compact allowed values")
    support_state: SettingSupport = meaning("whether the setting is usable")
    mutability: str = meaning("runtime or restart_required")
    invalidation: str = meaning("what must be recomputed if this changes")

    def __post_init__(self) -> None:
        _bounded(self.name, what="name", maximum=_TOKEN_MAX)
        _bounded(self.value, what="value", maximum=_LIBRARY_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)
        _bounded(self.allowed_values, what="allowed", maximum=_LIBRARY_MAX)
        if self.mutability not in {"runtime", "restart_required"}:
            raise ValidationError("setting mutability is not supported")
        _bounded(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="foundation.settings", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSettings(Contract):
    """Typed native-vLLM policy. The fallback runtime is not selected here."""

    python_version: str = meaning("managed interpreter version, not system Python")
    vllm_version: str = meaning("exact vLLM version pin")
    executor: ExecutorKind = meaning("native process; containers are deferred")
    backend: str = meaning("auto, cuda, or rocm")
    provision_mode: ProvisionMode = meaning("inspect, plan, or provision")
    environment_root_policy: str = meaning("generations live under the owned root")
    reuse_policy: str = meaning("reuse a verified generation; do not mutate it")
    timeout_seconds: int = meaning("bound on one process invocation")
    rocm_recipe: RuntimeRecipe = meaning("pinned AMD artifact compatibility")
    settings: tuple[FoundationSetting, ...] = meaning("inspectable records")

    def __post_init__(self) -> None:
        _bounded(self.python_version, what="python", maximum=16)
        _bounded(self.vllm_version, what="vllm", maximum=32)
        if self.backend not in {"auto", "cuda", "rocm"}:
            raise ValidationError("backend must be auto, cuda, or rocm")
        if self.environment_root_policy != "state_root_generations":
            raise ValidationError("environment root policy is not supported")
        if self.reuse_policy != "reuse_verified":
            raise ValidationError("reuse policy is not supported")
        if self.timeout_seconds < 1 or self.timeout_seconds > 3600:
            raise ValidationError("timeout is outside 1..3600 seconds")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many foundation settings")


@contract(kind="foundation.runtime_recipe", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeRecipe(Contract):
    """Compatibility identity of one published vLLM artifact."""

    recipe_id: str = meaning("stable id of this engine, version, and variant")
    engine: FoundationEngine = meaning("vllm")
    vllm_version: str = meaning("exact vLLM version")
    variant: str = meaning("wheel variant, for example rocm700 or cuda")
    python_version: str = meaning("interpreter the artifact was built for")
    rocm_line: str = meaning("major.minor ROCm identity, or none for CUDA")
    glibc_minimum: str = meaning("minimum glibc major.minor, or none")
    accelerator_architectures: str = meaning("comma-separated gfx names, or none")
    native_libraries: str = meaning("comma-separated sonames, or none")

    def __post_init__(self) -> None:
        _bounded(self.recipe_id, what="recipe", maximum=_TOKEN_MAX)
        _bounded(self.variant, what="variant", maximum=32)
        _bounded(self.python_version, what="python", maximum=16)
        _bounded(self.vllm_version, what="vllm", maximum=32)
        _bounded(self.rocm_line, what="rocm line", maximum=16)
        _bounded(self.glibc_minimum, what="glibc", maximum=16)
        _bounded(
            self.accelerator_architectures,
            what="architectures",
            maximum=_REASON_MAX,
        )
        _bounded(self.native_libraries, what="libraries", maximum=_LIBRARY_MAX)


@contract(kind="foundation.requirement", version=1)
@dataclass(frozen=True, slots=True)
class FoundationRequirement(Contract):
    """Bytes and memory to install the foundation. Not a model requirement."""

    persistent_bytes: int = meaning("installed environment bytes, conservative")
    transient_bytes: int = meaning("peak extra bytes during install")
    minimum_memory_bytes: int = meaning("RAM ceiling required to provision")

    def __post_init__(self) -> None:
        for name, value in (
            ("persistent_bytes", self.persistent_bytes),
            ("transient_bytes", self.transient_bytes),
            ("minimum_memory_bytes", self.minimum_memory_bytes),
        ):
            if value < 1:
                raise ValidationError("requirement bytes must be positive", field=name)


@contract(kind="foundation.candidate", version=1)
@dataclass(frozen=True, slots=True)
class FoundationCandidate(Contract):
    """Exact install candidate resolved before any mutation."""

    candidate_id: str = meaning("stable id of this pin and backend")
    family: FoundationFamily = meaning("direct")
    engine: FoundationEngine = meaning("vllm")
    executor: ExecutorKind = meaning("native_process")
    backend: Maybe[AcceleratorBackend] = meaning("cuda or rocm when chosen")
    python_version: str = meaning("managed Python pin")
    vllm_version: str = meaning("exact vLLM version")
    package_spec: str = meaning("exact package requirement, not an open range")
    package_source: str = meaning("index or wheel source without secrets")
    variant: str = meaning("cuda, rocm700, or none when no recipe was reached")
    required_rocm: str = meaning("required ROCm major.minor, or none")
    observed_rocm: Maybe[str] = meaning("ROCm version read from the host")
    observed_glibc: Maybe[str] = meaning("glibc version read from the host")
    accelerator_architecture: Maybe[str] = meaning("gfx name when observed")
    native_libraries: str = meaning("required sonames, or none")
    native_status: str = meaning("satisfied, realize, missing, or not_applicable")
    native_library_prefix: str = meaning("managed linker prefix, or none")
    support: SupportState = meaning("resolution outcome before provision")
    failure: FailureCode = meaning("none when the candidate is usable")
    reason: str = meaning("why this candidate was selected or refused")

    def __post_init__(self) -> None:
        _bounded(self.candidate_id, what="candidate", maximum=_TOKEN_MAX)
        _bounded(self.package_spec, what="package", maximum=_REASON_MAX)
        _bounded(self.package_source, what="source", maximum=_REASON_MAX)
        _bounded(self.variant, what="variant", maximum=32)
        _bounded(self.required_rocm, what="required rocm", maximum=16)
        _bounded(self.native_libraries, what="libraries", maximum=_LIBRARY_MAX)
        _bounded(self.native_status, what="native status", maximum=_LIBRARY_MAX)
        _bounded(self.native_library_prefix, what="library prefix", maximum=_REASON_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)


@contract(kind="foundation.generation", version=1)
@dataclass(frozen=True, slots=True)
class ManagedGeneration(Contract):
    """One immutable managed environment. A new pin is a new generation."""

    generation_id: str = meaning("identity of this environment generation")
    candidate_id: str = meaning("candidate this generation was built from")
    python_path: str = meaning("managed interpreter; not system Python")
    vllm_version: str = meaning("version recorded after verification")
    created_at: dt.datetime = meaning("when the generation was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "created_at", require_utc(self.created_at, what="created_at")
        )
        _bounded(self.generation_id, what="generation", maximum=_TOKEN_MAX)
        _bounded(self.candidate_id, what="candidate", maximum=_TOKEN_MAX)
        _bounded(self.python_path, what="python path", maximum=240)
        _bounded(self.vllm_version, what="vllm", maximum=32)


@contract(kind="foundation.verification", version=1)
@dataclass(frozen=True, slots=True)
class VerificationEvidence(Contract):
    """Import and version check. Not a model launch."""

    passed: bool = meaning("true only when the minimum checks passed")
    observed_version: Maybe[str] = meaning("vLLM version the interpreter reported")
    effective_python: Maybe[str] = meaning("managed interpreter version after verify")
    effective_torch: Maybe[str] = meaning("torch version the interpreter reported")
    effective_backend_runtime: Maybe[str] = meaning("torch CUDA or HIP version")
    failure: FailureCode = meaning("verification_failed, timeout, or none")
    reason: str = meaning("which check passed or failed")

    def __post_init__(self) -> None:
        _bounded(self.reason, what="verification reason", maximum=_REASON_MAX)


@contract(kind="foundation.capability", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCapability(Contract):
    """What this install can do. Serving settings are not chosen here."""

    engine: FoundationEngine = meaning("vllm")
    version: str = meaning("effective vLLM version")
    backend: AcceleratorBackend = meaning("cuda or rocm")
    import_state: FeatureState = meaning("whether import was verified")
    entrypoint_state: FeatureState = meaning("whether the module entry is present")
    server_launch: FeatureState = meaning("serving is unsupported in this block")
    streaming: FeatureState = meaning("not proven by installing the package")
    structured_output: FeatureState = meaning("not proven without a model")
    lora: FeatureState = meaning("not proven without a model")
    metrics: FeatureState = meaning("not proven without a server")

    def __post_init__(self) -> None:
        _bounded(self.version, what="version", maximum=32)
        if self.server_launch is not FeatureState.UNSUPPORTED:
            raise ValidationError("Foundation must not mark serving as supported")


@contract(kind="foundation.selection", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSelection(Contract):
    """Macropath decision: family plus engine, or a typed refusal."""

    selection_id: str = meaning("identity of this decision")
    family: FoundationFamily = meaning("direct")
    engine: FoundationEngine = meaning("vllm")
    executor: ExecutorKind = meaning("native_process")
    backend: Maybe[AcceleratorBackend] = meaning("cuda or rocm when a candidate exists")
    support: SupportState = meaning("support or failure state")
    failure: FailureCode = meaning("typed failure or none")
    candidate_id: Maybe[str] = meaning("resolved candidate when one exists")
    generation_id: Maybe[str] = meaning("generation when reused or created")
    capacity_evidence_id: str = meaning("Capacity snapshot this decision consumed")
    reason: str = meaning("why this selection was made")

    def __post_init__(self) -> None:
        _bounded(self.selection_id, what="selection", maximum=_TOKEN_MAX)
        _bounded(self.capacity_evidence_id, what="capacity", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)


@contract(kind="foundation.set", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSet(Contract):
    """Resolution plus optional provision and verify. Not a served model."""

    selection: FoundationSelection = meaning("the macropath decision")
    candidate: Maybe[FoundationCandidate] = meaning("exact pin when resolved")
    requirement: FoundationRequirement = meaning("install footprint bound")
    generation: Maybe[ManagedGeneration] = meaning("environment when provisioned")
    verification: Maybe[VerificationEvidence] = meaning("import check when attempted")
    capability: Maybe[RuntimeCapability] = meaning("profile when verification passed")
    settings: FoundationSettings = meaning("policy used")
    observed_at: dt.datetime = meaning("when this set was produced; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
