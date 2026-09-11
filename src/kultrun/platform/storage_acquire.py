"""Model acquisition with ResourceManager storage admission.

Lives in platform so `model` never imports `resource`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from kultrun.capacity.envelope import CapacityService
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.acquisition import AcquisitionService, needed_bytes, safe_storage
from kultrun.model.contracts import (
    AcquisitionReceipt,
    MemoryPlacement,
    ModelAcquisitionRequest,
)
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import StorageSanityEvidence
from kultrun.storage.footprint import model_acquisition_requirement
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.topology import bind_path, pools_from_host


class StorageAwareAcquisition:
    """Fresh capacity → destination pool → RM admit → fetch → rediscover."""

    def __init__(
        self,
        acquisition: AcquisitionService,
        resources: ResourceManager,
        capacity: CapacityService,
        characterization: StorageCharacterizationService,
        index: StorageEvidenceIndex,
        state_root: Path,
        *,
        allow_empirical: bool,
    ) -> None:
        self._acquisition = acquisition
        self._resources = resources
        self._capacity = capacity
        self._characterization = characterization
        self._index = index
        self._state_root = Path(state_root)
        self._allow_empirical = allow_empirical

    def acquire(
        self,
        request: ModelAcquisitionRequest,
        host: HostCapabilities,
        sanity: Mapping[str, StorageSanityEvidence],
        *,
        destination_mount: str | None = None,
    ) -> AcquisitionReceipt:
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
        self._index.record_expensive(
            characterized.evidence, characterized.empirical_evidence
        )
        envelope = self._capacity.compute(host, sanity, characterized.evidence)
        mount = destination_mount or _model_mount(host, self._state_root)
        named, safe = safe_storage(envelope, mount)
        if named is None or not is_resolved(safe) or not isinstance(safe, int):
            raise PreconditionFailedError(
                "SAFE storage is unresolved on the destination pool",
                reason="unresolved_storage_requirement",
                mount_point=mount,
            )
        needed = needed_bytes(request)
        if needed is None:
            raise PreconditionFailedError(
                "storage requirement is unresolved; unknown is not zero",
                reason="unresolved_storage_requirement",
            )
        requirement = model_acquisition_requirement(
            persistent_bytes=request.expected_storage_bytes,
            peak_bytes=request.expected_peak_bytes,
            mount_point=named,
        )
        peak = (
            requirement.required_peak_free_bytes
            if is_resolved(requirement.required_peak_free_bytes)
            else needed
        )
        admit = self._resources.admit(
            ResourceRequest(
                request_id=RequestId.generate(),
                host_id=host.host_id,
                plan_fingerprint=f"model-acquire:{request.model_id.value}",
                placement=MemoryPlacement.CPU_ONLY,
                ram_bytes=NOT_PROVIDED,
                accelerator_bytes=NOT_PROVIDED,
                unified_bytes=NOT_PROVIDED,
                incremental_storage_bytes=peak,
                storage_pool_mount=named,
                workload_type=WorkloadType.MODEL_ACQUISITION,
                model_id=request.model_id,
            ),
            envelope,
        )
        if admit.verdict is not AdmissionVerdict.ADMITTED:
            raise PreconditionFailedError(
                admit.reasons[0] if admit.reasons else "storage not admitted",
                reason=str(admit.reason_code),
            )
        try:
            return self._acquisition.acquire(
                request, envelope, host.host_id, destination_mount=named
            )
        finally:
            if admit.reservation is not None:
                self._resources.release(admit.reservation.reservation_id)
            self._index.invalidate(host.host_id)
            rediscovered = self._characterization.characterize(
                host,
                run_cleanup=True,
                run_empirical=False,
                probe_workspace=self._state_root,
            )
            self._index.record_observation(rediscovered.evidence)


def _model_mount(host: HostCapabilities, state_root: Path) -> str | None:
    pools = pools_from_host(host)
    pool = bind_path(state_root / "models", pools)
    if pool is None:
        return None
    return pool.mount_point
