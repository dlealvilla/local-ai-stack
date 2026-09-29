"""Non-content inference usage. Not a prompt store and not admission."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

NOT_RECORDED = "not_recorded"
PURPOSES = frozenset({"operator_test", "acceptance_probe", "user_request"})
OUTCOMES = frozenset({"completed", "failed"})
IDENTITY_KINDS = frozenset(
    {"warehouse_artifact", "provider_digest", "not_recorded"}
)
_TOKEN_MAX = 240


@contract(kind="kernel.inference_usage", version=1)
@dataclass(frozen=True, slots=True)
class InferenceUsage(Contract):
    """One request's accounting facts. Text is not a field."""

    usage_id: str = meaning("stable usage identity")
    request_id: str = meaning("request correlation")
    occurred_at: str = meaning("UTC time at the Rukan boundary")
    purpose: str = meaning("operator_test, acceptance_probe, or user_request")
    install_id: str = meaning("install id, or not_recorded")
    instance_id: str = meaning("serving instance, or not_recorded")
    plan_id: str = meaning("plan, or not_recorded")
    reservation_id: str = meaning("reservation, or not_recorded")
    generation_id: str = meaning("foundation generation, or not_recorded")
    model_identity: str = meaning("artifact id or provider digest")
    model_identity_kind: str = meaning("warehouse_artifact, provider_digest, or not_recorded")  # noqa: E501
    macropath: str = meaning("runtime family, or not_recorded")
    outcome: str = meaning("completed or failed")
    failure: str = meaning("typed failure, or none")
    status_code: int = meaning("protocol status; 0 when the call had none")
    input_tokens: str = meaning("reported input tokens, or not_recorded")
    output_tokens: str = meaning("reported output tokens, or not_recorded")
    latency_ms: str = meaning("Rukan boundary latency in milliseconds, or not_recorded")
    runtime_duration_ms: str = meaning("runtime-reported duration, or not_recorded")
    version: str = meaning("Rukan version")
    build_id: str = meaning("build id, or not_recorded")

    def __post_init__(self) -> None:
        if self.purpose not in PURPOSES:
            raise ValidationError("inference usage purpose is unknown")
        if self.outcome not in OUTCOMES:
            raise ValidationError("inference usage outcome is unknown")
        if self.model_identity_kind not in IDENTITY_KINDS:
            raise ValidationError("inference usage identity kind is unknown")
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValidationError("inference usage status code is invalid")
        if self.status_code < 0 or self.status_code > 599:
            raise ValidationError("inference usage status code is outside 0..599")
        for label, value in (
            ("usage", self.usage_id),
            ("request", self.request_id),
            ("occurred", self.occurred_at),
            ("failure", self.failure),
            ("version", self.version),
        ):
            _token(label, value)
        for label, value in (
            ("input tokens", self.input_tokens),
            ("output tokens", self.output_tokens),
            ("latency", self.latency_ms),
            ("runtime duration", self.runtime_duration_ms),
        ):
            _amount(label, value)


def _token(label: str, value: str) -> None:
    if not value or len(value) > _TOKEN_MAX:
        raise ValidationError(f"inference usage {label} is empty or too long")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValidationError(f"inference usage {label} must not contain controls")


def _amount(label: str, value: str) -> None:
    if value == NOT_RECORDED:
        return
    if not value.isdigit():
        raise ValidationError(f"inference usage {label} is not a count")
