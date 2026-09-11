"""Cheap observation must not erase authorizing characterization."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.storage.contracts import (
    EmpiricalProbeEvidence,
    StorageCapacityEvidence,
    StorageEvidenceStatus,
)
from kultrun.storage.index import StorageEvidenceIndex, evidence_key, observation_key
from kultrun.storage.limits import POLICY_VERSION
from tests.test_capacity import INSTANT, host

GIB = 1024**3


def _record(
    host_id: HostId,
    *,
    available: int | object = NOT_PROVIDED,
    fingerprint: str = "fp",
    mount: str = "/workspace",
) -> StorageCapacityEvidence:
    unresolved = available is NOT_PROVIDED
    status = (
        StorageEvidenceStatus.UNRESOLVED if unresolved else StorageEvidenceStatus.PROBED
    )
    return StorageCapacityEvidence(
        host_id=host_id,
        mount_point=mount,
        quota_identity="fuse:mfs:/workspace",
        pool_fingerprint=fingerprint,
        observed_at=INSTANT,
        status=status,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        reported_available_bytes=179 * 1024 * GIB if unresolved else available,
        operational_available_bytes=available,
        authorizing_available_bytes=available,
        selected_reason="test",
    )


def test_cheap_observation_does_not_clobber_authorizing(tmp_path: Path) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=25 * GIB)
    cheap = _record(subject.host_id)
    index.record_expensive({authorizing.mount_point: authorizing})
    index.record_observation({cheap.mount_point: cheap})
    planning = index.for_host(subject)
    assert planning["/workspace"].authorizing_available_bytes == 25 * GIB
    assert planning["/workspace"].status is StorageEvidenceStatus.PROBED
    assert index.for_host(subject)["/workspace"].status is StorageEvidenceStatus.PROBED


def test_identity_change_invalidates_authorizing(tmp_path: Path) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=25 * GIB, fingerprint="old")
    index.record_expensive({authorizing.mount_point: authorizing})
    remounted = _record(subject.host_id, fingerprint="new")
    index.record_observation({remounted.mount_point: remounted})
    planning = index.for_host(subject)
    assert planning["/workspace"].status is StorageEvidenceStatus.UNRESOLVED
    assert planning["/workspace"].pool_fingerprint == "new"


def test_empirical_evidence_is_persisted(tmp_path: Path) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=25 * GIB)
    empirical = EmpiricalProbeEvidence(
        host_id=subject.host_id,
        mount_point="/workspace",
        target_path="/workspace/.kultrun-sonar",
        max_probe_bytes=25 * GIB,
        bytes_physically_written=25 * GIB,
        search_granularity_bytes=64 * 1024**2,
        probe_ceiling_reached=True,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("storage.empirical"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=True,
        verified_lower_bound_bytes=25 * GIB,
    )
    index.record_expensive(
        {authorizing.mount_point: authorizing},
        {"/workspace": empirical},
    )
    stored = index.empirical_for_host(subject)
    assert stored["/workspace"].verified_lower_bound_bytes == 25 * GIB
    index.record_observation({"/workspace": _record(subject.host_id)})
    kept = index.empirical_for_host(subject)["/workspace"]
    assert kept.verified_lower_bound_bytes == 25 * GIB


def test_empirical_progress_does_not_promote_authorizing(tmp_path: Path) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=10 * GIB)
    index.record_expensive({authorizing.mount_point: authorizing})
    running = EmpiricalProbeEvidence(
        host_id=subject.host_id,
        mount_point="/workspace",
        target_path="/workspace/.kultrun-sonar",
        max_probe_bytes=256,
        bytes_physically_written=32,
        search_granularity_bytes=1,
        probe_ceiling_reached=False,
        confidence=Confidence.LOW,
        provenance=Provenance(
            producer=Name("storage.empirical"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version=POLICY_VERSION,
        ),
        cleanup_success=False,
        verified_lower_bound_bytes=32,
        run_state="running",
        completed_tier_units=(16, 24, 32),
    )
    index.put_empirical(running)
    planning = index.for_host(subject)
    assert planning["/workspace"].authorizing_available_bytes == 10 * GIB
    stored = index.empirical_for_host(subject)["/workspace"]
    assert stored.run_state == "running"
    assert stored.completed_tier_units == (16, 24, 32)


def test_observation_and_authorizing_use_distinct_keys() -> None:
    host_id = HostId.generate()
    assert observation_key(host_id, "/workspace") != evidence_key(host_id, "/workspace")
    assert observation_key(host_id, "/workspace").startswith("sco_")
    assert evidence_key(host_id, "/workspace").startswith("sce_")
