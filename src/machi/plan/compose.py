"""Compose one plan from upstream evidence. No downloads and no processes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from machi.capacity.contracts import AcceleratorCapacity, CapacityEnvelope
from machi.foundation.contracts import (
    FailureCode,
    FeatureState,
    FoundationEngine,
    FoundationSelection,
    RuntimeCapability,
    SupportState,
)
from machi.kernel.unresolved import NOT_PROVIDED, Unresolved, is_resolved
from machi.model.contracts import (
    ArtifactLifecycle,
    AvailableModelEntry,
    AvailableModels,
    CompatibilityState,
    ModelArtifact,
    ModelCompatibility,
    ModelDefinition,
    ModelRequirement,
    ModelSelection,
    ProviderQualification,
)
from machi.model.qualification import (
    DeployableModels,
    QualificationEvidence,
    covers,
    member_ids,
)
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanPreference,
    PlanProvenance,
    PlanStatus,
    ResourceRequest,
    RuntimeRecipe,
)
from machi.plan.identity import decision_id, plan_fingerprint, plan_id, request_id
from machi.plan.policy import (
    ACCELERATOR_COUNT,
    CPU_COUNT,
    DEFAULT_CONCURRENCY,
    DEFAULT_CONTEXT,
    MAX_CONCURRENCY,
    MAX_CONTEXT,
    MIN_CONCURRENCY,
    MIN_CONTEXT,
    POLICY_VERSION,
    RECIPE_SCHEMA,
    TRANSIENT_BYTES,
)


@dataclass(frozen=True, slots=True)
class PlanInputs:
    """Exact upstream records. Plan does not recompute them."""

    selection: ModelSelection
    available: AvailableModels
    artifact: ModelArtifact | None
    artifact_verified: bool
    foundation: FoundationSelection
    capability: RuntimeCapability | None
    envelope: CapacityEnvelope
    preference: PlanPreference
    deployable: DeployableModels
    qualification: QualificationEvidence
    hardware_class: str = "unspecified"
    probe: bool = False


@dataclass(frozen=True, slots=True)
class ServingDraft:
    definition: ModelDefinition
    requirement: ModelRequirement
    compatibility: ModelCompatibility
    artifact: ModelArtifact
    device: AcceleratorCapacity
    accelerator_bytes: int
    host_bytes: int
    context: int
    context_provenance: PlanProvenance
    concurrency: int
    concurrency_provenance: PlanProvenance
    fingerprint: str


def compose_plan(
    inputs: PlanInputs,
    build_recipe: Callable[[ServingDraft], RuntimeRecipe],
) -> PlanDecision:
    """Return a plan or a typed refusal. The same inputs yield the same token."""
    token = _fingerprint(inputs)
    draft = _draft(inputs, token)
    if isinstance(draft, PlanFailure):
        return _refused(token, draft, _reason(draft))
    recipe = build_recipe(draft)
    checked = _check_recipe(draft, recipe)
    if checked is not None:
        return _refused(token, checked, _reason(checked))
    configuration = DeploymentConfiguration(
        plan_id=plan_id(token),
        status=PlanStatus.PLANNED,
        model_id=draft.artifact.model_id,
        artifact_id=draft.artifact.artifact_id,
        immutable_revision=draft.artifact.immutable_revision,
        foundation_id=_foundation_identity(inputs),
        generation_id=str(inputs.foundation.generation_id),
        capacity_evidence_id=inputs.envelope.evidence_id,
        provider=recipe.provider,
        accelerator_count=ACCELERATOR_COUNT,
        accelerator_identity=draft.device.identity,
        context_length=draft.context,
        concurrency=draft.concurrency,
        dtype=_dtype(draft.definition),
        quantization=draft.definition.quantization.value,
        policy_version=POLICY_VERSION,
        fingerprint=token,
        settings=recipe.settings,
    )
    request = ResourceRequest(
        request_id=request_id(token),
        plan_id=configuration.plan_id,
        fingerprint=token,
        foundation_id=configuration.foundation_id,
        generation_id=configuration.generation_id,
        capacity_evidence_id=configuration.capacity_evidence_id,
        artifact_id=configuration.artifact_id,
        accelerator_count=ACCELERATOR_COUNT,
        accelerator_memory_bytes=draft.accelerator_bytes,
        host_memory_bytes=draft.host_bytes,
        persistent_bytes=draft.artifact.total_bytes,
        transient_bytes=TRANSIENT_BYTES,
        cpu_count=CPU_COUNT,
    )
    return PlanDecision(
        decision_id=decision_id(token),
        failure=PlanFailure.NONE,
        reason="single accelerator plan inside the cited safe capacity",
        fingerprint=token,
        configuration=configuration,
        request=request,
    )


def _draft(inputs: PlanInputs, token: str) -> ServingDraft | PlanFailure:
    del token
    entry = _entry(inputs)
    if entry is None:
        return PlanFailure.STALE_MODEL_INPUT
    definition = entry.definition
    compatibility = entry.compatibility
    requirement = entry.requirement
    if inputs.selection.compatibility_state is not compatibility.state:
        return PlanFailure.STALE_MODEL_INPUT
    if inputs.preference.accelerator_count != ACCELERATOR_COUNT:
        return PlanFailure.MULTI_ACCELERATOR_PLANNING_NOT_IMPLEMENTED
    artifact_failure = _artifact(inputs, definition)
    if artifact_failure is not None:
        return artifact_failure
    assert inputs.artifact is not None
    model_failure = _model(definition, compatibility, requirement)
    if model_failure is not None:
        return model_failure
    foundation_failure = _foundation(inputs)
    if foundation_failure is not None:
        return foundation_failure
    context = _context(definition, inputs.preference)
    if isinstance(context, PlanFailure):
        return context
    concurrency = _concurrency(inputs.preference)
    if isinstance(concurrency, PlanFailure):
        return concurrency
    covered = _qualified(inputs, definition, context[0], concurrency[0])
    if covered is not None:
        return covered
    device = _device(inputs.envelope)
    if isinstance(device, PlanFailure):
        return device
    host = inputs.envelope.memory.safe_bytes
    if not isinstance(host, int):
        return PlanFailure.CAPACITY_SNAPSHOT_UNRESOLVED
    if host < 1:
        return PlanFailure.INSUFFICIENT_SAFE_CAPACITY
    static = requirement.static_weight_bytes
    if not isinstance(static, int):
        return PlanFailure.MODEL_CONDITION_UNRESOLVED
    safe = device.safe_bytes
    assert isinstance(safe, int)
    if static > safe:
        return PlanFailure.SINGLE_ACCELERATOR_PLAN_NOT_FEASIBLE
    return ServingDraft(
        definition=definition,
        requirement=requirement,
        compatibility=compatibility,
        artifact=inputs.artifact,
        device=device,
        accelerator_bytes=safe,
        host_bytes=host,
        context=context[0],
        context_provenance=context[1],
        concurrency=concurrency[0],
        concurrency_provenance=concurrency[1],
        fingerprint="",
    )


def _artifact(inputs: PlanInputs, definition: ModelDefinition) -> PlanFailure | None:
    artifact = inputs.artifact
    cited = inputs.selection.artifact_id
    if artifact is None or not isinstance(cited, str):
        return PlanFailure.MODEL_ARTIFACT_NOT_STORED
    if artifact.lifecycle is not ArtifactLifecycle.STORED:
        return PlanFailure.MODEL_ARTIFACT_NOT_STORED
    if artifact.artifact_id != cited or artifact.model_id != definition.model_id:
        return PlanFailure.STALE_MODEL_INPUT
    if artifact.immutable_revision != inputs.selection.immutable_revision:
        return PlanFailure.STALE_MODEL_INPUT
    if artifact.immutable_revision != definition.immutable_revision:
        return PlanFailure.STALE_MODEL_INPUT
    if not inputs.artifact_verified:
        return PlanFailure.MODEL_ARTIFACT_INTEGRITY_FAILED
    return None


def _model(
    definition: ModelDefinition,
    compatibility: ModelCompatibility,
    requirement: ModelRequirement,
) -> PlanFailure | None:
    del requirement
    if definition.requires_remote_code:
        return PlanFailure.MODEL_NOT_COMPATIBLE
    if compatibility.policy_state is CompatibilityState.BLOCKED_BY_POLICY:
        return PlanFailure.MODEL_NOT_COMPATIBLE
    state = compatibility.state
    if state in {
        CompatibilityState.UNSUPPORTED,
        CompatibilityState.BLOCKED_BY_POLICY,
        CompatibilityState.INSUFFICIENT_CAPACITY,
    }:
        return PlanFailure.MODEL_NOT_COMPATIBLE
    if compatibility.provider_qualification is not ProviderQualification.QUALIFIED:
        return PlanFailure.FOUNDATION_NOT_QUALIFIED
    if state is not CompatibilityState.COMPATIBLE:
        return PlanFailure.MODEL_CONDITION_UNRESOLVED
    return None


def _qualified(
    inputs: PlanInputs,
    definition: ModelDefinition,
    context: int,
    concurrency: int,
) -> PlanFailure | None:
    """User plans require coverage. A probe plan is how that coverage is earned."""
    if inputs.probe:
        return None
    if definition.model_id not in member_ids(inputs.deployable):
        return PlanFailure.QUALIFICATION_REQUIRED
    evidence = inputs.qualification
    backend = inputs.foundation.backend
    backend_name = backend.value if is_resolved(backend) else "unresolved"
    dtype = definition.dtype if isinstance(definition.dtype, str) else "undetermined"
    if not covers(
        evidence,
        revision=definition.immutable_revision,
        generation_id=_foundation_identity(inputs),
        engine=inputs.foundation.engine.value,
        engine_version=(
            inputs.capability.version if inputs.capability is not None else "absent"
        ),
        backend=backend_name,
        hardware_class=inputs.hardware_class,
        dtype=dtype,
        quantization=definition.quantization.value,
        context=context,
        concurrency=concurrency,
        tensor_parallel=1,
        policy_version=evidence.policy_version,
    ):
        return PlanFailure.QUALIFICATION_DOES_NOT_COVER
    return None


def _foundation(inputs: PlanInputs) -> PlanFailure | None:
    foundation = inputs.foundation
    if foundation.support is not SupportState.READY:
        return PlanFailure.FOUNDATION_NOT_READY
    if foundation.failure is not FailureCode.NONE:
        return PlanFailure.FOUNDATION_NOT_READY
    if not isinstance(foundation.generation_id, str):
        return PlanFailure.FOUNDATION_NOT_READY
    capability = inputs.capability
    if capability is None or capability.engine is not FoundationEngine.VLLM:
        return PlanFailure.FOUNDATION_NOT_READY
    if capability.import_state is not FeatureState.VERIFIED:
        return PlanFailure.FOUNDATION_NOT_READY
    if capability.entrypoint_state is not FeatureState.VERIFIED:
        return PlanFailure.FOUNDATION_NOT_READY
    identity = _foundation_identity(inputs)
    if inputs.selection.foundation_id != identity:
        return PlanFailure.FOUNDATION_MISMATCH
    if inputs.available.foundation_id != identity:
        return PlanFailure.FOUNDATION_MISMATCH
    evidence = inputs.envelope.evidence_id
    if foundation.capacity_evidence_id != evidence:
        return PlanFailure.STALE_CAPACITY_INPUT
    if inputs.selection.capacity_evidence_id != evidence:
        return PlanFailure.STALE_CAPACITY_INPUT
    if inputs.available.capacity_evidence_id != evidence:
        return PlanFailure.STALE_CAPACITY_INPUT
    return None


def _foundation_identity(inputs: PlanInputs) -> str:
    generation = inputs.foundation.generation_id
    if isinstance(generation, str):
        return generation
    return inputs.foundation.selection_id


def _context(
    definition: ModelDefinition,
    preference: PlanPreference,
) -> tuple[int, PlanProvenance] | PlanFailure:
    declared = definition.context_length
    requested = preference.context_length
    if isinstance(requested, int):
        if requested < MIN_CONTEXT or requested > MAX_CONTEXT:
            return PlanFailure.INVALID_REQUESTED_CONTEXT
        if isinstance(declared, int) and requested > declared:
            return PlanFailure.INVALID_REQUESTED_CONTEXT
        return requested, PlanProvenance.ADMINISTRATOR_REQUEST
    if isinstance(declared, int):
        chosen = min(declared, DEFAULT_CONTEXT)
        if chosen < MIN_CONTEXT:
            return PlanFailure.INVALID_REQUESTED_CONTEXT
        if chosen == declared:
            return chosen, PlanProvenance.MODEL_METADATA
        return chosen, PlanProvenance.DERIVED
    return DEFAULT_CONTEXT, PlanProvenance.PRODUCT_DEFAULT


def _concurrency(
    preference: PlanPreference,
) -> tuple[int, PlanProvenance] | PlanFailure:
    requested = preference.concurrency
    if isinstance(requested, int):
        if requested < MIN_CONCURRENCY or requested > MAX_CONCURRENCY:
            return PlanFailure.INVALID_REQUESTED_CONCURRENCY
        return requested, PlanProvenance.ADMINISTRATOR_REQUEST
    return DEFAULT_CONCURRENCY, PlanProvenance.PRODUCT_DEFAULT


def _device(envelope: CapacityEnvelope) -> AcceleratorCapacity | PlanFailure:
    ranked: list[tuple[int, int, AcceleratorCapacity]] = []
    for device in envelope.accelerators:
        safe = device.safe_bytes
        if isinstance(safe, int):
            ranked.append((-safe, device.ordinal, device))
    if not ranked:
        return PlanFailure.CAPACITY_SNAPSHOT_UNRESOLVED
    ranked.sort()
    return ranked[0][2]


def _entry(inputs: PlanInputs) -> AvailableModelEntry | None:
    matches = [
        item
        for item in inputs.available.entries
        if item.definition.model_id == inputs.selection.model_id
        and item.definition.immutable_revision == inputs.selection.immutable_revision
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _check_recipe(draft: ServingDraft, recipe: RuntimeRecipe) -> PlanFailure | None:
    if recipe.schema_version != RECIPE_SCHEMA:
        return PlanFailure.UNSUPPORTED_RUNTIME_PROVIDER
    if recipe.provider != FoundationEngine.VLLM.value:
        return PlanFailure.UNSUPPORTED_RUNTIME_PROVIDER
    values = {item.name: item.value for item in recipe.settings}
    expected = {
        "parallelism": "1",
        "context_length": str(draft.context),
        "concurrency": str(draft.concurrency),
        "remote_code": "refuse",
        "artifact_reference": draft.artifact.artifact_id,
        "dtype": _dtype(draft.definition),
        "quantization": draft.definition.quantization.value,
        "memory_utilization": "0.90",
    }
    for name, value in expected.items():
        if values.get(name) != value:
            return PlanFailure.UNSUPPORTED_RUNTIME_PROVIDER
    return None


def _dtype(definition: ModelDefinition) -> str:
    if isinstance(definition.dtype, str):
        return definition.dtype
    return "undetermined"


def _fingerprint(inputs: PlanInputs) -> str:
    artifact = inputs.artifact
    capability = inputs.capability
    parts = [
        POLICY_VERSION,
        inputs.selection.selection_id,
        inputs.selection.model_id,
        inputs.selection.immutable_revision,
        _text(inputs.selection.artifact_id),
        inputs.selection.compatibility_state.value,
        inputs.foundation.selection_id,
        _text(inputs.foundation.generation_id),
        inputs.foundation.support.value,
        inputs.foundation.engine.value,
        inputs.envelope.evidence_id,
        _text(inputs.envelope.memory.safe_bytes),
        *(
            f"{item.identity}:{_text(item.safe_bytes)}:{item.ordinal}"
            for item in inputs.envelope.accelerators
        ),
        _text(inputs.preference.context_length),
        _text(inputs.preference.concurrency),
        str(inputs.preference.accelerator_count),
        "verified" if inputs.artifact_verified else "unverified",
        artifact.artifact_id if artifact is not None else "absent",
        str(artifact.total_bytes) if artifact is not None else "absent",
        artifact.lifecycle.value if artifact is not None else "absent",
        capability.version if capability is not None else "absent",
        capability.import_state.value if capability is not None else "absent",
        inputs.qualification.qualification_id,
        inputs.deployable.snapshot_id,
        inputs.hardware_class,
        "probe" if inputs.probe else "deploy",
        inputs.available.input_token,
        inputs.available.foundation_id,
    ]
    return plan_fingerprint(*parts)


def _text(value: object) -> str:
    if isinstance(value, Unresolved):
        return f"unresolved:{value.reason.value}"
    if isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return "absent"


def _refused(token: str, failure: PlanFailure, reason: str) -> PlanDecision:
    return PlanDecision(
        decision_id=decision_id(token),
        failure=failure,
        reason=reason,
        fingerprint=token,
        configuration=NOT_PROVIDED,
        request=NOT_PROVIDED,
    )


def _reason(failure: PlanFailure) -> str:
    return failure.value.replace("_", " ")
