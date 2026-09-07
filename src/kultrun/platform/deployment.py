"""Executable-model funnel. Maps runtime evidence into planning snapshots."""

from __future__ import annotations

import hashlib

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
)
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.acquisition import AcquisitionService, request_from_entry
from kultrun.model.catalogue import ModelCatalogue
from kultrun.model.contracts import (
    AcquisitionReceipt,
    ModelArtifact,
    ModelCatalogEntry,
)
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import (
    CapacityCommitments,
    CapacityFitClass,
    CompatibilityVerdict,
    DeploymentPlan,
    EligibilityVerdict,
    ModelEvaluation,
    PlanId,
    RuntimeCapabilitySnapshot,
    RuntimeEligibleModelCandidate,
    SelectionOutcome,
    SelectionRecommendation,
)
from kultrun.planning.eligibility import RuntimeEligibilityEvaluator
from kultrun.planning.service import SelectionService, plan_from
from kultrun.platform.runtime_setup import RuntimeSetupService
from kultrun.resource.contracts import ResourceSummary
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import RuntimeCapabilityProfile
from kultrun.storage.contracts import StorageSanityEvidence


class DeploymentService:
    """Phase 2: eligible models, capacity, plan, and acquisition modes."""

    def __init__(
        self,
        setup: RuntimeSetupService,
        selection: SelectionService,
        models: ModelCatalogue,
        acquisition: AcquisitionService,
        inventory: ModelInventory,
        capacity: CapacityService,
        resources: ResourceManager,
        store: Store,
        clock: Clock,
    ) -> None:
        self._setup = setup
        self._selection = selection
        self._models = models
        self._acquisition = acquisition
        self._inventory = inventory
        self._capacity = capacity
        self._resources = resources
        self._store = store
        self._clock = clock
        self._eligibility = RuntimeEligibilityEvaluator()

    def snapshot(
        self, profile: RuntimeCapabilityProfile
    ) -> RuntimeCapabilitySnapshot:
        return RuntimeCapabilitySnapshot(
            profile_id=profile.profile_id.value,
            installation_id=profile.installation_id.value,
            runtime_provider=profile.runtime_provider.value,
            runtime_family=profile.runtime_family.value,
            runtime_version=profile.runtime_version,
            executor_kind=profile.executor_kind.value,
            host_id=profile.host_id.value,
            status=profile.status.value,
            support_tier=profile.support_tier.value,
            supported_architectures=profile.supported_architectures,
            supported_formats=profile.supported_formats,
            supported_quantizations=profile.supported_quantizations,
            supported_modalities=profile.supported_modalities,
            verification_fingerprint=profile.verification_fingerprint,
        )

    def commitments_from(self, summary: ResourceSummary) -> CapacityCommitments:
        vram = 0
        if summary.accelerators:
            vram = summary.accelerators[0].reserved_bytes
        return CapacityCommitments(
            reserved_ram_bytes=summary.reserved_ram_bytes,
            reserved_vram_bytes=vram,
            reserved_unified_bytes=summary.reserved_unified_bytes,
        )

    def recommend(
        self,
        host: HostCapabilities,
        sanity: dict[str, StorageSanityEvidence],
    ) -> dict[str, object]:
        envelope = self._capacity.compute(host, sanity)
        profiles = self._setup.verified(host)
        if not profiles:
            empty = self._unverified(envelope)
            return {
                "state": SelectionOutcome.RUNTIME_NOT_VERIFIED.value,
                "download": False,
                "recommendation": empty,
                "plan": None,
                "eligibility": (),
                "feasible": (),
            }
        profile = profiles[0]
        snapshot = self.snapshot(profile)
        eligible, ineligible = self._partition(self._models.entries(), snapshot)
        summary = self._resources.summary(envelope)
        commitments = self.commitments_from(summary)
        recommendation = self._selection.recommend(
            envelope=envelope,
            candidates=tuple(item[0] for item in eligible),
            available_runtimes=(profile.runtime_family.value,),
            commitments=commitments,
            runtime=profile.runtime_family.value,
        )
        rejected = recommendation.rejected + tuple(
            _ineligible_evaluation(entry, verdict)
            for entry, verdict in ineligible
        )
        recommendation = SelectionRecommendation(
            outcome=recommendation.outcome,
            policy_version=recommendation.policy_version,
            estimator_provider=recommendation.estimator_provider,
            estimator_version=recommendation.estimator_version,
            recommended_at=recommendation.recommended_at,
            host_fingerprint=recommendation.host_fingerprint,
            primary=recommendation.primary,
            alternatives=recommendation.alternatives,
            underutilized=recommendation.underutilized,
            rejected=rejected,
            rationale=recommendation.rationale,
            evaluations=recommendation.evaluations + tuple(
                _ineligible_evaluation(entry, verdict)
                for entry, verdict in ineligible
            ),
            estimator_mode=recommendation.estimator_mode,
            requested_primary=recommendation.requested_primary,
            fallback_used=recommendation.fallback_used,
            fallback_reason=recommendation.fallback_reason,
        )
        planned = None
        if recommendation.primary is not None:
            matched = next(
                item[1]
                for item in eligible
                if item[0].metadata.model_id == recommendation.primary.model_id
            )
            planned = self._persist_plan(recommendation, profile, host, matched)
        return {
            "state": recommendation.outcome.value,
            "download": False,
            "recommendation": recommendation,
            "plan": planned,
            "runtime_profile_id": profile.profile_id.value,
            "runtime_provider": profile.runtime_provider.value,
            "runtime_version": profile.runtime_version,
            "eligibility": tuple(item[1] for item in eligible + ineligible),
        }

    def get_plan(self, plan_id: str) -> DeploymentPlan | None:
        return self._store.get(DeploymentPlan, plan_id)

    def require_fresh_plan(
        self, plan_id: str, host: HostCapabilities
    ) -> DeploymentPlan:
        plan = self.get_plan(plan_id)
        if plan is None:
            raise NotFoundError("no such deployment plan", plan_id=plan_id)
        if not is_resolved(plan.runtime_profile_id):
            raise PreconditionFailedError(
                "deployment plan has no runtime capability profile",
                reason="runtime_revalidation_required",
                plan_id=plan_id,
            )
        self._setup.require_current_profile(str(plan.runtime_profile_id), host)
        return plan

    def acquire_normal(
        self,
        plan_id: str,
        host: HostCapabilities,
        sanity: dict[str, StorageSanityEvidence],
    ) -> AcquisitionReceipt:
        plan = self.require_fresh_plan(plan_id, host)
        entry = self._models.acquirable(plan.logical_name.value)
        if entry is None:
            raise NotFoundError(
                "no such candidate", candidate=plan.logical_name.value
            )
        envelope = self._capacity.compute(host, sanity)
        request = request_from_entry(
            entry, mode="normal_execution", plan_id=plan.plan_id
        )
        return self._acquisition.acquire(request, envelope, host.host_id)

    def acquire_store_only(
        self,
        candidate: str,
        host: HostCapabilities,
        sanity: dict[str, StorageSanityEvidence],
    ) -> AcquisitionReceipt:
        entry = self._models.acquirable(candidate)
        if entry is None:
            raise NotFoundError("no such candidate", candidate=candidate)
        envelope = self._capacity.compute(host, sanity)
        request = request_from_entry(entry, mode="store_only")
        return self._acquisition.acquire(request, envelope, host.host_id)

    def artifact_for_plan(self, plan: DeploymentPlan) -> ModelArtifact | None:
        for artifact in self._inventory.artifacts():
            if (
                is_resolved(artifact.logical_name)
                and artifact.logical_name == plan.logical_name.value
            ):
                return artifact
        return None

    def currently_runnable(
        self, artifact: ModelArtifact, host: HostCapabilities
    ) -> dict[str, object]:
        profiles = self._setup.verified(host)
        if not profiles:
            return {
                "stored": True,
                "currently_runnable": False,
                "reason": "no_verified_compatible_runtime",
            }
        entry = None
        if is_resolved(artifact.logical_name):
            entry = self._models.acquirable(str(artifact.logical_name))
        if entry is None:
            return {
                "stored": True,
                "currently_runnable": False,
                "reason": "no_catalog_evidence",
            }
        for profile in profiles:
            verdict = self._eligibility.evaluate(entry.metadata, self.snapshot(profile))
            if verdict.verdict is EligibilityVerdict.ELIGIBLE:
                return {
                    "stored": True,
                    "currently_runnable": True,
                    "reason": "verified_runtime_eligible",
                    "runtime_profile_id": profile.profile_id.value,
                }
        return {
            "stored": True,
            "currently_runnable": False,
            "reason": "no_verified_compatible_runtime",
        }

    def _partition(
        self,
        entries: tuple[ModelCatalogEntry, ...],
        snapshot: RuntimeCapabilitySnapshot,
    ) -> tuple[
        list[tuple[ModelCatalogEntry, RuntimeEligibleModelCandidate]],
        list[tuple[ModelCatalogEntry, RuntimeEligibleModelCandidate]],
    ]:
        eligible: list[tuple[ModelCatalogEntry, RuntimeEligibleModelCandidate]] = []
        ineligible: list[tuple[ModelCatalogEntry, RuntimeEligibleModelCandidate]] = []
        for entry in entries:
            verdict = self._eligibility.evaluate(entry.metadata, snapshot)
            bucket = (
                eligible
                if verdict.verdict is EligibilityVerdict.ELIGIBLE
                else ineligible
            )
            bucket.append((entry, verdict))
        return eligible, ineligible

    def _persist_plan(
        self,
        recommendation: SelectionRecommendation,
        profile: RuntimeCapabilityProfile,
        host: HostCapabilities,
        eligibility: RuntimeEligibleModelCandidate,
    ) -> DeploymentPlan:
        base = plan_from(recommendation)
        if base is None or recommendation.primary is None:
            raise PreconditionFailedError("no primary recommendation to plan")
        primary = recommendation.primary
        plan_id = PlanId.generate()
        fingerprint = _plan_fingerprint(plan_id.value, profile, primary)
        plan = DeploymentPlan(
            model_id=base.model_id,
            logical_name=base.logical_name,
            source_ref=base.source_ref,
            quantization=base.quantization,
            runtime=profile.runtime_family.value,
            executor_kind=profile.executor_kind.value,
            plan_id=plan_id.value,
            runtime_profile_id=profile.profile_id.value,
            runtime_installation_id=profile.installation_id.value,
            runtime_version=profile.runtime_version,
            runtime_provider=profile.runtime_provider.value,
            host_id=host.host_id.value,
            host_fingerprint=host.fingerprint,
            context_tokens=primary.context_length_tokens,
            runtime_concurrency=1,
            eligibility_verdict=eligibility.verdict.value,
            capacity_fit=primary.capacity_fit.value,
            plan_fingerprint=fingerprint,
            placement=base.placement,
            expected_ram_bytes=base.expected_ram_bytes,
            expected_vram_bytes=base.expected_vram_bytes,
            expected_unified_bytes=base.expected_unified_bytes,
            expected_storage_bytes=base.expected_storage_bytes,
            expected_utilization=base.expected_utilization,
            estimator_provider=base.estimator_provider,
            policy_version=base.policy_version,
            rationale=base.rationale,
            estimator_mode=base.estimator_mode,
            fallback_used=base.fallback_used,
            fallback_reason=base.fallback_reason,
        )
        self._store.put(plan_id.value, plan)
        return plan

    def _unverified(self, envelope: CapacityEnvelope) -> SelectionRecommendation:
        return SelectionRecommendation(
            outcome=SelectionOutcome.RUNTIME_NOT_VERIFIED,
            policy_version=self._selection.policy.policy_version,
            estimator_provider=self._selection.estimator.identity.value,
            estimator_version=self._selection.estimator.version,
            estimator_mode=getattr(
                self._selection.estimator,
                "mode",
                self._selection.estimator.identity.value,
            ),
            requested_primary=getattr(
                self._selection.estimator,
                "requested_primary",
                self._selection.estimator.identity.value,
            ),
            recommended_at=self._clock.now(),
            host_fingerprint=envelope.host_fingerprint,
            rationale=(
                "No VERIFIED runtime capability profile exists. "
                "Executable recommendation is blocked.",
            ),
        )


