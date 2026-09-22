"""Compose one in-memory plan from the installed package. No server."""

from __future__ import annotations

import datetime as dt

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
from machi.plan.compose import PlanInputs, compose_plan
from machi.plan.contracts import PlanFailure, PlanPreference

FIXED = dt.datetime(2026, 9, 23, 8, 0, tzinfo=dt.UTC)


def main() -> int:
    digest = "a" * 64
    definition = ModelDefinition(
        model_id="mdl_prove",
        source_kind=ModelSourceKind.LOCAL,
        repository="fixture",
        requested_revision="local",
        immutable_revision="commit-prove",
        display_name="prove",
        architecture="LlamaForCausalLM",
        dtype="bfloat16",
        quantization=QuantizationKind.NONE,
        weight_format=WeightFormat.SAFETENSORS,
        context_length=2048,
        parameter_count=NOT_PROVIDED,
        license_id=NOT_PROVIDED,
        commercial_use=CommercialUse.UNKNOWN,
        gated=False,
        requires_remote_code=False,
        derivation=DerivationKind.ORIGINAL,
        base_model=NOT_PROVIDED,
    )
    compatibility = ModelCompatibility(
        state=CompatibilityState.COMPATIBLE,
        failure=ModelFailure.NONE,
        technical_state=CompatibilityState.COMPATIBLE,
        policy_state=CompatibilityState.COMPATIBLE,
        provider_qualification=ProviderQualification.QUALIFIED,
        reason="fixture",
    )
    artifact = ModelArtifact(
        artifact_id="mart_prove",
        model_id="mdl_prove",
        source_kind=ModelSourceKind.LOCAL,
        repository="fixture",
        immutable_revision="commit-prove",
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
    envelope = CapacityEnvelope(
        evidence_id="cev_prove",
        input_token="capacity-prove",
        memory=MemoryCapacity(
            physical_bytes=NOT_PROVIDED,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=8_000_000_000,
            strength=EvidenceStrength.REPORTED,
            reason="fixture host",
        ),
        accelerators=(
            AcceleratorCapacity(
                identity="accel_prove",
                ordinal=0,
                topology="discrete",
                physical_bytes=NOT_PROVIDED,
                current_used_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=8_000_000_000,
                strength=EvidenceStrength.REPORTED,
                reason="fixture device",
            ),
        ),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_prove",
                backing_resolved=True,
                reported_available_bytes=NOT_PROVIDED,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=NOT_PROVIDED,
                reserve_bytes=0,
                safe_bytes=20_000_000_000,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="fixture storage",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED,
        provider="native",
    )
    foundation = FoundationSelection(
        selection_id="fsel_prove",
        family=FoundationFamily.DIRECT,
        engine=FoundationEngine.VLLM,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=AcceleratorBackend.CUDA,
        support=SupportState.READY,
        failure=FailureCode.NONE,
        candidate_id="vllm-0.18.0-cuda",
        generation_id="fgen_prove",
        capacity_evidence_id="cev_prove",
        reason="fixture",
    )
    capability = RuntimeCapability(
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
    entry = AvailableModelEntry(
        definition=definition,
        compatibility=compatibility,
        requirement=ModelRequirement(
            persistent_bytes=1000,
            transient_bytes=1000,
            static_weight_bytes=1000,
        ),
        artifact_id="mart_prove",
        lifecycle="stored",
    )
    available = AvailableModels(
        snapshot_id="mav_prove",
        input_token="available-prove",
        foundation_id="fgen_prove",
        capacity_evidence_id="cev_prove",
        entries=(entry,),
        observed_at=FIXED,
    )
    selection = ModelSelection(
        selection_id="msel_prove",
        model_id="mdl_prove",
        artifact_id="mart_prove",
        immutable_revision="commit-prove",
        provenance=SelectionProvenance.ADMINISTRATOR_SELECTED,
        compatibility_state=CompatibilityState.COMPATIBLE,
        foundation_id="fgen_prove",
        capacity_evidence_id="cev_prove",
        reason="fixture",
    )
    decision = compose_plan(
        PlanInputs(
            selection=selection,
            available=available,
            artifact=artifact,
            artifact_verified=True,
            foundation=foundation,
            capability=capability,
            envelope=envelope,
            preference=PlanPreference(
                context_length=NOT_PROVIDED,
                concurrency=NOT_PROVIDED,
                accelerator_count=1,
            ),
        ),
        build_vllm_recipe,
    )
    if decision.failure is not PlanFailure.NONE:
        raise SystemExit(f"plan refused: {decision.failure.value}")
    configuration = decision.configuration
    request = decision.request
    if not is_resolved(configuration) or not is_resolved(request):
        raise SystemExit("plan outputs missing")
    values = {item.name: item.value for item in configuration.settings}
    if values.get("tensor_parallel_size") != "1":
        raise SystemExit("tensor parallel was not 1")
    if values.get("trust_remote_code") != "false":
        raise SystemExit("remote code was not refused")
    if "/" in values.get("artifact_reference", "/"):
        raise SystemExit("artifact reference is a path")
    if request.accelerator_memory_bytes != 8_000_000_000:
        raise SystemExit("request did not use the safe accelerator budget")
    print(f"plan_ok {configuration.plan_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
