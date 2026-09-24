"""Serve contracts (MACHI 9).

A serving instance is one logical deployment. It is not a pid.
Only a matching reservation may start it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

_TOKEN_MAX = 80
_REASON_MAX = 240


class ServeFailure(StrEnum):
    """Why serve did not proceed or did not finish cleanly."""

    NONE = "none"
    RESERVATION_REQUIRED = "reservation_required"
    RESERVATION_NOT_AUTHORIZED = "reservation_not_authorized"
    RESERVATION_RELEASED = "reservation_released"
    PLAN_RESERVATION_MISMATCH = "plan_reservation_mismatch"
    FOUNDATION_NOT_READY = "foundation_not_ready"
    FOUNDATION_MISMATCH = "foundation_mismatch"
    MODEL_ARTIFACT_NOT_STORED = "model_artifact_not_stored"
    MODEL_ARTIFACT_INTEGRITY_FAILED = "model_artifact_integrity_failed"
    UNSUPPORTED_SERVE_PROVIDER = "unsupported_serve_provider"
    ENDPOINT_UNAVAILABLE = "endpoint_unavailable"
    PORT_CONFLICT = "port_conflict"
    PROCESS_LAUNCH_FAILED = "process_launch_failed"
    PROCESS_EXITED_BEFORE_READY = "process_exited_before_ready"
    READINESS_TIMEOUT = "readiness_timeout"
    READINESS_FAILED = "readiness_failed"
    INFERENCE_FAILED = "inference_failed"
    PROCESS_STOP_FAILED = "process_stop_failed"
    PROCESS_IDENTITY_UNRESOLVED = "process_identity_unresolved"
    SERVING_STATE_INVALID = "serving_state_invalid"
    PROVIDER_RESIDENCY_MISMATCH = "provider_residency_mismatch"
    PROVIDER_UNLOAD_FAILED = "provider_unload_failed"
    PROVIDER_API_FAILED = "provider_api_failed"


class InstanceState(StrEnum):
    """Lifecycle of one logical instance. Ready is not 'process exists'."""

    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class HealthState(StrEnum):
    """Readiness of the runtime, distinct from the process existing."""

    UNKNOWN = "unknown"
    READY = "ready"
    UNREADY = "unready"


class ServeOutcome(StrEnum):
    STARTED = "started"
    READY = "ready"
    STOPPED = "stopped"
    REFUSED = "refused"
    PROVEN = "proven"
    FAILED = "failed"


@contract(kind="serve.instance", version=1)
@dataclass(frozen=True, slots=True)
class ServingInstance(Contract):
    """Logical serving deployment. Process details live in provider evidence."""

    instance_id: str = meaning("identity of this deployment")
    plan_id: str = meaning("plan this instance serves")
    fingerprint: str = meaning("plan fingerprint at start")
    reservation_id: str = meaning("reservation that authorized the start")
    generation_id: str = meaning("verified foundation generation")
    artifact_id: str = meaning("verified warehouse artifact")
    serve_provider: str = meaning("runtime provider, such as vllm")
    executor_kind: str = meaning("executor kind, such as native_process")
    endpoint_id: str = meaning("logical endpoint identity")
    state: InstanceState = meaning("lifecycle")
    health: HealthState = meaning("readiness, separate from process existence")
    evidence_id: str = meaning("provider evidence record")
    policy_version: str = meaning("serve policy that started this instance")

    def __post_init__(self) -> None:
        for name, value in (
            ("instance", self.instance_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("reservation", self.reservation_id),
            ("generation", self.generation_id),
            ("artifact", self.artifact_id),
            ("provider", self.serve_provider),
            ("executor", self.executor_kind),
            ("endpoint", self.endpoint_id),
            ("evidence", self.evidence_id),
            ("policy", self.policy_version),
        ):
            _bounded(value, what=name, maximum=_TOKEN_MAX)


@contract(kind="serve.transition", version=1)
@dataclass(frozen=True, slots=True)
class ServeTransition(Contract):
    """One lifecycle step. The instance record is not rewritten."""

    transition_id: str = meaning("identity of this step")
    instance_id: str = meaning("instance that moved")
    sequence: int = meaning("order of steps for this instance")
    state: InstanceState = meaning("state after this step")
    health: HealthState = meaning("readiness after this step")

    def __post_init__(self) -> None:
        _bounded(self.transition_id, what="transition", maximum=_TOKEN_MAX)
        _bounded(self.instance_id, what="instance", maximum=_TOKEN_MAX)
        if self.sequence < 0:
            raise ValidationError("transition sequence must not be negative")


@contract(kind="serve.inference", version=1)
@dataclass(frozen=True, slots=True)
class InferenceProof(Contract):
    """One request proof. Prompt text and generated text stay out."""

    proof_id: str = meaning("identity of this proof")
    instance_id: str = meaning("instance that served the request")
    plan_id: str = meaning("plan")
    fingerprint: str = meaning("plan fingerprint")
    reservation_id: str = meaning("reservation")
    generation_id: str = meaning("foundation generation")
    artifact_id: str = meaning("model artifact")
    request_kind: str = meaning("protocol request kind")
    status_code: int = meaning("protocol status")
    completion_tokens: Maybe[int] = meaning("token count when the runtime reported one")
    structurally_valid: bool = meaning("response had the expected structure")
    failure: ServeFailure = meaning("none when the proof succeeded")

    def __post_init__(self) -> None:
        for name, value in (
            ("proof", self.proof_id),
            ("instance", self.instance_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("reservation", self.reservation_id),
            ("generation", self.generation_id),
            ("artifact", self.artifact_id),
            ("request", self.request_kind),
        ):
            _bounded(value, what=name, maximum=_TOKEN_MAX)
        if self.status_code < 0 or self.status_code > 599:
            raise ValidationError("status code is outside the HTTP range")
        if isinstance(self.completion_tokens, int) and self.completion_tokens < 0:
            raise ValidationError("completion tokens must not be negative")


@contract(kind="serve.decision", version=1)
@dataclass(frozen=True, slots=True)
class ServeDecision(Contract):
    """Started, proven, stopped, or refused. Callers do not infer from exceptions."""

    outcome: ServeOutcome = meaning("what serve did")
    failure: ServeFailure = meaning("none when the outcome succeeded")
    reason: str = meaning("short explanation")
    instance: Maybe[ServingInstance] = meaning("instance when one exists")
    proof: Maybe[InferenceProof] = meaning("proof when one was recorded")

    def __post_init__(self) -> None:
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)
        if self.outcome is ServeOutcome.REFUSED and is_resolved(self.instance):
            raise ValidationError("a refusal before launch has no instance")
        if self.outcome is ServeOutcome.PROVEN and (
            not is_resolved(self.proof) or self.failure is not ServeFailure.NONE
        ):
            raise ValidationError("a proven outcome carries a successful proof")


def refused(failure: ServeFailure, reason: str) -> ServeDecision:
    return ServeDecision(
        outcome=ServeOutcome.REFUSED,
        failure=failure,
        reason=reason,
        instance=NOT_PROVIDED,
        proof=NOT_PROVIDED,
    )


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
