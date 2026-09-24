"""Provider-backed serving plan. It does not invent a warehouse artifact."""

from __future__ import annotations

from dataclasses import dataclass

from machi.capacity.contracts import AcceleratorCapacity, CapacityEnvelope
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from machi.model.provider_candidate import canonical_digest
from machi.model.provider_qualification import (
    OllamaQualificationEvidence,
    qualification_covers,
)
from machi.plan.contracts import (
    PlanFailure,
    PlanProvenance,
    PlanSetting,
    PlanStatus,
    _bounded,
)
from machi.plan.identity import decision_id, plan_fingerprint, plan_id, request_id
from machi.plan.policy import ACCELERATOR_COUNT, CPU_COUNT, POLICY_VERSION

_TOKEN_MAX = 80
_MAX_SETTINGS = 16


@contract(kind="plan.provider_configuration", version=1)
@dataclass(frozen=True, slots=True)
class ProviderDeploymentConfiguration(Contract):
    """Immutable provider serving request. The digest is the model identity."""

    plan_id: str = meaning("identity of this provider plan")
    status: PlanStatus = meaning("planned; stale is a later comparison")
    provider: str = meaning("runtime provider; ollama in this increment")
    display_name: str = meaning("catalog address; not the immutable identity")
    digest: str = meaning("immutable provider model digest")
    candidate_id: str = meaning("digest-derived candidate identity")
    foundation_id: str = meaning("foundation identity this plan cited")
    generation_id: str = meaning(
        "verified foundation generation (fgen_); not a runtime environment id"
    )
    execution_environment_fingerprint: str = meaning(
        "material accelerator environment"
    )
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    accelerator_count: int = meaning("accelerators this plan requests")
    accelerator_identity: str = meaning("capacity device identity")
    context_length: int = meaning("serving context sent as num_ctx")
    concurrency: int = meaning("bounded in-flight sequences")
    qualification_id: str = meaning("provider qualification that covers this plan")
    policy_version: str = meaning("plan policy that produced this result")
    fingerprint: str = meaning("deterministic token of the material inputs")
    settings: tuple[PlanSetting, ...] = meaning("effective serving settings")

    def __post_init__(self) -> None:
        for label, value in (
            ("plan", self.plan_id),
            ("provider", self.provider),
            ("name", self.display_name),
            ("digest", self.digest),
            ("candidate", self.candidate_id),
            ("foundation", self.foundation_id),
            ("generation", self.generation_id),
            ("environment", self.execution_environment_fingerprint),
            ("capacity", self.capacity_evidence_id),
            ("accelerator", self.accelerator_identity),
            ("qualification", self.qualification_id),
            ("policy", self.policy_version),
            ("fingerprint", self.fingerprint),
        ):
            _bounded(value, what=label, maximum=_TOKEN_MAX)
        if self.provider != "ollama":
            raise ValidationError("this provider plan increment is ollama")
        if self.accelerator_count != 1:
            raise ValidationError("this plan increment requests one accelerator")
        if self.context_length < 1 or self.concurrency != 1:
            raise ValidationError("provider serving bounds are context and one")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many plan settings")
        try:
            if canonical_digest(self.digest) != self.digest:
                raise ValidationError("provider plan digest is not canonical")
        except ValidationError as exc:
            raise ValidationError("provider plan digest is not canonical") from exc


