"""Derive ModelRequirement from the selected verified foundation.

Composition-owned. Planning still owns capacity fit. Runtime still owns
eligibility. Catalog metadata is not mutated.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    ArtifactState,
    ModelCatalogEntry,
    ModelRequirement,
    VerificationState,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.planning.contracts import (
    CapacityFitClass,
    CompatibilityVerdict,
    DeploymentCapacity,
    FeasibleModelCandidate,
    ModelEvaluation,
    SelectionPolicy,
    SelectionRecommendation,
)
from kultrun.planning.evaluate import deployment_capacity, evaluate
from kultrun.planning.service import (
    SelectionService,
    bind_runtime,
    estimation_request,
)
from kultrun.runtime.contracts import (
    EligibleModelView,
    EligibleViewStatus,
    RuntimeEligibilityStatus,
    RuntimeEligibleModelCandidate,
)


class RequirementStatus(StrEnum):
    """Whether a derived requirement may be used for capacity."""

    READY = "ready"
    REFUSED = "refused"
    UNRESOLVED = "unresolved"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


def requirement_basis(
    view_id: str,
    profile_id: str,
    model_id: str,
    runtime: str,
    runtime_version: str,
    estimator_version: str,
    *,
    source_revision: str = "",
    quantization: str = "",
    context_tokens: str = "",
    batch_size: str = "1",
) -> str:
    """Short fingerprint of the current requirement inputs."""
    material = "|".join(
        (
            "requirement",
            view_id,
            profile_id,
            model_id,
            runtime,
            runtime_version,
            estimator_version,
            source_revision,
            quantization,
            context_tokens,
            batch_size,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def capacity_verdict(
    fit: CapacityFitClass | None,
    *,
    assessed: bool,
    reasons: tuple[str, ...] = (),
) -> str:
    """Map existing fit classes plus dimension-specific infeasible codes."""
    if not assessed:
        return "not_assessed"
    if fit is None or fit is CapacityFitClass.UNRESOLVED:
        return "unresolved"
    if fit is CapacityFitClass.EXCEEDS_SAFE:
        for code in ("infeasible_vram", "infeasible_ram", "infeasible_storage"):
            if code in reasons:
                return code
        return "infeasible"
    return "feasible"


@dataclass(frozen=True, slots=True)
class RequirementAssessment:
    """One model's derived requirement and capacity. Not a persisted identity."""

    model_id: str
    logical_name: str
    requirement_status: RequirementStatus
    eligibility_status: str | None
    runtime: str | None
    runtime_version: str | None
    profile_id: str | None
    view_id: str
    view_status: str
    selection_mode: str | None
    selected_candidate_id: str | None
    requirement: ModelRequirement | None
    basis: str | None
    reasons: tuple[str, ...]
    capacity_assessed: bool
    capacity_fit: str | None
    capacity_verdict: str
    required_ram_bytes: object
    required_vram_bytes: object
    safe_ram_bytes: object
    safe_vram_bytes: object
    source_ref: str | None
    source_revision: object
    evaluation: ModelEvaluation | None
    available_ram_bytes: object = NOT_PROVIDED
    available_vram_bytes: object = NOT_PROVIDED
    incremental_storage_bytes: object = NOT_PROVIDED
    available_storage_bytes: object = NOT_PROVIDED
    snapshot_basis: str | None = None


def incremental_storage_demand(
    entry: ModelCatalogEntry,
    requirement: ModelRequirement,
    inventory: ModelInventory | None,
) -> Maybe[int]:
    """Acquisition footprint still required.

    Stored exact artifacts are not re-charged.
    """
    peak = requirement.peak_additional_bytes
    if inventory is None:
        return peak
    revision = entry.metadata.source_revision
    if not is_resolved(revision) or not isinstance(revision, str):
        return peak
    quantization = (
        str(entry.metadata.quantization)
        if is_resolved(entry.metadata.quantization)
        else None
    )
    found = inventory.find_stored(
        model_id=entry.metadata.model_id,
        revision=revision,
        quantization=quantization,
        artifact_format=None,
    )
    if found is None:
        return peak
    if found.state is not ArtifactState.STORED:
        return peak
    if found.verification_state not in {
        VerificationState.PASSED,
        VerificationState.NOT_VERIFIED,
    }:
        return peak
    return 0


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _candidate_for(
    view: EligibleModelView, model_id: str
) -> RuntimeEligibleModelCandidate | None:
    for item in view.candidates:
        if item.model_id == model_id:
            return item
    return None


