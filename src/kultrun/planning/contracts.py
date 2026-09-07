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


class PlanId(EntityId):
    """Identifies one persisted DeploymentPlan."""

    prefix = "dplan"


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
    RUNTIME_NOT_VERIFIED = "runtime_not_verified"


class EligibilityVerdict(StrEnum):
    """Whether a verified runtime can plausibly serve this model."""

    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
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
    """SAFE slice of the envelope for one proposed placement.

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
    requested_primary: str = meaning(
        "first provider asked", default=""
    )
    fallback_used: bool = meaning(
        "true when the primary provider failed to estimate", default=False
    )
    fallback_reason: Maybe[str] = meaning(
        "typed primary failure that caused fallback", default=NOT_PROVIDED
    )


@contract(kind="planning.deployment_plan", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentPlan(Contract):
    """What would be deployed. Does not reserve and does not download."""

    model_id: ModelId = meaning("selected candidate")
    logical_name: Name = meaning("catalog name")
    source_ref: str = meaning("upstream identity")
    quantization: Maybe[str] = meaning("selected variant")
    runtime: Maybe[str] = meaning("proposed runtime family")
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
        "minted plan identity when this plan has been persisted",
        default=NOT_PROVIDED,
    )
    runtime_profile_id: Maybe[str] = meaning(
        "RuntimeCapabilityProfile this plan assumes", default=NOT_PROVIDED
    )
    runtime_installation_id: Maybe[str] = meaning(
        "installation the profile was produced from", default=NOT_PROVIDED
    )
    runtime_version: Maybe[str] = meaning(
        "exact runtime version assumed", default=NOT_PROVIDED
    )
    runtime_provider: Maybe[str] = meaning(
        "adapter identity that will launch", default=NOT_PROVIDED
    )
    host_id: Maybe[str] = meaning("target host", default=NOT_PROVIDED)
    host_fingerprint: Maybe[str] = meaning(
        "host identity at planning time", default=NOT_PROVIDED
    )
    context_tokens: Maybe[int] = meaning(
        "context the estimate assumed", default=NOT_PROVIDED
    )
    runtime_concurrency: Maybe[int] = meaning(
        "planned runtime max sequences", default=NOT_PROVIDED
    )
    eligibility_verdict: Maybe[str] = meaning(
        "runtime eligibility at plan time", default=NOT_PROVIDED
    )
    capacity_fit: Maybe[str] = meaning(
        "capacity class at plan time", default=NOT_PROVIDED
    )
    plan_fingerprint: Maybe[str] = meaning(
        "identity of load-bearing plan assumptions", default=NOT_PROVIDED
    )


@contract(kind="planning.capacity_commitments", version=1)
@dataclass(frozen=True, slots=True)
class CapacityCommitments(Contract):
    """ACTIVE reservation bytes. Platform copies numbers; not ResourceManager."""

    reserved_ram_bytes: int = meaning("sum of ACTIVE RAM grants", default=0)
    reserved_vram_bytes: int = meaning(
        "sum of ACTIVE device-memory grants on the proposed accelerator",
        default=0,
    )
    reserved_unified_bytes: int = meaning(
        "sum of ACTIVE unified grants", default=0
    )


@contract(kind="planning.runtime_capability_snapshot", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCapabilitySnapshot(Contract):
    """Planning-owned view of a RuntimeCapabilityProfile. No runtime import."""

    profile_id: str = meaning("capability profile identity")
    installation_id: str = meaning("installation identity")
    runtime_provider: str = meaning("adapter identity")
    runtime_family: str = meaning("family used for eligibility")
    runtime_version: str = meaning("exact version")
    executor_kind: str = meaning("executor")
    host_id: str = meaning("host")
    status: str = meaning("verification status")
    support_tier: str = meaning("product, fixture, reference, or future")
    verification_fingerprint: str = meaning("environment identity")
    supported_architectures: tuple[str, ...] = meaning("claimed architectures")
    supported_formats: tuple[str, ...] = meaning("claimed formats", default=())
    supported_quantizations: tuple[str, ...] = meaning(
        "claimed quantizations", default=()
    )
    supported_modalities: tuple[str, ...] = meaning("claimed modalities", default=())


@contract(kind="planning.runtime_eligible_candidate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeEligibleModelCandidate(Contract):
    """Can this verified runtime plausibly serve this model? Not capacity."""

    model_id: ModelId = meaning("candidate identity")
    logical_name: Name = meaning("catalog name")
    profile_id: str = meaning("capability snapshot used")
    runtime_provider: str = meaning("adapter")
    runtime_family: str = meaning("family")
    runtime_version: str = meaning("version")
    executor_kind: str = meaning("executor")
    host_id: str = meaning("host")
    architecture: Maybe[str] = meaning("model architecture")
    artifact_format: Maybe[str] = meaning("inferred or stated format")
    quantization: Maybe[str] = meaning("model quantization")
    verdict: EligibilityVerdict = meaning("eligible, ineligible, or unresolved")
    reasons: tuple[str, ...] = meaning("why")
    confidence: Maybe[str] = meaning("how sure", default=NOT_PROVIDED)


@contract(kind="planning.feasible_candidate", version=1)
@dataclass(frozen=True, slots=True)
class FeasibleModelCandidate(Contract):
    """Runtime-eligible candidate after capacity assessment."""

    eligibility: RuntimeEligibleModelCandidate = meaning("upstream eligibility")
    evaluation: ModelEvaluation = meaning("capacity and compatibility evaluation")


@contract(kind="planning.selected_deployment", version=1)
@dataclass(frozen=True, slots=True)
class SelectedDeploymentCandidate(Contract):
    """Exact executable combination chosen for a DeploymentPlan."""

    model_id: ModelId = meaning("selected model")
    logical_name: Name = meaning("catalog name")
    source_ref: str = meaning("upstream identity")
    model_revision: Maybe[str] = meaning("revision when known")
    runtime_profile_id: str = meaning("verified profile")
    runtime_provider: str = meaning("launch adapter")
    runtime_family: str = meaning("family")
    runtime_version: str = meaning("exact version")
    executor_kind: str = meaning("executor")
    host_id: str = meaning("target host")
    quantization: Maybe[str] = meaning("variant")
    placement: MemoryPlacement = meaning("device strategy")
    context_tokens: Maybe[int] = meaning("planned context")
    runtime_concurrency: Maybe[int] = meaning("planned concurrency")
    eligibility_verdict: str = meaning("runtime eligibility")
    capacity_fit: str = meaning("capacity class")
    expected_ram_bytes: Maybe[int] = meaning("estimator RAM")
    expected_vram_bytes: Maybe[int] = meaning("estimator VRAM")
    expected_storage_bytes: Maybe[int] = meaning("peak acquisition")
    selection_reason: tuple[str, ...] = meaning("why this combination")
    confidence: Maybe[str] = meaning("selection confidence", default=NOT_PROVIDED)


def envelope_fingerprint(envelope: CapacityEnvelope) -> str:
    """Stable identity of the envelope a recommendation was computed against."""
    return envelope.host_fingerprint

