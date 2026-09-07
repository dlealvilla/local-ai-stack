"""Assemble evaluations into a recommendation. No reservations."""

from __future__ import annotations

import datetime as dt

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.kernel.clock import Clock
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.contracts import (
    MemoryPlacement,
    ModelCatalogEntry,
    ModelEstimationRequest,
)
from kultrun.model.ports import ModelRequirementEstimator
from kultrun.planning.contracts import (
    CapacityCommitments,
    CapacityFitClass,
    CompatibilityVerdict,
    DeploymentPlan,
    ModelEvaluation,
    SelectionOutcome,
    SelectionPolicy,
    SelectionRecommendation,
)
from kultrun.planning.evaluate import deployment_capacity, evaluate, rank_key


def _request(
    entry: ModelCatalogEntry,
    placement: MemoryPlacement,
    runtime: Maybe[str] = NOT_PROVIDED,
) -> ModelEstimationRequest:
    meta = entry.metadata
    req = entry.requirement
    context = (
        req.assumed_context_tokens
        if is_resolved(req.assumed_context_tokens)
        else meta.context_length_tokens
    )
    assumed = (
        runtime
        if is_resolved(runtime)
        else (meta.supported_runtimes[0] if meta.supported_runtimes else NOT_PROVIDED)
    )
    return ModelEstimationRequest(
        model_id=meta.model_id,
        source_ref=meta.source_ref,
        source_revision=meta.source_revision,
        artifact_format=NOT_PROVIDED,
        quantization=meta.quantization,
        context_tokens=context,
        runtime=assumed,
        placement=placement,
        offload_allowed=False,
        tensor_parallel=1,
        batch_size=1,
    )


class SelectionService:
    """Estimate with the active provider, then filter and rank."""

    def __init__(
        self,
        estimator: ModelRequirementEstimator,
        clock: Clock,
        policy: SelectionPolicy | None = None,
    ) -> None:
        self._estimator = estimator
        self._clock = clock
        self._policy = policy or SelectionPolicy()

    @property
    def estimator(self) -> ModelRequirementEstimator:
        return self._estimator

    @property
    def policy(self) -> SelectionPolicy:
        return self._policy

    def recommend(
        self,
        *,
        envelope: CapacityEnvelope,
        candidates: tuple[ModelCatalogEntry, ...],
        available_runtimes: tuple[str, ...] = (),
        commitments: CapacityCommitments | None = None,
        runtime: Maybe[str] = NOT_PROVIDED,
    ) -> SelectionRecommendation:
        capacity = deployment_capacity(envelope, commitments)
        evaluations = []
        for entry in candidates:
            request = _request(entry, capacity.placement, runtime)
            requirement = self._estimator.estimate(request)
            evaluations.append(
                evaluate(
                    entry.metadata,
                    requirement,
                    capacity,
                    available_runtimes,
                    self._policy,
                )
            )
        return _select(
            tuple(evaluations),
            self._policy,
            self._estimator,
            self._clock.now(),
            envelope.host_fingerprint,
        )


def plan_for_entry(
    service: SelectionService,
    entry: ModelCatalogEntry,
    envelope: CapacityEnvelope,
    available_runtimes: tuple[str, ...] = (),
) -> DeploymentPlan:
    """A plan for one known stored candidate. Does not change ranking."""
    capacity = deployment_capacity(envelope)
    requirement = service.estimator.estimate(_request(entry, capacity.placement))
    evaluation = evaluate(
        entry.metadata,
        requirement,
        capacity,
        available_runtimes,
        service.policy,
    )
    runtime = (
        evaluation.supported_runtimes[0] if evaluation.supported_runtimes else None
    )
    return DeploymentPlan(
        model_id=evaluation.model_id,
        logical_name=evaluation.logical_name,
        source_ref=evaluation.source_ref,
        quantization=evaluation.quantization,
        runtime=runtime if runtime is not None else NOT_PROVIDED,
        executor_kind="native-process",
        placement=capacity.placement,
        expected_ram_bytes=evaluation.required_ram_bytes,
        expected_vram_bytes=evaluation.required_vram_bytes,
        expected_unified_bytes=evaluation.required_unified_bytes,
        expected_storage_bytes=evaluation.required_storage_bytes,
        expected_utilization=evaluation.utilization.ratio,
        estimator_provider=(
            evaluation.estimator_provider
            if is_resolved(evaluation.estimator_provider)
            else service.estimator.identity.value
        ),
        policy_version=service.policy.policy_version,
        rationale=evaluation.reasons,
        estimator_mode=(
            evaluation.estimator_mode
            if is_resolved(evaluation.estimator_mode)
            else service.estimator.identity.value
        ),
        fallback_used=evaluation.fallback_used,
        fallback_reason=evaluation.fallback_reason,
    )