def assess_entry(
    view: EligibleModelView,
    entry: ModelCatalogEntry,
    envelope: CapacityEnvelope,
    estimator: ModelRequirementEstimator,
    policy: SelectionPolicy,
    *,
    capacity: DeploymentCapacity | None = None,
    inventory: ModelInventory | None = None,
) -> RequirementAssessment:
    """Derive one requirement. BLOCKED and UNRESOLVED skip the estimator."""
    ident = entry.metadata.model_id.value
    runtime = _token(view.runtime)
    version = _token(view.runtime_version) or NOT_PROVIDED
    profile_id = _token(view.profile_id)
    view_id = view.view_id.value
    candidate = _candidate_for(view, ident)
    eligibility = candidate.status.value if candidate is not None else None
    reasons: tuple[str, ...] = (
        tuple(item.value for item in view.reason_codes) if view.reason_codes else ()
    )
    if candidate is not None:
        reasons = candidate.reasons or reasons

    if view.status is EligibleViewStatus.UNAVAILABLE:
        return _row(
            entry,
            view,
            RequirementStatus.UNAVAILABLE,
            eligibility,
            None,
            reasons or ("selected verified foundation is unavailable",),
            assessed=False,
        )
    if view.status is EligibleViewStatus.STALE:
        return _row(
            entry,
            view,
            RequirementStatus.STALE,
            eligibility,
            None,
            reasons or ("runtime capability is stale",),
            assessed=False,
        )
    if candidate is None:
        return _row(
            entry,
            view,
            RequirementStatus.UNRESOLVED,
            None,
            None,
            ("eligibility candidate missing",),
            assessed=False,
        )
    if candidate.status is RuntimeEligibilityStatus.BLOCKED:
        return _row(
            entry,
            view,
            RequirementStatus.REFUSED,
            eligibility,
            None,
            candidate.reasons or ("runtime eligibility blocked",),
            assessed=False,
        )
    if candidate.status is RuntimeEligibilityStatus.UNRESOLVED:
        return _row(
            entry,
            view,
            RequirementStatus.UNRESOLVED,
            eligibility,
            None,
            candidate.reasons or ("runtime eligibility unresolved",),
            assessed=False,
        )
    if runtime is None or profile_id is None:
        return _row(
            entry,
            view,
            RequirementStatus.UNAVAILABLE,
            eligibility,
            None,
            ("selected runtime identity is missing",),
            assessed=False,
        )

    placement = capacity if capacity is not None else deployment_capacity(envelope)
    version_token = version if isinstance(version, str) else ""
    request = estimation_request(
        entry,
        placement.placement,
        runtime=runtime,
        runtime_version=version,
    )
    revision = (
        str(request.source_revision) if is_resolved(request.source_revision) else ""
    )
    quant = str(request.quantization) if is_resolved(request.quantization) else ""
    context = str(request.context_tokens) if is_resolved(request.context_tokens) else ""
    basis = requirement_basis(
        view_id,
        profile_id,
        ident,
        runtime,
        version_token,
        estimator.version,
        source_revision=revision,
        quantization=quant,
        context_tokens=context,
        batch_size=str(request.batch_size),
    )
    requirement = bind_runtime(
        estimator.estimate(request),
        runtime=runtime,
        runtime_version=version,
        basis=basis,
    )
    incremental = incremental_storage_demand(entry, requirement, inventory)
    evaluation = evaluate(
        entry.metadata,
        requirement,
        placement,
        policy,
        runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        incremental_storage_bytes=incremental,
    )
    return _row(
        entry,
        view,
        RequirementStatus.READY,
        eligibility,
        requirement,
        evaluation.reasons,
        assessed=True,
        evaluation=evaluation,
        basis=basis,
        runtime=runtime,
        runtime_version=_token(version),
        profile_id=profile_id,
    )


def assess_catalog(
    view: EligibleModelView,
    models: ModelCatalogue,
    envelope: CapacityEnvelope,
    estimator: ModelRequirementEstimator,
    policy: SelectionPolicy,
    *,
    capacity: DeploymentCapacity | None = None,
    inventory: ModelInventory | None = None,
) -> tuple[RequirementAssessment, ...]:
    """Catalog entries plus extras. Does not mutate metadata or inventory."""
    seen: set[str] = set()
    rows: list[RequirementAssessment] = []
    for entry in (*models.entries(), *models.extras()):
        ident = entry.metadata.model_id.value
        if ident in seen:
            continue
        seen.add(ident)
        rows.append(
            assess_entry(
                view,
                entry,
                envelope,
                estimator,
                policy,
                capacity=capacity,
                inventory=inventory,
            )
        )
    return tuple(rows)


