"""One deployed model-serving workload.

`docs/PRODUCT_VISION.md` §12 makes this a primary platform concept, and it
is deliberately distinct from the stored artifact: the same artifact can be
served by two instances with different context lengths, different
concurrency and different access policies.

**Status and health are different questions**, and Stage 1.6 requires them
kept apart. ``reachable`` asks whether the port answers; ``health`` asks
whether the API works. A process that has bound its port but cannot load
the model is reachable and unhealthy, and a platform that cannot express
that will report it as running.

**Two concurrency dimensions, never merged.** `docs/PRODUCT_VISION.md` §13:
``runtime_concurrency`` is how many requests one loaded instance handles;
``platform_max_concurrent_requests`` is the gateway's limit. The previous
attempt held a platform-level number that was never mapped to the runtime's
own control, which is why Stage 4.3 exists.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.execution.contracts import ExecutionId
from kultrun.host.contracts import HostId
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe
from kultrun.model.contracts import ArtifactId, ModelId
from kultrun.resource.contracts import ReservationId


class InstanceId(EntityId):
    """Identifies one serving instance."""

    prefix = "inst"


class InferenceRequestId(EntityId):
    """Identifies one non-streaming inference request. Not persisted."""

    prefix = "ireq"


class LifecycleState(StrEnum):
    """What the platform intends and observes about an instance."""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class DesiredState(StrEnum):
    """What Kultrun wants the instance to be. Not what it is."""

    RUNNING = "running"
    STOPPED = "stopped"


class ObservedState(StrEnum):
    """What the instance actually is, last reconciled."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class HealthState(StrEnum):
    """Whether the instance actually works.

    ``UNKNOWN`` is a real answer, not a placeholder: an instance that has
    not been probed since restart is not healthy and is not unhealthy, and
    reconciliation must be able to say so.
    """

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@contract(kind="inference.endpoint", version=1)
@dataclass(frozen=True, slots=True)
class InferenceEndpoint(Contract):
    """Where an instance can be reached."""

    scheme: str = meaning("transport scheme")
    address: str = meaning("host or address the instance is bound to")
    port: int = meaning("port the instance is bound to")
    base_path: str = meaning("path prefix the runtime serves under", default="/")


@contract(kind="inference.instance", version=1)
@dataclass(frozen=True, slots=True)
class InferenceInstance(Contract):
    """One model being served, on one host, under one configuration."""

    instance_id: InstanceId = meaning("platform-minted identity of this instance")
    host_id: HostId = meaning("the host it runs on")
    model_id: ModelId = meaning("the model it serves")
    runtime: Name = meaning("the inference runtime adapter serving it")
    executor: Name = meaning("the executor running the process")
    lifecycle_state: LifecycleState = meaning("what the platform intends and observes")
    health: HealthState = meaning("whether the API functions, as distinct from status")
    configuration_version: int = meaning(
        "advances when the serving configuration changes, so a restart can "
        "tell a stale instance from a current one"
    )
    model_revision: Maybe[str] = meaning(
        "the model revision being served", default=NOT_MEASURED
    )
    reachable: Maybe[bool] = meaning(
        "whether the port answers; a reachable port is not a working API",
        default=NOT_MEASURED,
    )
    endpoint: InferenceEndpoint | None = meaning(
        "where it is reachable, once it is", default=None
    )
    reservation_id: ReservationId | None = meaning(
        "the resources held for it; absent means nothing is held", default=None
    )
    context_length_tokens: Maybe[int] = meaning(
        "configured context length, which is a capacity decision not a setting",
        default=NOT_MEASURED,
    )
    runtime_concurrency: Maybe[int] = meaning(
        "simultaneous requests this instance is configured to handle",
        default=NOT_MEASURED,
    )
    platform_max_concurrent_requests: Maybe[int] = meaning(
        "the gateway's limit for this instance, a different dimension from "
        "runtime concurrency",
        default=NOT_MEASURED,
    )
    access_policy_ref: str | None = meaning(
        "the policy governing who may use it, by identifier", default=None
    )
    started_at: dt.datetime | None = meaning(
        "when it began serving; absent until it does", default=None
    )
    artifact_id: ArtifactId | None = meaning(
        "the STORED artifact this instance serves", default=None
    )
    desired_state: DesiredState = meaning(
        "what Kultrun wants", default=DesiredState.STOPPED
    )
    observed_state: ObservedState = meaning(
        "what was last reconciled", default=ObservedState.CREATED
    )
    execution_id: ExecutionId | None = meaning(
        "the executor handle, when a process was started", default=None
    )
    pid: Maybe[int] = meaning(
        "OS process id while one is known and owned", default=NOT_MEASURED
    )
    ready: Maybe[bool] = meaning(
        "whether the serving endpoint answered; distinct from process existence",
        default=NOT_MEASURED,
    )
    created_at: dt.datetime | None = meaning(
        "when the instance record was created", default=None
    )
    stopped_at: dt.datetime | None = meaning(
        "when the process last left running", default=None
    )
    last_observed_at: dt.datetime | None = meaning(
        "when observed state was last reconciled", default=None
    )
    exit_code: Maybe[int] = meaning(
        "process exit status when it has exited", default=NOT_MEASURED
    )
    failure_reason: Maybe[str] = meaning(
        "bounded why start or run failed", default=NOT_MEASURED
    )
    logical_name: Maybe[str] = meaning(
        "catalog name of the served candidate", default=NOT_MEASURED
    )
    quantization: Maybe[str] = meaning("variant being served", default=NOT_MEASURED)
    serving_runtime: Maybe[str] = meaning(
        "reference-serving identity; never an LLM engine in 1.5B",
        default=NOT_MEASURED,
    )
    plan_id: Maybe[str] = meaning(
        "DeploymentPlan identity this instance was created from",
        default=NOT_PROVIDED,
    )
    plan_basis: Maybe[str] = meaning(
        "DeploymentPlan basis consumed at create; not rewritten in place",
        default=NOT_PROVIDED,
    )
    runtime_version: Maybe[str] = meaning(
        "runtime version taken from the bound DeploymentPlan",
        default=NOT_PROVIDED,
    )
    placement: Maybe[str] = meaning(
        "device strategy taken from the bound DeploymentPlan",
        default=NOT_PROVIDED,
    )
    accelerator_index: int | None = meaning(
        "assigned accelerator taken from the bound DeploymentPlan",
        default=None,
    )