def plan_from(recommendation: SelectionRecommendation) -> DeploymentPlan | None:
    """A plan exists only when there is a primary recommendation."""
    primary = recommendation.primary
    if primary is None:
        return None
    runtime = primary.supported_runtimes[0] if primary.supported_runtimes else None
    return DeploymentPlan(
        model_id=primary.model_id,
        logical_name=primary.logical_name,
        source_ref=primary.source_ref,
        quantization=primary.quantization,
        runtime=runtime if runtime is not None else NOT_PROVIDED,
        executor_kind="native-process",
        placement=_placement_of(primary),
        expected_ram_bytes=primary.required_ram_bytes,
        expected_vram_bytes=primary.required_vram_bytes,
        expected_unified_bytes=primary.required_unified_bytes,
        expected_storage_bytes=primary.required_storage_bytes,
        expected_utilization=primary.utilization.ratio,
        estimator_provider=recommendation.estimator_provider,
        policy_version=recommendation.policy_version,
        rationale=recommendation.rationale,
        estimator_mode=recommendation.estimator_mode,
        fallback_used=recommendation.fallback_used,
        fallback_reason=recommendation.fallback_reason,
    )


def _placement_of(evaluation: ModelEvaluation) -> MemoryPlacement:
    if is_resolved(evaluation.safe_vram_bytes):
        return MemoryPlacement.DISCRETE_GPU
    if is_resolved(evaluation.safe_unified_bytes):
        return MemoryPlacement.UNIFIED_MEMORY
    return MemoryPlacement.CPU_ONLY