def is_selectable(item: RequirementAssessment) -> bool:
    """Hard gate: ELIGIBLE + READY + FEASIBLE against a CURRENT view."""
    return (
        item.view_status == EligibleViewStatus.CURRENT.value
        and item.eligibility_status == RuntimeEligibilityStatus.ELIGIBLE.value
        and item.requirement_status is RequirementStatus.READY
        and item.capacity_verdict == "feasible"
        and item.evaluation is not None
        and item.basis is not None
        and item.runtime is not None
        and item.profile_id is not None
    )


def feasible_candidates(
    assessments: Sequence[RequirementAssessment],
) -> tuple[FeasibleModelCandidate, ...]:
    """Selection input. BLOCKED, UNRESOLVED, INFEASIBLE, and stale are omitted."""
    rows: list[FeasibleModelCandidate] = []
    for item in assessments:
        if not is_selectable(item) or item.evaluation is None:
            continue
        revision: Maybe[str] = (
            item.source_revision
            if isinstance(item.source_revision, str)
            else NOT_PROVIDED
        )
        version: Maybe[str] = (
            item.runtime_version if item.runtime_version is not None else NOT_PROVIDED
        )
        rows.append(
            FeasibleModelCandidate(
                model_id=item.model_id,
                logical_name=item.logical_name,
                source_ref=item.source_ref or item.evaluation.source_ref,
                source_revision=revision,
                view_id=item.view_id,
                profile_id=item.profile_id or "",
                runtime=item.runtime or "",
                runtime_version=version,
                requirement_basis=item.basis or "",
                capacity_fit=item.capacity_fit or item.evaluation.capacity_fit.value,
                evaluation=item.evaluation,
            )
        )
    return tuple(rows)


def recommend_from_view(
    selection: SelectionService,
    envelope: CapacityEnvelope,
    assessments: Sequence[RequirementAssessment],
) -> SelectionRecommendation:
    """Existing ranking, applied only to currently feasible candidates."""
    return selection.rank_feasible(
        feasible_candidates(assessments),
        host_fingerprint=envelope.host_fingerprint,
    )


def _row(
    entry: ModelCatalogEntry,
    view: EligibleModelView,
    status: RequirementStatus,
    eligibility: str | None,
    requirement: ModelRequirement | None,
    reasons: tuple[str, ...],
    *,
    assessed: bool,
    evaluation: ModelEvaluation | None = None,
    basis: str | None = None,
    runtime: str | None = None,
    runtime_version: str | None = None,
    profile_id: str | None = None,
) -> RequirementAssessment:
    fit = None
    ram: object = NOT_PROVIDED
    vram: object = NOT_PROVIDED
    safe_ram: object = NOT_PROVIDED
    safe_vram: object = NOT_PROVIDED
    available_ram: object = NOT_PROVIDED
    available_vram: object = NOT_PROVIDED
    incremental: object = NOT_PROVIDED
    available_storage: object = NOT_PROVIDED
    snapshot: str | None = None
    fit_class: CapacityFitClass | None = None
    if evaluation is not None:
        fit = evaluation.capacity_fit.value
        ram = evaluation.required_ram_bytes
        vram = evaluation.required_vram_bytes
        safe_ram = evaluation.safe_ram_bytes
        safe_vram = evaluation.safe_vram_bytes
        available_ram = evaluation.available_ram_bytes
        available_vram = evaluation.available_vram_bytes
        incremental = evaluation.incremental_storage_bytes
        available_storage = evaluation.available_storage_bytes
        snapshot = (
            evaluation.snapshot_basis
            if is_resolved(evaluation.snapshot_basis)
            and isinstance(evaluation.snapshot_basis, str)
            else None
        )
        fit_class = evaluation.capacity_fit
    return RequirementAssessment(
        model_id=entry.metadata.model_id.value,
        logical_name=entry.metadata.logical_name.value,
        requirement_status=status,
        eligibility_status=eligibility,
        runtime=runtime or _token(view.runtime),
        runtime_version=runtime_version or _token(view.runtime_version),
        profile_id=profile_id or _token(view.profile_id),
        view_id=view.view_id.value,
        view_status=view.status.value,
        selection_mode=_token(view.selection_mode),
        selected_candidate_id=_token(view.selected_candidate_id),
        requirement=requirement,
        basis=basis,
        reasons=reasons,
        capacity_assessed=assessed,
        capacity_fit=fit,
        capacity_verdict=capacity_verdict(
            fit_class, assessed=assessed, reasons=reasons
        ),
        required_ram_bytes=ram,
        required_vram_bytes=vram,
        safe_ram_bytes=safe_ram,
        safe_vram_bytes=safe_vram,
        source_ref=entry.metadata.source_ref,
        source_revision=entry.metadata.source_revision,
        evaluation=evaluation,
        available_ram_bytes=available_ram,
        available_vram_bytes=available_vram,
        incremental_storage_bytes=incremental,
        available_storage_bytes=available_storage,
        snapshot_basis=snapshot,
    )


