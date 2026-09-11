"""Remaining is characterization minus managed growth, not a new Sonar run."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.kernel.clock import FixedClock
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import ArtifactId, ArtifactState, ModelArtifact, ModelId
from kultrun.model.inventory import ModelInventory
from kultrun.model.store import ModelArtifactStore
from kultrun.platform.managed_usage import PlatformManagedUsage
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import StorageEvidenceStatus
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.probes import ProbeRegistry
from kultrun.storage.remaining import remaining_after_usage
from kultrun.storage.topology import pools_from_host
from tests.test_capacity import INSTANT, host, mount
from tests.test_storage_persist import _record
from tests.test_storage_specialists import _emp, _RecordingSonar

GIB = 1024**3


class _Usage:
    def __init__(self, values: dict[str, int]) -> None:
        self._values = values

    def bytes_by_mount(self, host_id: object) -> dict[str, int]:
        del host_id
        return dict(self._values)


def test_managed_growth_reduces_planning_remaining_not_stored_snapshot(
    tmp_path: Path,
) -> None:
    subject = host()
    index = StorageEvidenceIndex(
        FileStore(tmp_path / "store"), _Usage({"/workspace": 0})
    )
    authorizing = replace(
        _record(subject.host_id, available=32 * GIB),
        accounted_managed_bytes=NOT_PROVIDED,
    )
    index.record_expensive({authorizing.mount_point: authorizing})
    stored = index.authorizing_for(subject.host_id, "/workspace")
    assert stored is not None
    assert stored.accounted_managed_bytes == 0
    assert stored.authorizing_available_bytes == 32 * GIB
    index.bind_usage(_Usage({"/workspace": 14 * GIB}))
    planning = index.for_host(subject)
    assert planning["/workspace"].authorizing_available_bytes == 18 * GIB
    assert planning["/workspace"].operational_available_bytes == 18 * GIB
    raw = index.authorizing_for(subject.host_id, "/workspace")
    assert raw is not None
    assert raw.authorizing_available_bytes == 32 * GIB
    assert "remaining after managed usage" in planning["/workspace"].selected_reason


def test_missing_accounted_snapshot_subtracts_all_known_managed(
    tmp_path: Path,
) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=32 * GIB)
    index.record_expensive({authorizing.mount_point: authorizing})
    index.bind_usage(_Usage({"/workspace": 14 * GIB}))
    planning = index.for_host(subject)
    assert planning["/workspace"].authorizing_available_bytes == 18 * GIB


def test_unresolved_recharacterization_does_not_drop_empirical(
    tmp_path: Path,
) -> None:
    subject = host()
    index = StorageEvidenceIndex(FileStore(tmp_path / "store"))
    authorizing = _record(subject.host_id, available=32 * GIB)
    empirical = replace(
        _emp(lower=32 * GIB, fingerprint="fp"),
        host_id=subject.host_id,
        mount_point="/workspace",
    )
    index.record_expensive(
        {authorizing.mount_point: authorizing},
        {"/workspace": empirical},
    )
    cheap = _record(subject.host_id)
    index.record_expensive({cheap.mount_point: cheap})
    planning = index.for_host(subject)
    assert planning["/workspace"].authorizing_available_bytes == 32 * GIB
    kept = index.empirical_for_host(subject)["/workspace"]
    assert kept.verified_lower_bound_bytes == 32 * GIB


def test_identity_matched_sonar_is_not_rerun(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subject = host(
        mounts=(mount(str(workspace), "fuse", free=176 * GIB, total=180 * GIB),)
    )
    pool = pools_from_host(subject)[0]
    store = FileStore(tmp_path / "store")
    index = StorageEvidenceIndex(store)
    empirical = replace(
        _emp(lower=32 * GIB, fingerprint=pool.fingerprint),
        host_id=subject.host_id,
        mount_point=pool.mount_point,
        quota_identity=pool.quota_identity,
    )
    authorizing = replace(
        _record(
            subject.host_id,
            available=32 * GIB,
            fingerprint=pool.fingerprint,
            mount=pool.mount_point,
        ),
        quota_identity=pool.quota_identity,
    )
    index.record_expensive(
        {authorizing.mount_point: authorizing},
        {pool.mount_point: empirical},
    )
    recorder = _RecordingSonar(empirical)
    service = StorageCharacterizationService(
        FixedClock(INSTANT),
        ProbeRegistry(()),
        empirical=recorder,
        index=index,
        use_live_native=False,
    )
    result = service.characterize(subject, run_cleanup=False, run_empirical=True)
    assert recorder.calls == 0
    assert pool.mount_point not in result.empirical_ran
    assert result.evidence[pool.mount_point].authorizing_available_bytes == 32 * GIB
    assert result.evidence[pool.mount_point].status is StorageEvidenceStatus.PROBED


def test_remaining_after_usage_is_zero_floor() -> None:
    evidence = _record(host().host_id, available=10 * GIB)
    reduced = remaining_after_usage(
        replace(evidence, accounted_managed_bytes=0), 40 * GIB
    )
    assert reduced.authorizing_available_bytes == 0
    assert is_resolved(reduced.authorizing_available_bytes)


def test_platform_managed_usage_sums_stored_artifacts(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "records")
    artifacts = ModelArtifactStore(tmp_path)
    inventory = ModelInventory(store, artifacts)
    subject = host()
    artifact = ModelArtifact(
        artifact_id=ArtifactId.generate(),
        model_id=ModelId.generate(),
        revision="rev-a",
        state=ArtifactState.STORED,
        installed_bytes=14 * GIB,
        storage_mount="/workspace",
    )
    path = artifacts.manifest_path(artifact.artifact_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    inventory.put(artifact, subject.host_id)
    usage = PlatformManagedUsage(store, inventory, tmp_path)
    found = usage.bytes_by_mount(subject.host_id)
    assert found["/workspace"] == 14 * GIB
    other = host()
    assert usage.bytes_by_mount(other.host_id) == {}
