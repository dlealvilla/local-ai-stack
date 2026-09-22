"""Plan contracts (MACHI 7).

A plan is a request for admission. It does not reserve resources or
start a runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

_TOKEN_MAX = 80
_REASON_MAX = 240
_MAX_SETTINGS = 16


class PlanFailure(StrEnum):
    """Why a plan was not produced, or why an old plan is stale."""

    NONE = "none"
    MODEL_ARTIFACT_NOT_STORED = "model_artifact_not_stored"
    MODEL_ARTIFACT_INTEGRITY_FAILED = "model_artifact_integrity_failed"
    MODEL_NOT_COMPATIBLE = "model_not_compatible"
    MODEL_CONDITION_UNRESOLVED = "model_condition_unresolved"
    FOUNDATION_NOT_READY = "foundation_not_ready"
    FOUNDATION_NOT_QUALIFIED = "foundation_not_qualified"
    FOUNDATION_MISMATCH = "foundation_mismatch"
    CAPACITY_SNAPSHOT_UNRESOLVED = "capacity_snapshot_unresolved"
    INSUFFICIENT_SAFE_CAPACITY = "insufficient_safe_capacity"
    SINGLE_ACCELERATOR_PLAN_NOT_FEASIBLE = "single_accelerator_plan_not_feasible"
    MULTI_ACCELERATOR_PLANNING_NOT_IMPLEMENTED = (
        "multi_accelerator_planning_not_implemented"
    )
    UNSUPPORTED_RUNTIME_PROVIDER = "unsupported_runtime_provider"
    INVALID_REQUESTED_CONTEXT = "invalid_requested_context"
    INVALID_REQUESTED_CONCURRENCY = "invalid_requested_concurrency"
    STALE_MODEL_INPUT = "stale_model_input"
    STALE_FOUNDATION_INPUT = "stale_foundation_input"
    STALE_CAPACITY_INPUT = "stale_capacity_input"
    STALE_POLICY_INPUT = "stale_policy_input"
    STALE_PREFERENCE_INPUT = "stale_preference_input"


class PlanProvenance(StrEnum):
    """Where an effective plan value came from."""

    MODEL_METADATA = "model_metadata"
    FOUNDATION_CAPABILITY = "foundation_capability"
    CAPACITY = "capacity"
    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR_REQUEST = "administrator_request"
    DERIVED = "derived"


class PlanStatus(StrEnum):
    """Immutable plan state. Admitted and running belong later."""

    PLANNED = "planned"
    REFUSED = "refused"
    STALE = "stale"


@contract(kind="plan.setting", version=1)
@dataclass(frozen=True, slots=True)
class PlanSetting(Contract):
    """One effective serving value and who chose it."""

    name: str = meaning("setting name")
    value: str = meaning("effective value")
    provenance: PlanProvenance = meaning("why this value was chosen")
    reason: str = meaning("short justification")

    def __post_init__(self) -> None:
        _bounded(self.name, what="setting", maximum=_TOKEN_MAX)
        _bounded(self.value, what="value", maximum=_REASON_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)


@contract(kind="plan.preference", version=1)
@dataclass(frozen=True, slots=True)
class PlanPreference(Contract):
    """Bounded request. It cannot raise a hard upstream limit."""

    context_length: Maybe[int] = meaning("requested context, or unresolved")
    concurrency: Maybe[int] = meaning("requested concurrency, or unresolved")
    accelerator_count: int = meaning("requested accelerators; only one is planned")

    def __post_init__(self) -> None:
        if isinstance(self.context_length, int) and self.context_length < 1:
            raise ValidationError("requested context must be positive")
        if isinstance(self.concurrency, int) and self.concurrency < 1:
            raise ValidationError("requested concurrency must be positive")
        if self.accelerator_count < 1:
            raise ValidationError("accelerator count must be positive")


@contract(kind="plan.configuration", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentConfiguration(Contract):
    """Immutable serving request. Not an admission and not a process."""

    plan_id: str = meaning("identity of this plan")
    status: PlanStatus = meaning("planned; stale is a later comparison")
    model_id: str = meaning("logical model")
    artifact_id: str = meaning("verified warehouse artifact")
    immutable_revision: str = meaning("exact revision")
    foundation_id: str = meaning("foundation identity this plan cited")
    generation_id: str = meaning("verified runtime generation")
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    provider: str = meaning("runtime provider from the foundation")
    accelerator_count: int = meaning("accelerators this plan requests")
    accelerator_identity: str = meaning("capacity device identity")
    context_length: int = meaning("serving context, not the model maximum")
    concurrency: int = meaning("bounded in-flight sequences")
    dtype: str = meaning("dtype carried from the artifact")
    quantization: str = meaning("published quantization carried forward")
    policy_version: str = meaning("plan policy that produced this result")
    fingerprint: str = meaning("deterministic token of the material inputs")
    settings: tuple[PlanSetting, ...] = meaning("effective serving settings")

    def __post_init__(self) -> None:
        _bounded(self.plan_id, what="plan", maximum=_TOKEN_MAX)
        _bounded(self.model_id, what="model", maximum=_TOKEN_MAX)
        _bounded(self.artifact_id, what="artifact", maximum=_TOKEN_MAX)
        _bounded(self.immutable_revision, what="revision", maximum=_TOKEN_MAX)
        _bounded(self.foundation_id, what="foundation", maximum=_TOKEN_MAX)
        _bounded(self.generation_id, what="generation", maximum=_TOKEN_MAX)
        _bounded(self.capacity_evidence_id, what="capacity", maximum=_TOKEN_MAX)
        _bounded(self.provider, what="provider", maximum=_TOKEN_MAX)
        _bounded(self.accelerator_identity, what="accelerator", maximum=_TOKEN_MAX)
        _bounded(self.dtype, what="dtype", maximum=_TOKEN_MAX)
        _bounded(self.quantization, what="quantization", maximum=_TOKEN_MAX)
        _bounded(self.policy_version, what="policy", maximum=_TOKEN_MAX)
        _bounded(self.fingerprint, what="fingerprint", maximum=_TOKEN_MAX)
        if self.accelerator_count != 1:
            raise ValidationError("this plan increment requests one accelerator")
        if self.context_length < 1 or self.concurrency < 1:
            raise ValidationError("serving bounds must be positive")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many plan settings")


@contract(kind="plan.resource_request", version=1)
@dataclass(frozen=True, slots=True)
class ResourceRequest(Contract):
    """What admission is asked to grant. Not a reservation."""

    request_id: str = meaning("identity of this request")
    plan_id: str = meaning("configuration this request belongs to")
    fingerprint: str = meaning("same material token as the configuration")
    foundation_id: str = meaning("foundation identity cited")
    generation_id: str = meaning("runtime generation cited")
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    artifact_id: str = meaning("warehouse artifact cited")
    accelerator_count: int = meaning("accelerators requested")
    accelerator_memory_bytes: int = meaning("SAFE accelerator budget requested")
    host_memory_bytes: int = meaning("SAFE host memory budget requested")
    persistent_bytes: int = meaning("warehouse bytes already stored")
    transient_bytes: int = meaning("extra staging bytes for serving")
    cpu_count: int = meaning("process slots requested")

    def __post_init__(self) -> None:
        _bounded(self.request_id, what="request", maximum=_TOKEN_MAX)
        _bounded(self.plan_id, what="plan", maximum=_TOKEN_MAX)
        _bounded(self.fingerprint, what="fingerprint", maximum=_TOKEN_MAX)
        _bounded(self.foundation_id, what="foundation", maximum=_TOKEN_MAX)
        _bounded(self.generation_id, what="generation", maximum=_TOKEN_MAX)
        _bounded(self.capacity_evidence_id, what="capacity", maximum=_TOKEN_MAX)
        _bounded(self.artifact_id, what="artifact", maximum=_TOKEN_MAX)
        if self.accelerator_count != 1:
            raise ValidationError("this request asks for one accelerator")
        if self.accelerator_memory_bytes < 1 or self.host_memory_bytes < 1:
            raise ValidationError("memory requests must be positive")
        if self.persistent_bytes < 0 or self.transient_bytes < 0:
            raise ValidationError("storage requests must not be negative")
        if self.cpu_count < 1:
            raise ValidationError("cpu request must be positive")


@contract(kind="plan.decision", version=1)
@dataclass(frozen=True, slots=True)
class PlanDecision(Contract):
    """One compose result. A refusal does not contain a configuration."""

    decision_id: str = meaning("identity of this decision")
    failure: PlanFailure = meaning("none when a plan was produced")
    reason: str = meaning("why this result was produced")
    fingerprint: str = meaning("token of the inputs, including refusals")
    configuration: Maybe[DeploymentConfiguration] = meaning(
        "planned configuration, or unresolved when refused"
    )
    request: Maybe[ResourceRequest] = meaning(
        "resource request, or unresolved when refused"
    )

    def __post_init__(self) -> None:
        _bounded(self.decision_id, what="decision", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)
        _bounded(self.fingerprint, what="fingerprint", maximum=_TOKEN_MAX)
        configured = is_resolved(self.configuration)
        requested = is_resolved(self.request)
        if self.failure is PlanFailure.NONE:
            if not configured or not requested:
                raise ValidationError("a planned decision needs both outputs")
        elif configured or requested:
            raise ValidationError("a refusal does not carry a plan")


@dataclass(frozen=True, slots=True)
class RuntimeRecipe:
    """Provider payload already checked by that provider."""

    provider: str
    schema_version: int
    settings: tuple[PlanSetting, ...]


def default_preference() -> PlanPreference:
    """No administrator override."""
    return PlanPreference(
        context_length=NOT_PROVIDED,
        concurrency=NOT_PROVIDED,
        accelerator_count=1,
    )


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