def _select(
    evaluations: tuple[ModelEvaluation, ...],
    policy: SelectionPolicy,
    estimator: ModelRequirementEstimator,
    when: dt.datetime,
    fingerprint: str,
) -> SelectionRecommendation:
    if not evaluations:
        provider, version, mode, requested, fallback_used, fallback_reason = (
            _provenance(None, estimator)
        )
        return SelectionRecommendation(
            outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATE,
            policy_version=policy.policy_version,
            estimator_provider=provider,
            estimator_version=version,
            recommended_at=when,
            host_fingerprint=fingerprint,
            rationale=("No runtime-eligible candidates remain.",),
            estimator_mode=mode,
            requested_primary=requested,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
    ranked = tuple(sorted(evaluations, key=rank_key))
    preferred_ids = {
        item.model_id.value
        for item in ranked
        if item.capacity_fit is CapacityFitClass.PREFERRED
        and item.compatibility is CompatibilityVerdict.COMPATIBLE
    }
    under_ids = {
        item.model_id.value
        for item in ranked
        if item.capacity_fit is CapacityFitClass.UNDERUTILIZED
        and item.compatibility is CompatibilityVerdict.COMPATIBLE
    }
    preferred = tuple(item for item in ranked if item.model_id.value in preferred_ids)
    under = tuple(item for item in ranked if item.model_id.value in under_ids)
    rejected = tuple(
        item
        for item in ranked
        if item.model_id.value not in preferred_ids
        and item.model_id.value not in under_ids
    )
    source = preferred[0] if preferred else (evaluations[0] if evaluations else None)
    provider, version, mode, requested, fallback_used, fallback_reason = _provenance(
        source, estimator
    )
    if preferred:
        primary, rest = preferred[0], preferred[1:]
        return SelectionRecommendation(
            outcome=SelectionOutcome.RECOMMENDED,
            policy_version=policy.policy_version,
            estimator_provider=provider,
            estimator_version=version,
            recommended_at=when,
            host_fingerprint=fingerprint,
            primary=primary,
            alternatives=rest,
            underutilized=under,
            rejected=rejected,
            rationale=_why(primary),
            evaluations=evaluations,
            estimator_mode=mode,
            requested_primary=requested,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
    if under and not policy.allow_underutilized_fallback:
        return SelectionRecommendation(
            outcome=SelectionOutcome.NO_PREFERRED_CANDIDATE,
            policy_version=policy.policy_version,
            estimator_provider=provider,
            estimator_version=version,
            recommended_at=when,
            host_fingerprint=fingerprint,
            underutilized=under,
            rejected=rejected,
            rationale=(
                "All compatible candidates underutilize the current "
                "safe deployment capacity.",
            ),
            evaluations=evaluations,
            estimator_mode=mode,
            requested_primary=requested,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
    unresolved = all(
        item.capacity_fit is CapacityFitClass.UNRESOLVED
        or item.compatibility is CompatibilityVerdict.UNRESOLVED
        for item in evaluations
    )
    if unresolved:
        return SelectionRecommendation(
            outcome=SelectionOutcome.UNRESOLVED,
            policy_version=policy.policy_version,
            estimator_provider=provider,
            estimator_version=version,
            recommended_at=when,
            host_fingerprint=fingerprint,
            rejected=rejected or ranked,
            rationale=("Load-bearing requirement or estimator is unresolved.",),
            evaluations=evaluations,
            estimator_mode=mode,
            requested_primary=requested,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
    return SelectionRecommendation(
        outcome=SelectionOutcome.NO_FEASIBLE_CANDIDATE,
        policy_version=policy.policy_version,
        estimator_provider=provider,
        estimator_version=version,
        recommended_at=when,
        host_fingerprint=fingerprint,
        underutilized=under,
        rejected=rejected,
        rationale=("No candidate fits SAFE deployment capacity.",),
        evaluations=evaluations,
        estimator_mode=mode,
        requested_primary=requested,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


def _provenance(
    source: ModelEvaluation | None, estimator: ModelRequirementEstimator
) -> tuple[str, str, str, str, bool, Maybe[str]]:
    """Router provenance when present; otherwise the estimator's identity."""
    provider = estimator.identity.value
    version = estimator.version
    mode = estimator.identity.value
    requested = estimator.identity.value
    fallback_used = False
    fallback_reason: Maybe[str] = NOT_PROVIDED
    if source is None or not is_resolved(source.estimator_mode):
        return provider, version, mode, requested, fallback_used, fallback_reason
    if is_resolved(source.estimator_provider):
        provider = source.estimator_provider
    if is_resolved(source.estimator_version):
        version = source.estimator_version
    mode = source.estimator_mode
    if is_resolved(source.requested_primary):
        requested = source.requested_primary
    fallback_used = source.fallback_used
    fallback_reason = source.fallback_reason
    return provider, version, mode, requested, fallback_used, fallback_reason


def _why(winner: ModelEvaluation) -> tuple[str, ...]:
    ratio = winner.utilization.ratio
    used = f"{float(ratio):.1%}" if is_resolved(ratio) else "unknown"
    limiting = (
        winner.utilization.limiting_resource
        if is_resolved(winner.utilization.limiting_resource)
        else "memory"
    )
    return (
        f"fits SAFE {limiting} at {used} utilization",
        "compatible runtime",
        "ranked by capability proxy, then operating headroom",
        *winner.reasons,
    )