def assessment_payload(row: RequirementAssessment) -> dict[str, object]:
    """API-shaped derived assessment. GET is not a mutation."""
    requirement = row.requirement
    return {
        "model_id": row.model_id,
        "logical_name": row.logical_name,
        "requirement_status": row.requirement_status.value,
        "eligibility_status": row.eligibility_status,
        "runtime": row.runtime,
        "runtime_version": row.runtime_version,
        "profile_id": row.profile_id,
        "view_id": row.view_id,
        "view_status": row.view_status,
        "selection_mode": row.selection_mode,
        "selected_candidate_id": row.selected_candidate_id,
        "requirement": requirement,
        "basis": row.basis,
        "reasons": list(row.reasons),
        "capacity_assessed": row.capacity_assessed,
        "capacity_fit": row.capacity_fit,
        "capacity_verdict": row.capacity_verdict,
        "required_ram_bytes": (
            row.required_ram_bytes if is_resolved(row.required_ram_bytes) else None
        ),
        "required_vram_bytes": (
            row.required_vram_bytes if is_resolved(row.required_vram_bytes) else None
        ),
        "safe_ram_bytes": (
            row.safe_ram_bytes if is_resolved(row.safe_ram_bytes) else None
        ),
        "safe_vram_bytes": (
            row.safe_vram_bytes if is_resolved(row.safe_vram_bytes) else None
        ),
        "available_ram_bytes": (
            row.available_ram_bytes if is_resolved(row.available_ram_bytes) else None
        ),
        "available_vram_bytes": (
            row.available_vram_bytes if is_resolved(row.available_vram_bytes) else None
        ),
        "incremental_storage_bytes": (
            row.incremental_storage_bytes
            if is_resolved(row.incremental_storage_bytes)
            else None
        ),
        "available_storage_bytes": (
            row.available_storage_bytes
            if is_resolved(row.available_storage_bytes)
            else None
        ),
        "snapshot_basis": row.snapshot_basis,
        "assumed_runtime": (
            requirement.assumed_runtime
            if requirement is not None and is_resolved(requirement.assumed_runtime)
            else None
        ),
        "assumed_context_tokens": (
            requirement.assumed_context_tokens
            if requirement is not None
            and is_resolved(requirement.assumed_context_tokens)
            else None
        ),
        "assumed_batch_size": (
            requirement.assumed_batch_size
            if requirement is not None and is_resolved(requirement.assumed_batch_size)
            else None
        ),
        "vram_weights_bytes": (
            requirement.vram_weights_bytes
            if requirement is not None and is_resolved(requirement.vram_weights_bytes)
            else None
        ),
        "vram_kv_cache_bytes": (
            requirement.vram_kv_cache_bytes
            if requirement is not None and is_resolved(requirement.vram_kv_cache_bytes)
            else None
        ),
        "vram_overhead_bytes": (
            requirement.vram_overhead_bytes
            if requirement is not None and is_resolved(requirement.vram_overhead_bytes)
            else None
        ),
        "safety_allowance_bytes": (
            requirement.safety_allowance_bytes
            if requirement is not None
            and is_resolved(requirement.safety_allowance_bytes)
            else None
        ),
        "estimator_provider": (
            requirement.estimator_provider
            if requirement is not None and is_resolved(requirement.estimator_provider)
            else None
        ),
        "mutations": False,
    }
