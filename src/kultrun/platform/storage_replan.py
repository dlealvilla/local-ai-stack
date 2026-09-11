"""Bounded AUTO storage replan. Sequences existing services; does not rank.

Planning still ranks Available Models. ResourceManager still admits.
Storage still owns the 20% ceiling math. This module only retries a
capacity/footprint failure by selecting a real smaller candidate after
fresh recomputation.

The percentage is a candidate-footprint ceiling:

    attempt 0 = 100.000%
    retry 1   = 80.000%
    retry 2   = 64.000%
    retry 3   = 51.200%
    retry 4   = 40.960%
    retry 5   = 32.768%

``next = previous * 0.80``, never ``original - 20`` percentage points, and
never ``requirement *= 0.80``, ``SAFE *= 0.80``, or mutated capacity.

Unresolved automatic capacity is last-resort manual evidence, not a
reduction. MANUAL selection is never converted to AUTO.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.errors import PreconditionFailedError, ValidationError
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import MemoryPlacement, ModelId
from kultrun.planning.contracts import (
    AvailableModelMember,
    AvailableModelView,
    DeploymentPlan,
    ModelSelectionMode,
)
from kultrun.platform.available_models import FunnelPass
from kultrun.platform.deployment_plan import DeploymentPlanningService
from kultrun.platform.model_selection import (
    ModelSelectionOverview,
    ModelSelectionService,
)
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    FoundationSelectionMode,
    InstallationStatus,
    RuntimePolicy,
    RuntimeSupportDescriptor,
)
from kultrun.runtime.resolve import ExecutorCapabilityView
from kultrun.runtime.selection import ROLE_BLOCKED, FoundationSelectionService
from kultrun.storage.characterize import (
    Characterization,
    StorageCharacterizationService,
)
from kultrun.storage.contracts import (
    LowSpaceGuidance,
    StorageCapacityEvidence,
    StorageSanityEvidence,
)
from kultrun.storage.footprint import runtime_provisioning_requirement
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.limits import MAX_STORAGE_REDUCTIONS
from kultrun.storage.reduction import (
    is_footprint_retryable,
    is_manual_capacity_required,
    peak_cap_bytes,
    select_smaller,
)
from kultrun.storage.topology import mount_for_path

FoundationInputs = tuple[
    Sequence[ExecutorCapabilityView],
    Sequence[RuntimeSupportDescriptor],
    RuntimePolicy | None,
]

REDISCOVER_CODES = frozenset(
    {
        "storage_quota_exceeded",
        "storage_space_exhausted",
        "insufficient_safe_storage",
        "runtime_storage_infeasible",
        "storage_low_space",
        "unresolved_safe_capacity",
    }
)


class ReplanOutcome(StrEnum):
    """How the bounded loop finished."""

    SUCCEEDED = "succeeded"
    LOW_SPACE = "low_space"
    MANUAL_BLOCKED = "selected_configuration_no_longer_feasible"
    MANUAL_CAPACITY_REQUIRED = "manual_capacity_required"
    NOT_RETRYABLE = "not_retryable"
    TERMINAL = "terminal_failure"


class ReplanStage(StrEnum):
    """Which materialization the failure belonged to."""

    MODEL = "model"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class ReplanAttempt:
    """One original or reduced attempt. Not a workflow engine."""

    attempt: int
    footprint_ceiling_bytes: int
    prior_candidate: str | None
    prior_footprint_bytes: int | None
    failure_code: str | None
    snapshot_basis: str | None
    candidate: str | None
    candidate_footprint_bytes: int | None
    plan_id: str | None
    plan_basis: str | None
    request_id: str | None
    admission: str | None
    result: str
    considered: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StorageReplanReport:
    """Explainable result of at most original + five reductions."""

    outcome: ReplanOutcome
    stage: ReplanStage
    original_candidate: str
    original_footprint_bytes: int
    attempts: tuple[ReplanAttempt, ...]
    alternatives: tuple[tuple[str, int], ...]
    low_space: tuple[LowSpaceGuidance, ...]
    runtime_reprovision: bool
    message: str

    def payload(self) -> dict[str, object]:
        return {
            "outcome": self.outcome.value,
            "stage": self.stage.value,
            "original_candidate": self.original_candidate,
            "original_footprint_bytes": self.original_footprint_bytes,
            "attempts": [
                {
                    "attempt": item.attempt,
                    "footprint_ceiling_bytes": item.footprint_ceiling_bytes,
                    "prior_candidate": item.prior_candidate,
                    "prior_footprint_bytes": item.prior_footprint_bytes,
                    "failure_code": item.failure_code,
                    "snapshot_basis": item.snapshot_basis,
                    "candidate": item.candidate,
                    "candidate_footprint_bytes": item.candidate_footprint_bytes,
                    "plan_id": item.plan_id,
                    "plan_basis": item.plan_basis,
                    "request_id": item.request_id,
                    "admission": item.admission,
                    "result": item.result,
                    "considered": list(item.considered),
                }
                for item in self.attempts
            ],
            "alternatives": [
                {"identity": ident, "footprint_bytes": peak}
                for ident, peak in self.alternatives
            ],
            "low_space": [
                {
                    "mount_point": item.mount_point,
                    "authorizing_bytes": item.authorizing_available_bytes,
                    "message": item.message,
                    "rediscovery_required": item.rediscovery_required,
                }
                for item in self.low_space
            ],
            "runtime_reprovision": self.runtime_reprovision,
            "message": self.message,
            "max_reductions": MAX_STORAGE_REDUCTIONS,
            "retry_beyond_five": False,
        }


def member_footprint(member: AvailableModelMember) -> int | None:
    """Peak remaining materialization on the model destination pool."""
    value = member.incremental_storage_bytes
    return value if isinstance(value, int) else None


class StorageReplanService:
    """Control-plane loop: rediscover → recompute → ceiling → new plan → admit."""

    def __init__(
        self,
        *,
        characterization: StorageCharacterizationService,
        funnel: Callable[[HostCapabilities], FunnelPass],
        model_selection: ModelSelectionService,
        plans: DeploymentPlanningService,
        resources: ResourceManager,
        capacity: CapacityService,
        stored_sanity: Callable[
            [HostCapabilities], Mapping[str, StorageSanityEvidence]
        ],
        foundation: FoundationSelectionService,
        foundation_inputs: Callable[[HostCapabilities], FoundationInputs],
        index: StorageEvidenceIndex | None,
        state_root: Path,
        allow_empirical: bool,
    ) -> None:
        self._characterization = characterization
        self._funnel = funnel
        self._models = model_selection
        self._plans = plans
        self._resources = resources
        self._capacity = capacity
        self._stored_sanity = stored_sanity
        self._foundation = foundation
        self._foundation_inputs = foundation_inputs
        self._index = index
        self._state_root = Path(state_root)
        self._allow_empirical = allow_empirical

    def handle(
        self,
        host: HostCapabilities,
        *,
        failure_code: str,
        original_identity: str,
        original_footprint: int,
        stage: ReplanStage = ReplanStage.MODEL,
    ) -> StorageReplanReport:
        """Retry at most five smaller real candidates. Never a sixth."""
        attempts = [
            ReplanAttempt(
                attempt=0,
                footprint_ceiling_bytes=original_footprint,
                prior_candidate=None,
                prior_footprint_bytes=None,
                failure_code=failure_code,
                snapshot_basis=None,
                candidate=original_identity,
                candidate_footprint_bytes=original_footprint,
                plan_id=None,
                plan_basis=None,
                request_id=None,
                admission=None,
                result="failed",
            )
        ]
        rediscover = failure_code in REDISCOVER_CODES
        characterized = self._characterize(host, rediscover=rediscover)
        if failure_code == "storage_low_space" or (
            characterized is not None and characterized.low_space
        ):
            return _report(
                ReplanOutcome.LOW_SPACE,
                stage,
                original_identity,
                original_footprint,
                attempts,
                (),
                characterized.low_space if characterized is not None else (),
                False,
                "authorizing storage is below the low-space threshold; "
                "clear space, then rediscover before any 20% reduction",
            )
        if is_manual_capacity_required(failure_code) and _capacity_unresolved(
            characterized
        ):
            return _report(
                ReplanOutcome.MANUAL_CAPACITY_REQUIRED,
                stage,
                original_identity,
                original_footprint,
                attempts,
                (),
                (),
                False,
                "automatic storage capacity is unresolved; "
                "administrator capacity may be supplied as last resort",
            )
        if not is_footprint_retryable(failure_code):
            return _report(
                ReplanOutcome.NOT_RETRYABLE,
                stage,
                original_identity,
                original_footprint,
                attempts,
                (),
                (),
                False,
                f"failure {failure_code} is not a footprint-retry trigger",
            )
        retain_runtime = self._retain_runtime(host)
        if stage is ReplanStage.RUNTIME:
            return self._replan_runtime(
                host,
                original_identity=original_identity,
                original_footprint=original_footprint,
                attempts=attempts,
                retain_runtime=retain_runtime,
            )
        return self._replan_model(
            host,
            original_identity=original_identity,
            original_footprint=original_footprint,
            attempts=attempts,
            retain_runtime=retain_runtime,
        )

    def _characterize(
        self, host: HostCapabilities, *, rediscover: bool
    ) -> Characterization | None:
        if not rediscover:
            return None
        characterized = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=self._allow_empirical,
        )
        if self._index is not None:
            self._index.record_expensive(
                characterized.evidence, characterized.empirical_evidence
            )
        return characterized

    def _retain_runtime(self, host: HostCapabilities) -> bool:
        try:
            executors, descriptors, policy = self._foundation_inputs(host)
            evidence = self._index.for_host(host) if self._index is not None else None
            overview = self._foundation.view(
                host,
                executors,
                descriptors,
                policy,
                storage_evidence=evidence,
                require_storage=True,
            )
        except (PreconditionFailedError, ValidationError, TypeError, AttributeError):
            return False
        selected = overview.selection.selected_candidate_id
        if not isinstance(selected, str):
            return False
        classified = next(
            (item for item in overview.candidates if item.candidate_id == selected),
            None,
        )
        if classified is not None and classified.role == ROLE_BLOCKED:
            return False
        installation = self._foundation.installation_for(selected)
        if installation is None:
            return False
        return installation.status is InstallationStatus.INSTALLED

    def _replan_model(
        self,
        host: HostCapabilities,
        *,
        original_identity: str,
        original_footprint: int,
        attempts: list[ReplanAttempt],
        retain_runtime: bool,
    ) -> StorageReplanReport:
        stored = self._models.stored(host)
        mode = stored.selection_mode if stored is not None else ModelSelectionMode.AUTO
        if mode is ModelSelectionMode.MANUAL:
            funnel = self._funnel(host)
            cap = peak_cap_bytes(original_footprint, 1)
            return _report(
                ReplanOutcome.MANUAL_BLOCKED,
                ReplanStage.MODEL,
                original_identity,
                original_footprint,
                attempts,
                _model_alternatives(funnel, cap),
                (),
                not retain_runtime,
                "SELECTED_CONFIGURATION_NO_LONGER_FEASIBLE; "
                "MANUAL choice was not replaced",
            )
        prior = original_identity
        prior_peak = original_footprint
        last_funnel: FunnelPass | None = None
        for reduction in range(1, MAX_STORAGE_REDUCTIONS + 1):
            cap = peak_cap_bytes(original_footprint, reduction)
            last_funnel = self._funnel(host)
            members = _members_within(last_funnel.available, cap)
            considered = tuple(item.model_id for item in members)
            chosen = select_smaller(
                members,
                peak_of=_peak_or_zero,
                original_peak=original_footprint,
                reduction=reduction,
            )
            if chosen is None or member_footprint(chosen) is None:
                attempts.append(
                    ReplanAttempt(
                        attempt=reduction,
                        footprint_ceiling_bytes=cap,
                        prior_candidate=prior,
                        prior_footprint_bytes=prior_peak,
                        failure_code=None,
                        snapshot_basis=_snapshot(last_funnel),
                        candidate=None,
                        candidate_footprint_bytes=None,
                        plan_id=None,
                        plan_basis=None,
                        request_id=None,
                        admission=None,
                        result="no_candidate",
                        considered=considered,
                    )
                )
                continue
            filtered = _filter_funnel(last_funnel, {item.model_id for item in members})
            overview = self._models.select_auto(
                host,
                filtered.eligible,
                filtered.envelope,
                filtered.assessments,
                filtered.available,
            )
            auto_id = overview.selection.selected_model_id
            if isinstance(auto_id, str):
                auto_member = next(
                    (item for item in members if item.model_id == auto_id), None
                )
                if auto_member is not None:
                    chosen = auto_member
            plan = self._refresh_plan(host, filtered, overview)
            request_id, admission = self._admit_model(host, chosen, plan)
            admitted = admission == AdmissionVerdict.ADMITTED.value
            attempts.append(
                ReplanAttempt(
                    attempt=reduction,
                    footprint_ceiling_bytes=cap,
                    prior_candidate=prior,
                    prior_footprint_bytes=prior_peak,
                    failure_code=None if admitted else admission,
                    snapshot_basis=_snapshot(last_funnel),
                    candidate=chosen.model_id,
                    candidate_footprint_bytes=member_footprint(chosen),
                    plan_id=_plan_token(plan, "plan_id"),
                    plan_basis=_plan_token(plan, "plan_basis"),
                    request_id=request_id,
                    admission=admission,
                    result="admitted" if admitted else "rejected",
                    considered=considered,
                )
            )
            if admitted:
                return _report(
                    ReplanOutcome.SUCCEEDED,
                    ReplanStage.MODEL,
                    original_identity,
                    original_footprint,
                    attempts,
                    _model_alternatives(last_funnel, cap),
                    (),
                    not retain_runtime,
                    "selected a smaller available model under the footprint ceiling",
                )
            prior = chosen.model_id
            prior_peak = member_footprint(chosen) or prior_peak
        assert last_funnel is not None
        return _report(
            ReplanOutcome.TERMINAL,
            ReplanStage.MODEL,
            original_identity,
            original_footprint,
            attempts,
            _model_alternatives(
                last_funnel, peak_cap_bytes(original_footprint, MAX_STORAGE_REDUCTIONS)
            ),
            (),
            not retain_runtime,
            "five reductions failed to admit a smaller deployment; "
            "storage remediation is required",
        )

    def _replan_runtime(
        self,
        host: HostCapabilities,
        *,
        original_identity: str,
        original_footprint: int,
        attempts: list[ReplanAttempt],
        retain_runtime: bool,
    ) -> StorageReplanReport:
        executors, descriptors, policy = self._foundation_inputs(host)
        stored = self._foundation.stored(host)
        if (
            stored is not None
            and stored.selection_mode is FoundationSelectionMode.MANUAL
        ):
            return _report(
                ReplanOutcome.MANUAL_BLOCKED,
                ReplanStage.RUNTIME,
                original_identity,
                original_footprint,
                attempts,
                (),
                (),
                False,
                "SELECTED_CONFIGURATION_NO_LONGER_FEASIBLE; "
                "MANUAL foundation was not replaced",
            )
        evidence = self._index.for_host(host) if self._index is not None else {}
        mount = mount_for_path(self._state_root / "runtimes", host)
        requirement = runtime_provisioning_requirement(
            mount_point=mount if mount is not None else NOT_PROVIDED
        )
        peak = (
            requirement.required_peak_free_bytes
            if isinstance(requirement.required_peak_free_bytes, int)
            else original_footprint
        )
        for reduction in range(1, MAX_STORAGE_REDUCTIONS + 1):
            cap = peak_cap_bytes(original_footprint, reduction)
            if peak > cap:
                attempts.append(
                    ReplanAttempt(
                        attempt=reduction,
                        footprint_ceiling_bytes=cap,
                        prior_candidate=original_identity,
                        prior_footprint_bytes=original_footprint,
                        failure_code="runtime_storage_infeasible",
                        snapshot_basis=None,
                        candidate=None,
                        candidate_footprint_bytes=peak,
                        plan_id=None,
                        plan_basis=None,
                        request_id=None,
                        admission=None,
                        result="no_candidate",
                    )
                )
                continue
            overview = self._foundation.select_auto(
                host,
                executors,
                descriptors,
                policy,
                storage_evidence=evidence,
                require_storage=True,
            )
            selected = overview.selection.selected_candidate_id
            identity = selected if isinstance(selected, str) else None
            attempts.append(
                ReplanAttempt(
                    attempt=reduction,
                    footprint_ceiling_bytes=cap,
                    prior_candidate=original_identity,
                    prior_footprint_bytes=original_footprint,
                    failure_code=None,
                    snapshot_basis=None,
                    candidate=identity,
                    candidate_footprint_bytes=peak,
                    plan_id=None,
                    plan_basis=None,
                    request_id=None,
                    admission=None,
                    result="selected" if identity else "no_candidate",
                )
            )
            if identity is not None:
                return _report(
                    ReplanOutcome.SUCCEEDED,
                    ReplanStage.RUNTIME,
                    original_identity,
                    original_footprint,
                    attempts,
                    (),
                    (),
                    True,
                    "selected a storage-feasible foundation under the ceiling",
                )
        return _report(
            ReplanOutcome.TERMINAL,
            ReplanStage.RUNTIME,
            original_identity,
            original_footprint,
            attempts,
            (),
            (),
            not retain_runtime,
            "no smaller supported runtime fits the reduced ceiling",
        )

    def _refresh_plan(
        self,
        host: HostCapabilities,
        funnel: FunnelPass,
        overview: ModelSelectionOverview,
    ) -> DeploymentPlan | None:
        foundation = self._foundation.stored(host)
        refreshed = self._plans.refresh(
            host,
            funnel.eligible,
            funnel.envelope,
            funnel.assessments,
            overview,
            foundation,
        )
        return refreshed.plan

    def _admit_model(
        self,
        host: HostCapabilities,
        member: AvailableModelMember,
        plan: DeploymentPlan | None,
    ) -> tuple[str | None, str]:
        peak = member_footprint(member)
        if peak is None:
            return None, "unresolved"
        mount = mount_for_path(self._state_root / "models", host)
        live = self._capacity.compute(
            host,
            dict(self._stored_sanity(host)),
            storage_evidence=_storage(self._index, host),
        )
        fingerprint = (
            str(plan.plan_basis)
            if plan is not None and is_resolved(plan.plan_basis)
            else f"replan:{member.model_id}"
        )
        request = ResourceRequest(
            request_id=RequestId.generate(),
            host_id=host.host_id,
            plan_fingerprint=fingerprint,
            placement=MemoryPlacement.CPU_ONLY,
            ram_bytes=_maybe_int(member.required_ram_bytes),
            accelerator_bytes=_maybe_int(member.required_vram_bytes),
            unified_bytes=NOT_PROVIDED,
            incremental_storage_bytes=peak,
            storage_pool_mount=mount if isinstance(mount, str) else NOT_PROVIDED,
            workload_type=WorkloadType.MODEL_ACQUISITION,
            model_id=_model_id(member.model_id),
        )
        decision = self._resources.admit(request, live)
        if decision.reservation is not None:
            self._resources.release(decision.reservation.reservation_id)
        return request.request_id.value, decision.verdict.value


def _report(
    outcome: ReplanOutcome,
    stage: ReplanStage,
    original: str,
    footprint: int,
    attempts: list[ReplanAttempt],
    alternatives: tuple[tuple[str, int], ...],
    low_space: tuple[LowSpaceGuidance, ...],
    reprovision: bool,
    message: str,
) -> StorageReplanReport:
    return StorageReplanReport(
        outcome=outcome,
        stage=stage,
        original_candidate=original,
        original_footprint_bytes=footprint,
        attempts=tuple(attempts),
        alternatives=alternatives,
        low_space=low_space,
        runtime_reprovision=reprovision,
        message=message,
    )


def _maybe_int(value: object) -> Maybe[int]:
    return value if isinstance(value, int) else NOT_PROVIDED


def _model_id(value: str) -> ModelId | None:
    try:
        return ModelId.parse(value)
    except (ValueError, ValidationError):
        return None


def _storage(
    index: StorageEvidenceIndex | None, host: HostCapabilities
) -> dict[str, StorageCapacityEvidence]:
    if index is None:
        return {}
    return index.for_host(host)


def _capacity_unresolved(characterized: Characterization | None) -> bool:
    if characterized is None or not characterized.evidence:
        return True
    return not any(
        is_resolved(item.authorizing_available_bytes)
        for item in characterized.evidence.values()
    )


def _snapshot(funnel: FunnelPass) -> str | None:
    basis = funnel.available.snapshot_basis
    return basis or None


def _plan_token(plan: DeploymentPlan | None, field: str) -> str | None:
    if plan is None:
        return None
    value = getattr(plan, field)
    return value if isinstance(value, str) else None


def _peak_or_zero(member: AvailableModelMember) -> int:
    return member_footprint(member) or 0


def _members_within(
    view: AvailableModelView, ceiling: int
) -> tuple[AvailableModelMember, ...]:
    kept: list[AvailableModelMember] = []
    for item in view.members:
        peak = member_footprint(item)
        if peak is not None and peak <= ceiling:
            kept.append(item)
    return tuple(kept)


def _model_alternatives(
    funnel: FunnelPass, ceiling: int
) -> tuple[tuple[str, int], ...]:
    rows: list[tuple[str, int]] = []
    for item in _members_within(funnel.available, ceiling):
        peak = member_footprint(item)
        if peak is not None:
            rows.append((item.model_id, peak))
    return tuple(rows)


def _filter_funnel(funnel: FunnelPass, allowed: set[str]) -> FunnelPass:
    members = tuple(
        item for item in funnel.available.members if item.model_id in allowed
    )
    available = replace(funnel.available, members=members, available_count=len(members))
    assessments = tuple(item for item in funnel.assessments if item.model_id in allowed)
    return FunnelPass(
        eligible=funnel.eligible,
        envelope=funnel.envelope,
        capacity=funnel.capacity,
        assessments=assessments,
        available=available,
        discovery=funnel.discovery,
        estimated_feasible=funnel.estimated_feasible,
        validation=funnel.validation,
    )