MAX_PROMPT_CHARS = 32_768
MAX_OUTPUT_TOKENS = 2_048
DEFAULT_OUTPUT_TOKENS = 64
MAX_INFERENCE_TIMEOUT_SECONDS = 300.0
DEFAULT_INFERENCE_TIMEOUT_SECONDS = 60.0
MIN_INFERENCE_TIMEOUT_SECONDS = 1.0
VLLM_STARTUP_TIMEOUT_SECONDS = 1800.0
REFERENCE_STARTUP_TIMEOUT_SECONDS = 5.0


@contract(kind="inference.request", version=1)
@dataclass(frozen=True, slots=True)
class InferenceRequest(Contract):
    """One bounded non-streaming generation. Not a vLLM or OpenAI payload."""

    prompt: str = meaning("caller text to generate from; never a model identity")
    max_output_tokens: int = meaning(
        "upper bound on generated tokens", default=DEFAULT_OUTPUT_TOKENS
    )
    temperature: float = meaning(
        "sampling temperature; 0 is deterministic-ish", default=0.0
    )
    timeout_seconds: float = meaning(
        "bounded wait for the runtime response",
        default=DEFAULT_INFERENCE_TIMEOUT_SECONDS,
    )

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValidationError("prompt must be non-empty", parameter="prompt")
        if len(self.prompt) > MAX_PROMPT_CHARS:
            raise ValidationError(
                "prompt exceeds the supported size",
                parameter="prompt",
                maximum=MAX_PROMPT_CHARS,
            )
        if self.max_output_tokens < 1:
            raise ValidationError(
                "max_output_tokens must be greater than zero",
                parameter="max_output_tokens",
            )
        if self.max_output_tokens > MAX_OUTPUT_TOKENS:
            raise ValidationError(
                "max_output_tokens exceeds the supported bound",
                parameter="max_output_tokens",
                maximum=MAX_OUTPUT_TOKENS,
            )
        if not 0.0 <= self.temperature <= 2.0:
            raise ValidationError(
                "temperature must be between 0 and 2",
                parameter="temperature",
            )
        if not (
            MIN_INFERENCE_TIMEOUT_SECONDS
            <= self.timeout_seconds
            <= MAX_INFERENCE_TIMEOUT_SECONDS
        ):
            raise ValidationError(
                "timeout_seconds is outside the supported bound",
                parameter="timeout_seconds",
            )


@contract(kind="inference.response", version=1)
@dataclass(frozen=True, slots=True)
class InferenceResponse(Contract):
    """Normalized generation result. Prompt and text are transient."""

    request_id: InferenceRequestId = meaning("platform-minted identity of this request")
    instance_id: InstanceId = meaning("instance that produced the text")
    model_id: ModelId = meaning("planned model identity")
    served_model: str = meaning("served-model identity verified at readiness")
    generated_text: str = meaning("model output; not persisted by default")
    runtime: Name = meaning("runtime adapter that served the request")
    latency_ms: int = meaning("wall time from request accept to response")
    finish_reason: Maybe[str] = meaning(
        "runtime finish reason when supplied", default=NOT_PROVIDED
    )
    input_tokens: Maybe[int] = meaning(
        "prompt token count when the runtime supplied one", default=NOT_MEASURED
    )
    output_tokens: Maybe[int] = meaning(
        "generated token count when the runtime supplied one", default=NOT_MEASURED
    )
    runtime_version: Maybe[str] = meaning(
        "runtime version taken from the instance plan provenance",
        default=NOT_PROVIDED,
    )
    executor: Maybe[str] = meaning(
        "executor that owns the runtime process", default=NOT_PROVIDED
    )
    configuration_current: Maybe[bool] = meaning(
        "whether the bound DeploymentPlan is still CURRENT; overlay only",
        default=NOT_MEASURED,
    )
