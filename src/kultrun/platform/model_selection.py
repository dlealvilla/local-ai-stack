"""Bounded model selection. Recommendation is not a DeploymentPlan.

Composition-owned. Planning ranks feasible candidates. Runtime still owns
eligibility. Capacity still owns SAFE math. This service persists AUTO|MANUAL
choice and does not acquire, admit, or start inference.
"""

from __future__ import annotations

import fcntl
import hashlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import ModelCatalogEntry
from kultrun.planning.contracts import (
    FeasibleModelCandidate,
    ModelSelection,
    ModelSelectionId,
    ModelSelectionMode,
    ModelSelectionStatus,
    SelectionRecommendation,
)
from kultrun.planning.service import SelectionService, plan_from
from kultrun.platform.requirement import (
    RequirementAssessment,
    RequirementStatus,
    assessment_payload,
    feasible_candidates,
    recommend_from_view,
)
from kultrun.runtime.contracts import EligibleModelView, EligibleViewStatus

MODEL_SELECTION_SCHEMA = "planning.model_selection@1"
LOCK_NAME = "select.lock"


def fingerprint_model_selection_id(host_id: str) -> ModelSelectionId:
    """One current model-selection identity per host."""
    digest = hashlib.sha256(f"{MODEL_SELECTION_SCHEMA}|{host_id}".encode()).hexdigest()
    return ModelSelectionId(f"msel_{digest[:16]}")


