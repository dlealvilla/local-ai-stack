"""InstallRecord (MACHI 1.1.1)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecord,
    InstallRecordStatus,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    StateRootBinding,
)
from machi.install.defaults import MACHI_OWNER_FILENAME
from machi.install.events import (
    INSTALL_RECORD_ESTABLISHED_TYPE,
    InstallRecordEstablishedPayload,
    install_record_established,
    root_fingerprint,
)
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ConflictError, ValidationError
from machi.kernel.ids import InstallId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.store import Store
from machi.kernel.unresolved import is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 15, 0, 30, tzinfo=dt.UTC)
KIND = "install_record"
BUILD_A = BuildIdentity(
    version="0.1.0",
    origin=BuildOrigin.ARTIFACT,
    source_commit="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    build_id="0.1.0+aaaaaaaaaaaa",
    built_at="2026-09-15T00:00:00+00:00",
    clean_source=True,
)
BUILD_B = BuildIdentity(
    version="0.1.1",
    origin=BuildOrigin.ARTIFACT,
    source_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    build_id="0.1.1+bbbbbbbbbbbb",
    built_at="2026-09-16T00:00:00+00:00",
    clean_source=True,
)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(FIXED)


@pytest.fixture
def binder(tmp_path: Path, clock: FixedClock) -> StateRootBinder:
    return StateRootBinder(clock=clock, default_root=tmp_path / "unused-default")


@pytest.fixture
def marker(clock: FixedClock) -> SelfOwnershipMarker:
    return SelfOwnershipMarker(clock=clock)


@pytest.fixture
def seeder(clock: FixedClock) -> RegistrySeed:
    return RegistrySeed(clock=clock)


@pytest.fixture
def identity(clock: FixedClock) -> InstallIdentity:
    return InstallIdentity(clock=clock)


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "control-plane")


def _key(establishment: LocalOwnershipEstablishment) -> str:
    return establishment.marker.marker_id.value


def _path(store: FileStore, marker_id: str) -> Path:
    return store.root / KIND / f"{marker_id}.json"


def _owned(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    store: FileStore,
    root: Path,
) -> tuple[
    StateRootBinding,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
]:
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    seeded = seeder.seed(binding, establishment, store)
    return binding, establishment, seeded


def test_install_identity_consumes_the_store_port(store: FileStore) -> None:
    assert isinstance(store, Store)


def test_first_establish_mints_one_install_id(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding, establishment, seeded = _owned(binder, marker, seeder, store, root)
    result = identity.establish(binding, establishment, seeded, store, BUILD_A)
    dest = _path(store, _key(establishment))
    assert dest.is_file()
    assert result.status is InstallRecordStatus.INSTALL_RECORD_PRESENT
    assert result.created is True
    assert result.existed is False
    assert result.dual_ownership is False
    assert result.destructive_authorization is False
    assert result.record.install_id.value.startswith("inst_")
    assert result.record.marker_id == establishment.marker.marker_id
    assert result.record.root_fingerprint == establishment.marker.root_fingerprint
    assert result.record.created_by_build_id == BUILD_A.build_id
    assert result.record.created_by_origin == "artifact"
    document = json.loads(dest.read_text(encoding="utf-8"))
    assert document["kind"] == KIND
    assert document["record_key"] == _key(establishment)
    assert str(root.resolve()) not in json.dumps(document)
    assert str(store.root) not in json.dumps(document)
    assert not (root / KIND).exists()
    assert "irun_" not in json.dumps(document)
    assert "host_" not in json.dumps(document)


def test_reentry_preserves_install_id_and_does_not_rewrite(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "once"
    binding, establishment, seeded = _owned(binder, marker, seeder, store, root)
    first = identity.establish(binding, establishment, seeded, store, BUILD_A)
    original = _path(store, first.record.marker_id.value).read_text(encoding="utf-8")
    later = InstallIdentity(clock=FixedClock(FIXED + dt.timedelta(hours=1)))
    second = later.establish(binding, establishment, seeded, store, BUILD_A)
    assert second.record.install_id == first.record.install_id
    assert second.record.created_at == first.record.created_at
    assert second.record.created_by_build_id == first.record.created_by_build_id
    assert second.existed is True
    assert second.created is False
    assert _path(store, first.record.marker_id.value).read_text(encoding="utf-8") == (
        original
    )


def test_different_build_reentry_keeps_creation_provenance(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "upgrade"
    binding, establishment, seeded = _owned(binder, marker, seeder, store, root)
    first = identity.establish(binding, establishment, seeded, store, BUILD_A)
    second = identity.establish(binding, establishment, seeded, store, BUILD_B)
    assert second.record.install_id == first.record.install_id
    assert second.record.created_by_build_id == BUILD_A.build_id
    assert second.record.created_by_source_commit == BUILD_A.source_commit
    assert second.record.created_by_version == BUILD_A.version
    assert second.existed is True
    assert second.created is False


def test_root_marker_mismatch_fails_closed_without_writing(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    _bind_a, est_a, seeded_a = _owned(binder, marker, seeder, store, tmp_path / "a")
    bind_b = binder.bind(explicit=tmp_path / "b")
    with pytest.raises(ConflictError, match="do not agree"):
        identity.establish(bind_b, est_a, seeded_a, store, BUILD_A)
    assert list((store.root / KIND).glob("*.json")) == []


def test_registry_mismatch_fails_closed_without_writing(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    bind_a, est_a, _seeded_a = _owned(binder, marker, seeder, store, tmp_path / "a")
    _bind_b, _est_b, seeded_b = _owned(binder, marker, seeder, store, tmp_path / "b")
    with pytest.raises(ConflictError, match="do not agree"):
        identity.establish(bind_a, est_a, seeded_b, store, BUILD_A)
    assert list((store.root / KIND).glob("*.json")) == []


def test_marker_b_with_registry_b_on_root_a_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    bind_a, _est_a, _seeded_a = _owned(binder, marker, seeder, store, tmp_path / "a")
    _bind_b, est_b, seeded_b = _owned(binder, marker, seeder, store, tmp_path / "b")
    with pytest.raises(ConflictError, match="do not agree"):
        identity.establish(bind_a, est_b, seeded_b, store, BUILD_A)
    assert list((store.root / KIND).glob("*.json")) == []


def test_two_installations_coexist_in_one_store(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    bind_a, est_a, seeded_a = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    bind_b, est_b, seeded_b = _owned(
        binder, marker, seeder, store, tmp_path / "installation-b"
    )
    record_a = identity.establish(bind_a, est_a, seeded_a, store, BUILD_A)
    record_b = identity.establish(bind_b, est_b, seeded_b, store, BUILD_A)
    assert record_a.record.install_id != record_b.record.install_id
    assert record_a.record.marker_id != record_b.record.marker_id
    assert record_a.record.root_fingerprint != record_b.record.root_fingerprint
    again_a = identity.establish(bind_a, est_a, seeded_a, store, BUILD_A)
    assert again_a.record.install_id == record_a.record.install_id
    loaded_b = store.get(InstallRecord, _key(est_b))
    assert loaded_b == record_b.record


def test_copied_root_cannot_obtain_an_install_record(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    bind_a, est_a, seeded_a = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    original = identity.establish(bind_a, est_a, seeded_a, store, BUILD_A)
    dest = _path(store, original.record.marker_id.value)
    original_bytes = dest.read_text(encoding="utf-8")
    copied = tmp_path / "installation-copy"
    shutil.copytree(tmp_path / "installation-a", copied)
    bind_copy = binder.bind(explicit=copied)
    with pytest.raises(ConflictError, match="copied marker"):
        marker.establish(bind_copy)
    with pytest.raises(ConflictError, match="do not agree"):
        identity.establish(bind_copy, est_a, seeded_a, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == original_bytes
    assert list((store.root / KIND).glob("*.json")) == [dest]


def test_conflicting_install_record_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    binding, establishment, seeded = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    first = identity.establish(binding, establishment, seeded, store, BUILD_A)
    dest = _path(store, first.record.marker_id.value)
    payload = json.loads(dest.read_text(encoding="utf-8"))
    payload["root_fingerprint"] = root_fingerprint(str((tmp_path / "other").resolve()))
    payload["install_id"] = InstallId.generate().value
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ConflictError, match="does not match"):
        identity.establish(binding, establishment, seeded, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == before


def test_malformed_install_record_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    binding, establishment, seeded = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    first = identity.establish(binding, establishment, seeded, store, BUILD_A)
    dest = _path(store, first.record.marker_id.value)
    dest.write_text("{broken\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="malformed JSON"):
        identity.establish(binding, establishment, seeded, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == "{broken\n"


def test_unsupported_schema_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    binding, establishment, seeded = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    dest_dir = store.root / KIND
    dest_dir.mkdir(parents=True)
    dest = dest_dir / f"{_key(establishment)}.json"
    dest.write_text(
        json.dumps(
            {
                "kind": KIND,
                "schema_version": 99,
                "record_key": _key(establishment),
                "install_id": InstallId.generate().value,
                "marker_id": _key(establishment),
                "product": "machi",
                "root_fingerprint": establishment.marker.root_fingerprint,
                "created_at": FIXED.isoformat().replace("+00:00", "Z"),
                "created_by_version": "0.1.0",
                "created_by_origin": "artifact",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="refusing to repair"):
        identity.establish(binding, establishment, seeded, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == before


def test_corruption_is_local_to_the_affected_record(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    seeded_records = []
    for name in ("a", "b", "c"):
        binding, establishment, seeded = _owned(
            binder, marker, seeder, store, tmp_path / name
        )
        seeded_records.append(
            identity.establish(binding, establishment, seeded, store, BUILD_A)
        )
    broken = _path(store, seeded_records[1].record.marker_id.value)
    broken.write_text("{broken\n", encoding="utf-8")
    loaded_a = store.get(InstallRecord, seeded_records[0].record.marker_id.value)
    assert loaded_a == seeded_records[0].record
    with pytest.raises(ValidationError, match="malformed JSON"):
        store.get(InstallRecord, seeded_records[1].record.marker_id.value)
    loaded_c = store.get(InstallRecord, seeded_records[2].record.marker_id.value)
    assert loaded_c == seeded_records[2].record


def test_event_resolves_install_id_and_keeps_run_and_host_unresolved(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    binding, establishment, seeded = _owned(
        binder, marker, seeder, store, tmp_path / "installation-a"
    )
    result = identity.establish(binding, establishment, seeded, store, BUILD_A)
    event = install_record_established(result)
    assert event.event_type.value == INSTALL_RECORD_ESTABLISHED_TYPE
    assert event.component_id.value == "1.1.1"
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, InstallRecordEstablishedPayload)
    assert is_resolved(event.install_id)
    assert event.install_id == result.record.install_id
    assert "install_run_id" in unresolved_fields(event)
    assert "host_id" in unresolved_fields(event)
    blob = json.dumps(to_dict(event))
    assert str((tmp_path / "installation-a").resolve()) not in blob
    assert str(store.root) not in blob
    assert "install.completed" not in blob
    assert "ownership.verified" not in blob
    assert event.payload.destructive_authorization is False


def test_cli_establish_reentry_and_separate_store_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    control = tmp_path / "control-plane"
    assert (
        main(
            [
                "install",
                "establish-record",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    first = capsys.readouterr().out
    assert '"kind": "install_record"' in first
    assert '"status": "install_record_present"' in first
    assert '"event_type": "install.record.established"' in first
    assert '"privacy": "restricted"' in first
    assert '"dual_ownership": true' not in first
    assert '"destructive_authorization": true' not in first
    event_at = first.find('"kind": "event_record"')
    assert event_at >= 0
    assert str(root.resolve()) not in first[event_at:]
    assert str(control.resolve()) not in first[event_at:]
    assert (root / MACHI_OWNER_FILENAME).is_file()
    assert not (root / KIND).exists()
    journal = (root / "journal" / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in journal.splitlines()]
    bound = next(
        item for item in events if item.get("event_type") == "install.state_root.bound"
    )
    established = next(
        item
        for item in events
        if item.get("event_type") == "install.record.established"
    )
    assert "$unresolved" in json.dumps(bound["install_id"])
    assert isinstance(established["install_id"], str)
    assert established["install_id"].startswith("inst_")
    assert "$unresolved" in json.dumps(established["install_run_id"])
    assert "$unresolved" in json.dumps(established["host_id"])
    assert (
        main(
            [
                "install",
                "establish-record",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    second = capsys.readouterr().out
    assert "created  false" in second
    assert '"created": false' in second


def test_cli_copied_root_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    control = tmp_path / "control-plane"
    assert (
        main(
            [
                "install",
                "establish-record",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    capsys.readouterr()
    copied = tmp_path / "installation-copy"
    shutil.copytree(root, copied)
    assert (
        main(
            [
                "install",
                "establish-record",
                "--state-root",
                str(copied),
                "--store-dir",
                str(control),
            ]
        )
        == 2
    )
    assert "copied marker" in capsys.readouterr().err
    assert not (control / KIND / "copied").exists()
    assert len(list((control / KIND).glob("*.json"))) == 1
