"""Process launch and observation, without runtime or model semantics.

The executor receives a structured specification — an executable and an
argument list — never a shell string. Native process execution is
first-class; a container engine is an adapter behind the same port.
Docker-specific fields do not belong on these generic contracts.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ExecutionId(EntityId):
    """Identifies one execution the platform started."""

    prefix = "exec"


class ExecutionState(StrEnum):
    """Observed process lifecycle. Desired state is a separate field."""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    EXITED = "exited"
    FAILED = "failed"


class ExecutionHealth(StrEnum):
    """Whether the process is functioning, as distinct from whether it exists.

    Stage 1.3 has no application-level probe. ``UNKNOWN`` is the honest
    v0 answer: a live PID is not proof that a future inference API works.
    """

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ExecutionOwnership(StrEnum):
    """Whether Kultrun can prove this process is the one it started.

    After a control-plane restart the PID in a record may have been reused.
    Claiming that process would be lying. ``UNVERIFIED`` means it looks
    alive and we will not signal it.
    """

    OWNED = "owned"
    UNVERIFIED = "unverified"
    ABSENT = "absent"


class FeatureSupport(StrEnum):
    """Whether an executor feature is actually provided.

    ``UNKNOWN`` is a real answer. It is not unsupported and it is not a
    pass. Callers must not treat it as ``False`` or as zero.
    """

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class ExecutorAvailability(StrEnum):
    """Whether this executor can be used on the current host."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNRESOLVED = "unresolved"


class PullPolicy(StrEnum):
    """Whether the engine may fetch an image. Ordinary reads never pull."""

    NEVER = "never"
    IF_MISSING = "if_missing"
    ALWAYS = "always"


class ContainerNetworkMode(StrEnum):
    """How the executor realizes the spec's generic network bindings."""

    HOST = "host"
    BRIDGE = "bridge"


class EngineFailureKind(StrEnum):
    """Normalized engine failure. Never a vendor exception type."""

    BINARY_MISSING = "binary_missing"
    DAEMON_UNAVAILABLE = "daemon_unavailable"
    PERMISSION_DENIED = "permission_denied"
    UNSUPPORTED_VERSION = "unsupported_version"
    IMAGE_MISSING = "image_missing"
    INVALID_IMAGE = "invalid_image"
    COMMAND_UNAVAILABLE = "command_unavailable"
    NETWORK_FAILURE = "network_failure"
    EXECUTION_FAILURE = "execution_failure"


@contract(kind="execution.device_request", version=1)
@dataclass(frozen=True, slots=True)
class DeviceRequest(Contract):
    """An accelerator Kultrun has already decided to attach.

    Named the way Kultrun identifies devices, not the way a container
    runtime names them. Translation to a CDI name belongs in an OCI
    adapter later, never here.
    """

    index: int = meaning("which accelerator, as Kultrun numbers them on the host")


