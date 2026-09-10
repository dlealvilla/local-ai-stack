"""Capacity-first foundation realization. ResourceManager admits before pip."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import MemoryPlacement
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    InstallationStatus,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeSupportDescriptor,
)
from kultrun.runtime.resolve import ExecutorCapabilityView
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import (
    StorageCapacityEvidence,
    StorageFailureCode,
    StorageSanityEvidence,
)
from kultrun.storage.contradiction import contradict
from kultrun.storage.failures import is_capacity_failure
from kultrun.storage.footprint import runtime_provisioning_requirement
from kultrun.storage.index import StorageEvidenceIndex
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
    ) -> None:
        self._foundation = foundation
        self._characterization = characterization
        self._resources = resources
        self._capacity = capacity
        self._state_root = Path(state_root)
        self._index = index
        self._allow_empirical = allow_empirical

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
    ) -> RuntimeInstallation:
        if storage_evidence is None:
            characterized = self._characterization.characterize(
                host,
                run_cleanup=True,
                run_empirical=self._allow_empirical,
                probe_workspace=self._state_root,
            )
            if characterized.low_space:
                raise PreconditionFailedError(
                    characterized.low_space[0].message,
                    reason="storage_low_space",
                    mount_point=characterized.low_space[0].mount_point,
                )
            storage_evidence = characterized.evidence
            if self._index is not None:
                self._index.put_many(dict(storage_evidence))
        overview = self._foundation.view(
            host,
            executors,
            descriptors,
            policy,
            components=components,
            storage_evidence=storage_evidence,
            require_storage=True,
        )
        selected = overview.selection.selected_candidate_id
        if not isinstance(selected, str):
            raise PreconditionFailedError(
                "no storage-feasible foundation to realize",
                reason="runtime_storage_infeasible",
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
            raise PreconditionFailedError(
                decision.reasons[0] if decision.reasons else "storage not admitted",
                reason=str(decision.reason_code),
            )
        try:
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
        if self._index is not None:
            self._index.invalidate(host.host_id)
        rediscovered = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=False,
            probe_workspace=self._state_root,
        )
        if self._index is not None:
            self._index.put_many(rediscovered.evidence)