@contract(kind="plan.provider_resource_request", version=1)
@dataclass(frozen=True, slots=True)
class ProviderResourceRequest(Contract):
    """Bytes a provider plan asks to hold. There is no warehouse artifact."""

    request_id: str = meaning("identity of this request")
    plan_id: str = meaning("provider plan this request belongs to")
    fingerprint: str = meaning("same material token as the provider plan")
    foundation_id: str = meaning("foundation identity cited")
    generation_id: str = meaning(
        "verified foundation generation (fgen_); not a runtime environment id"
    )
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    digest: str = meaning("provider model digest cited")
    accelerator_count: int = meaning("accelerators requested")
    accelerator_memory_bytes: int = meaning("SAFE accelerator budget requested")
    host_memory_bytes: int = meaning("SAFE host memory budget requested")
    persistent_bytes: int = meaning("warehouse bytes; zero for an already-local model")
    transient_bytes: int = meaning("extra staging bytes for serving")
    cpu_count: int = meaning("process slots requested")

    def __post_init__(self) -> None:
        for label, value in (
            ("request", self.request_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("foundation", self.foundation_id),
            ("generation", self.generation_id),
            ("capacity", self.capacity_evidence_id),
            ("digest", self.digest),
        ):
            _bounded(value, what=label, maximum=_TOKEN_MAX)
        if self.accelerator_count != 1:
            raise ValidationError("this request asks for one accelerator")
        if self.accelerator_memory_bytes < 1 or self.host_memory_bytes < 1:
            raise ValidationError("memory requests must be positive")
        if self.persistent_bytes < 0 or self.transient_bytes < 0:
            raise ValidationError("storage requests must not be negative")
        if self.cpu_count < 1:
            raise ValidationError("cpu request must be positive")


@contract(kind="plan.provider_decision", version=1)
@dataclass(frozen=True, slots=True)
class ProviderPlanDecision(Contract):
    """One provider compose result. A refusal carries no configuration."""

    decision_id: str = meaning("identity of this decision")
    failure: PlanFailure = meaning("none when a provider plan was produced")
    reason: str = meaning("why this result was produced")
    fingerprint: str = meaning("token of the inputs, including refusals")
    configuration: Maybe[ProviderDeploymentConfiguration] = meaning(
        "planned provider configuration, or unresolved when refused"
    )
    request: Maybe[ProviderResourceRequest] = meaning(
        "provider resource request, or unresolved when refused"
    )

    def __post_init__(self) -> None:
        _bounded(self.decision_id, what="decision", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="reason", maximum=240)
        _bounded(self.fingerprint, what="fingerprint", maximum=_TOKEN_MAX)
        configured = is_resolved(self.configuration)
        requested = is_resolved(self.request)
        if self.failure is PlanFailure.NONE:
            if not configured or not requested:
                raise ValidationError("a planned decision needs both outputs")
        elif configured or requested:
            raise ValidationError("a refusal does not carry a plan")


@dataclass(frozen=True, slots=True)
class ProviderPlanInputs:
    """Records the provider plan may cite. It does not recompute them."""

    display_name: str
    digest: str
    candidate_id: str
    qualification: OllamaQualificationEvidence
    envelope: CapacityEnvelope
    foundation_id: str
    generation_id: str
    foundation_ready: bool
    accelerator_identity: str
    execution_environment_fingerprint: str
    context: int
    concurrency: int


def compose_provider_plan(inputs: ProviderPlanInputs) -> ProviderPlanDecision:
    """Return a provider plan or a typed refusal. Bytes are the cited SAFE ceiling."""
    token = _fingerprint(inputs)
    failure = _refusal(inputs)
    if failure is not None:
        return _refused(token, failure, _reason(failure))
    device = _device(inputs)
    assert isinstance(device, AcceleratorCapacity)
    host = inputs.envelope.memory.safe_bytes
    accel = device.safe_bytes
    assert isinstance(host, int)
    assert isinstance(accel, int)
    settings = (
        PlanSetting(
            "context_length",
            str(inputs.context),
            PlanProvenance.ADMINISTRATOR_REQUEST,
            "requested context is sent as num_ctx",
        ),
        PlanSetting(
            "concurrency",
            "1",
            PlanProvenance.PRODUCT_DEFAULT,
            "this increment serves one sequence",
        ),
        PlanSetting(
            "qualification_id",
            inputs.qualification.qualification_id,
            PlanProvenance.DERIVED,
            "coverage comes from the provider qualification",
        ),
    )
    configuration = ProviderDeploymentConfiguration(
        plan_id=plan_id(token),
        status=PlanStatus.PLANNED,
        provider="ollama",
        display_name=inputs.display_name,
        digest=canonical_digest(inputs.digest),
        candidate_id=inputs.candidate_id,
        foundation_id=inputs.foundation_id,
        generation_id=inputs.generation_id,
        execution_environment_fingerprint=inputs.execution_environment_fingerprint,
        capacity_evidence_id=inputs.envelope.evidence_id,
        accelerator_count=ACCELERATOR_COUNT,
        accelerator_identity=device.identity,
        context_length=inputs.context,
        concurrency=1,
        qualification_id=inputs.qualification.qualification_id,
        policy_version=POLICY_VERSION,
        fingerprint=token,
        settings=settings,
    )
    request = ProviderResourceRequest(
        request_id=request_id(token),
        plan_id=configuration.plan_id,
        fingerprint=token,
        foundation_id=configuration.foundation_id,
        generation_id=configuration.generation_id,
        capacity_evidence_id=configuration.capacity_evidence_id,
        digest=configuration.digest,
        accelerator_count=ACCELERATOR_COUNT,
        accelerator_memory_bytes=accel,
        host_memory_bytes=host,
        persistent_bytes=0,
        transient_bytes=0,
        cpu_count=CPU_COUNT,
    )
    return ProviderPlanDecision(
        decision_id=decision_id(token),
        failure=PlanFailure.NONE,
        reason="provider plan inside the cited safe capacity",
        fingerprint=token,
        configuration=configuration,
        request=request,
    )


def _fingerprint(inputs: ProviderPlanInputs) -> str:
    try:
        digest = canonical_digest(inputs.digest)
    except ValidationError:
        digest = inputs.digest
    return plan_fingerprint(
        "provider-plan",
        POLICY_VERSION,
        "ollama",
        digest,
        inputs.candidate_id,
        inputs.foundation_id,
        inputs.generation_id,
        inputs.execution_environment_fingerprint,
        inputs.envelope.evidence_id,
        inputs.accelerator_identity,
        str(inputs.context),
        str(inputs.concurrency),
        inputs.qualification.qualification_id,
    )


def _refusal(inputs: ProviderPlanInputs) -> PlanFailure | None:
    if not inputs.foundation_ready:
        return PlanFailure.FOUNDATION_NOT_READY
    if not inputs.foundation_id or not inputs.generation_id:
        return PlanFailure.FOUNDATION_MISMATCH
    if not inputs.generation_id.startswith("fgen_"):
        return PlanFailure.FOUNDATION_MISMATCH
    if inputs.foundation_id.startswith("renv_"):
        return PlanFailure.FOUNDATION_MISMATCH
    if inputs.generation_id != inputs.qualification.generation_id:
        return PlanFailure.FOUNDATION_MISMATCH
    if inputs.concurrency != 1:
        return PlanFailure.INVALID_REQUESTED_CONCURRENCY
    if inputs.context < 1:
        return PlanFailure.INVALID_REQUESTED_CONTEXT
    try:
        canonical_digest(inputs.digest)
    except ValidationError:
        return PlanFailure.QUALIFICATION_DOES_NOT_COVER
    if (
        inputs.execution_environment_fingerprint
        != inputs.qualification.execution_environment_fingerprint
    ):
        return PlanFailure.QUALIFICATION_DOES_NOT_COVER
    if not qualification_covers(
        inputs.qualification,
        digest=inputs.digest,
        generation_id=inputs.generation_id,
        context=inputs.context,
        concurrency=inputs.concurrency,
    ):
        return PlanFailure.QUALIFICATION_DOES_NOT_COVER
    if inputs.qualification.display_name != inputs.display_name:
        return PlanFailure.QUALIFICATION_DOES_NOT_COVER
    host = inputs.envelope.memory.safe_bytes
    if not isinstance(host, int):
        return PlanFailure.CAPACITY_SNAPSHOT_UNRESOLVED
    if host < 1:
        return PlanFailure.INSUFFICIENT_SAFE_CAPACITY
    device = _device(inputs)
    if isinstance(device, PlanFailure):
        return device
    if not isinstance(device.safe_bytes, int) or device.safe_bytes < 1:
        return PlanFailure.CAPACITY_SNAPSHOT_UNRESOLVED
    return None


def _device(
    inputs: ProviderPlanInputs,
) -> AcceleratorCapacity | PlanFailure:
    found = [
        item
        for item in inputs.envelope.accelerators
        if item.identity == inputs.accelerator_identity
    ]
    if len(found) != 1:
        return PlanFailure.SINGLE_ACCELERATOR_PLAN_NOT_FEASIBLE
    return found[0]


def _refused(token: str, failure: PlanFailure, reason: str) -> ProviderPlanDecision:
    return ProviderPlanDecision(
        decision_id=decision_id(token),
        failure=failure,
        reason=reason,
        fingerprint=token,
        configuration=NOT_PROVIDED,
        request=NOT_PROVIDED,
    )


def _reason(failure: PlanFailure) -> str:
    return failure.value.replace("_", " ")