@contract(kind="execution.spec", version=1)
@dataclass(frozen=True, slots=True)
class ExecutorSpec(Contract):
    """A structured process launch. Never a shell command string."""

    executable: str = meaning("the program to exec; not a shell line")
    arguments: tuple[str, ...] = meaning(
        "argv after the executable; each element is one argument"
    )
    environment: tuple[str, ...] = meaning(
        "extra environment bindings as NAME=value strings", default=()
    )
    working_directory: str | None = meaning(
        "working directory, or the executor's default", default=None
    )
    output_limit_bytes: int = meaning(
        "stdout and stderr are each truncated at this size", default=16 * 1024
    )
    grace_period_seconds: float = meaning(
        "how long SIGTERM may take before SIGKILL", default=2.0
    )
    device_requests: tuple[DeviceRequest, ...] = meaning(
        "accelerators already authorized for this launch; unused by the "
        "native executor in Stage 1.3",
        default=(),
    )
    filesystem_mappings: tuple[str, ...] = meaning(
        "generic filesystem requirements the executor should honour; "
        "empty when the workload uses the host filesystem as-is",
        default=(),
    )
    network_bindings: tuple[str, ...] = meaning(
        "generic bind or publish requirements, never a Docker network name",
        default=(),
    )

    def __post_init__(self) -> None:
        _reject_shell_string(self.executable, what="executable")
        if not self.executable.strip():
            raise ValidationError("executable must not be empty")
        if "\0" in self.executable:
            raise ValidationError("executable must not contain a NUL")
        for argument in self.arguments:
            if not isinstance(argument, str):
                raise ValidationError(
                    "every argument must be a string",
                    actual_type=type(argument).__name__,
                )
            if "\0" in argument:
                raise ValidationError("arguments must not contain a NUL")
        for entry in self.environment:
            name, value = _split_env(entry)
            if not _ENV_NAME.match(name):
                raise ValidationError(
                    "environment name is not a valid identifier",
                    name=name,
                )
            if "\0" in value:
                raise ValidationError(
                    "environment values must not contain a NUL",
                    name=name,
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
        for mapping in self.filesystem_mappings:
            if not mapping or "\0" in mapping:
                raise ValidationError("filesystem mapping is malformed")
        for binding in self.network_bindings:
            if not binding or "\0" in binding:
                raise ValidationError("network binding is malformed")


@contract(kind="execution.handle", version=1)
@dataclass(frozen=True, slots=True)
class ExecutorHandle(Contract):
    """One execution, as the platform last observed it.

    Desired, observed and health stay separate fields even when v0 leaves
    health unknown. Collections of these are `executions[]`; there is no
    `current_execution`.
    """

    execution_id: ExecutionId = meaning("platform-minted identity of this execution")
    host_id: HostId = meaning("the host the process was started on")
    executor: Name = meaning("which executor adapter started it")
    desired_state: ExecutionState = meaning("what Kultrun wants")
    observed_state: ExecutionState = meaning("what actually exists")
    health: ExecutionHealth = meaning(
        "whether it is functioning; unknown until a real probe exists"
    )
    ownership: ExecutionOwnership = meaning(
        "whether this PID is proven to be the process we started"
    )
    created_at: dt.datetime = meaning("when the record was created, UTC")
    executable: str = meaning("the program that was exec'd")
    arguments: tuple[str, ...] = meaning("the argument list that was exec'd")
    pid: Maybe[int] = meaning(
        "operating-system process id while one is known", default=NOT_MEASURED
    )
    started_at: dt.datetime | None = meaning(
        "when the process became running; absent until it does", default=None
    )
    exited_at: dt.datetime | None = meaning(
        "when the process left running; absent while it has not", default=None
    )
    exit_code: Maybe[int] = meaning(
        "wait status when observed exited or failed", default=NOT_MEASURED
    )
    stdout: str = meaning("bounded stdout captured so far", default="")
    stderr: str = meaning("bounded stderr captured so far", default="")
    output_truncated: bool = meaning(
        "true when a stream hit the capture limit", default=False
    )
    detail: str | None = meaning(
        "why a start or stop failed, when it did", default=None
    )
    external_identity: Maybe[str] = meaning(
        "executor-native identity that is not a PID: a container id, "
        "task id, or fixture token. Unresolved when the executor has none",
        default=NOT_MEASURED,
    )
    network_bindings: tuple[str, ...] = meaning(
        "observed bind or publish points, when the executor can report them",
        default=(),
    )


@contract(kind="execution.capability_profile", version=1)
@dataclass(frozen=True, slots=True)
class ExecutorCapabilityProfile(Contract):
    """What this executor can provide on the current host.

    Capability evidence, not runtime logic and not admission. Unknown
    stays unknown.
    """

    executor: Name = meaning("which executor adapter produced this profile")
    executor_type: Name = meaning(
        "generic execution mechanism: process, recording, later container"
    )
    host_id: HostId = meaning("the host these capabilities were judged against")
    availability: ExecutorAvailability = meaning(
        "whether this executor can be used here now"
    )
    process_execution: FeatureSupport = meaning("can start an isolated workload")
    structured_argv: FeatureSupport = meaning("accepts argv as a string tuple")
    environment_variables: FeatureSupport = meaning("can apply NAME=value bindings")
    working_directory: FeatureSupport = meaning("can set a working directory")
    filesystem_access: str = meaning(
        "how files are visible: host_native, mapped, or unknown"
    )
    networking: str = meaning(
        "how the workload reaches the network: host_native, isolated, or unknown"
    )
    port_binding: FeatureSupport = meaning("can bind or publish ports")
    accelerator_exposure: FeatureSupport = meaning(
        "can expose already-authorized accelerators to the workload"
    )
    bounded_stdout: FeatureSupport = meaning("captures bounded stdout")
    bounded_stderr: FeatureSupport = meaning("captures bounded stderr")
    lifecycle_observation: FeatureSupport = meaning(
        "can refresh observed execution state"
    )
    graceful_termination: FeatureSupport = meaning("can request a graceful stop")
    forced_termination: FeatureSupport = meaning(
        "can force-stop after the grace period"
    )
    isolation: FeatureSupport = meaning(
        "whether the executor isolates the workload from the host"
    )
    host_fingerprint: Maybe[str] = meaning(
        "stable host fingerprint consumed from HostCapabilities",
        default=NOT_PROVIDED,
    )
    reason: Maybe[str] = meaning(
        "why availability is not available, when it is not", default=NOT_PROVIDED
    )
    accelerator_exposure_mode: Maybe[str] = meaning(
        "how devices are exposed: host_process_inheritance, mapped, unknown",
        default=NOT_PROVIDED,
    )
    limitations: tuple[str, ...] = meaning(
        "features this implementation does not provide", default=()
    )
    evidence: tuple[str, ...] = meaning(
        "short provenance facts; never a vendor object", default=()
    )
    confidence: Confidence = meaning(
        "how much weight a caller may place on this report",
        default=Confidence.UNKNOWN,
    )


@contract(kind="execution.container_config", version=1)
@dataclass(frozen=True, slots=True)
class ContainerExecutionConfig(Contract):
    """Executor-owned container realization. Not a RuntimeLaunchSpec field."""

    image: str = meaning("OCI image reference the engine should run")
    pull_policy: PullPolicy = meaning(
        "when an image may be fetched; never during ordinary reads",
        default=PullPolicy.NEVER,
    )
    network_mode: ContainerNetworkMode = meaning(
        "how generic network bindings are realized",
        default=ContainerNetworkMode.HOST,
    )
    working_directory: str | None = meaning(
        "container working directory when the executor maps one",
        default=None,
    )
    name_prefix: str = meaning(
        "prefix for generated container names; must stay Kultrun-owned",
        default="kultrun-",
    )
    managed_label: str = meaning(
        "identity label that constrains cleanup",
        default="kultrun.managed=1",
    )
    remove_on_stop: bool = meaning(
        "whether this executor removes the container after stop",
        default=True,
    )
    engine_executable: str = meaning(
        "engine CLI name or path; composition-controlled, never caller argv",
        default="docker",
    )

    def __post_init__(self) -> None:
        _reject_shell_string(self.engine_executable, what="engine executable")
        if not self.image.strip() or any(
            character in self.image for character in " \t\n;|&$`()<>"
        ):
            raise ValidationError(
                "image reference is not a safe token", image=self.image
            )
        if not self.name_prefix.startswith("kultrun"):
            raise ValidationError(
                "container name prefix must be Kultrun-owned",
                name_prefix=self.name_prefix,
            )
        if "=" not in self.managed_label:
            raise ValidationError("managed label must be key=value")
        key, _, value = self.managed_label.partition("=")
        if not key.startswith("kultrun.") or not value:
            raise ValidationError(
                "managed label must be a kultrun.* key",
                managed_label=self.managed_label,
            )
        if self.working_directory is not None and (
            not self.working_directory.strip() or "\0" in self.working_directory
        ):
            raise ValidationError("working directory is malformed")


@contract(kind="execution.engine_probe", version=1)
@dataclass(frozen=True, slots=True)
class ContainerEngineProbe(Contract):
    """Whether a container engine is actually usable, not theoretically."""

    engine: Name = meaning("which engine adapter produced this probe")
    availability: ExecutorAvailability = meaning(
        "available only when the engine answered a bounded probe"
    )
    failure_kind: Maybe[str] = meaning(
        "normalized reason when availability is not available",
        default=NOT_PROVIDED,
    )
    version: Maybe[str] = meaning(
        "engine version when the probe obtained one", default=NOT_PROVIDED
    )
    reason: Maybe[str] = meaning(
        "human-readable normalized detail, never raw CLI stderr",
        default=NOT_PROVIDED,
    )
    evidence: tuple[str, ...] = meaning(
        "short provenance facts; never a vendor object", default=()
    )


def environment_as_dict(entries: tuple[str, ...]) -> dict[str, str]:
    """NAME=value strings into a mapping. Entries are already validated."""
    return dict(_split_env(entry) for entry in entries)


def _split_env(entry: str) -> tuple[str, str]:
    if "=" not in entry:
        raise ValidationError(
            "environment entry must be NAME=value",
            entry=entry,
        )
    name, value = entry.split("=", 1)
    return name, value


_SHELL_NAMES = frozenset({"sh", "bash", "zsh", "dash", "csh", "ksh", "fish"})


def _reject_shell_string(value: str, *, what: str) -> None:
    """Refuse the shapes that would turn structured launch into `sh -c`."""
    if not isinstance(value, str):
        raise ValidationError(
            f"{what} must be a string",
            actual_type=type(value).__name__,
        )
    if Path(value).name in _SHELL_NAMES:
        raise ValidationError(
            f"{what} must not be a shell; Kultrun does not expose sh -c",
            executable=value,
        )