def _ineligible_evaluation(
    entry: ModelCatalogEntry, verdict: RuntimeEligibleModelCandidate
) -> ModelEvaluation:
    meta = entry.metadata
    req = entry.requirement
    from kultrun.evidence.contracts import Confidence
    from kultrun.planning.contracts import CapacityUtilization

    return ModelEvaluation(
        model_id=meta.model_id,
        logical_name=meta.logical_name,
        source_ref=meta.source_ref,
        compatibility=CompatibilityVerdict.UNSUPPORTED,
        capacity_fit=CapacityFitClass.EXCEEDS_SAFE,
        storage_feasible=NOT_PROVIDED,
        required_ram_bytes=req.ram_bytes,
        required_vram_bytes=req.estimated_vram_bytes,
        required_unified_bytes=req.unified_memory_bytes,
        required_storage_bytes=req.peak_additional_bytes,
        safe_ram_bytes=NOT_PROVIDED,
        safe_vram_bytes=NOT_PROVIDED,
        safe_unified_bytes=NOT_PROVIDED,
        utilization=CapacityUtilization(
            ratio=NOT_PROVIDED, limiting_resource=NOT_PROVIDED, ram_ratio=NOT_PROVIDED
        ),
        preferred=False,
        reasons=verdict.reasons,
        unresolved=(),
        confidence=Confidence.HIGH,
        estimator_provider=NOT_PROVIDED,
        parameter_count=meta.parameter_count,
        quantization=meta.quantization,
        context_length_tokens=meta.context_length_tokens,
        supported_runtimes=meta.supported_runtimes,
    )


def _plan_fingerprint(
    plan_id: str, profile: RuntimeCapabilityProfile, primary: ModelEvaluation
) -> str:
    raw = "|".join(
        [
            plan_id,
            profile.profile_id.value,
            profile.runtime_version,
            profile.verification_fingerprint,
            primary.model_id.value,
            str(primary.quantization if is_resolved(primary.quantization) else ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
