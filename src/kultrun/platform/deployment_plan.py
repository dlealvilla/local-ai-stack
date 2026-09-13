"""Authoritative DeploymentPlan. Consumes selection; does not execute.

Composition-owned. Planning owns the contract. Runtime still owns
eligibility. Capacity still owns SAFE math. This service persists one
current plan per host and does not acquire, admit, or start inference.
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
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import MemoryPlacement
from kultrun.planning.contracts import (
    DeploymentPlan,
    DeploymentPlanId,
    DeploymentPlanStatus,
    ModelEvaluation,
    ModelSelectionStatus,
)
from kultrun.platform.model_selection import ModelSelectionOverview
from kultrun.platform.requirement import RequirementAssessment, RequirementStatus
from kultrun.runtime.contracts import (
    EligibleModelView,
    EligibleViewStatus,
    FoundationSelection,
)
from kultrun.storage.topology import mount_for_path

DEPLOYMENT_PLAN_SCHEMA = "planning.deployment_plan@1"
LOCK_NAME = "plan.lock"


def fingerprint_deployment_plan_id(host_id: str) -> DeploymentPlanId:
    """One current deployment-plan identity per host."""
    digest = hashlib.sha256(f"{DEPLOYMENT_PLAN_SCHEMA}|{host_id}".encode()).hexdigest()
    return DeploymentPlanId(f"dplan_{digest[:16]}")


def plan_basis(
    eligible: EligibleModelView,
    envelope: CapacityEnvelope,
    selection: ModelSelectionOverview,
    assessment: RequirementAssessment,
    *,
    foundation_selection_id: str,
    executor_identity: str,
    policy_version: str,
    storage_pool_mount: str = "",
) -> str:
    """Fingerprint of the inputs that make a deployment plan current."""
    selected = _token(selection.selection.selected_model_id) or ""
    revision = _token(selection.selection.selected_source_revision) or ""
    context = ""
    if assessment.requirement is not None and is_resolved(
        assessment.requirement.assumed_context_tokens
    ):
        context = str(assessment.requirement.assumed_context_tokens)
    placement = _placement_of(assessment.evaluation) if assessment.evaluation else None
    accel = _accelerator_index(envelope)
    material = "|".join(
        (
            DEPLOYMENT_PLAN_SCHEMA,
            eligible.host_id.value,
            eligible.view_id.value,
            envelope.host_fingerprint,
            foundation_selection_id,
            _token(eligible.selected_candidate_id) or "",
            _token(eligible.installation_id) or "",
            _token(eligible.profile_id) or "",
            _token(eligible.runtime) or "",
            _token(eligible.runtime_version) or "",
            executor_identity,
            selection.selection.selection_id.value,
            selection.selection.selection_mode.value,
            selection.selection.selection_basis,
            selected,
            revision,
            assessment.basis or "",
            assessment.capacity_fit or "",
            policy_version,
            context,
            placement.value if placement is not None else "",
            "" if accel is None else str(accel),
            storage_pool_mount,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


class DeploymentPlanLock:
    """One lock for competing plan mutations. Not admission."""

    def __init__(self, state_root: Path) -> None:
        root = Path(state_root).resolve() / "deployments"
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
class DeploymentPlanOverview:
    """Persisted plan plus computed currentness. Not a reservation."""

    plan: DeploymentPlan | None
    status: DeploymentPlanStatus
    reasons: tuple[str, ...]
    current_basis: str | None
    refreshable: bool

    def payload(self) -> dict[str, object]:
        """API-shaped view. GET callers must not treat this as a mutation."""
        plan = self.plan
        return {
            "plan": plan,
            "status": self.status.value,
            "authoritative": True,
            "id": _token(plan.plan_id) if plan is not None else None,
            "plan_id": _token(plan.plan_id) if plan is not None else None,
            "plan_basis": _token(plan.plan_basis) if plan is not None else None,
            "current_basis": self.current_basis,
            "generation": plan.generation if plan is not None else None,
            "reasons": list(self.reasons),
            "refreshable": self.refreshable,
            "host_id": _token(plan.host_id) if plan is not None else None,
            "foundation_selection_id": (
                _token(plan.foundation_selection_id) if plan is not None else None
            ),
            "selected_candidate_id": (
                _token(plan.selected_candidate_id) if plan is not None else None
            ),
            "installation_id": (
                _token(plan.installation_id) if plan is not None else None
            ),
            "profile_id": _token(plan.profile_id) if plan is not None else None,
            "runtime": _token(plan.runtime) if plan is not None else None,
            "runtime_version": (
                _token(plan.runtime_version) if plan is not None else None
            ),
            "executor": _token(plan.executor_kind) if plan is not None else None,
            "model_id": plan.model_id.value if plan is not None else None,
            "selected_model": plan.logical_name.value if plan is not None else None,
            "source_ref": plan.source_ref if plan is not None else None,
            "source_revision": (
                _token(plan.source_revision) if plan is not None else None
            ),
            "quantization": _token(plan.quantization) if plan is not None else None,
            "model_selection_id": (
                _token(plan.model_selection_id) if plan is not None else None
            ),
            "model_selection_mode": (
                _token(plan.model_selection_mode) if plan is not None else None
            ),
            "recommended_model_id": (
                _token(plan.recommended_model_id) if plan is not None else None
            ),
            "requirement": _requirement(plan) if plan is not None else None,
            "capacity": _capacity(plan) if plan is not None else None,
            "resource_request": _resource_spec(plan) if plan is not None else None,
            "settings": _settings(plan) if plan is not None else None,
            "storage_pool_mount": (
                _token(plan.storage_pool_mount) if plan is not None else None
            ),
            "mutations": False,
            "acquire": False,
            "admit": False,
            "launch": False,
        }


class DeploymentPlanningService:
    """Persist one current DeploymentPlan per host. Does not execute."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        lock: DeploymentPlanLock,
        executor_identity: str,
        policy_version: str,
        state_root: Path | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._lock = lock
        self._executor_identity = executor_identity
        self._policy_version = policy_version
        self._state_root = (
            Path(state_root).resolve() if state_root is not None else None
        )

    def stored(self, host: HostCapabilities) -> DeploymentPlan | None:
        """Persisted plan, if any. Does not revalidate."""
        return self._load(host.host_id.value)

    def view(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
        selection: ModelSelectionOverview,
        foundation: FoundationSelection | None,
    ) -> DeploymentPlanOverview:
        """Classify the persisted plan. GET must not persist."""
        with self._lock.hold():
            return self._view(
                host, eligible, envelope, assessments, selection, foundation
            )

    def refresh(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
        selection: ModelSelectionOverview,
        foundation: FoundationSelection | None,
    ) -> DeploymentPlanOverview:
        """Persist a CURRENT plan from upstream state. Does not execute."""
        with self._lock.hold():
            draft, _reasons = self._draft(
                host, eligible, envelope, assessments, selection, foundation
            )
            if draft is None:
                return self._view(
                    host, eligible, envelope, assessments, selection, foundation
                )
            stored = self._load(host.host_id.value)
            now = self._clock.now()
            previous = stored.model_id.value if stored is not None else None
            changed = previous != draft.model_id.value
            if stored is None:
                record = replace(
                    draft,
                    created_at=now,
                    selected_at=now,
                    generation=1,
                )
            else:
                record = replace(
                    draft,
                    created_at=stored.created_at,
                    selected_at=now if changed else stored.selected_at,
                    generation=(
                        stored.generation + 1 if changed else stored.generation
                    ),
                )
            ident = fingerprint_deployment_plan_id(host.host_id.value)
            self._store.put(ident.value, record)
            return self._view(
                host, eligible, envelope, assessments, selection, foundation
            )

    def _view(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
        selection: ModelSelectionOverview,
        foundation: FoundationSelection | None,
    ) -> DeploymentPlanOverview:
        stored = self._load(host.host_id.value)
        draft, reasons = self._draft(
            host, eligible, envelope, assessments, selection, foundation
        )
        current = _token(draft.plan_basis) if draft is not None else None
        if stored is None:
            note = reasons if reasons else ("no persisted deployment plan",)
            return DeploymentPlanOverview(
                plan=None,
                status=DeploymentPlanStatus.UNAVAILABLE,
                reasons=note,
                current_basis=current,
                refreshable=draft is not None,
            )
        stored_basis = _token(stored.plan_basis)
        if draft is not None and stored_basis == current:
            return DeploymentPlanOverview(
                plan=stored,
                status=DeploymentPlanStatus.CURRENT,
                reasons=(),
                current_basis=current,
                refreshable=True,
            )
        stale_reasons = reasons or ("deployment plan basis changed",)
        return DeploymentPlanOverview(
            plan=stored,
            status=DeploymentPlanStatus.STALE,
            reasons=stale_reasons,
            current_basis=current,
            refreshable=draft is not None,
        )

    def _draft(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        assessments: Sequence[RequirementAssessment],
        selection: ModelSelectionOverview,
        foundation: FoundationSelection | None,
    ) -> tuple[DeploymentPlan | None, tuple[str, ...]]:
        assessment, reasons = _selected_assessment(eligible, selection, assessments)
        if assessment is None or assessment.evaluation is None:
            return None, reasons
        if foundation is None:
            return None, ("foundation selection is unavailable",)
        if not isinstance(foundation.selected_candidate_id, str):
            return None, ("foundation selection is unavailable",)
        foundation_id = foundation.selection_id.value
        executor = _token(eligible.executor) or self._executor_identity
        storage_mount = ""
        if self._state_root is not None:
            found = mount_for_path(self._state_root / "models", host)
            storage_mount = found if isinstance(found, str) else ""
        basis = plan_basis(
            eligible,
            envelope,
            selection,
            assessment,
            foundation_selection_id=foundation_id,
            executor_identity=executor,
            policy_version=self._policy_version,
            storage_pool_mount=storage_mount,
        )
        evaluation = assessment.evaluation
        requirement = assessment.requirement
        context: Maybe[int] = (
            requirement.assumed_context_tokens
            if requirement is not None
            else NOT_PROVIDED
        )
        revision: Maybe[str]
        if is_resolved(selection.selection.selected_source_revision):
            revision = selection.selection.selected_source_revision
        elif isinstance(assessment.source_revision, str):
            revision = assessment.source_revision
        else:
            revision = NOT_PROVIDED
        ident = fingerprint_deployment_plan_id(host.host_id.value)
        now = self._clock.now()
        provider = (
            evaluation.estimator_provider
            if is_resolved(evaluation.estimator_provider)
            else ""
        )
        mode = (
            evaluation.estimator_mode if is_resolved(evaluation.estimator_mode) else ""
        )
        return (
            DeploymentPlan(
                model_id=evaluation.model_id,
                logical_name=evaluation.logical_name,
                source_ref=evaluation.source_ref,
                quantization=evaluation.quantization,
                runtime=_maybe(eligible.runtime),
                executor_kind=executor,
                placement=_placement_of(evaluation),
                expected_ram_bytes=evaluation.required_ram_bytes,
                expected_vram_bytes=evaluation.required_vram_bytes,
                expected_unified_bytes=evaluation.required_unified_bytes,
                expected_storage_bytes=evaluation.required_storage_bytes,
                expected_utilization=evaluation.utilization.ratio,
                estimator_provider=provider,
                policy_version=self._policy_version,
                rationale=evaluation.reasons,
                estimator_mode=mode,
                fallback_used=evaluation.fallback_used,
                fallback_reason=evaluation.fallback_reason,
                plan_id=ident.value,
                host_id=host.host_id.value,
                created_at=now,
                selected_at=now,
                plan_basis=basis,
                generation=1,
                foundation_selection_id=foundation_id,
                selected_candidate_id=_maybe(eligible.selected_candidate_id),
                installation_id=_maybe(eligible.installation_id),
                profile_id=_maybe(eligible.profile_id),
                runtime_version=_maybe(eligible.runtime_version),
                model_selection_id=selection.selection.selection_id.value,
                model_selection_mode=selection.selection.selection_mode.value,
                model_selection_basis=selection.selection.selection_basis,
                recommended_model_id=_maybe(selection.selection.recommended_model_id),
                source_revision=revision,
                requirement_basis=assessment.basis or NOT_PROVIDED,
                context_tokens=context,
                capacity_fit=assessment.capacity_fit or NOT_PROVIDED,
                capacity_verdict=assessment.capacity_verdict,
                host_fingerprint=envelope.host_fingerprint,
                accelerator_index=_accelerator_index(envelope),
                eligible_view_id=eligible.view_id.value,
                storage_pool_mount=storage_mount or NOT_PROVIDED,
            ),
            (),
        )

    def _load(self, host_id: str) -> DeploymentPlan | None:
        return self._store.get(
            DeploymentPlan, fingerprint_deployment_plan_id(host_id).value
        )


