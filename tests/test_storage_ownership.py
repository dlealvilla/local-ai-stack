"""Managed ownership: dual evidence, conflict safety, Step 0 cleanup."""

from __future__ import annotations

import json
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock
from kultrun.storage.cleanup import step0_cleanup
from kultrun.storage.contracts import (
    LOCAL_OWNER_FILENAME,
    CleanupPolicy,
    LifecycleState,
    ManagedResourceType,
    OwnershipConflict,
    OwnershipId,
    OwnershipRecord,
)
from kultrun.storage.ownership import OwnershipService
from tests.test_capacity import INSTANT

HOST = HostId.generate()


def _service(tmp_path: Path) -> OwnershipService:
    state = tmp_path / "state"
    state.mkdir()
    return OwnershipService(FileStore(tmp_path / "records"), FixedClock(INSTANT), state)


def test_manifest_and_registry_agree(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "runtimes" / "staging"
    record = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_STAGING,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    marker = service.load_marker(root)
    stored = service.get(record.ownership_id)
    assert marker == record
    assert stored == record
    assert (root / LOCAL_OWNER_FILENAME).is_file()
    conflict, found = service.classify(root)
    assert conflict is OwnershipConflict.NONE
    assert found == record


def test_registry_rebuilds_from_local_marker(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "cache"
    record = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.INSTALL_CACHE,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    assert service.get(record.ownership_id) is not None
    FileStore(tmp_path / "records").delete(OwnershipRecord, record.ownership_id.value)
    other = OwnershipService(
        FileStore(tmp_path / "records"), FixedClock(INSTANT), service.state_root
    )
    assert other.get(record.ownership_id) is None
    rebuilt = other.reconcile()
    assert len(rebuilt) == 1
    assert other.get(record.ownership_id) == record


def test_missing_manifest_is_not_deleted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "runtimes" / "gone"
    record = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_STAGING,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    (root / LOCAL_OWNER_FILENAME).unlink()
    conflict, _found = service.classify(root)
    assert conflict is OwnershipConflict.MANIFEST_MISSING
    report = step0_cleanup(service, HOST)
    assert record.ownership_id.value in {
        item.ownership_id.value for item in service.records()
    }
    assert root.is_dir()
    assert report.removed == 0
    assert str(root) in report.unresolved


def test_missing_registry_is_not_deleted_without_rebuild(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "staging"
    record = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_STAGING,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    FileStore(tmp_path / "records").delete(OwnershipRecord, record.ownership_id.value)
    conflict, _found = service.classify(root)
    assert conflict is OwnershipConflict.REGISTRY_MISSING
    report = service.cleanup_disposable(HOST)
    assert root.is_dir()
    assert report.removed == 0
    assert str(root) in report.unresolved


def test_step0_rebuilds_registry_then_may_clean(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "tmp" / "abandoned"
    service.assert_owned(
        root,
        HOST,
        ManagedResourceType.TEMP,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    FileStore(tmp_path / "records").delete(
        OwnershipRecord, service.records()[0].ownership_id.value
    )
    report = step0_cleanup(service, HOST)
    assert report.removed == 1
    assert not root.exists()


def test_conflicting_identity_is_not_deleted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "models"
    record = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.MODEL_ARTIFACT,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    other = OwnershipRecord(
        ownership_id=OwnershipId.generate(),
        host_id=HOST,
        resource_type=ManagedResourceType.RUNTIME_FINAL,
        managed_root=str(root),
        created_at=record.created_at,
        kultrun_version=record.kultrun_version,
        created_by=record.created_by,
        lifecycle_state=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
        protected=False,
        rollback_protected=False,
        evidence_retained=False,
    )
    (root / LOCAL_OWNER_FILENAME).write_text(
        json.dumps(
            {
                **{
                    key: value
                    for key, value in json.loads(
                        (root / LOCAL_OWNER_FILENAME).read_text()
                    ).items()
                    if key != "ownership_id"
                },
                "ownership_id": other.ownership_id.value,
            }
        ),
        encoding="utf-8",
    )
    conflict, _found = service.classify(root)
    assert conflict in {
        OwnershipConflict.IDENTITY_MISMATCH,
        OwnershipConflict.REGISTRY_MISSING,
    }
    report = service.cleanup_disposable(HOST)
    assert root.is_dir()
    assert report.removed == 0


def test_active_resource_is_protected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "runtimes" / "live"
    service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_FINAL,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    report = step0_cleanup(service, HOST, active_roots=(root,))
    assert root.is_dir()
    assert report.removed == 0
    assert str(root) in report.unresolved or str(root) in report.protected


def test_rollback_and_evidence_are_protected(tmp_path: Path) -> None:
    service = _service(tmp_path)
    rollback = service.state_root / "runtimes" / "prior"
    evidence = service.state_root / "logs" / "capture"
    service.assert_owned(
        rollback,
        HOST,
        ManagedResourceType.RUNTIME_FINAL,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
        rollback_protected=True,
    )
    service.assert_owned(
        evidence,
        HOST,
        ManagedResourceType.LOGS,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
        evidence_retained=True,
    )
    report = step0_cleanup(service, HOST)
    assert rollback.is_dir()
    assert evidence.is_dir()
    assert report.removed == 0
    assert str(rollback) in report.protected
    assert str(evidence) in report.protected


def test_failed_staging_is_removed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "runtimes" / ".staging" / "attempt-1"
    (root / "venv").mkdir(parents=True)
    (root / "venv" / "junk").write_text("x", encoding="utf-8")
    service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_STAGING,
        lifecycle=LifecycleState.FAILED,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    report = step0_cleanup(service, HOST)
    assert report.removed == 1
    assert not root.exists()
    assert service.records() == ()


def test_unrelated_tree_is_untouched(tmp_path: Path) -> None:
    service = _service(tmp_path)
    customer = service.state_root / "customer-docs"
    customer.mkdir()
    (customer / "notes.txt").write_text("keep me", encoding="utf-8")
    report = step0_cleanup(service, HOST)
    assert (customer / "notes.txt").read_text(encoding="utf-8") == "keep me"
    assert report.removed == 0


def test_unlabelled_legacy_is_reported_not_deleted(tmp_path: Path) -> None:
    service = _service(tmp_path)
    legacy = service.state_root / "runtimes"
    leftover = legacy / "old-venv"
    leftover.mkdir(parents=True)
    (leftover / "file").write_text("legacy", encoding="utf-8")
    report = step0_cleanup(service, HOST)
    assert leftover.is_dir()
    assert (leftover / "file").read_text(encoding="utf-8") == "legacy"
    assert report.removed == 0
    assert any("runtimes" in item for item in report.legacy_unlabelled)


def test_cleanup_is_idempotent(tmp_path: Path) -> None:
    service = _service(tmp_path)
    root = service.state_root / "tmp" / "probe"
    service.assert_owned(
        root,
        HOST,
        ManagedResourceType.SONAR_PROBE,
        lifecycle=LifecycleState.DISPOSABLE,
        cleanup_policy=CleanupPolicy.DISPOSABLE,
    )
    first = step0_cleanup(service, HOST)
    second = step0_cleanup(service, HOST)
    assert first.removed == 1
    assert second.removed == 0
    assert second.rediscovery_required is True


def test_generation_is_a_lifecycle_seam_not_selection(tmp_path: Path) -> None:
    service = _service(tmp_path)
    generation = service.open_generation(HOST, rollback_protected=True)
    root = service.state_root / "runtimes" / "gen"
    owned = service.assert_owned(
        root,
        HOST,
        ManagedResourceType.RUNTIME_FINAL,
        installation_generation_id=generation.generation_id.value,
        protected=True,
    )
    attached = service.attach_to_generation(generation, owned.ownership_id)
    assert owned.ownership_id.value in attached.ownership_ids
    assert attached.rollback_protected is True
    assert attached.generation_id.value.startswith("igen_")
