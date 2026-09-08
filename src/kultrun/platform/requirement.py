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
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import ModelCatalogEntry, ModelRequirement
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.planning.contracts import (
    CapacityFitClass,
    CompatibilityVerdict,
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
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def capacity_verdict(fit: CapacityFitClass | None, *, assessed: bool) -> str:
    """Map existing fit classes. Not a new capacity vocabulary."""
    if not assessed:
        return "not_assessed"
    if fit is None or fit is CapacityFitClass.UNRESOLVED:
        return "unresolved"
    if fit is CapacityFitClass.EXCEEDS_SAFE:
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

    capacity = deployment_capacity(envelope)
    version_token = version if isinstance(version, str) else ""
    basis = requirement_basis(
        view_id,
        profile_id,
        ident,
        runtime,
        version_token,
        estimator.version,
    )
    request = estimation_request(
        entry,
        capacity.placement,
        runtime=runtime,
        runtime_version=version,
    )
    requirement = bind_runtime(
        estimator.estimate(request),
        runtime=runtime,
        runtime_version=version,
        basis=basis,
    )
    evaluation = evaluate(
        entry.metadata,
        requirement,
        capacity,
        policy,
        runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
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
) -> tuple[RequirementAssessment, ...]:
    """Catalog entries plus extras. Does not mutate metadata or inventory."""
    seen: set[str] = set()
    rows: list[RequirementAssessment] = []
    for entry in (*models.entries(), *models.extras()):
        ident = entry.metadata.model_id.value
        if ident in seen:
            continue
        seen.add(ident)
        rows.append(assess_entry(view, entry, envelope, estimator, policy))
    return tuple(rows)


MappingCompat = dict[str, CompatibilityVerdict]


def planning_inputs(
    assessments: Sequence[RequirementAssessment],
) -> tuple[str, MappingCompat]:
    """Runtime identity and compatibility tokens for existing ranking."""
    runtime = ""
    mapping: dict[str, CompatibilityVerdict] = {}
    for item in assessments:
        if item.runtime and not runtime:
            runtime = item.runtime
        if item.requirement_status is RequirementStatus.READY:
            mapping[item.model_id] = CompatibilityVerdict.COMPATIBLE
        elif item.requirement_status is RequirementStatus.REFUSED:
            mapping[item.model_id] = CompatibilityVerdict.UNSUPPORTED
        else:
            mapping[item.model_id] = CompatibilityVerdict.UNRESOLVED
    return runtime, mapping


def recommend_from_view(
    selection: SelectionService,
    view: EligibleModelView,
    envelope: CapacityEnvelope,
    candidates: tuple[ModelCatalogEntry, ...],
    assessments: Sequence[RequirementAssessment],
) -> SelectionRecommendation:
    """Existing ranking, fed by remapped requirement inputs."""
    runtime, mapping = planning_inputs(assessments)
    if not runtime:
        runtime = _token(view.runtime) or ""
    version = _token(view.runtime_version) or NOT_PROVIDED
    basis = next((item.basis for item in assessments if item.basis), NOT_PROVIDED)
    return selection.recommend(
        envelope=envelope,
        candidates=candidates,
        runtime=runtime or "unresolved",
        runtime_compatibility=mapping,
        runtime_version=version,
        requirement_basis=basis if isinstance(basis, str) else NOT_PROVIDED,
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
    fit_class: CapacityFitClass | None = None
    if evaluation is not None:
        fit = evaluation.capacity_fit.value
        ram = evaluation.required_ram_bytes
        vram = evaluation.required_vram_bytes
        safe_ram = evaluation.safe_ram_bytes
        safe_vram = evaluation.safe_vram_bytes
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
        capacity_verdict=capacity_verdict(fit_class, assessed=assessed),
        required_ram_bytes=ram,
        required_vram_bytes=vram,
        safe_ram_bytes=safe_ram,
        safe_vram_bytes=safe_vram,
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
        "assumed_runtime": (
            requirement.assumed_runtime
            if requirement is not None and is_resolved(requirement.assumed_runtime)
            else None
        ),
        "mutations": False,
    }