def _selected_assessment(
    eligible: EligibleModelView,
    selection: ModelSelectionOverview,
    assessments: Sequence[RequirementAssessment],
) -> tuple[RequirementAssessment | None, tuple[str, ...]]:
    reasons: list[str] = []
    if eligible.status is EligibleViewStatus.UNAVAILABLE:
        reasons.append("selected verified foundation is unavailable")
    elif eligible.status is EligibleViewStatus.STALE:
        reasons.append("runtime capability is stale")
    if selection.status is ModelSelectionStatus.UNAVAILABLE:
        reasons.append("model selection is unavailable")
    elif selection.status is ModelSelectionStatus.INVALID:
        reasons.append("model selection is invalid")
    elif selection.status is ModelSelectionStatus.STALE:
        reasons.append("model selection is stale")
    selected = _token(selection.selection.selected_model_id)
    if selected is None:
        reasons.append("no selected model")
        return None, tuple(reasons)
    ids = {item.model_id for item in selection.feasible}
    if selected not in ids:
        reasons.append("selected model is not in the current feasible set")
        return None, tuple(reasons)
    item = next((row for row in assessments if row.model_id == selected), None)
    if item is None:
        reasons.append("selected model has no requirement assessment")
        return None, tuple(reasons)
    if item.requirement_status is not RequirementStatus.READY:
        reasons.append("selected model requirement is not ready")
        return None, tuple(reasons)
    if item.capacity_verdict != "feasible":
        reasons.append("selected model is not feasible")
        return None, tuple(reasons)
    if item.evaluation is None:
        reasons.append("selected model has no capacity evaluation")
        return None, tuple(reasons)
    if reasons:
        return None, tuple(reasons)
    return item, ()