def selection_basis(
    view: EligibleModelView,
    envelope: CapacityEnvelope,
    policy_version: str,
    feasible: Sequence[FeasibleModelCandidate],
) -> str:
    """Fingerprint of the inputs that make a selection current."""
    foundation = _token(view.selected_candidate_id) or ""
    profile = _token(view.profile_id) or ""
    members = ",".join(
        f"{item.model_id}:{item.requirement_basis}:{item.capacity_fit}"
        for item in sorted(feasible, key=lambda item: item.model_id)
    )
    material = "|".join(
        (
            MODEL_SELECTION_SCHEMA,
            view.view_id.value,
            foundation,
            profile,
            envelope.host_fingerprint,
            policy_version,
            members,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


class ModelSelectionLock:
    """One lock for competing model-selection mutations. Not admission."""

    def __init__(self, state_root: Path) -> None:
        root = Path(state_root).resolve() / "models"
        root.mkdir(parents=True, exist_ok=True)
        self._path = root / LOCK_NAME

    @contextmanager
    def hold(self) -> Iterator[None]:
        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


@dataclass(frozen=True, slots=True)
class ModelSelectionOverview:
    """Current recommendation, selection, and feasible set. Not a plan."""

    selection: ModelSelection
    status: ModelSelectionStatus
    recommendation: SelectionRecommendation
    feasible: tuple[FeasibleModelCandidate, ...]
    assessments: tuple[RequirementAssessment, ...]
    view: EligibleModelView
    reasons: tuple[str, ...]

    def payload(self) -> dict[str, object]:
        """API-shaped view. GET callers must not treat this as a mutation."""
        recommended = self.selection.recommended_logical_name
        selected = self.selection.selected_logical_name
        planned = plan_from(self.recommendation)
        return {
            "selection": self.selection,
            "selection_mode": self.selection.selection_mode.value,
            "status": self.status.value,
            "recommended_model_id": _token(self.selection.recommended_model_id),
            "selected_model_id": _token(self.selection.selected_model_id),
            "recommended": recommended if isinstance(recommended, str) else None,
            "selected": selected if isinstance(selected, str) else None,
            "selection_basis": self.selection.selection_basis,
            "feasible": [
                {
                    "model_id": item.model_id,
                    "logical_name": item.logical_name,
                    "capacity_fit": item.capacity_fit,
                    "requirement_basis": item.requirement_basis,
                    "runtime": item.runtime,
                    "selected": item.model_id
                    == _token(self.selection.selected_model_id),
                }
                for item in self.feasible
            ],
            "feasible_count": len(self.feasible),
            "reasons": list(self.reasons),
            "download": False,
            "estimator_mode": self.recommendation.estimator_mode,
            "estimator_provider": self.recommendation.estimator_provider,
            "estimator_version": self.recommendation.estimator_version,
            "requested_primary": self.recommendation.requested_primary,
            "fallback_used": self.recommendation.fallback_used,
            "fallback_reason": self.recommendation.fallback_reason,
            "policy_version": self.recommendation.policy_version,
            "outcome": self.recommendation.outcome.value,
            "recommendation": self.recommendation,
            "plan": planned,
            "plan_authoritative": False,
            "runtime_eligibility_status": self.view.status.value,
            "runtime_eligibility_authoritative": self.view.status.value == "current",
            "selected_runtime": _token(self.view.runtime),
            "selected_runtime_version": _token(self.view.runtime_version),
            "assessments": [assessment_payload(item) for item in self.assessments],
            "mutations": False,
            "acquire": False,
            "admit": False,
        }


class ModelSelectionService:
    """Persist AUTO|MANUAL model choice over the current feasible set."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        ranking: SelectionService,
        models: ModelCatalogue,
        lock: ModelSelectionLock,
    ) -> None:
        self._store = store
        self._clock = clock
        self._ranking = ranking
        self._models = models
        self._lock = lock

    def stored(self, host: HostCapabilities) -> ModelSelection | None:
        """Persisted selection, if any. Does not rank or probe."""
        return self._load(host.host_id.value)

    def view(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
    ) -> ModelSelectionOverview:
        """Classify the current set. GET must not persist."""
        with self._lock.hold():
            return self._view(host, eligible, envelope, assessments)

    def select_auto(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
    ) -> ModelSelectionOverview:
        """Follow the current recommendation. Does not acquire or admit."""
        with self._lock.hold():
            overview = self._view(host, eligible, envelope, assessments)
            self._persist(
                host,
                ModelSelectionMode.AUTO,
                overview.recommendation,
                overview.feasible,
                overview.selection.selection_basis,
                selected_id=_token(overview.selection.recommended_model_id),
            )
            return self._view(host, eligible, envelope, assessments)

    def select_manual(
        self,
        token: str,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
    ) -> ModelSelectionOverview:
        """Hold a currently feasible model. Recommendation stays distinct."""
        if not token.strip():
            raise ValidationError("a model is required", parameter="model")
        with self._lock.hold():
            overview = self._view(host, eligible, envelope, assessments)
            entry = self._resolve(token)
            if entry is None:
                raise NotFoundError("no such model", model=token)
            ident = entry.metadata.model_id.value
            if ident not in {item.model_id for item in overview.feasible}:
                self._refuse(token, ident, overview.assessments, eligible)
            self._persist(
                host,
                ModelSelectionMode.MANUAL,
                overview.recommendation,
                overview.feasible,
                overview.selection.selection_basis,
                selected_id=ident,
            )
            return self._view(host, eligible, envelope, assessments)

    def _view(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
    ) -> ModelSelectionOverview:
        feasible = feasible_candidates(assessments)
        recommendation = recommend_from_view(self._ranking, envelope, assessments)
        basis = selection_basis(
            eligible, envelope, self._ranking.policy.policy_version, feasible
        )
        stored = self._load(host.host_id.value)
        selection, status, reasons = self._effective(
            host, stored, recommendation, feasible, eligible, basis
        )
        return ModelSelectionOverview(
            selection=selection,
            status=status,
            recommendation=recommendation,
            feasible=feasible,
            assessments=tuple(assessments),
            view=eligible,
            reasons=reasons,
        )

    def _effective(
        self,
        host: HostCapabilities,
        stored: ModelSelection | None,
        recommendation: SelectionRecommendation,
        feasible: tuple[FeasibleModelCandidate, ...],
        eligible: EligibleModelView,
        basis: str,
    ) -> tuple[ModelSelection, ModelSelectionStatus, tuple[str, ...]]:
        rec_id, rec_name, rec_ref, rec_rev = _recommended_identity(
            recommendation, feasible
        )
        now = self._clock.now()
        if stored is None:
            record = ModelSelection(
                selection_id=fingerprint_model_selection_id(host.host_id.value),
                host_id=host.host_id,
                selection_mode=ModelSelectionMode.AUTO,
                recommended_model_id=rec_id,
                selected_model_id=rec_id,
                recommended_logical_name=rec_name,
                selected_logical_name=rec_name,
                selected_source_ref=rec_ref,
                selected_source_revision=rec_rev,
                selection_basis=basis,
                created_at=now,
                selected_at=now,
                generation=0,
            )
            status, reasons = _status(eligible, record, feasible, basis)
            return record, status, reasons

        selected_id = stored.selected_model_id
        selected_name = stored.selected_logical_name
        selected_ref = stored.selected_source_ref
        selected_rev = stored.selected_source_revision
        if stored.selection_mode is ModelSelectionMode.AUTO:
            selected_id = rec_id
            selected_name = rec_name
            selected_ref = rec_ref
            selected_rev = rec_rev
        record = replace(
            stored,
            recommended_model_id=rec_id,
            recommended_logical_name=rec_name,
            selected_model_id=selected_id,
            selected_logical_name=selected_name,
            selected_source_ref=selected_ref,
            selected_source_revision=selected_rev,
            selection_basis=basis
            if stored.selection_mode is ModelSelectionMode.AUTO
            else stored.selection_basis,
        )
        if stored.selection_mode is ModelSelectionMode.AUTO:
            record = replace(record, selection_basis=basis)
        status, reasons = _status(eligible, record, feasible, basis)
        return record, status, reasons

    def _persist(
        self,
        host: HostCapabilities,
        mode: ModelSelectionMode,
        recommendation: SelectionRecommendation,
        feasible: tuple[FeasibleModelCandidate, ...],
        basis: str,
        *,
        selected_id: str | None,
    ) -> ModelSelection:
        rec_id, rec_name, rec_ref, rec_rev = _recommended_identity(
            recommendation, feasible
        )
        chosen = _lookup(feasible, selected_id) if selected_id is not None else None
        selected: Maybe[str] = selected_id if selected_id is not None else NOT_PROVIDED
        selected_name: Maybe[str] = (
            chosen.logical_name
            if chosen is not None
            else rec_name
            if mode is ModelSelectionMode.AUTO
            else NOT_PROVIDED
        )
        selected_ref: Maybe[str] = (
            chosen.source_ref
            if chosen is not None
            else rec_ref
            if mode is ModelSelectionMode.AUTO
            else NOT_PROVIDED
        )
        selected_rev: Maybe[str] = (
            chosen.source_revision
            if chosen is not None
            else rec_rev
            if mode is ModelSelectionMode.AUTO
            else NOT_PROVIDED
        )
        stored = self._load(host.host_id.value)
        now = self._clock.now()
        previous = stored.selected_model_id if stored is not None else None
        changed = previous != selected
        if stored is None:
            record = ModelSelection(
                selection_id=fingerprint_model_selection_id(host.host_id.value),
                host_id=host.host_id,
                selection_mode=mode,
                recommended_model_id=rec_id,
                selected_model_id=selected,
                recommended_logical_name=rec_name,
                selected_logical_name=selected_name,
                selected_source_ref=selected_ref,
                selected_source_revision=selected_rev,
                selection_basis=basis,
                created_at=now,
                selected_at=now,
                generation=1,
            )
        else:
            record = replace(
                stored,
                selection_mode=mode,
                recommended_model_id=rec_id,
                selected_model_id=selected,
                recommended_logical_name=rec_name,
                selected_logical_name=selected_name,
                selected_source_ref=selected_ref,
                selected_source_revision=selected_rev,
                selection_basis=basis,
                selected_at=now if changed else stored.selected_at,
                generation=stored.generation + 1 if changed else stored.generation,
            )
        self._store.put(record.selection_id.value, record)
        return record

    def _load(self, host_id: str) -> ModelSelection | None:
        return self._store.get(
            ModelSelection, fingerprint_model_selection_id(host_id).value
        )

    def _resolve(self, token: str) -> ModelCatalogEntry | None:
        needle = token.strip()
        for entry in (*self._models.entries(), *self._models.extras()):
            if entry.metadata.logical_name.value == needle:
                return entry
            if entry.metadata.model_id.value == needle:
                return entry
        return None

    def _refuse(
        self,
        token: str,
        ident: str,
        assessments: Sequence[RequirementAssessment],
        eligible: EligibleModelView,
    ) -> None:
        if eligible.status is EligibleViewStatus.UNAVAILABLE:
            raise PreconditionFailedError(
                "model selection basis is unavailable",
                model=token,
                reason="selection_basis_stale",
            )
        if eligible.status is EligibleViewStatus.STALE:
            raise PreconditionFailedError(
                "model selection basis is stale",
                model=token,
                reason="selection_basis_stale",
            )
        item = next((row for row in assessments if row.model_id == ident), None)
        if item is None:
            raise NotFoundError("no such model", model=token)
        if item.eligibility_status == "blocked":
            raise PreconditionFailedError(
                "blocked model cannot be selected",
                model=token,
                reason="model_not_eligible",
            )
        if (
            item.eligibility_status == "unresolved"
            or item.requirement_status is RequirementStatus.UNRESOLVED
        ):
            raise PreconditionFailedError(
                "unresolved model cannot be selected",
                model=token,
                reason="model_requirement_unresolved",
            )
        if item.capacity_verdict == "infeasible":
            raise PreconditionFailedError(
                "infeasible model cannot be selected",
                model=token,
                reason="model_infeasible",
            )
        if item.requirement_status in {
            RequirementStatus.STALE,
            RequirementStatus.UNAVAILABLE,
        }:
            raise PreconditionFailedError(
                "model selection basis is stale",
                model=token,
                reason="selection_basis_stale",
            )
        raise PreconditionFailedError(
            "model is not in the current feasible set",
            model=token,
            reason="model_not_in_current_feasible_set",
        )


def _recommended_identity(
    recommendation: SelectionRecommendation,
    feasible: tuple[FeasibleModelCandidate, ...],
) -> tuple[Maybe[str], Maybe[str], Maybe[str], Maybe[str]]:
    primary = recommendation.primary
    if primary is None:
        return NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED
    match = _lookup(feasible, primary.model_id.value)
    revision: Maybe[str] = (
        match.source_revision
        if match is not None and is_resolved(match.source_revision)
        else NOT_PROVIDED
    )
    return (
        primary.model_id.value,
        primary.logical_name.value,
        primary.source_ref,
        revision,
    )


def _lookup(
    feasible: Sequence[FeasibleModelCandidate], model_id: str | None
) -> FeasibleModelCandidate | None:
    if model_id is None:
        return None
    for item in feasible:
        if item.model_id == model_id:
            return item
    return None


def _status(
    eligible: EligibleModelView,
    selection: ModelSelection,
    feasible: tuple[FeasibleModelCandidate, ...],
    current_basis: str,
) -> tuple[ModelSelectionStatus, tuple[str, ...]]:
    if eligible.status is EligibleViewStatus.UNAVAILABLE:
        return ModelSelectionStatus.UNAVAILABLE, (
            "selected verified foundation is unavailable",
        )
    if eligible.status is EligibleViewStatus.STALE:
        return ModelSelectionStatus.STALE, ("runtime capability is stale",)
    selected = _token(selection.selected_model_id)
    ids = {item.model_id for item in feasible}
    if selection.selection_mode is ModelSelectionMode.MANUAL:
        if selected is None or selected not in ids:
            return ModelSelectionStatus.INVALID, (
                "selected model is not in the current feasible set",
            )
        if selection.selection_basis != current_basis:
            return ModelSelectionStatus.STALE, ("model selection basis changed",)
        return ModelSelectionStatus.CURRENT, ()
    return ModelSelectionStatus.CURRENT, ()
