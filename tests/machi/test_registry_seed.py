"""RegistrySeed (MACHI 1.3.2)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryRecord,
    RegistrySeedStatus,
)
from machi.install.defaults import MACHI_OWNER_FILENAME
from machi.install.events import (
    REGISTRY_SEEDED_TYPE,
    OwnershipRegistrySeededPayload,
    ownership_registry_seeded,
    root_fingerprint,
)
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.store import Store
from machi.main import main

FIXED = dt.datetime(2026, 9, 14, 23, 30, tzinfo=dt.UTC)
KIND = "local_ownership_registry_record"


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
def registry(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "control-registry")


def _key(establishment: LocalOwnershipEstablishment) -> str:
    return establishment.marker.marker_id.value


def _record_path(store: FileStore, marker_id: str) -> Path:
    return store.root / KIND / f"{marker_id}.json"


def test_registry_seed_consumes_the_store_port(registry: FileStore) -> None:
    assert isinstance(registry, Store)


def test_first_seed_creates_one_registry_record(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    result = seeder.seed(binding, establishment, registry)
    dest = _record_path(registry, _key(establishment))
    assert dest.is_file()
    assert result.status is RegistrySeedStatus.REGISTRY_SEED_PRESENT
    assert result.dual_ownership is False
    assert result.destructive_authorization is False
    assert result.created is True
    assert result.existed is False
    assert result.record.marker_id == establishment.marker.marker_id
    assert result.record.root_fingerprint == establishment.marker.root_fingerprint
    assert result.record.product == "machi"
    assert result.record.created_at == FIXED
    document = json.loads(dest.read_text(encoding="utf-8"))
    assert document["kind"] == KIND
    assert document["record_key"] == _key(establishment)
    assert str(root.resolve()) not in json.dumps(document)
    assert str(registry.root) not in json.dumps(document)
    assert not (root / KIND).exists()


def test_reentry_preserves_registry_identity_and_does_not_rewrite(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "once"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    first = seeder.seed(binding, establishment, registry)
    original = _record_path(registry, first.record.marker_id.value).read_text(
        encoding="utf-8"
    )
    later = RegistrySeed(clock=FixedClock(FIXED + dt.timedelta(hours=1)))
    second = later.seed(binding, establishment, registry)
    assert second.record.marker_id == first.record.marker_id
    assert second.record.created_at == first.record.created_at
    assert second.record.root_fingerprint == first.record.root_fingerprint
    assert second.existed is True
    assert second.created is False
    assert (
        _record_path(registry, first.record.marker_id.value).read_text(encoding="utf-8")
        == original
    )


def test_root_marker_mismatch_fails_closed_without_writing(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    binding_a = binder.bind(explicit=root_a)
    establishment_a = marker.establish(binding_a)
    binding_b = binder.bind(explicit=root_b)
    with pytest.raises(ConflictError, match="do not agree"):
        seeder.seed(binding_b, establishment_a, registry)
    assert list(registry.root.rglob("*.json")) == []


def test_two_markers_coexist_in_one_registry(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "installation-a"
    root_b = tmp_path / "installation-b"
    bind_a = binder.bind(explicit=root_a)
    bind_b = binder.bind(explicit=root_b)
    est_a = marker.establish(bind_a)
    est_b = marker.establish(bind_b)
    seeded_a = seeder.seed(bind_a, est_a, registry)
    seeded_b = seeder.seed(bind_b, est_b, registry)
    assert seeded_a.record.marker_id != seeded_b.record.marker_id
    assert seeded_a.record.root_fingerprint != seeded_b.record.root_fingerprint
    again_a = seeder.seed(bind_a, est_a, registry)
    assert again_a.record.marker_id == seeded_a.record.marker_id
    assert again_a.record.created_at == seeded_a.record.created_at
    loaded_b = registry.get(LocalOwnershipRegistryRecord, _key(est_b))
    assert loaded_b == seeded_b.record


def test_copied_root_cannot_be_seeded(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "installation-a"
    bind_a = binder.bind(explicit=root_a)
    est_a = marker.establish(bind_a)
    original = seeder.seed(bind_a, est_a, registry)
    dest = _record_path(registry, original.record.marker_id.value)
    original_bytes = dest.read_text(encoding="utf-8")
    copied = tmp_path / "installation-copy"
    shutil.copytree(root_a, copied)
    bind_copy = binder.bind(explicit=copied)
    with pytest.raises(ConflictError, match="copied marker"):
        marker.establish(bind_copy)
    with pytest.raises(ConflictError, match="do not agree"):
        seeder.seed(bind_copy, est_a, registry)
    assert dest.read_text(encoding="utf-8") == original_bytes
    assert list((registry.root / KIND).glob("*.json")) == [dest]


def test_conflicting_registry_record_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    first = seeder.seed(binding, establishment, registry)
    dest = _record_path(registry, first.record.marker_id.value)
    payload = json.loads(dest.read_text(encoding="utf-8"))
    other = tmp_path / "other"
    payload["root_fingerprint"] = root_fingerprint(str(other.resolve()))
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ConflictError, match="does not match"):
        seeder.seed(binding, establishment, registry)
    assert dest.read_text(encoding="utf-8") == before


def test_malformed_registry_record_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    first = seeder.seed(binding, establishment, registry)
    dest = _record_path(registry, first.record.marker_id.value)
    dest.write_text("{broken\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="malformed JSON"):
        seeder.seed(binding, establishment, registry)
    assert dest.read_text(encoding="utf-8") == "{broken\n"


def test_unsupported_schema_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    dest_dir = registry.root / KIND
    dest_dir.mkdir(parents=True)
    dest = dest_dir / f"{_key(establishment)}.json"
    dest.write_text(
        json.dumps(
            {
                "kind": KIND,
                "schema_version": 99,
                "record_key": _key(establishment),
                "marker_id": _key(establishment),
                "product": "machi",
                "root_fingerprint": establishment.marker.root_fingerprint,
                "created_at": FIXED.isoformat().replace("+00:00", "Z"),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="refusing to repair"):
        seeder.seed(binding, establishment, registry)
    assert dest.read_text(encoding="utf-8") == before


def test_corruption_is_local_to_the_affected_record(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    seeded = []
    for name in ("a", "b", "c"):
        binding = binder.bind(explicit=tmp_path / name)
        establishment = marker.establish(binding)
        seeded.append(seeder.seed(binding, establishment, registry))
    broken = _record_path(registry, seeded[1].record.marker_id.value)
    broken.write_text("{broken\n", encoding="utf-8")
    loaded_a = registry.get(
        LocalOwnershipRegistryRecord, seeded[0].record.marker_id.value
    )
    assert loaded_a == seeded[0].record
    with pytest.raises(ValidationError, match="malformed JSON"):
        registry.get(LocalOwnershipRegistryRecord, seeded[1].record.marker_id.value)
    loaded_c = registry.get(
        LocalOwnershipRegistryRecord, seeded[2].record.marker_id.value
    )
    assert loaded_c == seeded[2].record


def test_two_registry_stores_are_isolated(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    tmp_path: Path,
) -> None:
    store_a = FileStore(tmp_path / "control-a")
    store_b = FileStore(tmp_path / "control-b")
    binding = binder.bind(explicit=tmp_path / "installation-a")
    establishment = marker.establish(binding)
    seeded = seeder.seed(binding, establishment, store_a)
    with pytest.raises(NotFoundError):
        store_b.get(LocalOwnershipRegistryRecord, _key(establishment))
    assert (
        store_a.get(LocalOwnershipRegistryRecord, _key(establishment)) == seeded.record
    )


def test_seed_event_is_restricted_and_omits_paths(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    registry: FileStore,
    tmp_path: Path,
) -> None:
    root = tmp_path / "installation-a"
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    seeded = seeder.seed(binding, establishment, registry)
    event = ownership_registry_seeded(seeded)
    assert event.event_type.value == REGISTRY_SEEDED_TYPE
    assert event.component_id.value == "1.3.2"
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, OwnershipRegistrySeededPayload)
    blob = json.dumps(to_dict(event))
    assert str(root.resolve()) not in blob
    assert str(registry.root) not in blob
    assert "ownership.verified" not in blob
    assert event.payload.dual_ownership is False
    assert event.payload.destructive_authorization is False
    assert "install_run_id" in unresolved_fields(event)


def test_cli_seed_reentry_and_separate_registry_tree(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    registry = tmp_path / "control-registry"
    assert (
        main(
            [
                "install",
                "seed-registry",
                "--state-root",
                str(root),
                "--registry-store-dir",
                str(registry),
            ]
        )
        == 0
    )
    first = capsys.readouterr().out
    assert '"kind": "local_ownership_registry_record"' in first
    assert '"status": "registry_seed_present"' in first
    assert '"event_type": "install.ownership.registry_seeded"' in first
    assert '"privacy": "restricted"' in first
    assert '"dual_ownership": true' not in first
    assert '"destructive_authorization": true' not in first
    event_at = first.find('"kind": "event_record"')
    assert event_at >= 0
    assert str(root.resolve()) not in first[event_at:]
    assert str(registry.resolve()) not in first[event_at:]
    assert (root / MACHI_OWNER_FILENAME).is_file()
    assert not (root / KIND).exists()
    assert (
        main(
            [
                "install",
                "seed-registry",
                "--state-root",
                str(root),
                "--registry-store-dir",
                str(registry),
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
    registry = tmp_path / "control-registry"
    assert (
        main(
            [
                "install",
                "seed-registry",
                "--state-root",
                str(root),
                "--registry-store-dir",
                str(registry),
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
                "seed-registry",
                "--state-root",
                str(copied),
                "--registry-store-dir",
                str(registry),
            ]
        )
        == 2
    )
    assert "copied marker" in capsys.readouterr().err
