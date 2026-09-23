"""Plan composition. No admission, download, or runtime launch."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

from machi.adapters.persistence.file_store import FileStore
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceStrength,
    MemoryCapacity,
    StorageDomainCapacity,
)
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import not_attempted
from machi.foundation.contracts import (
    AcceleratorBackend,
    ExecutorKind,
    FailureCode,
    FeatureState,
    FoundationEngine,
    FoundationFamily,
    FoundationSelection,
    RuntimeCapability,
    SupportState,
)
from machi.kernel.clock import FixedClock
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.model.contracts import (
    ArtifactLifecycle,
    AvailableModelEntry,
    AvailableModels,
    CommercialUse,
    CompatibilityState,
    DerivationKind,
    ModelArtifact,
    ModelCompatibility,
    ModelDefinition,
    ModelFailure,
    ModelFileRecord,
    ModelRequirement,
    ModelSelection,
    ModelSourceKind,
    ProviderQualification,
    QuantizationKind,
    SelectionProvenance,
    WeightFormat,
)
from machi.model.environment import execution_environment_fingerprint
from machi.model.qualification import (
    POLICY_VERSION as QUALIFICATION_POLICY,
)
from machi.model.qualification import (
    DeployableMember,
    DeployableModels,
    QualificationEvidence,
    QualificationOutcome,
    qualification_identity,
)
from machi.plan.compose import PlanInputs, ServingDraft, compose_plan
from machi.plan.contracts import (
    DeploymentConfiguration,
    PlanDecision,
    PlanFailure,
    PlanPreference,
    PlanStatus,
    ResourceRequest,
    RuntimeRecipe,
)
from machi.plan.events import plan_events
from machi.plan.policy import POLICY_VERSION
from machi.plan.stale import assess_plan

FIXED = dt.datetime(2026, 9, 23, 8, 0, tzinfo=dt.UTC)
ARCH = "LlamaForCausalLM"


def _device(
    identity: str,
    safe: int | object,
    *,
    ordinal: int = 0,
) -> AcceleratorCapacity:
    return AcceleratorCapacity(
        identity=identity,
        ordinal=ordinal,
        topology="discrete",
        physical_bytes=NOT_PROVIDED if not isinstance(safe, int) else safe * 2,
        current_used_bytes=NOT_PROVIDED,
        reserve_bytes=0,
        safe_bytes=safe if isinstance(safe, int) else NOT_PROVIDED,
        strength=EvidenceStrength.REPORTED,
        reason="safe budget" if isinstance(safe, int) else "safe budget unknown",
    )


def _envelope(
    *devices: AcceleratorCapacity,
    evidence: str = "cev_plan",
    host: int | object = 9_000_000_000,
) -> CapacityEnvelope:
    if not devices:
        devices = (_device("accel_0", 8_000_000_000),)
    return CapacityEnvelope(
        evidence_id=evidence,
        input_token="capacity-plan-token",
        memory=MemoryCapacity(
            physical_bytes=32_000_000_000,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=host if isinstance(host, int) else NOT_PROVIDED,
            strength=EvidenceStrength.REPORTED,
            reason="host safe budget",
        ),
        accelerators=devices,
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_plan",
                backing_resolved=True,
                reported_available_bytes=20_000_000_000,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=20_000_000_000,
                reserve_bytes=0,
                safe_bytes=20_000_000_000,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="storage domain",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED,
        provider="native",
    )


def _definition(
    *,
    context: int | object = 8192,
    remote: bool = False,
) -> ModelDefinition:
    return ModelDefinition(
        model_id="mdl_plan",
        source_kind=ModelSourceKind.HUB,
        repository="org/tiny",
        requested_revision="main",
        immutable_revision="commit-plan",
        display_name="tiny",
        architecture=ARCH,
        dtype="bfloat16",
        quantization=QuantizationKind.NONE,
        weight_format=WeightFormat.SAFETENSORS,
        context_length=context if isinstance(context, int) else NOT_PROVIDED,
        parameter_count=NOT_PROVIDED,
        license_id=NOT_PROVIDED,
        commercial_use=CommercialUse.UNKNOWN,
        gated=False,
        requires_remote_code=remote,
        derivation=DerivationKind.ORIGINAL,
        base_model=NOT_PROVIDED,
    )


def _compatibility(
    state: CompatibilityState = CompatibilityState.COMPATIBLE,
    qualification: ProviderQualification = ProviderQualification.QUALIFIED,
) -> ModelCompatibility:
    return ModelCompatibility(
        state=state,
        failure=ModelFailure.NONE,
        technical_state=state,
        policy_state=CompatibilityState.COMPATIBLE,
        provider_qualification=qualification,
        reason="test assessment",
    )


def _artifact(
    revision: str = "commit-plan",
    artifact: str = "mart_plan",
) -> ModelArtifact:
    digest = "a" * 64
    return ModelArtifact(
        artifact_id=artifact,
        model_id="mdl_plan",
        source_kind=ModelSourceKind.HUB,
        repository="org/tiny",
        immutable_revision=revision,
        variant="bfloat16-none-safetensors",
        lifecycle=ArtifactLifecycle.STORED,
        total_bytes=1000,
        files=(
            ModelFileRecord(
                relative_path="model.safetensors",
                size_bytes=1000,
                sha256=digest,
            ),
        ),
        config_sha256=digest,
        derivation=DerivationKind.ORIGINAL,
        base_model=NOT_PROVIDED,
        parent_artifact_id=NOT_PROVIDED,
        acquired_at=FIXED,
    )


def _foundation(
    *,
    generation: str = "fgen_plan",
    support: SupportState = SupportState.READY,
    evidence: str = "cev_plan",
    engine: FoundationEngine = FoundationEngine.VLLM,
) -> FoundationSelection:
    return FoundationSelection(
        selection_id="fsel_plan",
        family=FoundationFamily.DIRECT,
        engine=engine,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=AcceleratorBackend.CUDA,
        support=support,
        failure=FailureCode.NONE,
        candidate_id="vllm-0.18.0-cuda",
        generation_id=generation,
        capacity_evidence_id=evidence,
        reason="verified generation",
    )


def _capability() -> RuntimeCapability:
    return RuntimeCapability(
        engine=FoundationEngine.VLLM,
        version="0.18.0",
        backend=AcceleratorBackend.CUDA,
        import_state=FeatureState.VERIFIED,
        entrypoint_state=FeatureState.VERIFIED,
        server_launch=FeatureState.UNSUPPORTED,
        streaming=FeatureState.DECLARED_BY_VERSION,
        structured_output=FeatureState.UNRESOLVED,
        lora=FeatureState.UNRESOLVED,
        metrics=FeatureState.UNRESOLVED,
    )


def _inputs(
    *,
    definition: ModelDefinition | None = None,
    compatibility: ModelCompatibility | None = None,
    artifact: ModelArtifact | None = None,
    verified: bool = True,
    foundation: FoundationSelection | None = None,
    capability: RuntimeCapability | None = None,
    envelope: CapacityEnvelope | None = None,
    preference: PlanPreference | None = None,
    static_bytes: int | object = 1000,
    omit_artifact: bool = False,
) -> PlanInputs:
    definition = definition or _definition()
    compatibility = compatibility or _compatibility()
    artifact = None if omit_artifact else artifact or _artifact()
    foundation = foundation or _foundation()
    envelope = envelope or _envelope()
    generation = foundation.generation_id
    identity = generation if isinstance(generation, str) else foundation.selection_id
    entry = AvailableModelEntry(
        definition=definition,
        compatibility=compatibility,
        requirement=ModelRequirement(
            persistent_bytes=1000,
            transient_bytes=1000,
            static_weight_bytes=(
                static_bytes if isinstance(static_bytes, int) else NOT_PROVIDED
            ),
        ),
        artifact_id=artifact.artifact_id if artifact is not None else NOT_PROVIDED,
        lifecycle=artifact.lifecycle.value if artifact is not None else NOT_PROVIDED,
    )
    available = AvailableModels(
        snapshot_id="mav_plan",
        input_token="available-plan-token",
        foundation_id=identity,
        capacity_evidence_id=envelope.evidence_id,
        entries=(entry,),
        observed_at=FIXED,
    )
    backend = foundation.backend
    backend_name = backend.value if isinstance(backend, AcceleratorBackend) else "cuda"
    qualification = _qualification(definition, identity, backend_name)
    deployable = DeployableModels(
        snapshot_id="dep_plan",
        capacity_snapshot_id="cap_plan",
        members=(
            DeployableMember(
                model_id=definition.model_id,
                immutable_revision=definition.immutable_revision,
                qualification_id=qualification.qualification_id,
                total_required_vram_bytes=1000,
            ),
        ),
        observed_at=FIXED,
    )
    selection = ModelSelection(
        selection_id="msel_plan",
        model_id=definition.model_id,
        artifact_id=artifact.artifact_id if artifact is not None else NOT_PROVIDED,
        immutable_revision=definition.immutable_revision,
        provenance=SelectionProvenance.ADMINISTRATOR_SELECTED,
        compatibility_state=compatibility.state,
        foundation_id=identity,
        capacity_evidence_id=envelope.evidence_id,
        reason="administrator selected",
    )
    return PlanInputs(
        selection=selection,
        available=available,
        artifact=artifact,
        artifact_verified=verified,
        foundation=foundation,
        capability=_capability() if capability is None else capability,
        envelope=envelope,
        preference=preference
        or PlanPreference(
            context_length=NOT_PROVIDED,
            concurrency=NOT_PROVIDED,
            accelerator_count=1,
        ),
        deployable=deployable,
        qualification=qualification,
        execution_environment_fingerprint=(
            qualification.execution_environment_fingerprint
        ),
    )


def _environment(generation: str) -> str:
    return execution_environment_fingerprint(
        vendor="nvidia",
        accelerator_model="fixture",
        capability="unspecified",
        runtime_capability="fixture-runtime",
        generation_id=generation,
    )


def _qualification(
    definition: ModelDefinition, generation: str, backend: str
) -> QualificationEvidence:
    environment = _environment(generation)
    identity = qualification_identity(
        revision=definition.immutable_revision,
        generation_id=generation,
        engine="vllm",
        engine_version="0.18.0",
        backend=backend,
        hardware_class="unspecified",
        execution_environment_fingerprint=environment,
        dtype="bfloat16",
        quantization="none",
        context=8192,
        concurrency=16,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
    )
    return QualificationEvidence(
        qualification_id=identity,
        artifact_id="mart_plan",
        immutable_revision=definition.immutable_revision,
        generation_id=generation,
        engine="vllm",
        engine_version="0.18.0",
        backend=backend,
        hardware_class="unspecified",
        execution_environment_fingerprint=environment,
        dtype="bfloat16",
        quantization="none",
        context=8192,
        concurrency=16,
        tensor_parallel=1,
        policy_version=QUALIFICATION_POLICY,
        outcome=QualificationOutcome.PASS,
        failure="none",
        load_seconds=NOT_PROVIDED,
        ttft_seconds=NOT_PROVIDED,
        tokens_per_second=NOT_PROVIDED,
        peak_vram_bytes=NOT_PROVIDED,
        peak_ram_bytes=NOT_PROVIDED,
        measured=False,
        observed_at=FIXED,
    )


def _plan(inputs: PlanInputs | None = None) -> PlanDecision:
    return compose_plan(inputs or _inputs(), build_vllm_recipe)


def _ok(
    decision: PlanDecision,
) -> tuple[DeploymentConfiguration, ResourceRequest]:
    configuration = decision.configuration
    request = decision.request
    assert is_resolved(configuration)
    assert is_resolved(request)
    return configuration, request


def test_valid_plan_is_deterministic_and_does_not_reserve() -> None:
    first = _plan()
    second = _plan()
    assert first.failure is PlanFailure.NONE
    assert first.fingerprint == second.fingerprint
    assert first.decision_id == second.decision_id
    configuration, request = _ok(first)
    assert configuration.plan_id == request.plan_id
    assert configuration.fingerprint == request.fingerprint
    assert configuration.status is PlanStatus.PLANNED
    assert configuration.accelerator_count == 1
    assert request.accelerator_count == 1
    assert request.host_memory_bytes != request.accelerator_memory_bytes
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("src/machi/plan").glob("*.py")
    )
    assert "ResourceReservation" not in source
    values = {item.name: item.value for item in configuration.settings}
    assert values["tensor_parallel_size"] == "1"
    assert values["trust_remote_code"] == "false"
    assert values["artifact_reference"] == "mart_plan"
    assert values["max_model_len"] == "4096"
    assert "/" not in values["artifact_reference"]


def test_material_input_changes_the_fingerprint() -> None:
    base = _plan()
    definition = replace(_definition(), immutable_revision="commit-other")
    changed_model = _plan(
        _inputs(
            definition=definition,
            artifact=_artifact(revision="commit-other", artifact="mart_other"),
        )
    )
    changed_capacity = _plan(_inputs(envelope=_envelope(evidence="cev_other")))
    changed_foundation = _plan(_inputs(foundation=_foundation(generation="fgen_other")))
    preference = PlanPreference(
        context_length=1024,
        concurrency=NOT_PROVIDED,
        accelerator_count=1,
    )
    changed_preference = _plan(_inputs(preference=preference))
    assert changed_model.fingerprint != base.fingerprint
    assert changed_capacity.fingerprint != base.fingerprint
    assert changed_foundation.fingerprint != base.fingerprint
    assert changed_preference.fingerprint != base.fingerprint


def test_staleness_names_the_changed_input() -> None:
    inputs = _inputs()
    decision = _plan(inputs)
    configuration, _request = _ok(decision)
    assert assess_plan(configuration, inputs, build_vllm_recipe) is PlanFailure.NONE
    other = replace(_definition(), immutable_revision="commit-other")
    assert (
        assess_plan(
            configuration,
            _inputs(
                definition=other,
                artifact=_artifact(revision="commit-other", artifact="mart_other"),
            ),
            build_vllm_recipe,
        )
        is PlanFailure.STALE_MODEL_INPUT
    )
    assert (
        assess_plan(
            configuration,
            _inputs(foundation=_foundation(generation="fgen_other")),
            build_vllm_recipe,
        )
        is PlanFailure.STALE_FOUNDATION_INPUT
    )
    assert (
        assess_plan(
            configuration,
            _inputs(envelope=_envelope(evidence="cev_other")),
            build_vllm_recipe,
        )
        is PlanFailure.STALE_CAPACITY_INPUT
    )
    assert (
        assess_plan(
            configuration,
            _inputs(verified=False),
            build_vllm_recipe,
        )
        is PlanFailure.MODEL_ARTIFACT_INTEGRITY_FAILED
    )
    stale_policy = replace(configuration, policy_version="m7.plan.0")
    assert (
        assess_plan(stale_policy, inputs, build_vllm_recipe)
        is PlanFailure.STALE_POLICY_INPUT
    )
    preference = PlanPreference(
        context_length=1024,
        concurrency=2,
        accelerator_count=1,
    )
    assert (
        assess_plan(configuration, _inputs(preference=preference), build_vllm_recipe)
        is PlanFailure.STALE_PREFERENCE_INPUT
    )


def test_backend_environment_and_revision_do_not_reuse_coverage() -> None:
    inputs = _inputs()
    decision = _plan(inputs)
    configuration, _request = _ok(decision)
    rocm = replace(inputs.foundation, backend=AcceleratorBackend.ROCM)
    assert (
        assess_plan(
            configuration,
            replace(inputs, foundation=rocm),
            build_vllm_recipe,
        )
        is not PlanFailure.NONE
    )
    assert (
        assess_plan(
            configuration,
            replace(inputs, execution_environment_fingerprint="exe_other"),
            build_vllm_recipe,
        )
        is not PlanFailure.NONE
    )
    shifted = replace(inputs.available.entries[0].definition, dtype="float16")
    entry = replace(inputs.available.entries[0], definition=shifted)
    available = replace(inputs.available, entries=(entry,))
    assert _plan(replace(inputs, available=available)).failure is (
        PlanFailure.QUALIFICATION_DOES_NOT_COVER
    )
    member = replace(
        inputs.deployable.members[0],
        immutable_revision="revision-not-covered",
    )
    deployable = replace(inputs.deployable, members=(member,))
    assert _plan(replace(inputs, deployable=deployable)).failure is (
        PlanFailure.QUALIFICATION_REQUIRED
    )


def test_refusals_cover_model_foundation_and_capacity() -> None:
    missing = _plan(_inputs(omit_artifact=True))
    assert missing.failure is PlanFailure.MODEL_ARTIFACT_NOT_STORED
    assert _plan(_inputs(verified=False)).failure is (
        PlanFailure.MODEL_ARTIFACT_INTEGRITY_FAILED
    )
    unsupported = _compatibility(CompatibilityState.UNSUPPORTED)
    refused_model = _plan(_inputs(compatibility=unsupported))
    assert refused_model.failure is PlanFailure.MODEL_NOT_COMPATIBLE
    conditional = _compatibility(CompatibilityState.CONDITIONALLY_COMPATIBLE)
    assert _plan(_inputs(compatibility=conditional)).failure is (
        PlanFailure.MODEL_CONDITION_UNRESOLVED
    )
    deferred = _compatibility(
        CompatibilityState.COMPATIBLE,
        ProviderQualification.DEFERRED,
    )
    refused = _plan(_inputs(compatibility=deferred))
    assert refused.failure is PlanFailure.FOUNDATION_NOT_QUALIFIED
    assert "amd" not in refused.reason
    assert "nvidia" not in refused.reason
    rocm = replace(_foundation(), backend=AcceleratorBackend.ROCM)
    qualified = _plan(
        _inputs(
            foundation=rocm,
            capability=replace(_capability(), backend=AcceleratorBackend.ROCM),
        )
    )
    assert qualified.failure is PlanFailure.NONE
    unready = _plan(_inputs(foundation=_foundation(support=SupportState.SUPPORTED)))
    assert unready.failure is PlanFailure.FOUNDATION_NOT_READY
    mismatch = _inputs()
    mismatch = replace(
        mismatch,
        selection=replace(mismatch.selection, foundation_id="fsel_other"),
    )
    assert _plan(mismatch).failure is PlanFailure.FOUNDATION_MISMATCH
    assert _plan(_inputs(static_bytes=NOT_PROVIDED)).failure is (
        PlanFailure.MODEL_CONDITION_UNRESOLVED
    )
    huge = _plan(_inputs(static_bytes=9_000_000_000))
    assert huge.failure is PlanFailure.SINGLE_ACCELERATOR_PLAN_NOT_FEASIBLE
    unknown_device = _plan(
        _inputs(envelope=_envelope(_device("accel_0", NOT_PROVIDED)))
    )
    assert unknown_device.failure is PlanFailure.CAPACITY_SNAPSHOT_UNRESOLVED
    many = PlanPreference(
        context_length=NOT_PROVIDED,
        concurrency=NOT_PROVIDED,
        accelerator_count=2,
    )
    assert _plan(_inputs(preference=many)).failure is (
        PlanFailure.MULTI_ACCELERATOR_PLANNING_NOT_IMPLEMENTED
    )
    remote = _plan(_inputs(definition=_definition(remote=True)))
    assert remote.failure is PlanFailure.MODEL_NOT_COMPATIBLE


def test_context_and_concurrency_are_bounded() -> None:
    long_request = PlanPreference(
        context_length=9000,
        concurrency=NOT_PROVIDED,
        accelerator_count=1,
    )
    assert _plan(_inputs(preference=long_request)).failure is (
        PlanFailure.INVALID_REQUESTED_CONTEXT
    )
    short = PlanPreference(context_length=1024, concurrency=2, accelerator_count=1)
    decision = _plan(_inputs(preference=short))
    configuration, _request = _ok(decision)
    assert configuration.context_length == 1024
    assert configuration.concurrency == 2
    too_many = PlanPreference(
        context_length=NOT_PROVIDED,
        concurrency=100,
        accelerator_count=1,
    )
    assert _plan(_inputs(preference=too_many)).failure is (
        PlanFailure.INVALID_REQUESTED_CONCURRENCY
    )


def test_request_uses_safe_bytes_and_round_trips(tmp_path: Path) -> None:
    device = _device("accel_0", 5_000_000)
    decision = _plan(_inputs(envelope=_envelope(device, host=7_000_000)))
    _configuration, request = _ok(decision)
    assert request.accelerator_memory_bytes == 5_000_000
    assert request.host_memory_bytes == 7_000_000
    assert request.persistent_bytes == 1000
    assert request.transient_bytes == 0
    assert request.accelerator_memory_bytes != 10_000_000
    store = FileStore(tmp_path)
    stored = store.create(decision.decision_id, decision)
    assert stored.created is True
    loaded = store.get(type(decision), decision.decision_id)
    assert loaded == decision
    again = store.create(decision.decision_id, decision)
    assert again.existed is True
    assert not (tmp_path / "resource_reservation").exists()


def test_two_devices_still_plan_one() -> None:
    small = _device("accel_small", 4_000_000, ordinal=0)
    large = _device("accel_large", 9_000_000, ordinal=1)
    decision = _plan(_inputs(envelope=_envelope(small, large)))
    configuration, _request = _ok(decision)
    assert configuration.accelerator_identity == "accel_large"
    assert configuration.accelerator_count == 1


def test_events_omit_paths_and_a_foreign_recipe_is_refused() -> None:
    decision = _plan()
    event = plan_events(decision, clock=FixedClock(FIXED))[0]
    rendered = str(event.payload)
    assert event.event_type.value == "plan.created"
    assert "mart_plan" not in rendered
    assert "/root" not in rendered
    assert POLICY_VERSION

    def other(draft: ServingDraft) -> RuntimeRecipe:
        recipe = build_vllm_recipe(draft)
        return replace(recipe, provider="other")

    refused = compose_plan(_inputs(), other)
    assert refused.failure is PlanFailure.UNSUPPORTED_RUNTIME_PROVIDER
