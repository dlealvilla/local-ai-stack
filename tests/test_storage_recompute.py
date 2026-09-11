"""Destination-pool acquisition and recomputation after storage events."""

from __future__ import annotations

from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.acquisition import needed_bytes, safe_storage
from kultrun.planning.evaluate import deployment_capacity
from kultrun.storage.contracts import StorageEvidenceStatus
from kultrun.storage.contradiction import contradict
from kultrun.storage.reduction import select_smaller
from tests.test_capacity import INSTANT
from tests.test_storage_evidence import _evidence

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


def test_safe_storage_uses_named_destination_not_first_pool() -> None:
    envelope = CapacityEnvelope(
        host_id=HostId.generate(),
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/runtimes",
                space=_layered(2 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
            PoolCapacity(
                mount_point="/models",
                space=_layered(20 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
        ),
    )
    mount, safe = safe_storage(envelope, "/models")
    assert mount == "/models"
    assert safe == 20 * GIB
    first_only, _unresolved = safe_storage(envelope)
    assert first_only is None
    assert not is_resolved(_unresolved)


def test_needed_bytes_prefers_peak() -> None:
    from kultrun.model.contracts import (
        AcquisitionId,
        ModelAcquisitionRequest,
        ModelId,
    )

    request = ModelAcquisitionRequest(
        request_id=AcquisitionId.generate(),
        model_id=ModelId.generate(),
        logical_name=Name("m"),
        source=Name("huggingface"),
        source_ref="probe/model",
        expected_storage_bytes=8 * GIB,
        expected_peak_bytes=12 * GIB,
    )
    assert needed_bytes(request) == 12 * GIB


def test_contradiction_invalidates_planning_storage() -> None:
    item = _evidence(native_available=40 * GIB)
    broken = contradict(
        item,
        __import__(
            "kultrun.storage.contracts", fromlist=["StorageFailureCode"]
        ).StorageFailureCode.STORAGE_QUOTA_EXCEEDED,
    )
    assert broken.status is StorageEvidenceStatus.CONTRADICTED
    envelope = CapacityEnvelope(
        host_id=item.host_id,
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/",
                space=_layered(NOT_PROVIDED),
                requirement=EvidenceRequirement.UNKNOWN,
            ),
        ),
    )
    capacity = deployment_capacity(envelope)
    assert not is_resolved(capacity.safe_storage_bytes)


def test_replan_selects_real_candidates_not_scaled_numbers() -> None:
    candidates = (
        ("A", 40 * GIB),
        ("B", 35 * GIB),
        ("C", 31 * GIB),
        ("D", 26 * GIB),
        ("E", 20 * GIB),
    )
    chosen = select_smaller(
        candidates,
        peak_of=lambda item: item[1],
        original_peak=40 * GIB,
        reduction=1,
    )
    assert chosen is not None
    assert chosen[0] == "C"
    assert chosen[1] == 31 * GIB
    assert chosen[1] != int(40 * GIB * 0.80)


def test_deployment_capacity_uses_named_pool_not_first_fuse() -> None:
    from kultrun.kernel.unresolved import is_resolved
    from kultrun.planning.evaluate import deployment_capacity

    envelope = CapacityEnvelope(
        host_id=HostId.generate(),
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(NOT_PROVIDED),
                requirement=EvidenceRequirement.UNKNOWN,
            ),
            PoolCapacity(
                mount_point="/",
                space=_layered(20 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
            ),
        ),
    )
    unnamed = deployment_capacity(envelope)
    assert unnamed.safe_storage_bytes == 20 * GIB
    named = deployment_capacity(envelope, storage_mount="/")
    assert named.safe_storage_bytes == 20 * GIB
    other = deployment_capacity(envelope, storage_mount="/workspace")
    assert not is_resolved(other.safe_storage_bytes)


def test_fixture_native_does_not_stat_the_replay_machine() -> None:
    from kultrun.storage.native import native_available_bytes
    from kultrun.storage.ports import StorageEnvironment
    from tests.test_capacity import mount as make_mount

    declared = 32_118_607_872
    facts = make_mount("/", "overlay", free=declared)
    environment = StorageEnvironment(
        os_name="linux",
        architecture="x86_64",
        mount_point="/",
        filesystem_type="overlay",
        device="overlay",
    )
    value, source = native_available_bytes(facts, environment, live=False)
    assert source == "host-mount-free"
    assert value == declared
