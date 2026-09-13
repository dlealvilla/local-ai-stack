"""Staged Available Models funnel. Recommendation is a later consumer.

Composition-owned. Discovery, eligibility, cheap weight evidence, and
deep estimation stay behind existing ports. This service produces the
authoritative AvailableModelView, persists one current record per host,
and never ranks.
"""

from __future__ import annotations

import fcntl
import hashlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    CheapSizeClass,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
    WeightEvidenceSource,
    WeightFootprintEvidence,
)
from kultrun.model.discovery import (
    DiscoveryQuery,
    DiscoveryResult,
    FunnelQuery,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.ports import (
    ModelDiscoverySource,
    ModelRequirementEstimator,
    WeightEvidenceProvider,
)
from kultrun.planning.contracts import (
    AvailableModelExclusion,
    AvailableModelMember,
    AvailableModelView,
    AvailableModelViewId,
    AvailableViewStatus,
    CompatibilityVerdict,
    DeploymentCapacity,
    FunnelStage,
    SelectionPolicy,
)
from kultrun.planning.evaluate import cheap_weight_fit, evaluate
from kultrun.platform.observation import (
    OperationalJournal,
    OperationalOutcome,
    OperationalStage,
    attr,
)
from kultrun.platform.requirement import (
    RequirementAssessment,
    RequirementStatus,
    assess_entry,
    capacity_verdict,
    incremental_storage_demand,
    is_selectable,
)
from kultrun.platform.runtime_memory import (
    CALIBRATED_INSUFFICIENT_VRAM,
    VALIDATION_UNRESOLVED,
    AppliedCalibration,
    CalibrationOutcome,
    CapacityRefresh,
    EstimatedFeasibleCandidate,
    RuntimeMemoryCalibrationService,
    requires_runtime_validation,
)
from kultrun.runtime.contracts import (
    EligibleModelView,
    EligibleViewStatus,
    RuntimeEligibilityStatus,
    RuntimeEligibleModelCandidate,
    RuntimeValidationStatus,
)

AVAILABLE_SCHEMA = "planning.available_model_view@1"
LOCK_NAME = "available.lock"
POLICY_BLOCKED = "policy_blocked"
CONTEXT_UNSUPPORTED = "context_unsupported"
METADATA_UNRESOLVED = "required_model_metadata_missing"
WEIGHTS_EXCEED = "weights_exceed_available_placement"


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


class AvailableModelsLock:
    """One lock for Available Models persistence. Not admission."""

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


def store_key(host_id: str) -> str:
    """One current Available Models record per host."""
    digest = hashlib.sha256(f"{AVAILABLE_SCHEMA}|host|{host_id}".encode()).hexdigest()
    return f"amv_{digest[:16]}"


def fingerprint_view_id(view_basis: str) -> AvailableModelViewId:
    """Identity of this availability basis. Not a recommendation."""
    digest = hashlib.sha256(f"{AVAILABLE_SCHEMA}|{view_basis}".encode()).hexdigest()
    return AvailableModelViewId(f"amv_{digest[:16]}")


def view_basis(
    *,
    host_fingerprint: str,
    eligible_view_id: str,
    foundation: str,
    profile_id: str,
    snapshot_basis: str,
    requested_context: str,
    policy_version: str,
    discovery: str,
    members: Sequence[AvailableModelMember],
) -> str:
    """Fingerprint of material availability inputs. Recommendation excluded."""
    member_part = ",".join(
        f"{item.model_id}:{item.requirement_basis}:{item.source_revision}"
        for item in sorted(members, key=lambda item: item.model_id)
    )
    material = "|".join(
        (
            AVAILABLE_SCHEMA,
            host_fingerprint,
            eligible_view_id,
            foundation,
            profile_id,
            snapshot_basis,
            requested_context,
            policy_version,
            discovery,
            member_part,
        )
    )
    return hashlib.sha256(material.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class FunnelPass:
    """One Available Models evaluation. Selector input is ``available``."""

    eligible: EligibleModelView
    envelope: CapacityEnvelope
    capacity: DeploymentCapacity
    assessments: tuple[RequirementAssessment, ...]
    available: AvailableModelView
    discovery: DiscoveryResult
    estimated_feasible: tuple[EstimatedFeasibleCandidate, ...] = ()
    validation: CalibrationOutcome | None = None


class _CountingEstimator:
    """Counts deep estimates. Does not choose a provider."""

    def __init__(self, inner: ModelRequirementEstimator) -> None:
        self.inner = inner
        self.calls = 0

    @property
    def identity(self) -> Name:
        return self.inner.identity

    @property
    def version(self) -> str:
        return self.inner.version

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        self.calls += 1
        return self.inner.estimate(request)


class AvailableModelsService:
    """Produce and persist Available Models. Does not recommend or select."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        models: ModelCatalogue,
        estimator: ModelRequirementEstimator,
        policy: SelectionPolicy,
        lock: AvailableModelsLock,
        *,
        weights: WeightEvidenceProvider | None = None,
        structural: WeightEvidenceProvider | None = None,
        inventory: ModelInventory | None = None,
        calibrator: RuntimeMemoryCalibrationService | None = None,
        refresh_capacity: CapacityRefresh | None = None,
        journal: OperationalJournal | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._models = models
        self._estimator = estimator
        self._policy = policy
        self._lock = lock
        self._weights = weights
        self._structural = structural
        self._inventory = inventory
        self._calibrator = calibrator
        self._refresh_capacity = refresh_capacity
        self._journal = journal

    def stored(self, host: HostCapabilities) -> AvailableModelView | None:
        """Persisted view, if any. Does not recompute."""
        return self._store.get(AvailableModelView, store_key(host.host_id.value))

    def _record_models(
        self, host: HostCapabilities, view: AvailableModelView
    ) -> None:
        if self._journal is None:
            return
        for member in view.members:
            self._journal.emit(
                host_id=host.host_id,
                stage=OperationalStage.MODEL,
                event_type="model.available",
                summary=f"{member.logical_name} ELIGIBLE",
                outcome=OperationalOutcome.PASS,
                attributes=(
                    attr("model", member.logical_name),
                    attr("model_id", member.model_id),
                ),
            )
        for item in view.exclusions:
            self._journal.emit(
                host_id=host.host_id,
                stage=OperationalStage.MODEL,
                event_type="model.blocked",
                summary=f"{item.logical_name} BLOCKED: {item.reason}",
                outcome=OperationalOutcome.BLOCKED,
                reason_code=item.reason,
                attributes=(attr("model", item.logical_name),),
            )

    def evaluate(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        *,
        persist: bool = False,
        query: FunnelQuery | None = None,
    ) -> FunnelPass:
        """Run the funnel. GET callers pass persist=False."""
        with self._lock.hold():
            result = self._evaluate(
                host, eligible, envelope, capacity, query, persist=persist
            )
            if persist:
                self._store.put(store_key(host.host_id.value), result.available)
                self._record_models(host, result.available)
            return result

    def _evaluate(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        query: FunnelQuery | None,
        *,
        persist: bool,
    ) -> FunnelPass:
        funnel = query or FunnelQuery()
        discovery = _discover(self._models, funnel.discovery)
        universe_entries = _unique((*self._models.entries(), *self._models.extras()))
        discovered_entries = _unique(
            (*discovery.catalog_entries, *self._models.extras())
        )
        discovered_ids = {entry.metadata.model_id.value for entry in discovered_entries}
        catalog_refs = {entry.metadata.source_ref for entry in discovered_entries}
        exclusions: list[AvailableModelExclusion] = []
        compatible: list[ModelCatalogEntry] = []
        for entry in universe_entries:
            if entry.metadata.model_id.value not in discovered_ids:
                exclusions.append(
                    _exclusion(
                        entry,
                        FunnelStage.DISCOVERY,
                        "remote_not_discovered",
                        ("not present after source discovery filter",),
                    )
                )
                continue
            extra = _extra_compatibility(entry, funnel)
            if extra is not None:
                exclusions.append(extra)
                continue
            candidate = _candidate(eligible, entry.metadata.model_id.value)
            if candidate is None:
                exclusions.append(
                    _exclusion(
                        entry,
                        FunnelStage.COMPATIBILITY,
                        METADATA_UNRESOLVED,
                        ("eligibility candidate missing",),
                    )
                )
                continue
            if candidate.status is RuntimeEligibilityStatus.BLOCKED:
                exclusions.append(
                    _exclusion(
                        entry,
                        FunnelStage.COMPATIBILITY,
                        _reason_code(candidate),
                        candidate.reasons,
                    )
                )
                continue
            if candidate.status is RuntimeEligibilityStatus.UNRESOLVED:
                exclusions.append(
                    _exclusion(
                        entry,
                        FunnelStage.COMPATIBILITY,
                        _reason_code(candidate) or METADATA_UNRESOLVED,
                        candidate.reasons,
                    )
                )
                continue
            compatible.append(entry)
        for hit in discovery.remote_hits:
            if hit.source_ref in catalog_refs:
                continue
            exclusions.append(
                AvailableModelExclusion(
                    model_id=hit.source_ref,
                    logical_name=hit.source_ref,
                    stage=FunnelStage.COMPATIBILITY,
                    reason=METADATA_UNRESOLVED,
                    notes=("remote hit has no catalog metadata",),
                )
            )

        deep_entries: list[tuple[ModelCatalogEntry, WeightFootprintEvidence]] = []
        cheap_reject = 0
        for entry in compatible:
            evidence = _weight_evidence(
                entry,
                self._weights,
                self._structural,
                available_vram_bytes=capacity.available_vram_bytes,
            )
            decision = cheap_weight_fit(
                evidence,
                capacity,
                gpu_resident=not self._policy.allow_offload,
            )
            if decision.classification is CheapSizeClass.PROVEN_IMPOSSIBLE:
                cheap_reject += 1
                exclusions.append(
                    _exclusion(
                        entry,
                        FunnelStage.CHEAP_SIZE_BOUND,
                        decision.reason or WEIGHTS_EXCEED,
                        ("cheap factual weight bound",),
                        weight_lower_bound_bytes=evidence.serialized_weight_tensor_bytes,
                        allowed_placement_bytes=decision.allowed_placement_bytes,
                        weight_evidence_source=evidence.evidence_source.value,
                    )
                )
                continue
            deep_entries.append((entry, evidence))

        counter = _CountingEstimator(self._estimator)
        assessments: list[RequirementAssessment] = []
        estimated: list[EstimatedFeasibleCandidate] = []
        deep_ids = {entry.metadata.model_id.value for entry, _ in deep_entries}
        for entry in universe_entries:
            ident = entry.metadata.model_id.value
            if ident in deep_ids:
                continue
            assessments.append(
                _unestimated_row(
                    eligible,
                    entry,
                    next(
                        (item for item in exclusions if item.model_id == ident),
                        None,
                    ),
                )
            )

        for entry, evidence in deep_entries:
            row = assess_entry(
                eligible,
                entry,
                envelope,
                counter,
                self._policy,
                capacity=capacity,
                inventory=self._inventory,
            )
            assessments.append(row)
            if is_selectable(row) and row.requirement is not None:
                estimated.append(
                    EstimatedFeasibleCandidate(
                        model_id=row.model_id,
                        logical_name=row.logical_name,
                        entry=entry,
                        requirement=row.requirement,
                        evidence=evidence,
                    )
                )
            else:
                exclusions.append(_deep_exclusion(row, evidence, capacity))

        validation: CalibrationOutcome | None = None
        applied_by_id: dict[str, AppliedCalibration] = {}
        if requires_runtime_validation(eligible.runtime):
            estimated, assessments, exclusions, envelope, capacity, validation = (
                self._calibrate_vllm(
                    host,
                    eligible,
                    envelope,
                    capacity,
                    estimated,
                    assessments,
                    exclusions,
                    persist=persist,
                )
            )
            if validation is not None:
                applied_by_id = {item.model_id: item for item in validation.applied}

        members: list[AvailableModelMember] = []
        for feasible in estimated:
            applied = applied_by_id.get(feasible.model_id)
            if requires_runtime_validation(eligible.runtime):
                if (
                    applied is None
                    or applied.status is RuntimeValidationStatus.UNRESOLVED
                ):
                    exclusions.append(
                        _calibration_exclusion(
                            feasible,
                            capacity,
                            VALIDATION_UNRESOLVED,
                            applied.notes
                            if applied is not None
                            else ("runtime validation unresolved",),
                        )
                    )
                    continue
                row = _reassess(
                    eligible,
                    feasible,
                    applied.requirement,
                    capacity,
                    self._policy,
                    self._inventory,
                )
                assessments = [
                    row if item.model_id == row.model_id else item
                    for item in assessments
                ]
                if is_selectable(row):
                    members.append(
                        _member(
                            row,
                            feasible.entry,
                            feasible.evidence,
                            capacity,
                            applied,
                        )
                    )
                else:
                    reason = CALIBRATED_INSUFFICIENT_VRAM
                    if row.capacity_verdict not in {
                        "infeasible_vram",
                        "infeasible",
                    }:
                        reason = row.capacity_verdict
                    exclusions.append(
                        _calibration_exclusion(
                            feasible,
                            capacity,
                            reason,
                            row.reasons,
                            required_vram_bytes=_optional_int(
                                row.required_vram_bytes
                            ),
                        )
                    )
            else:
                assessed = next(
                    (
                        item
                        for item in assessments
                        if item.model_id == feasible.model_id
                    ),
                    None,
                )
                if assessed is not None:
                    members.append(
                        _member(
                            assessed,
                            feasible.entry,
                            feasible.evidence,
                            capacity,
                        )
                    )

        snapshot = (
            capacity.snapshot_basis
            if is_resolved(capacity.snapshot_basis)
            and isinstance(capacity.snapshot_basis, str)
            else ""
        )
        sorted_members = tuple(sorted(members, key=lambda item: item.logical_name))
        sorted_exclusions = tuple(
            sorted(exclusions, key=lambda item: (item.stage.value, item.logical_name))
        )
        context: Maybe[int] = (
            funnel.requested_context_tokens
            if funnel.requested_context_tokens is not None
            else NOT_PROVIDED
        )
        foundation = _token(eligible.selected_candidate_id) or ""
        profile = _token(eligible.profile_id) or ""
        basis = view_basis(
            host_fingerprint=envelope.host_fingerprint,
            eligible_view_id=eligible.view_id.value,
            foundation=foundation,
            profile_id=profile,
            snapshot_basis=snapshot,
            requested_context=str(funnel.requested_context_tokens or ""),
            policy_version=self._policy.policy_version,
            discovery=_discovery_token(discovery),
            members=sorted_members,
        )
        status = _view_status(eligible)
        view = AvailableModelView(
            view_id=fingerprint_view_id(basis),
            host_id=host.host_id,
            status=status,
            evaluated_at=self._clock.now(),
            view_basis=basis,
            snapshot_basis=snapshot,
            host_fingerprint=envelope.host_fingerprint,
            eligible_view_id=eligible.view_id.value,
            runtime=eligible.runtime,
            runtime_version=eligible.runtime_version,
            requested_context_tokens=context,
            universe_count=max(discovery.universe_count, len(universe_entries)),
            discovered_count=max(discovery.discovered_count, len(discovered_entries)),
            compatibility_count=len(compatible),
            cheap_reject_count=cheap_reject,
            deep_analyzed_count=len(deep_entries),
            available_count=len(sorted_members),
            excluded_count=len(sorted_exclusions),
            estimator_invocations=counter.calls,
            members=sorted_members,
            exclusions=sorted_exclusions,
            policy_version=self._policy.policy_version,
            estimated_feasible_count=len(estimated),
            validation_class_count=(
                len(validation.classes) if validation is not None else 0
            ),
            probe_invocations=(
                validation.probe_invocations if validation is not None else 0
            ),
        )
        return FunnelPass(
            eligible=eligible,
            envelope=envelope,
            capacity=capacity,
            assessments=tuple(assessments),
            available=view,
            discovery=discovery,
            estimated_feasible=tuple(estimated),
            validation=validation,
        )

    def _calibrate_vllm(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        estimated: list[EstimatedFeasibleCandidate],
        assessments: list[RequirementAssessment],
        exclusions: list[AvailableModelExclusion],
        *,
        persist: bool,
    ) -> tuple[
        list[EstimatedFeasibleCandidate],
        list[RequirementAssessment],
        list[AvailableModelExclusion],
        CapacityEnvelope,
        DeploymentCapacity,
        CalibrationOutcome | None,
    ]:
        if self._calibrator is None:
            missing = CalibrationOutcome(
                applied=tuple(
                    AppliedCalibration(
                        model_id=item.model_id,
                        requirement=item.requirement,
                        status=RuntimeValidationStatus.UNRESOLVED,
                        profile_id=None,
                        sentinel_model_id=item.model_id,
                        class_key="unresolved",
                        base_model_bytes=0,
                        runtime_extra_bytes=0,
                        kv_bytes=0,
                        safety_bytes=0,
                        unexpected_lowering=False,
                        notes=("runtime memory calibrator not configured",),
                    )
                    for item in estimated
                ),
                classes=(),
                probe_order=(),
                probe_invocations=0,
            )
            return estimated, assessments, exclusions, envelope, capacity, missing
        current_estimated = estimated
        current_envelope = envelope
        current_capacity = capacity
        outcome: CalibrationOutcome | None = None
        for attempt in range(2):
            outcome = self._calibrator.calibrate(
                host=host,
                eligible=eligible,
                envelope=current_envelope,
                capacity=current_capacity,
                estimated=current_estimated,
                allow_live_probe=persist,
                persist_profiles=persist,
            )
            if not outcome.capacity_stale:
                break
            if self._refresh_capacity is None or attempt == 1:
                break
            current_envelope, current_capacity = self._refresh_capacity(host)
            current_estimated = []
            rebuilt: list[RequirementAssessment] = [
                item
                for item in assessments
                if item.model_id not in {row.model_id for row in estimated}
            ]
            for candidate in estimated:
                row = _reassess(
                    eligible,
                    candidate,
                    candidate.requirement,
                    current_capacity,
                    self._policy,
                    self._inventory,
                )
                rebuilt.append(row)
                if is_selectable(row) and row.requirement is not None:
                    current_estimated.append(
                        replace(candidate, requirement=row.requirement)
                    )
                else:
                    exclusions.append(
                        _deep_exclusion(row, candidate.evidence, current_capacity)
                    )
            assessments = rebuilt
        if persist and self._refresh_capacity is not None:
            current_envelope, current_capacity = self._refresh_capacity(host)
        assert outcome is not None
        return (
            current_estimated,
            assessments,
            exclusions,
            current_envelope,
            current_capacity,
            outcome,
        )


def _discover(models: ModelCatalogue, query: DiscoveryQuery) -> DiscoveryResult:
    source = models.source
    if isinstance(source, ModelDiscoverySource):
        return source.discover(query)
    catalog = models.entries()
    return DiscoveryResult(
        universe_count=len(catalog),
        discovered_count=len(catalog),
        criteria=query,
        catalog_entries=catalog,
        live=False,
        notes=("source has no discovery listing; catalog retained",),
    )


def _unique(entries: Sequence[ModelCatalogEntry]) -> tuple[ModelCatalogEntry, ...]:
    seen: set[str] = set()
    rows: list[ModelCatalogEntry] = []
    for entry in entries:
        ident = entry.metadata.model_id.value
        if ident in seen:
            continue
        seen.add(ident)
        rows.append(entry)
    return tuple(rows)


def _candidate(
    view: EligibleModelView, model_id: str
) -> RuntimeEligibleModelCandidate | None:
    for item in view.candidates:
        if item.model_id == model_id:
            return item
    return None


def _token(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _reason_code(candidate: RuntimeEligibleModelCandidate) -> str:
    if candidate.reason_codes:
        return candidate.reason_codes[0].value
    return "unsupported_runtime"


def _extra_compatibility(
    entry: ModelCatalogEntry, funnel: FunnelQuery
) -> AvailableModelExclusion | None:
    meta = entry.metadata
    if funnel.allow_commercially_restricted is False:
        restricted = meta.commercial_use_restricted
        if restricted is True:
            return _exclusion(
                entry,
                FunnelStage.COMPATIBILITY,
                POLICY_BLOCKED,
                ("commercial use restricted by policy",),
            )
    requested = funnel.requested_context_tokens
    advertised = meta.context_length_tokens
    if requested is not None and isinstance(advertised, int) and requested > advertised:
        return _exclusion(
            entry,
            FunnelStage.COMPATIBILITY,
            CONTEXT_UNSUPPORTED,
            (f"requested context {requested} exceeds advertised {advertised}",),
        )
    return None


def _weight_evidence(
    entry: ModelCatalogEntry,
    weights: WeightEvidenceProvider | None,
    structural: WeightEvidenceProvider | None,
    *,
    available_vram_bytes: object = NOT_PROVIDED,
) -> WeightFootprintEvidence:
    if weights is None:
        return WeightFootprintEvidence(
            model_id=entry.metadata.model_id,
            source_ref=entry.metadata.source_ref,
            evidence_source=WeightEvidenceSource.UNAVAILABLE,
            serialized_weight_tensor_bytes=NOT_PROVIDED,
            confidence=Confidence.UNKNOWN,
            provenance=("weight evidence provider not configured",),
            source_revision=entry.metadata.source_revision,
            provider_failure="metadata_unavailable",
        )
    evidence = weights.footprint(entry)
    if is_resolved(evidence.serialized_weight_tensor_bytes):
        return evidence
    if structural is None:
        return evidence
    bound = structural
    placer = getattr(structural, "for_placement", None)
    if callable(placer):
        bound = placer(available_vram_bytes)
    extra = bound.footprint(entry)
    if is_resolved(extra.serialized_weight_tensor_bytes):
        return extra
    return evidence


def _exclusion(
    entry: ModelCatalogEntry,
    stage: FunnelStage,
    reason: str,
    notes: tuple[str, ...],
    *,
    weight_lower_bound_bytes: object = NOT_PROVIDED,
    allowed_placement_bytes: object = NOT_PROVIDED,
    required_vram_bytes: object = NOT_PROVIDED,
    available_vram_bytes: object = NOT_PROVIDED,
    weight_evidence_source: object = NOT_PROVIDED,
) -> AvailableModelExclusion:
    return AvailableModelExclusion(
        model_id=entry.metadata.model_id.value,
        logical_name=entry.metadata.logical_name.value,
        stage=stage,
        reason=reason,
        notes=notes,
        weight_lower_bound_bytes=weight_lower_bound_bytes
        if isinstance(weight_lower_bound_bytes, int)
        else NOT_PROVIDED,
        allowed_placement_bytes=allowed_placement_bytes
        if isinstance(allowed_placement_bytes, int)
        else NOT_PROVIDED,
        required_vram_bytes=required_vram_bytes
        if isinstance(required_vram_bytes, int)
        else NOT_PROVIDED,
        available_vram_bytes=available_vram_bytes
        if isinstance(available_vram_bytes, int)
        else NOT_PROVIDED,
        weight_evidence_source=weight_evidence_source
        if isinstance(weight_evidence_source, str)
        else NOT_PROVIDED,
    )


def _reassess(
    view: EligibleModelView,
    candidate: EstimatedFeasibleCandidate,
    requirement: ModelRequirement,
    capacity: DeploymentCapacity,
    policy: SelectionPolicy,
    inventory: ModelInventory | None,
) -> RequirementAssessment:
    incremental = incremental_storage_demand(candidate.entry, requirement, inventory)
    evaluation = evaluate(
        candidate.entry.metadata,
        requirement,
        capacity,
        policy,
        runtime_compatibility=CompatibilityVerdict.COMPATIBLE,
        incremental_storage_bytes=incremental,
    )
    fit = evaluation.capacity_fit
    return replace(
        _unestimated_row(view, candidate.entry, None),
        requirement_status=RequirementStatus.READY,
        eligibility_status=RuntimeEligibilityStatus.ELIGIBLE.value,
        requirement=requirement,
        basis=(
            requirement.requirement_basis
            if isinstance(requirement.requirement_basis, str)
            else None
        ),
        reasons=evaluation.reasons,
        capacity_assessed=True,
        capacity_fit=fit.value,
        capacity_verdict=capacity_verdict(
            fit, assessed=True, reasons=evaluation.reasons
        ),
        required_ram_bytes=evaluation.required_ram_bytes,
        required_vram_bytes=evaluation.required_vram_bytes,
        safe_ram_bytes=evaluation.safe_ram_bytes,
        safe_vram_bytes=evaluation.safe_vram_bytes,
        evaluation=evaluation,
        available_ram_bytes=evaluation.available_ram_bytes,
        available_vram_bytes=evaluation.available_vram_bytes,
        incremental_storage_bytes=evaluation.incremental_storage_bytes,
        available_storage_bytes=evaluation.available_storage_bytes,
        snapshot_basis=(
            evaluation.snapshot_basis
            if isinstance(evaluation.snapshot_basis, str)
            else None
        ),
        runtime=_token(view.runtime),
        runtime_version=_token(view.runtime_version),
        profile_id=_token(view.profile_id),
        view_status=view.status.value,
    )


def _calibration_exclusion(
    candidate: EstimatedFeasibleCandidate,
    capacity: DeploymentCapacity,
    reason: str,
    notes: tuple[str, ...],
    *,
    required_vram_bytes: int | None = None,
) -> AvailableModelExclusion:
    required = required_vram_bytes
    if required is None:
        required = (
            candidate.requirement.estimated_vram_bytes
            if isinstance(candidate.requirement.estimated_vram_bytes, int)
            else None
        )
    available = _optional_int(capacity.available_vram_bytes)
    return AvailableModelExclusion(
        model_id=candidate.model_id,
        logical_name=candidate.logical_name,
        stage=FunnelStage.RUNTIME_CALIBRATION,
        reason=reason,
        notes=notes,
        required_vram_bytes=required if required is not None else NOT_PROVIDED,
        available_vram_bytes=available if available is not None else NOT_PROVIDED,
        weight_evidence_source=candidate.evidence.evidence_source.value,
        weight_lower_bound_bytes=(
            candidate.evidence.serialized_weight_tensor_bytes
            if isinstance(candidate.evidence.serialized_weight_tensor_bytes, int)
            else NOT_PROVIDED
        ),
    )


def _deep_exclusion(
    row: RequirementAssessment,
    evidence: WeightFootprintEvidence,
    capacity: DeploymentCapacity,
) -> AvailableModelExclusion:
    reason = row.capacity_verdict
    if reason in {"feasible", "not_assessed"}:
        reason = "requirement_unresolved"
    if row.requirement_status is RequirementStatus.UNRESOLVED:
        reason = "requirement_unresolved"
    vram = _optional_int(row.required_vram_bytes)
    available = _optional_int(row.available_vram_bytes)
    if available is None:
        available = _optional_int(capacity.available_vram_bytes)
    weight = _optional_int(evidence.serialized_weight_tensor_bytes)
    return AvailableModelExclusion(
        model_id=row.model_id,
        logical_name=row.logical_name,
        stage=FunnelStage.DEEP_CAPACITY,
        reason=reason,
        notes=row.reasons,
        weight_lower_bound_bytes=weight if weight is not None else NOT_PROVIDED,
        required_vram_bytes=vram if vram is not None else NOT_PROVIDED,
        available_vram_bytes=available if available is not None else NOT_PROVIDED,
        weight_evidence_source=evidence.evidence_source.value,
    )


def _member(
    row: RequirementAssessment,
    entry: ModelCatalogEntry,
    evidence: WeightFootprintEvidence,
    capacity: DeploymentCapacity,
    applied: AppliedCalibration | None = None,
) -> AvailableModelMember:
    evaluation = row.evaluation
    context: Maybe[int] = NOT_PROVIDED
    if row.requirement is not None and is_resolved(
        row.requirement.assumed_context_tokens
    ):
        context = row.requirement.assumed_context_tokens
    available_vram = (
        evaluation.available_vram_bytes
        if evaluation is not None and is_resolved(evaluation.available_vram_bytes)
        else capacity.available_vram_bytes
    )
    return AvailableModelMember(
        model_id=row.model_id,
        logical_name=row.logical_name,
        source_ref=entry.metadata.source_ref,
        source_revision=entry.metadata.source_revision,
        runtime=row.runtime or "",
        runtime_version=row.runtime_version
        if row.runtime_version is not None
        else NOT_PROVIDED,
        quantization=entry.metadata.quantization,
        requested_context_tokens=context,
        required_vram_bytes=row.required_vram_bytes
        if isinstance(row.required_vram_bytes, int)
        else NOT_PROVIDED,
        available_vram_bytes=available_vram
        if isinstance(available_vram, int)
        else NOT_PROVIDED,
        required_ram_bytes=row.required_ram_bytes
        if isinstance(row.required_ram_bytes, int)
        else NOT_PROVIDED,
        available_ram_bytes=row.available_ram_bytes
        if isinstance(row.available_ram_bytes, int)
        else NOT_PROVIDED,
        incremental_storage_bytes=row.incremental_storage_bytes
        if isinstance(row.incremental_storage_bytes, int)
        else NOT_PROVIDED,
        available_storage_bytes=row.available_storage_bytes
        if isinstance(row.available_storage_bytes, int)
        else NOT_PROVIDED,
        requirement_provider=(
            row.requirement.estimator_provider
            if row.requirement is not None
            and is_resolved(row.requirement.estimator_provider)
            else NOT_PROVIDED
        ),
        requirement_confidence=(
            row.requirement.confidence.value
            if row.requirement is not None
            else NOT_PROVIDED
        ),
        requirement_basis=row.basis or "",
        weight_evidence_source=evidence.evidence_source.value
        if evidence.evidence_source is not WeightEvidenceSource.UNAVAILABLE
        else NOT_PROVIDED,
        weight_lower_bound_bytes=evidence.serialized_weight_tensor_bytes
        if isinstance(evidence.serialized_weight_tensor_bytes, int)
        else NOT_PROVIDED,
        result="available",
        validation_status=(
            applied.status.value if applied is not None else NOT_PROVIDED
        ),
        runtime_memory_profile_id=(
            applied.profile_id
            if applied is not None and applied.profile_id
            else NOT_PROVIDED
        ),
        sentinel_model_id=(
            applied.sentinel_model_id
            if applied is not None and applied.sentinel_model_id is not None
            else NOT_PROVIDED
        ),
        validation_class=applied.class_key if applied is not None else NOT_PROVIDED,
        base_model_memory_bytes=(
            applied.base_model_bytes if applied is not None else NOT_PROVIDED
        ),
        runtime_extra_bytes=(
            applied.runtime_extra_bytes if applied is not None else NOT_PROVIDED
        ),
        kv_requirement_bytes=applied.kv_bytes if applied is not None else NOT_PROVIDED,
        validation_confidence=_validation_label(applied),
    )


def _unestimated_row(
    view: EligibleModelView,
    entry: ModelCatalogEntry,
    exclusion: AvailableModelExclusion | None,
) -> RequirementAssessment:
    reasons = exclusion.notes if exclusion is not None else ("not deep-analyzed",)
    eligibility = None
    candidate = _candidate(view, entry.metadata.model_id.value)
    if candidate is not None:
        eligibility = candidate.status.value
        reasons = candidate.reasons or reasons
    return RequirementAssessment(
        model_id=entry.metadata.model_id.value,
        logical_name=entry.metadata.logical_name.value,
        requirement_status=RequirementStatus.REFUSED
        if exclusion is not None and exclusion.stage is FunnelStage.CHEAP_SIZE_BOUND
        else RequirementStatus.UNRESOLVED
        if eligibility == RuntimeEligibilityStatus.UNRESOLVED.value
        else RequirementStatus.REFUSED,
        eligibility_status=eligibility,
        runtime=_token(view.runtime),
        runtime_version=_token(view.runtime_version),
        profile_id=_token(view.profile_id),
        view_id=view.view_id.value,
        view_status=view.status.value,
        selection_mode=_token(view.selection_mode),
        selected_candidate_id=_token(view.selected_candidate_id),
        requirement=None,
        basis=None,
        reasons=reasons,
        capacity_assessed=False,
        capacity_fit=None,
        capacity_verdict="not_assessed",
        required_ram_bytes=NOT_PROVIDED,
        required_vram_bytes=NOT_PROVIDED,
        safe_ram_bytes=NOT_PROVIDED,
        safe_vram_bytes=NOT_PROVIDED,
        source_ref=entry.metadata.source_ref,
        source_revision=entry.metadata.source_revision,
        evaluation=None,
    )


def _view_status(eligible: EligibleModelView) -> AvailableViewStatus:
    if eligible.status is EligibleViewStatus.UNAVAILABLE:
        return AvailableViewStatus.UNAVAILABLE
    if eligible.status is EligibleViewStatus.STALE:
        return AvailableViewStatus.STALE
    return AvailableViewStatus.CURRENT


def _discovery_token(discovery: DiscoveryResult) -> str:
    criteria = discovery.criteria
    return "|".join(
        (
            str(criteria.pipeline_tag),
            str(criteria.gated),
            ",".join(criteria.apps),
            str(discovery.universe_count),
            str(discovery.discovered_count),
            str(discovery.live),
        )
    )


def available_payload(view: AvailableModelView) -> dict[str, object]:
    """API-shaped Available Models. GET is not a mutation."""
    return {
        "status": view.status.value,
        "view_id": view.view_id.value,
        "view_basis": view.view_basis,
        "snapshot_basis": view.snapshot_basis,
        "runtime": view.runtime if isinstance(view.runtime, str) else None,
        "runtime_version": (
            view.runtime_version if isinstance(view.runtime_version, str) else None
        ),
        "requested_context_tokens": (
            view.requested_context_tokens
            if isinstance(view.requested_context_tokens, int)
            else None
        ),
        "host_fingerprint": view.host_fingerprint,
        "eligible_view_id": view.eligible_view_id,
        "policy_version": view.policy_version,
        "counts": {
            "universe": view.universe_count,
            "discovered": view.discovered_count,
            "compatibility": view.compatibility_count,
            "cheap_reject": view.cheap_reject_count,
            "deep_analyzed": view.deep_analyzed_count,
            "available": view.available_count,
            "excluded": view.excluded_count,
            "estimator_invocations": view.estimator_invocations,
            "estimated_feasible": view.estimated_feasible_count,
            "validation_classes": view.validation_class_count,
            "probe_invocations": view.probe_invocations,
        },
        "available": [_member_payload(item) for item in view.members],
        "excluded": [_exclusion_payload(item) for item in view.exclusions],
        "recommendation": False,
        "selection": False,
        "mutations": False,
    }


def _member_payload(item: AvailableModelMember) -> dict[str, object]:
    return {
        "model_id": item.model_id,
        "logical_name": item.logical_name,
        "source_ref": item.source_ref,
        "revision": _optional_str(item.source_revision),
        "runtime": item.runtime,
        "runtime_version": _optional_str(item.runtime_version),
        "quantization": _optional_str(item.quantization),
        "requested_context": _optional_int(item.requested_context_tokens),
        "weight_evidence_source": _optional_str(item.weight_evidence_source),
        "weight_lower_bound_bytes": _optional_int(item.weight_lower_bound_bytes),
        "required_vram_bytes": _optional_int(item.required_vram_bytes),
        "available_vram_bytes": _optional_int(item.available_vram_bytes),
        "required_ram_bytes": _optional_int(item.required_ram_bytes),
        "available_ram_bytes": _optional_int(item.available_ram_bytes),
        "incremental_storage_bytes": _optional_int(item.incremental_storage_bytes),
        "available_storage_bytes": _optional_int(item.available_storage_bytes),
        "requirement_provider": _optional_str(item.requirement_provider),
        "requirement_confidence": _optional_str(item.requirement_confidence),
        "requirement_basis": item.requirement_basis,
        "result": item.result,
        "validation_status": _optional_str(item.validation_status),
        "runtime_memory_profile_id": _optional_str(item.runtime_memory_profile_id),
        "sentinel_model_id": _optional_str(item.sentinel_model_id),
        "validation_class": _optional_str(item.validation_class),
        "base_model_memory_bytes": _optional_int(item.base_model_memory_bytes),
        "runtime_extra_bytes": _optional_int(item.runtime_extra_bytes),
        "kv_requirement_bytes": _optional_int(item.kv_requirement_bytes),
        "validation_confidence": _optional_str(item.validation_confidence),
    }


def _exclusion_payload(item: AvailableModelExclusion) -> dict[str, object]:
    return {
        "model_id": item.model_id,
        "logical_name": item.logical_name,
        "stage": item.stage.value,
        "reason": item.reason,
        "notes": list(item.notes),
        "weight_lower_bound_bytes": _optional_int(item.weight_lower_bound_bytes),
        "allowed_placement_bytes": _optional_int(item.allowed_placement_bytes),
        "required_vram_bytes": _optional_int(item.required_vram_bytes),
        "available_vram_bytes": _optional_int(item.available_vram_bytes),
        "weight_evidence_source": _optional_str(item.weight_evidence_source),
    }


def format_funnel(view: AvailableModelView) -> str:
    """CLI funnel counts. Not a recommendation."""
    lines = [
        "MODEL FEASIBILITY FUNNEL",
        f"Universe / Source considered:       {view.universe_count}",
        f"Remote discovered:                  {view.discovered_count}",
        f"Compatibility candidates:           {view.compatibility_count}",
        f"Cheap proven-impossible rejects:    {view.cheap_reject_count}",
        f"Deep analyzed:                      {view.deep_analyzed_count}",
        f"Estimated-feasible:                 {view.estimated_feasible_count}",
        f"Available Models:                   {view.available_count}",
        f"Excluded:                           {view.excluded_count}",
    ]
    return "\n".join(lines)


def format_available_models(view: AvailableModelView) -> str:
    """Print Available Models before any recommendation."""
    runtime = view.runtime if isinstance(view.runtime, str) else "-"
    version = view.runtime_version if isinstance(view.runtime_version, str) else "-"
    context = (
        str(view.requested_context_tokens)
        if isinstance(view.requested_context_tokens, int)
        else "per-model"
    )
    vram = "-"
    if view.members:
        first = view.members[0].available_vram_bytes
        if isinstance(first, int):
            vram = _gib(first)
    elif view.exclusions:
        first_ex = view.exclusions[0].available_vram_bytes
        if isinstance(first_ex, int):
            vram = _gib(first_ex)
    lines = [
        "================ AVAILABLE MODELS ================",
        f"Status: {view.status.value.upper()}",
        f"Runtime: {runtime} {version}",
        f"Context: {context}",
        f"Current available VRAM: {vram}",
        "",
        f"AVAILABLE ({view.available_count})",
        "",
    ]
    if not view.members:
        lines.append("(none)")
        lines.append("")
    for index, member in enumerate(view.members, start=1):
        lines.extend(_format_member(index, member))
        lines.append("")
    lines.append("EXCLUDED / NOT AVAILABLE")
    lines.append("")
    if not view.exclusions:
        lines.append("(none)")
        lines.append("")
    for excluded in view.exclusions:
        lines.extend(_format_exclusion(excluded))
        lines.append("")
    lines.append("==================================================")
    return "\n".join(lines)


def _format_member(index: int, item: AvailableModelMember) -> list[str]:
    quant = item.quantization if isinstance(item.quantization, str) else "-"
    weight = (
        _gib(item.weight_lower_bound_bytes)
        if isinstance(item.weight_lower_bound_bytes, int)
        else "unknown"
    )
    source = (
        item.weight_evidence_source
        if isinstance(item.weight_evidence_source, str)
        else "-"
    )
    required = (
        _gib(item.required_vram_bytes)
        if isinstance(item.required_vram_bytes, int)
        else "unknown"
    )
    available = (
        _gib(item.available_vram_bytes)
        if isinstance(item.available_vram_bytes, int)
        else "unknown"
    )
    revision = item.source_revision if isinstance(item.source_revision, str) else "-"
    provider = (
        item.requirement_provider if isinstance(item.requirement_provider, str) else "-"
    )
    return [
        f"{index}. {item.logical_name}",
        f"   quantization: {quant}",
        f"   revision: {revision}",
        f"   weight lower-bound: {weight}",
        f"   weight evidence: {source}",
        f"   required VRAM: {required}",
        f"   available VRAM: {available}",
        f"   requirement provider: {provider}",
        f"   validation: {_member_validation_label(item)}",
        "   result: AVAILABLE",
    ]


def _format_exclusion(item: AvailableModelExclusion) -> list[str]:
    lines = [
        item.logical_name,
        f"   stage: {item.stage.value.upper()}",
        f"   reason: {item.reason.upper()}",
    ]
    if isinstance(item.weight_lower_bound_bytes, int):
        lines.append(f"   weight lower-bound: {_gib(item.weight_lower_bound_bytes)}")
    if isinstance(item.allowed_placement_bytes, int):
        lines.append(f"   available placement: {_gib(item.allowed_placement_bytes)}")
    if isinstance(item.required_vram_bytes, int):
        lines.append(f"   required VRAM: {_gib(item.required_vram_bytes)}")
    if isinstance(item.available_vram_bytes, int):
        lines.append(f"   available VRAM: {_gib(item.available_vram_bytes)}")
    return lines


def _gib(value: int) -> str:
    return f"{value / (1024**3):.1f} GiB"


def _validation_label(applied: AppliedCalibration | None) -> Maybe[str]:
    if applied is None:
        return NOT_PROVIDED
    return _member_validation_label_from_status(applied.status)


def _member_validation_label(item: AvailableModelMember) -> str:
    status = item.validation_status
    if not isinstance(status, str):
        return "-"
    try:
        token = RuntimeValidationStatus(status)
    except ValueError:
        return status
    return _member_validation_label_from_status(token)


def _member_validation_label_from_status(status: RuntimeValidationStatus) -> str:
    if status is RuntimeValidationStatus.MEASURED_RUNTIME:
        return "Measured"
    if status is RuntimeValidationStatus.CALIBRATED_FROM_HIGH_PRESSURE_SENTINEL:
        return "Calibrated"
    if status is RuntimeValidationStatus.CACHED_RUNTIME_CALIBRATION:
        return "Cached calibration"
    return "Unresolved"
