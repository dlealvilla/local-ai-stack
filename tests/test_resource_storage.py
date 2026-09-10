"""ResourceManager per-pool storage admission."""

from __future__ import annotations

from pathlib import Path

from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import MemoryPlacement
from kultrun.resource.contracts import (
    AdmissionReason,
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.lock import AdmissionLock
from kultrun.resource.manager import ResourceManager
from tests.test_capacity import INSTANT

GIB = 1024**3


def _layered(safe: Maybe[int]) -> LayeredBytes:
    return LayeredBytes(
        reported_bytes=100 * GIB if isinstance(safe, int) else NOT_PROVIDED,
        effective_bytes=safe if isinstance(safe, int) else NOT_PROVIDED,
        safe_bytes=safe,
        confidence=Confidence.HIGH,
        provenance=Provenance(
            producer=Name("test"),
            producer_version="t",
            observed_at=INSTANT,
            policy_version="t",
        ),
    )


def _envelope(pools: tuple[tuple[str, Maybe[int]], ...]) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=HostId.generate(),
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=tuple(
            PoolCapacity(
                mount_point=mount,
                space=_layered(safe),
                requirement=EvidenceRequirement.SUFFICIENT,
            )
            for mount, safe in pools
        ),
    )


def _manager(tmp_path: Path) -> ResourceManager:
    from kultrun.adapters.persistence.file_store import FileStore

    return ResourceManager(
        FileStore(tmp_path / "records"),
        FixedClock(INSTANT),
        AdmissionLock(tmp_path / "state"),
    )


def _request(
    envelope: CapacityEnvelope,
    *,
    incremental_storage_bytes: Maybe[int] = 10 * GIB,
    storage_pool_mount: Maybe[str] = "/models",
    workload_type: WorkloadType = WorkloadType.MODEL_ACQUISITION,
) -> ResourceRequest:
    return ResourceRequest(
        request_id=RequestId.generate(),
        host_id=envelope.host_id,
        plan_fingerprint="storage-test",
        placement=MemoryPlacement.CPU_ONLY,
        ram_bytes=NOT_PROVIDED,
        accelerator_bytes=NOT_PROVIDED,
        unified_bytes=NOT_PROVIDED,
        incremental_storage_bytes=incremental_storage_bytes,
        storage_pool_mount=storage_pool_mount,
        workload_type=workload_type,
    )


def test_requirement_over_capacity_never_admits(tmp_path: Path) -> None:
    envelope = _envelope((("/models", 5 * GIB), ("/runtimes", 50 * GIB)))
    decision = _manager(tmp_path).admit(
        _request(envelope, incremental_storage_bytes=10 * GIB), envelope
    )
    assert decision.verdict is AdmissionVerdict.REJECTED
    assert decision.reason_code == AdmissionReason.INSUFFICIENT_SAFE_STORAGE.value


def test_named_pool_not_first_pool(tmp_path: Path) -> None:
    envelope = _envelope((("/runtimes", 2 * GIB), ("/models", 20 * GIB)))
    decision = _manager(tmp_path).admit(
        _request(envelope, storage_pool_mount="/models"), envelope
    )
    assert decision.verdict is AdmissionVerdict.ADMITTED
    assert decision.reservation is not None
    assert decision.reservation.storage_pool_mount == "/models"


def test_unresolved_safe_is_unresolved(tmp_path: Path) -> None:
    envelope = _envelope((("/models", NOT_PROVIDED),))
    decision = _manager(tmp_path).admit(_request(envelope), envelope)
    assert decision.verdict is AdmissionVerdict.UNRESOLVED
    assert decision.reason_code == AdmissionReason.UNRESOLVED_SAFE_CAPACITY.value


def test_runtime_provisioning_does_not_need_an_artifact(tmp_path: Path) -> None:
    envelope = _envelope((("/runtimes", 40 * GIB),))
    decision = _manager(tmp_path).admit(
        _request(
            envelope,
            storage_pool_mount="/runtimes",
            incremental_storage_bytes=20 * GIB,
            workload_type=WorkloadType.RUNTIME_PROVISIONING,
        ),
        envelope,
    )
    assert decision.verdict is AdmissionVerdict.ADMITTED
    assert decision.reservation is not None
    assert decision.reservation.admitted_storage_bytes == 20 * GIB
