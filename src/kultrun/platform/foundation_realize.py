"""Capacity-first foundation realization. ResourceManager admits before pip."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import MemoryPlacement
from kultrun.platform.contracts import MinimumFeasibilityVerdict
from kultrun.platform.minimum import (
    assess_minimum,
    destination_pool,
    nearby_state_roots,
)
from kultrun.platform.observation import (
    OperationalJournal,
    OperationalOutcome,
    OperationalStage,
    attr,
)
from kultrun.platform.runs import DeploymentRunStore
from kultrun.platform.storage_replan import (
    ReplanOutcome,
    ReplanStage,
    StorageReplanService,
)
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    CompatibilityClass,
    InstallationStatus,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)
from kultrun.runtime.resolve import ExecutorCapabilityView
from kultrun.runtime.selection import FoundationOverview, FoundationSelectionService
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import (
    ManagedOccupancyClass,
    ManagedOccupancyItem,
    OwnershipRecord,
    StorageCapacityEvidence,
    StorageFailureCode,
    StoragePool,
    StorageSanityEvidence,
)
from kultrun.storage.contradiction import contradict
from kultrun.storage.failures import is_capacity_failure
from kultrun.storage.footprint import runtime_provisioning_requirement
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.inventory import (
    classify_occupancy,
    totals_by_pool,
    unique_occupancy,
)
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.recharacterize import should_recharacterize
from kultrun.storage.reclaim import execute_reclaim, plan_reclaim
from kultrun.storage.reduction import (
    is_footprint_retryable,
    is_manual_capacity_required,
)
from kultrun.storage.topology import bind_path, pools_from_host


class FoundationRealizeService:
    """Characterize → exclude infeasible → admit storage → realize → rediscover."""

    def __init__(
        self,
        foundation: FoundationSelectionService,
        characterization: StorageCharacterizationService,
        resources: ResourceManager,
        capacity: CapacityService,
        state_root: Path,
        index: StorageEvidenceIndex | None = None,
        *,
        allow_empirical: bool = False,
        replan: StorageReplanService | None = None,
        journal: OperationalJournal | None = None,
        ownership: OwnershipService | None = None,
        runs: DeploymentRunStore | None = None,
        occupancy_records: (
            Callable[
                [HostCapabilities],
                tuple[tuple[OwnershipRecord, ...], tuple[Path, ...], tuple[Path, ...]],
            ]
            | None
        ) = None,
    ) -> None:
        self._foundation = foundation
        self._characterization = characterization
        self._resources = resources
        self._capacity = capacity
        self._state_root = Path(state_root)
        self._index = index
        self._allow_empirical = allow_empirical
        self._replan = replan
        self._journal = journal
        self._ownership = ownership
        self._runs = runs
        self._occupancy_records = occupancy_records

    def occupancy_items(
        self, host: HostCapabilities
    ) -> tuple[ManagedOccupancyItem, ...]:
        """Classify dual-owned roots. Does not probe or delete."""
        records, live_roots, reusable_roots = self._occupancy(host)
        return unique_occupancy(
            classify_occupancy(
                records,
                pools_from_host(host),
                current_state_root=self._state_root,
                live_roots=live_roots,
                reusable_roots=reusable_roots,
            )
        )

    def realize(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
        retry: bool = False,
        storage_evidence: Mapping[str, StorageCapacityEvidence] | None = None,
        sanity: Mapping[str, StorageSanityEvidence] | None = None,
        _replanned: bool = False,
    ) -> RuntimeInstallation:
        try:
            return self._realize_inner(
                host,
                executors,
                descriptors,
                policy,
                components=components,
                retry=retry,
                storage_evidence=storage_evidence,
                sanity=sanity,
                _replanned=_replanned,
            )
        except PreconditionFailedError as error:
            self._fail_product(host, error)
            raise

    def _realize_inner(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
        retry: bool = False,
        storage_evidence: Mapping[str, StorageCapacityEvidence] | None = None,
        sanity: Mapping[str, StorageSanityEvidence] | None = None,
        _replanned: bool = False,
    ) -> RuntimeInstallation:
        try:
            installation = self._realize_once(
                host,
                executors,
                descriptors,
                policy,
                components=components,
                retry=retry,
                storage_evidence=storage_evidence,
                sanity=sanity,
            )
        except PreconditionFailedError as error:
            self._raise_or_replan(host, error, replanned=_replanned)
            return self._realize_inner(
                host,
                executors,
                descriptors,
                policy,
                components=components,
                retry=retry,
                storage_evidence=None,
                sanity=sanity,
                _replanned=True,
            )
        code = (
            installation.last_failure_code
            if is_resolved(installation.last_failure_code)
            else None
        )
        if (
            not _replanned
            and self._replan is not None
            and installation.status is InstallationStatus.FAILED
            and isinstance(code, str)
            and is_footprint_retryable(code)
            and self._try_replan(host, code)
        ):
            return self._realize_inner(
                host,
                executors,
                descriptors,
                policy,
                components=components,
                retry=retry,
                storage_evidence=None,
                sanity=sanity,
                _replanned=True,
            )
        return installation

    def _raise_or_replan(
        self,
        host: HostCapabilities,
        error: PreconditionFailedError,
        *,
        replanned: bool,
    ) -> None:
        if replanned or self._replan is None:
            raise error
        code = str(error.context.get("reason") or "")
        if is_manual_capacity_required(code):
            raise PreconditionFailedError(
                "automatic storage capacity is unresolved; "
                "administrator capacity may be supplied as last resort",
                reason="manual_capacity_required",
            )
        if not is_footprint_retryable(code):
            raise error
        if not self._try_replan(host, code):
            raise error

    def _try_replan(self, host: HostCapabilities, code: str) -> bool:
        if self._replan is None:
            return False
        selected = _selected_identity(self._foundation, host)
        peak = runtime_provisioning_requirement().required_peak_free_bytes
        footprint = peak if isinstance(peak, int) else 0
        report = self._replan.handle(
            host,
            failure_code=code,
            original_identity=selected,
            original_footprint=footprint,
            stage=ReplanStage.RUNTIME,
        )
        if report.outcome is ReplanOutcome.SUCCEEDED:
            return True
        if report.outcome is ReplanOutcome.MANUAL_BLOCKED:
            raise PreconditionFailedError(report.message, reason=report.outcome.value)
        if report.outcome is ReplanOutcome.LOW_SPACE:
            raise PreconditionFailedError(report.message, reason="storage_low_space")
        raise PreconditionFailedError(report.message, reason=report.outcome.value)

    def _realize_once(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
        retry: bool = False,
        storage_evidence: Mapping[str, StorageCapacityEvidence] | None = None,
        sanity: Mapping[str, StorageSanityEvidence] | None = None,
    ) -> RuntimeInstallation:
        if storage_evidence is None:
            characterized = self._characterization.characterize(
                host,
                run_cleanup=True,
                run_empirical=self._allow_empirical,
            )
            if characterized.low_space:
                raise PreconditionFailedError(
                    characterized.low_space[0].message,
                    reason="storage_low_space",
                    mount_point=characterized.low_space[0].mount_point,
                )
            storage_evidence = characterized.evidence
            if self._index is not None:
                self._index.record_expensive(
                    dict(storage_evidence), characterized.empirical_evidence
                )
                planning = self._index.for_host(host)
                if planning:
                    storage_evidence = planning
        storage_evidence = self._apply_minimum_and_reclaim(
            host, descriptors, storage_evidence, sanity
        )
        overview = self._foundation.view(
            host,
            executors,
            descriptors,
            policy,
            components=components,
            storage_evidence=storage_evidence,
            require_storage=True,
        )
        self._emit_runtime_funnel(host.host_id, overview)
        selected = overview.selection.selected_candidate_id
        if not isinstance(selected, str):
            raise PreconditionFailedError(
                "no storage-feasible foundation to realize",
                reason="runtime_storage_infeasible",
            )
        overview = self._foundation.ensure_auto_selection(
            host,
            executors,
            descriptors,
            policy,
            components=components,
            storage_evidence=storage_evidence,
            require_storage=True,
            selected_candidate_id=selected,
        )
        selected = overview.selection.selected_candidate_id
        if not isinstance(selected, str):
            raise PreconditionFailedError(
                "no storage-feasible foundation to realize",
                reason="runtime_storage_infeasible",
            )
        self._emit(
            host.host_id,
            OperationalStage.RUNTIME,
            "runtime.selected",
            f"{_runtime_family(overview, selected)} selected",
            OperationalOutcome.PASS,
            candidate=selected,
            runtime=_runtime_family(overview, selected),
        )
        for item in overview.candidates:
            blocked = item.role == "blocked"
            self._emit(
                host.host_id,
                OperationalStage.RUNTIME,
                "runtime.candidate_evaluated",
                f"evaluating {item.candidate_id} {item.role}",
                OperationalOutcome.BLOCKED if blocked else OperationalOutcome.INFO,
                candidate=item.candidate_id,
                reason=item.reason if blocked else None,
            )
        envelope = self._capacity.compute(
            host, sanity or {}, storage_evidence=storage_evidence
        )
        pools = pools_from_host(host)
        dest = bind_path(self._state_root / "runtimes", pools)
        mount = dest.mount_point if dest is not None else None
        if not isinstance(mount, str):
            raise PreconditionFailedError(
                "runtime destination pool is unresolved",
                reason="storage_pool_unresolved",
            )
        requirement = runtime_provisioning_requirement(mount_point=mount)
        request = ResourceRequest(
            request_id=RequestId.generate(),
            host_id=host.host_id,
            plan_fingerprint=f"runtime-provision:{selected}",
            placement=MemoryPlacement.CPU_ONLY,
            ram_bytes=NOT_PROVIDED,
            accelerator_bytes=NOT_PROVIDED,
            unified_bytes=NOT_PROVIDED,
            incremental_storage_bytes=requirement.required_peak_free_bytes,
            storage_pool_mount=mount,
            workload_type=WorkloadType.RUNTIME_PROVISIONING,
        )
        decision = self._resources.admit(request, envelope)
        if decision.verdict is not AdmissionVerdict.ADMITTED:
            code = str(decision.reason_code)
            if is_manual_capacity_required(code):
                raise PreconditionFailedError(
                    "automatic storage capacity is unresolved; "
                    "administrator capacity may be supplied as last resort",
                    reason="manual_capacity_required",
                )
            raise PreconditionFailedError(
                decision.reasons[0] if decision.reasons else "storage not admitted",
                reason=code,
            )
        self._emit(
            host.host_id,
            OperationalStage.ADMISSION,
            "resource.admission_completed",
            "admission PASS",
            OperationalOutcome.PASS,
            candidate=selected,
            mount=mount,
        )
        try:
            self._emit(
                host.host_id,
                OperationalStage.RUNTIME,
                "runtime.provision_started",
                "installing selected runtime",
                OperationalOutcome.INFO,
                candidate=selected,
            )
            installation = self._foundation.realize_selected(
                host,
                executors,
                descriptors,
                policy,
                components=components,
                retry=retry,
                storage_evidence=storage_evidence,
                require_storage=True,
            )
        finally:
            if decision.reservation is not None:
                self._resources.release(decision.reservation.reservation_id)
        outcome = (
            OperationalOutcome.PASS
            if installation.status is InstallationStatus.INSTALLED
            else OperationalOutcome.FAIL
        )
        size = (
            f"{installation.installed_bytes} bytes"
            if is_resolved(installation.installed_bytes)
            else "size unknown"
        )
        self._emit(
            host.host_id,
            OperationalStage.RUNTIME,
            "runtime.provision_completed",
            f"installed {installation.runtime.value} {size}",
            outcome,
            candidate=selected,
            bytes=installation.installed_bytes
            if is_resolved(installation.installed_bytes)
            else None,
            mount=mount,
        )
        self._after(host, storage_evidence, installation)
        return installation

    def _after(
        self,
        host: HostCapabilities,
        storage_evidence: Mapping[str, StorageCapacityEvidence],
        installation: RuntimeInstallation,
    ) -> None:
        code = (
            installation.last_failure_code
            if is_resolved(installation.last_failure_code)
            else None
        )
        if installation.status is InstallationStatus.FAILED and isinstance(code, str):
            try:
                failure = StorageFailureCode(code)
            except ValueError:
                failure = None
            if failure is not None and is_capacity_failure(failure):
                if self._index is not None:
                    for item in storage_evidence.values():
                        self._index.put(contradict(item, failure))
                return
        rediscovered = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=False,
        )
        if self._index is not None:
            self._index.record_observation(rediscovered.evidence)

    def _apply_minimum_and_reclaim(
        self,
        host: HostCapabilities,
        descriptors: Sequence[RuntimeSupportDescriptor],
        storage_evidence: Mapping[str, StorageCapacityEvidence],
        sanity: Mapping[str, StorageSanityEvidence] | None,
    ) -> Mapping[str, StorageCapacityEvidence]:
        pools = pools_from_host(host)
        dest = destination_pool(self._state_root, pools)
        records, live_roots, reusable_roots = self._occupancy(host)
        items = classify_occupancy(
            records,
            pools,
            current_state_root=self._state_root,
            live_roots=live_roots,
            reusable_roots=reusable_roots,
        )
        mount = dest.mount_point if dest is not None else None
        evidence = storage_evidence.get(mount) if isinstance(mount, str) else None
        envelope = self._capacity.compute(
            host, sanity or {}, storage_evidence=storage_evidence
        )
        grouped = (
            totals_by_pool(items).get(dest.mount_point) if dest is not None else None
        )
        reclaimable = grouped.reclaimable_bytes if grouped is not None else 0
        self._emit_occupancy(host.host_id, items, dest.mount_point if dest else None)
        pre = assess_minimum(
            host,
            destination=dest,
            evidence=evidence,
            items=items,
            descriptors=descriptors,
            ram_safe_bytes=envelope.memory.safe_bytes,
        )
        capacity_needed = pre.requires_reclamation
        if dest is not None and reclaimable > 0:
            storage_evidence, items, records = self._cleanup_stale(
                host,
                dest,
                items,
                records,
                storage_evidence,
                sanity,
                descriptors,
                capacity_needed=capacity_needed,
            )
        elif dest is not None and self._allow_empirical and self._index is not None:
            empirical = self._index.empirical_for_host(host).get(dest.mount_point)
            if self._empirical_predates_reclaim(host, empirical):
                storage_evidence = self._refresh_after_occupancy(
                    host,
                    dest,
                    items,
                    storage_evidence,
                    sanity,
                    actual_reclaimed=0,
                )
        if dest is not None:
            evidence = storage_evidence.get(dest.mount_point)
            envelope = self._capacity.compute(
                host, sanity or {}, storage_evidence=storage_evidence
            )
        assessment = assess_minimum(
            host,
            destination=dest,
            evidence=evidence,
            items=items,
            descriptors=descriptors,
            ram_safe_bytes=envelope.memory.safe_bytes,
        )
        self._emit_minimum(host.host_id, assessment)
        if assessment.verdict is MinimumFeasibilityVerdict.FAIL:
            code = (
                assessment.reason_code
                if is_resolved(assessment.reason_code)
                else "minimum_storage"
            )
            raise PreconditionFailedError(
                assessment.condition or "minimum feasibility failed",
                reason=str(code),
            )
        if assessment.requires_reclamation:
            raise PreconditionFailedError(
                assessment.condition or "capacity still infeasible after cleanup",
                reason="reclamation_not_safe",
            )
        return storage_evidence

    def _cleanup_stale(
        self,
        host: HostCapabilities,
        dest: StoragePool,
        items: tuple[ManagedOccupancyItem, ...],
        records: tuple[OwnershipRecord, ...],
        storage_evidence: Mapping[str, StorageCapacityEvidence],
        sanity: Mapping[str, StorageSanityEvidence] | None,
        descriptors: Sequence[RuntimeSupportDescriptor],
        *,
        capacity_needed: bool,
    ) -> tuple[
        Mapping[str, StorageCapacityEvidence],
        tuple[ManagedOccupancyItem, ...],
        tuple[OwnershipRecord, ...],
    ]:
        del descriptors
        if self._ownership is None:
            raise PreconditionFailedError(
                "stale Kultrun state is cleanup-eligible but cannot be executed safely",
                reason="reclamation_not_safe",
            )
        plan = plan_reclaim(
            items,
            mount_point=dest.mount_point,
            capacity_required=capacity_needed,
        )
        if plan.expected_bytes <= 0:
            return storage_evidence, items, records
        self._emit(
            host.host_id,
            OperationalStage.STORAGE,
            "storage.reclaim_planned",
            f"reclaim {plan.expected_bytes} bytes",
            OperationalOutcome.INFO,
            bytes=plan.expected_bytes,
            cleanup_lifecycle=True,
            cleanup_capacity=capacity_needed,
        )
        allowed = (
            *nearby_state_roots(self._state_root),
            self._state_root,
            *(
                Path(item.managed_root)
                for item in items
                if item.occupancy_class is ManagedOccupancyClass.RECLAIMABLE
            ),
        )
        result = execute_reclaim(plan, records, self._ownership, allowed_roots=allowed)
        self._emit(
            host.host_id,
            OperationalStage.STORAGE,
            "storage.reclaim_completed",
            f"Cleanup PASS — {_fmt_bytes(result.actual_bytes)} reclaimed"
            if result.actual_bytes > 0 and not result.blocked
            else f"reclaimed {result.actual_bytes} bytes",
            OperationalOutcome.PASS
            if result.actual_bytes > 0 and not result.blocked
            else OperationalOutcome.FAIL,
            bytes=result.actual_bytes,
            byte_band=_byte_band(result.actual_bytes),
            cleanup_lifecycle=True,
            cleanup_capacity=capacity_needed,
        )
        if result.blocked or (result.actual_bytes <= 0 and plan.expected_bytes > 0):
            raise PreconditionFailedError(
                "planned reclaim of stale Kultrun state failed",
                reason="reclamation_not_safe",
            )
        pools = pools_from_host(host)
        records, live_roots, reusable_roots = self._occupancy(host)
        items = classify_occupancy(
            records,
            pools,
            current_state_root=self._state_root,
            live_roots=live_roots,
            reusable_roots=reusable_roots,
        )
        storage_evidence = self._refresh_after_occupancy(
            host,
            dest,
            items,
            storage_evidence,
            sanity,
            actual_reclaimed=result.actual_bytes,
        )
        return storage_evidence, items, records

    def _refresh_after_occupancy(
        self,
        host: HostCapabilities,
        dest: StoragePool,
        items: tuple[ManagedOccupancyItem, ...],
        storage_evidence: Mapping[str, StorageCapacityEvidence],
        sanity: Mapping[str, StorageSanityEvidence] | None,
        *,
        actual_reclaimed: int,
    ) -> Mapping[str, StorageCapacityEvidence]:
        evidence = storage_evidence.get(dest.mount_point)
        empirical = None
        if self._index is not None:
            empirical = self._index.empirical_for_host(host).get(dest.mount_point)
        envelope = self._capacity.compute(
            host, sanity or {}, storage_evidence=storage_evidence
        )
        current_safe: object = NOT_PROVIDED
        for pool in envelope.pools:
            if pool.mount_point == dest.mount_point:
                current_safe = pool.space.safe_bytes
                break
        peak = runtime_provisioning_requirement().required_peak_free_bytes
        required = peak if isinstance(peak, int) else 0
        blocks = not is_resolved(current_safe) or (
            isinstance(current_safe, int) and current_safe < required
        )
        grouped = totals_by_pool(items).get(dest.mount_point)
        managed_now = None
        if grouped is not None:
            managed_now = (
                grouped.active_bytes
                + grouped.reusable_bytes
                + grouped.reclaimable_bytes
                + grouped.protected_bytes
            )
        run_empirical = bool(
            self._allow_empirical
            and (
                should_recharacterize(
                    empirical,
                    evidence,
                    managed_now=managed_now if isinstance(managed_now, int) else None,
                    reclaimable_bytes=grouped.reclaimable_bytes if grouped else 0,
                    current_safe_blocks=blocks,
                    actual_reclaimed_bytes=actual_reclaimed,
                )
                or (
                    blocks
                    and self._empirical_predates_reclaim(host, empirical)
                )
            )
        )
        if run_empirical and self._index is not None:
            self._index.invalidate(host.host_id, dest.mount_point)
            self._emit(
                host.host_id,
                OperationalStage.STORAGE,
                "storage.recharacterized",
                "occupancy dropped; occupancy-conditional upper is not a quota",
                OperationalOutcome.INFO,
                reason="managed_occupancy_dropped",
            )
        characterized = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=run_empirical,
        )
        storage_evidence = characterized.evidence
        if self._index is not None:
            if run_empirical:
                self._index.record_expensive(
                    dict(storage_evidence), characterized.empirical_evidence
                )
            else:
                self._index.record_observation(characterized.evidence)
            planning = self._index.for_host(host)
            if planning:
                storage_evidence = planning
        return storage_evidence

    def _empirical_predates_reclaim(
        self, host: HostCapabilities, empirical: object
    ) -> bool:
        """True when a later reclaim made an occupancy-conditional upper stale."""
        if self._journal is None or empirical is None:
            return False
        upper = getattr(empirical, "observed_failure_upper_bytes", None)
        if not is_resolved(upper):
            return False
        provenance = getattr(empirical, "provenance", None)
        observed = getattr(provenance, "observed_at", None)
        if observed is None:
            return False
        for fact in self._journal.facts(host.host_id):
            if fact.event_type.value != "storage.reclaim_completed":
                continue
            if fact.outcome is not OperationalOutcome.PASS:
                continue
            if fact.occurred_at >= observed:
                return True
        return False

    def _emit_occupancy(
        self,
        host_id: HostId,
        items: Sequence[ManagedOccupancyItem],
        mount: str | None,
    ) -> None:
        grouped = totals_by_pool(items).get(mount) if mount is not None else None
        reclaimable = grouped.reclaimable_bytes if grouped is not None else 0
        self._emit(
            host_id,
            OperationalStage.STORAGE,
            "storage.occupancy_classified",
            (
                f"{_fmt_bytes(reclaimable)} obsolete Kultrun state identified"
                if reclaimable > 0
                else "no cleanup-eligible Kultrun state"
            ),
            OperationalOutcome.INFO,
            reclaimable_bytes=reclaimable,
            reusable_bytes=grouped.reusable_bytes if grouped is not None else 0,
            active_bytes=grouped.active_bytes if grouped is not None else 0,
            protected_bytes=grouped.protected_bytes if grouped is not None else 0,
            unknown_bytes=grouped.unknown_bytes if grouped is not None else 0,
            cleanup_lifecycle=reclaimable > 0,
        )

    def _emit_runtime_funnel(
        self, host_id: HostId, overview: FoundationOverview
    ) -> None:
        rows = (
            *overview.resolution.candidates,
            *overview.resolution.unsupported,
            *overview.resolution.unresolved,
        )
        discovered = len(rows)
        product_selectable = sum(
            1 for item in rows if item.support_tier is RuntimeSupportTier.PRODUCT
        )
        host_compatible = sum(
            1
            for item in rows
            if item.compatibility is not CompatibilityClass.UNSUPPORTED
            or "unsupported_platform" not in {code.value for code in item.reason_codes}
        )
        executor_ok = sum(
            1
            for item in rows
            if "executor_unavailable" not in {code.value for code in item.reason_codes}
        )
        capacity_ok = sum(
            1
            for item in rows
            if item.compatibility
            in {CompatibilityClass.COMPATIBLE, CompatibilityClass.CONDITIONAL}
        )
        feasible = len(overview.resolution.candidates)
        self._emit(
            host_id,
            OperationalStage.RUNTIME,
            "runtime.funnel_completed",
            f"{discovered} candidates → {feasible} feasible",
            OperationalOutcome.INFO,
            discovered=discovered,
            product_selectable=product_selectable,
            host_compatible=host_compatible,
            executor_compatible=executor_ok,
            capacity_feasible=capacity_ok,
        )

    def _occupancy(
        self, host: HostCapabilities
    ) -> tuple[tuple[OwnershipRecord, ...], tuple[Path, ...], tuple[Path, ...]]:
        if self._occupancy_records is None:
            return (), (), ()
        return self._occupancy_records(host)

    def _emit_minimum(self, host_id: HostId, assessment: object) -> None:
        from kultrun.platform.contracts import MinimumFeasibilityAssessment

        if not isinstance(assessment, MinimumFeasibilityAssessment):
            return
        outcome = (
            OperationalOutcome.PASS
            if assessment.verdict is MinimumFeasibilityVerdict.PASS
            else OperationalOutcome.FAIL
        )
        self._emit(
            host_id,
            OperationalStage.FEASIBILITY,
            "minimum.feasibility_completed",
            f"MINIMUM FEASIBILITY {assessment.verdict.value.upper()}",
            outcome,
            reason=assessment.reason_code
            if is_resolved(assessment.reason_code)
            else None,
            verdict=assessment.verdict.value,
            profile=assessment.profile_version,
            requires_reclamation=assessment.requires_reclamation,
            byte_band=_byte_band(assessment.potential_safe_bytes),
            current_authorizing_bytes=(
                assessment.current_authorizing_bytes
                if is_resolved(assessment.current_authorizing_bytes)
                else None
            ),
            current_safe_bytes=(
                assessment.current_safe_bytes
                if is_resolved(assessment.current_safe_bytes)
                else None
            ),
            reclaimable_bytes=assessment.reclaimable_bytes,
            reusable_bytes=assessment.reusable_bytes,
            required_peak_bytes=assessment.required_peak_bytes,
            net_new_bytes=assessment.net_new_bytes,
            potential_authorizing_bytes=(
                assessment.potential_authorizing_bytes
                if is_resolved(assessment.potential_authorizing_bytes)
                else None
            ),
            potential_safe_bytes=(
                assessment.potential_safe_bytes
                if is_resolved(assessment.potential_safe_bytes)
                else None
            ),
        )
        for item in assessment.foundations:
            self._emit(
                host_id,
                OperationalStage.FEASIBILITY,
                "foundation.possibility",
                f"{item.family} {item.host_possibility.value}",
                OperationalOutcome.INFO,
                runtime=item.family,
                possibility=item.host_possibility.value,
                support_tier=item.support_tier,
            )

    def _fail_product(
        self, host: HostCapabilities, error: PreconditionFailedError
    ) -> None:
        reason = str(error.context.get("reason") or "") or None
        stage = OperationalStage.DEPLOYMENT
        if reason in _MINIMUM_REASON_CODES:
            stage = OperationalStage.FEASIBILITY
        self._emit(
            host.host_id,
            stage,
            "deployment.failed",
            error.message,
            OperationalOutcome.FAIL,
            reason=reason,
        )
        if self._runs is not None:
            self._runs.mark_failed()

    def _emit(
        self,
        host_id: HostId,
        stage: OperationalStage,
        event_type: str,
        summary: str,
        outcome: OperationalOutcome,
        reason: str | None = None,
        **fields: object,
    ) -> None:
        if self._journal is None:
            return
        attributes = tuple(
            attr(key, value) for key, value in fields.items() if value is not None
        )
        self._journal.emit(
            host_id=host_id,
            stage=stage,
            event_type=event_type,
            summary=summary,
            outcome=outcome,
            reason_code=reason,
            attributes=attributes,
        )


_MINIMUM_REASON_CODES = frozenset(
    {
        "minimum_storage",
        "minimum_ram",
        "unsupported_platform",
        "unsupported_architecture",
        "accelerator_requirement",
        "no_plausible_foundation",
        "reclamation_not_safe",
    }
)


def _fmt_bytes(value: int) -> str:
    gib = value / (1024**3)
    if gib >= 1:
        return f"{gib:.1f} GiB"
    mib = value / (1024**2)
    if mib >= 1:
        return f"{mib:.1f} MiB"
    return f"{value} B"


def _byte_band(value: object) -> str | None:
    if not isinstance(value, int):
        return None
    gib = value / (1024**3)
    for edge in (8, 16, 24, 32, 48, 64, 96, 128, 192, 256):
        if gib <= edge:
            return f"<={edge}GiB"
    return ">256GiB"


def _runtime_family(overview: FoundationOverview, selected: str) -> str:
    for item in (
        *overview.resolution.candidates,
        *overview.resolution.unsupported,
        *overview.resolution.unresolved,
    ):
        if item.candidate_id.value == selected:
            return item.runtime.value
    return selected


def _selected_identity(
    foundation: FoundationSelectionService, host: HostCapabilities
) -> str:
    stored = foundation.stored(host)
    if stored is None:
        return "unselected"
    selected = stored.selected_candidate_id
    return selected if isinstance(selected, str) else "unselected"
