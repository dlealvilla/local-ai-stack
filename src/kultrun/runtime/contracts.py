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
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
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
