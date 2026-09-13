"""Planning contracts: fit against SAFE capacity, then recommend.

Planning never reserves. It never selects a concrete estimator. It
never averages providers. A recommendation is recomputed, not stored as
truth.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import MemoryPlacement, ModelId


class CompatibilityVerdict(StrEnum):
    """Can this candidate run here, aside from capacity-fit."""

    COMPATIBLE = "compatible"
    CONDITIONALLY_COMPATIBLE = "conditionally_compatible"
    UNSUPPORTED = "unsupported"
    UNRESOLVED = "unresolved"


class CapacityFitClass(StrEnum):
    """How the candidate uses SAFE deployment capacity."""

    PREFERRED = "preferred"
    UNDERUTILIZED = "underutilized"
    EXCEEDS_SAFE = "exceeds_safe"
    UNRESOLVED = "unresolved"


class SelectionOutcome(StrEnum):
    """What the selector concluded for the whole candidate set."""

    RECOMMENDED = "recommended"
    NO_PREFERRED_CANDIDATE = "no_preferred_candidate"
    NO_FEASIBLE_CANDIDATE = "no_feasible_candidate"
    UNRESOLVED = "unresolved"


POLICY_VERSION = "1.4B.0"
DEFAULT_MIN_UTILIZATION = 0.20
DEFAULT_MAX_UTILIZATION = 1.00


@contract(kind="planning.selection_policy", version=1)
@dataclass(frozen=True, slots=True)
class SelectionPolicy(Contract):
    """Preferred-band bounds. Policy, not architecture constants."""

    policy_version: str = meaning(
        "which policy produced a recommendation",
        default=POLICY_VERSION,
    )
    minimum_capacity_utilization: float = meaning(
        "below this, a feasible candidate is underutilized, not preferred",
        default=DEFAULT_MIN_UTILIZATION,
    )
    maximum_capacity_utilization: float = meaning(
        "above this, relative to SAFE capacity, the candidate is infeasible",
        default=DEFAULT_MAX_UTILIZATION,
    )
    allow_underutilized_fallback: bool = meaning(
        "whether underutilized candidates may be promoted; v0 is off",
        default=False,
    )
    allow_offload: bool = meaning(
        "whether CPU offload is an accepted fit; v0 is off",
        default=False,
    )


@contract(kind="planning.deployment_capacity", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentCapacity(Contract):
    """SAFE envelope plus current available for one proposed placement.

    Available is SAFE minus ACTIVE commitments when a snapshot is bound.
    Not a universal server score. Storage is carried for the separate
    hard check and is not a utilization input.
    """

    host_id: HostId = meaning("which host this placement is for")
    host_fingerprint: str = meaning("envelope shape this was taken from")
    placement: MemoryPlacement = meaning("which memory model this slice uses")
    safe_ram_bytes: Maybe[int] = meaning("SAFE system memory for this placement")
    safe_vram_bytes: Maybe[int] = meaning(
        "SAFE device memory of the proposed accelerator; unresolved on CPU"
    )
    safe_unified_bytes: Maybe[int] = meaning(
        "SAFE unified memory when that is the placement; never a VRAM alias"
    )
    safe_storage_bytes: Maybe[int] = meaning(
        "SAFE free space for the peak-acquisition check; not in utilization"
    )
    envelope_policy_version: str = meaning("headroom policy of the source envelope")
    accelerator_index: int | None = meaning(
        "assigned accelerator for discrete GPU; none for CPU-only",
        default=None,
    )
    available_ram_bytes: Maybe[int] = meaning(
        "current RAM available for another workload; SAFE minus ACTIVE",
        default=NOT_PROVIDED,
    )
    available_vram_bytes: Maybe[int] = meaning(
        "current device memory available for another workload; SAFE minus ACTIVE",
        default=NOT_PROVIDED,
    )
    available_unified_bytes: Maybe[int] = meaning(
        "current unified memory available for another workload",
        default=NOT_PROVIDED,
    )
    available_storage_bytes: Maybe[int] = meaning(
        "current incremental storage available; SAFE free space minus "
        "pending reservations",
        default=NOT_PROVIDED,
    )
    snapshot_basis: Maybe[str] = meaning(
        "current-capacity snapshot identity used for this comparison",
        default=NOT_PROVIDED,
    )


@contract(kind="planning.capacity_utilization", version=1)
@dataclass(frozen=True, slots=True)
class CapacityUtilization(Contract):
    """max(required/safe) over applicable deployment-limiting memory."""

    ratio: Maybe[float] = meaning(
        "limiting-resource ratio; unresolved if a load-bearing input is"
    )
    limiting_resource: Maybe[str] = meaning(
        "which memory resource produced the ratio, when known"
    )
    ram_ratio: Maybe[float] = meaning("required RAM / SAFE RAM, when both exist")
    vram_ratio: Maybe[float] = meaning(
        "required VRAM / SAFE VRAM, when both exist",
        default=NOT_PROVIDED,
    )
    unified_ratio: Maybe[float] = meaning(
        "required unified / SAFE unified, when both exist",
        default=NOT_PROVIDED,
    )


@contract(kind="planning.model_evaluation", version=1)
@dataclass(frozen=True, slots=True)
class ModelEvaluation(Contract):
    """Explainable feasibility for one candidate under current inputs."""

    model_id: ModelId = meaning("which candidate")
    logical_name: Name = meaning("stable catalog name")
    source_ref: str = meaning("upstream identity")
    compatibility: CompatibilityVerdict = meaning("runtime/format/offload verdict")
    capacity_fit: CapacityFitClass = meaning("preferred-band class")
    storage_feasible: Maybe[bool] = meaning(
        "peak acquisition vs SAFE storage; unknown is not a pass"
    )
    required_ram_bytes: Maybe[int] = meaning("estimator RAM")
    required_vram_bytes: Maybe[int] = meaning("estimator deployed accelerator memory")
    required_unified_bytes: Maybe[int] = meaning("estimator unified memory")
    required_storage_bytes: Maybe[int] = meaning("peak acquisition bytes")
    safe_ram_bytes: Maybe[int] = meaning("SAFE RAM used for the comparison")
    safe_vram_bytes: Maybe[int] = meaning("SAFE VRAM used for the comparison")
    safe_unified_bytes: Maybe[int] = meaning("SAFE unified used for the comparison")
    utilization: CapacityUtilization = meaning("limiting-resource ratio")
    preferred: bool = meaning("inside the configured preferred band")
    reasons: tuple[str, ...] = meaning("why this class, including exclusions")
    unresolved: tuple[str, ...] = meaning("load-bearing fields that stayed unknown")
    confidence: Confidence = meaning("requirement confidence")
    estimator_provider: Maybe[str] = meaning("active estimator identity")
    parameter_count: Maybe[int] = meaning("capability proxy for v0 ranking")
    quantization: Maybe[str] = meaning("variant identity for ranking")
    context_length_tokens: Maybe[int] = meaning("advertised context")
    supported_runtimes: tuple[str, ...] = meaning("runtimes this variant names")
    estimator_version: Maybe[str] = meaning(
        "effective estimator version", default=NOT_PROVIDED
    )
    estimator_mode: Maybe[str] = meaning(
        "configured mode: auto, or a strict provider id", default=NOT_PROVIDED
    )
    requested_primary: Maybe[str] = meaning(
        "first provider asked", default=NOT_PROVIDED
    )
    fallback_used: bool = meaning(
        "true when the primary provider failed to estimate", default=False
    )
    fallback_reason: Maybe[str] = meaning(
        "typed primary failure that caused fallback", default=NOT_PROVIDED
    )
    available_ram_bytes: Maybe[int] = meaning(
        "current available RAM used for the hard predicate", default=NOT_PROVIDED
    )
    available_vram_bytes: Maybe[int] = meaning(
        "current available VRAM used for the hard predicate", default=NOT_PROVIDED
    )
    available_unified_bytes: Maybe[int] = meaning(
        "current available unified memory used for the hard predicate",
        default=NOT_PROVIDED,
    )
    available_storage_bytes: Maybe[int] = meaning(
        "current available incremental storage used for the hard predicate",
        default=NOT_PROVIDED,
    )
    incremental_storage_bytes: Maybe[int] = meaning(
        "acquisition footprint still required; zero when the exact artifact is stored",
        default=NOT_PROVIDED,
    )
    snapshot_basis: Maybe[str] = meaning(
        "current-capacity snapshot identity for this row", default=NOT_PROVIDED
    )


@contract(kind="planning.selection_recommendation", version=1)
@dataclass(frozen=True, slots=True)
class SelectionRecommendation(Contract):
    """Selector output. Recomputed. Active estimator only."""

    outcome: SelectionOutcome = meaning("what the selector concluded")
    policy_version: str = meaning("SelectionPolicy that produced this")
    estimator_provider: str = meaning("the one estimator used")
    estimator_version: str = meaning("that estimator's version")
    recommended_at: dt.datetime = meaning("when this was computed, UTC")
    host_fingerprint: str = meaning("capacity envelope identity")
    primary: ModelEvaluation | None = meaning(
        "preferred winner, when the outcome is recommended",
        default=None,
    )
    alternatives: tuple[ModelEvaluation, ...] = meaning(
        "other preferred candidates, ranked",
        default=(),
    )
    underutilized: tuple[ModelEvaluation, ...] = meaning(
        "feasible but below the minimum; not auto-promoted",
        default=(),
    )
    rejected: tuple[ModelEvaluation, ...] = meaning(
        "infeasible, unsupported, or unresolved",
        default=(),
    )
    rationale: tuple[str, ...] = meaning(
        "why the outcome is what it is",
        default=(),
    )
    evaluations: tuple[ModelEvaluation, ...] = meaning(
        "every candidate, in catalog order",
        default=(),
    )
    estimator_mode: str = meaning(
        "configured mode: auto, or a strict provider id", default="auto"
    )
    requested_primary: str = meaning("first provider asked", default="")
    fallback_used: bool = meaning(
        "true when the primary provider failed to estimate", default=False
    )
    fallback_reason: Maybe[str] = meaning(
        "typed primary failure that caused fallback", default=NOT_PROVIDED
    )


class ModelSelectionId(EntityId):
    """Deterministic identity of the current model selection on one host."""

    prefix = "msel"


class ModelSelectionMode(StrEnum):
    """Product model-selection mode. Not FoundationSelection AUTO/MANUAL."""

    AUTO = "auto"
    MANUAL = "manual"


class ModelSelectionStatus(StrEnum):
    """Whether the current model selection may be treated as executable."""

    CURRENT = "current"
    STALE = "stale"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class FeasibleModelCandidate:
    """Eligible and currently feasible. Derived ranking input, not persisted.

    Does not copy ModelMetadata, RuntimeCapabilityProfile, or CapacityEnvelope.
    """

    model_id: str
    logical_name: str
    source_ref: str
    source_revision: Maybe[str]
    view_id: str
    profile_id: str
    runtime: str
    runtime_version: Maybe[str]
    requirement_basis: str
    capacity_fit: str
    evaluation: ModelEvaluation


@contract(kind="planning.model_selection", version=1)
@dataclass(frozen=True, slots=True)
class ModelSelection(Contract):
    """Recommended versus selected model. Not a DeploymentPlan."""

    selection_id: ModelSelectionId = meaning(
        "fingerprint of the current model selection record for one host"
    )
    host_id: HostId = meaning("host this selection applies to")
    selection_mode: ModelSelectionMode = meaning(
        "AUTO follows the current recommendation; MANUAL holds another "
        "currently feasible model"
    )
    created_at: dt.datetime = meaning("when this selection record was first written")
    selected_at: dt.datetime = meaning("when the current selection last changed")
    selection_basis: str = meaning(
        "fingerprint of foundation, view, requirement, capacity, and policy"
    )
    recommended_model_id: Maybe[str] = meaning(
        "current feasible recommendation; unresolved when none exists",
        default=NOT_PROVIDED,
    )
    selected_model_id: Maybe[str] = meaning(
        "model AUTO or MANUAL chose; unresolved when none exists",
        default=NOT_PROVIDED,
    )
    recommended_logical_name: Maybe[str] = meaning(
        "catalog name of the current recommendation", default=NOT_PROVIDED
    )
    selected_logical_name: Maybe[str] = meaning(
        "catalog name of the selected model", default=NOT_PROVIDED
    )
    selected_source_ref: Maybe[str] = meaning(
        "upstream identity of the selected model", default=NOT_PROVIDED
    )
    selected_source_revision: Maybe[str] = meaning(
        "immutable revision of the selected model, when known",
        default=NOT_PROVIDED,
    )
    generation: int = meaning(
        "increments when the selected model identity changes", default=1
    )


class DeploymentPlanId(EntityId):
    """Deterministic identity of the current deployment plan on one host."""

    prefix = "dplan"


class DeploymentPlanStatus(StrEnum):
    """Whether a persisted deployment plan may be treated as executable truth."""

    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@contract(kind="planning.deployment_plan", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentPlan(Contract):
    """Control-plane deployment decision. Does not reserve, download, or start.

    A record with ``plan_id`` is the host's persisted authoritative plan.
    ``plan_from`` projections omit ``plan_id`` and are not executable truth.
    """

    model_id: ModelId = meaning("selected candidate")
    logical_name: Name = meaning("catalog name")
    source_ref: str = meaning("upstream identity")
    quantization: Maybe[str] = meaning("selected variant")
    runtime: Maybe[str] = meaning("proposed runtime")
    executor_kind: Maybe[str] = meaning("proposed executor")
    placement: MemoryPlacement = meaning("proposed device strategy")
    expected_ram_bytes: Maybe[int] = meaning("estimator RAM")
    expected_vram_bytes: Maybe[int] = meaning("estimator VRAM")
    expected_unified_bytes: Maybe[int] = meaning("estimator unified memory")
    expected_storage_bytes: Maybe[int] = meaning("peak acquisition")
    expected_utilization: Maybe[float] = meaning("limiting-resource ratio")
    estimator_provider: str = meaning("active estimator")
    policy_version: str = meaning("policy that selected this")
    rationale: tuple[str, ...] = meaning("why this candidate")
    estimator_mode: str = meaning("configured estimator mode", default="auto")
    fallback_used: bool = meaning(
        "true when the primary provider failed to estimate", default=False
    )
    fallback_reason: Maybe[str] = meaning(
        "typed primary failure that caused fallback", default=NOT_PROVIDED
    )
    plan_id: Maybe[str] = meaning(
        "fingerprint of the current authoritative plan for one host",
        default=NOT_PROVIDED,
    )
    host_id: Maybe[str] = meaning(
        "host this plan applies to; unresolved on recommendation projections",
        default=NOT_PROVIDED,
    )
    created_at: Maybe[dt.datetime] = meaning(
        "when this authoritative plan was first written", default=NOT_PROVIDED
    )
    selected_at: Maybe[dt.datetime] = meaning(
        "when the selected deployment identity last changed", default=NOT_PROVIDED
    )
    plan_basis: Maybe[str] = meaning(
        "fingerprint of foundation, runtime, selection, requirement, and capacity",
        default=NOT_PROVIDED,
    )
    generation: int = meaning(
        "increments when the selected model identity changes", default=1
    )
    foundation_selection_id: Maybe[str] = meaning(
        "FoundationSelection identity this plan consumed", default=NOT_PROVIDED
    )
    selected_candidate_id: Maybe[str] = meaning(
        "selected runtime candidate identity", default=NOT_PROVIDED
    )
    installation_id: Maybe[str] = meaning(
        "matching RuntimeInstallation identity", default=NOT_PROVIDED
    )
    profile_id: Maybe[str] = meaning(
        "matching RuntimeCapabilityProfile identity", default=NOT_PROVIDED
    )
    runtime_version: Maybe[str] = meaning(
        "selected runtime version", default=NOT_PROVIDED
    )
    model_selection_id: Maybe[str] = meaning(
        "ModelSelection identity this plan consumed", default=NOT_PROVIDED
    )
    model_selection_mode: Maybe[str] = meaning(
        "AUTO or MANUAL at plan creation", default=NOT_PROVIDED
    )
    model_selection_basis: Maybe[str] = meaning(
        "ModelSelection basis fingerprint consumed", default=NOT_PROVIDED
    )
    recommended_model_id: Maybe[str] = meaning(
        "recommendation at plan creation; not substituted for selected",
        default=NOT_PROVIDED,
    )
    source_revision: Maybe[str] = meaning(
        "immutable revision of the selected model, when known",
        default=NOT_PROVIDED,
    )
    requirement_basis: Maybe[str] = meaning(
        "ModelRequirement basis consumed", default=NOT_PROVIDED
    )
    context_tokens: Maybe[int] = meaning(
        "context length the requirement assumed", default=NOT_PROVIDED
    )
    capacity_fit: Maybe[str] = meaning(
        "capacity-fit class of the selected model", default=NOT_PROVIDED
    )
    capacity_verdict: Maybe[str] = meaning(
        "feasible when this plan was written; CURRENT requires feasible",
        default=NOT_PROVIDED,
    )
    host_fingerprint: Maybe[str] = meaning(
        "capacity envelope identity consumed", default=NOT_PROVIDED
    )
    accelerator_index: int | None = meaning(
        "assigned accelerator for discrete GPU; none otherwise", default=None
    )
    eligible_view_id: Maybe[str] = meaning(
        "EligibleModelView identity consumed", default=NOT_PROVIDED
    )
    storage_pool_mount: Maybe[str] = meaning(
        "destination StoragePool this plan would consume", default=NOT_PROVIDED
    )


class AvailableModelViewId(EntityId):
    """Deterministic identity of the current Available Models view on one host."""

    prefix = "amv"


class AvailableViewStatus(StrEnum):
    """Whether the persisted Available Models view may be treated as authority."""

    CURRENT = "current"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class FunnelStage(StrEnum):
    """Which analysis stage excluded a candidate. Not a ranking class."""

    DISCOVERY = "discovery"
    COMPATIBILITY = "compatibility"
    CHEAP_SIZE_BOUND = "cheap_size_bound"
    DEEP_CAPACITY = "deep_capacity"
    RUNTIME_CALIBRATION = "runtime_calibration"


@contract(kind="planning.available_model_member", version=1)
@dataclass(frozen=True, slots=True)
class AvailableModelMember(Contract):
    """One model currently available to deploy as the next workload."""

    model_id: str = meaning("catalog model identity")
    logical_name: str = meaning("catalog logical name")
    source_ref: str = meaning("upstream identity")
    source_revision: Maybe[str] = meaning("immutable revision, when known")
    runtime: str = meaning("selected verified runtime family")
    runtime_version: Maybe[str] = meaning("selected runtime version")
    quantization: Maybe[str] = meaning("variant identity")
    requested_context_tokens: Maybe[int] = meaning(
        "serving context this availability assumed"
    )
    required_vram_bytes: Maybe[int] = meaning("deep ModelRequirement VRAM")
    available_vram_bytes: Maybe[int] = meaning(
        "current available VRAM from the snapshot used for this view"
    )
    required_ram_bytes: Maybe[int] = meaning("deep ModelRequirement RAM")
    available_ram_bytes: Maybe[int] = meaning("current available RAM")
    incremental_storage_bytes: Maybe[int] = meaning(
        "acquisition footprint still required"
    )
    available_storage_bytes: Maybe[int] = meaning("current incremental storage")
    requirement_provider: Maybe[str] = meaning("estimator that produced demand")
    requirement_confidence: Maybe[str] = meaning("requirement confidence")
    requirement_basis: str = meaning("ModelRequirement input fingerprint")
    weight_evidence_source: Maybe[str] = meaning(
        "cheap weight-footprint provider, when one ran", default=NOT_PROVIDED
    )
    weight_lower_bound_bytes: Maybe[int] = meaning(
        "serialized tensor bytes lower bound, when known", default=NOT_PROVIDED
    )
    result: str = meaning(
        "always available for members of this view", default="available"
    )
    validation_status: Maybe[str] = meaning(
        "measured, calibrated, cached, or unresolved runtime validation",
        default=NOT_PROVIDED,
    )
    runtime_memory_profile_id: Maybe[str] = meaning(
        "measured RuntimeMemoryProfile applied to this member",
        default=NOT_PROVIDED,
    )
    sentinel_model_id: Maybe[str] = meaning(
        "highest-pressure sentinel of this validation class",
        default=NOT_PROVIDED,
    )
    validation_class: Maybe[str] = meaning(
        "runtime-memory class key", default=NOT_PROVIDED
    )
    base_model_memory_bytes: Maybe[int] = meaning(
        "final base-model VRAM component", default=NOT_PROVIDED
    )
    runtime_extra_bytes: Maybe[int] = meaning(
        "final non-KV runtime-extra VRAM component", default=NOT_PROVIDED
    )
    kv_requirement_bytes: Maybe[int] = meaning(
        "KV cache for the requested context", default=NOT_PROVIDED
    )
    validation_confidence: Maybe[str] = meaning(
        "how the runtime-memory figures were obtained", default=NOT_PROVIDED
    )


@contract(kind="planning.available_model_exclusion", version=1)
@dataclass(frozen=True, slots=True)
class AvailableModelExclusion(Contract):
    """Why a discovered or catalog model is not currently available."""

    model_id: str = meaning("catalog or synthetic identity")
    logical_name: str = meaning("display name")
    stage: FunnelStage = meaning("which funnel stage excluded this candidate")
    reason: str = meaning("normalized reason code")
    notes: tuple[str, ...] = meaning("short factual notes", default=())
    weight_lower_bound_bytes: Maybe[int] = meaning(
        "cheap lower bound when Stage C rejected", default=NOT_PROVIDED
    )
    allowed_placement_bytes: Maybe[int] = meaning(
        "placement budget used for the cheap bound", default=NOT_PROVIDED
    )
    required_vram_bytes: Maybe[int] = meaning(
        "deep required VRAM when Stage E rejected", default=NOT_PROVIDED
    )
    available_vram_bytes: Maybe[int] = meaning(
        "snapshot available VRAM when Stage E rejected", default=NOT_PROVIDED
    )
    weight_evidence_source: Maybe[str] = meaning(
        "cheap evidence provider", default=NOT_PROVIDED
    )


@contract(kind="planning.available_model_view", version=1)
@dataclass(frozen=True, slots=True)
class AvailableModelView(Contract):
    """Models that can individually be the next workload. Not a recommendation.

    Persisted. Recommendation and selection are forbidden from this basis.
    """

    view_id: AvailableModelViewId = meaning(
        "fingerprint of host, foundation, snapshot, requirements, and policy"
    )
    host_id: HostId = meaning("host this view applies to")
    status: AvailableViewStatus = meaning("current, stale, or unavailable")
    evaluated_at: dt.datetime = meaning("when this view was computed, UTC")
    view_basis: str = meaning("fingerprint of material availability inputs")
    snapshot_basis: str = meaning(
        "CurrentCapacitySnapshot identity used for every member"
    )
    host_fingerprint: str = meaning("capacity envelope identity")
    eligible_view_id: str = meaning("EligibleModelView identity consumed")
    runtime: Maybe[str] = meaning("selected verified runtime family")
    runtime_version: Maybe[str] = meaning("selected runtime version")
    requested_context_tokens: Maybe[int] = meaning(
        "serving context assumed for this pass, when one global value applied"
    )
    universe_count: int = meaning("source records considered before remote filter")
    discovered_count: int = meaning("records after remote filter plus curated catalog")
    compatibility_count: int = meaning("survivors of local runtime compatibility")
    cheap_reject_count: int = meaning("proven impossible by cheap weight bound")
    deep_analyzed_count: int = meaning("candidates that invoked deep estimation")
    available_count: int = meaning("members of this view")
    excluded_count: int = meaning("recorded exclusions")
    estimator_invocations: int = meaning("deep estimator calls for this pass")
    members: tuple[AvailableModelMember, ...] = meaning(
        "currently available models, unsorted product set", default=()
    )
    exclusions: tuple[AvailableModelExclusion, ...] = meaning(
        "why other candidates are not available", default=()
    )
    policy_version: str = meaning("selection/capacity policy of this pass", default="")
    estimated_feasible_count: int = meaning(
        "static estimated-feasible candidates before runtime calibration",
        default=0,
    )
    validation_class_count: int = meaning(
        "runtime-memory classes formed from estimated-feasible candidates",
        default=0,
    )
    probe_invocations: int = meaning(
        "sentinel probes executed for this pass", default=0
    )


def envelope_fingerprint(envelope: CapacityEnvelope) -> str:
    """Stable identity of the envelope a recommendation was computed against."""
    return envelope.host_fingerprint