def _placement_of(evaluation: ModelEvaluation) -> MemoryPlacement:
    if is_resolved(evaluation.safe_vram_bytes):
        return MemoryPlacement.DISCRETE_GPU
    if is_resolved(evaluation.safe_unified_bytes):
        return MemoryPlacement.UNIFIED_MEMORY
    return MemoryPlacement.CPU_ONLY


def _accelerator_index(envelope: CapacityEnvelope) -> int | None:
    devices = envelope.accelerators
    if not devices:
        return None
    return devices[0].index


def _maybe(value: object) -> Maybe[str]:
    token = _token(value)
    return token if token is not None else NOT_PROVIDED


def _resolved_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _requirement(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "basis": _token(plan.requirement_basis),
        "ram_bytes": _resolved_int(plan.expected_ram_bytes),
        "vram_bytes": _resolved_int(plan.expected_vram_bytes),
        "unified_bytes": _resolved_int(plan.expected_unified_bytes),
        "storage_bytes": _resolved_int(plan.expected_storage_bytes),
        "context_tokens": _resolved_int(plan.context_tokens),
        "estimator_provider": plan.estimator_provider,
        "utilization": (
            plan.expected_utilization
            if is_resolved(plan.expected_utilization)
            else None
        ),
    }


def _capacity(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "fit": _token(plan.capacity_fit),
        "verdict": _token(plan.capacity_verdict),
        "host_fingerprint": _token(plan.host_fingerprint),
        "accelerator_index": plan.accelerator_index,
        "placement": plan.placement.value,
    }


def _resource_spec(plan: DeploymentPlan) -> dict[str, object]:
    """Normalized resource intent. Not submitted to ResourceManager."""
    return {
        "artifact_id": None,
        "model_id": plan.model_id.value,
        "plan_fingerprint": _token(plan.plan_basis),
        "placement": plan.placement.value,
        "ram_bytes": _resolved_int(plan.expected_ram_bytes),
        "accelerator_bytes": _resolved_int(plan.expected_vram_bytes),
        "unified_bytes": _resolved_int(plan.expected_unified_bytes),
        "accelerator_index": plan.accelerator_index,
        "runtime": _token(plan.runtime),
        "model_revision": _token(plan.source_revision),
        "quantization": _token(plan.quantization),
        "context_tokens": _resolved_int(plan.context_tokens),
        "host_fingerprint": _token(plan.host_fingerprint),
        "storage_pool_mount": _token(plan.storage_pool_mount),
        "submitted": False,
    }


def _settings(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "placement": plan.placement.value,
        "context_tokens": _resolved_int(plan.context_tokens),
        "accelerator_index": plan.accelerator_index,
        "executor": _token(plan.executor_kind),
        "runtime_concurrency": None,
        "platform_max_concurrent_requests": None,
    }
