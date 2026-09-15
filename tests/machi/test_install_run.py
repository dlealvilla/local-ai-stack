"""InstallRunStore (MACHI 1.4.1)."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import threading
from pathlib import Path

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecord,
    InstallRunRecord,
    InstallRunStatus,
)
from machi.install.defaults import MACHI_OWNER_FILENAME
from machi.install.events import (
    INSTALL_BOUND_TYPE,
    InstallBoundPayload,
    install_bound,
)
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.install.run import InstallRunStore
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, to_dict, unresolved_fields
from machi.kernel.store import RecordT, Store, StoreCreateResult
from machi.kernel.unresolved import is_resolved
from machi.main import main

FIXED = dt.datetime(2026, 9, 15, 2, 0, tzinfo=dt.UTC)
KIND = "install_run"
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
def runs(clock: FixedClock) -> InstallRunStore:
    return InstallRunStore(clock=clock)


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "control-plane")


def _install(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    root: Path,
) -> InstallRecord:
    binding = binder.bind(explicit=root)
    establishment = marker.establish(binding)
    seeded = seeder.seed(binding, establishment, store)
    return identity.establish(binding, establishment, seeded, store, BUILD_A).record


def _path(store: FileStore, install_id: str) -> Path:
    return store.root / KIND / f"{install_id}.json"


def test_install_run_store_consumes_the_store_port(store: FileStore) -> None:
    assert isinstance(store, Store)


def test_first_establish_mints_one_install_run_id(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    result = runs.establish(record, store, BUILD_A)
    dest = _path(store, record.install_id.value)
    assert dest.is_file()
    assert result.status is InstallRunStatus.INSTALL_RUN_PRESENT
    assert result.created is True
    assert result.existed is False
    assert result.dual_ownership is False
    assert result.destructive_authorization is False
    assert result.record.install_run_id.value.startswith("irun_")
    assert result.record.install_id == record.install_id
    assert result.record.created_by_build_id == BUILD_A.build_id
    document = json.loads(dest.read_text(encoding="utf-8"))
    assert document["kind"] == KIND
    assert document["record_key"] == record.install_id.value
    assert str((tmp_path / "installation-a").resolve()) not in json.dumps(document)
    assert str(store.root) not in json.dumps(document)
    assert not (tmp_path / "installation-a" / KIND).exists()
    assert "host_" not in json.dumps(document)


def test_reentry_preserves_install_run_id_and_does_not_rewrite(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(binder, marker, seeder, identity, store, tmp_path / "once")
    first = runs.establish(record, store, BUILD_A)
    original = _path(store, record.install_id.value).read_text(encoding="utf-8")
    later = InstallRunStore(clock=FixedClock(FIXED + dt.timedelta(hours=1)))
    second = later.establish(record, store, BUILD_A)
    third = InstallRunStore(clock=FixedClock(FIXED + dt.timedelta(hours=2))).establish(
        record, store, BUILD_A
    )
    assert second.record.install_run_id == first.record.install_run_id
    assert third.record.install_run_id == first.record.install_run_id
    assert second.record.created_at == first.record.created_at
    assert second.record.created_by_build_id == first.record.created_by_build_id
    assert second.existed is True
    assert second.created is False
    assert _path(store, record.install_id.value).read_text(encoding="utf-8") == original


def test_different_build_reentry_keeps_creation_provenance(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(binder, marker, seeder, identity, store, tmp_path / "upgrade")
    first = runs.establish(record, store, BUILD_A)
    second = runs.establish(record, store, BUILD_B)
    assert second.record.install_run_id == first.record.install_run_id
    assert second.record.created_by_build_id == BUILD_A.build_id
    assert second.record.created_by_source_commit == BUILD_A.source_commit
    assert second.record.created_by_version == BUILD_A.version
    assert second.existed is True
    assert second.created is False


def test_two_installations_coexist_in_one_store(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record_a = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    record_b = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-b"
    )
    run_a = runs.establish(record_a, store, BUILD_A)
    run_b = runs.establish(record_b, store, BUILD_A)
    assert run_a.record.install_run_id != run_b.record.install_run_id
    assert run_a.record.install_id != run_b.record.install_id
    again_a = runs.establish(record_a, store, BUILD_A)
    assert again_a.record.install_run_id == run_a.record.install_run_id
    loaded_b = store.get(InstallRunRecord, record_b.install_id.value)
    assert loaded_b == run_b.record


def test_copied_root_cannot_obtain_an_install_run(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    original = runs.establish(record, store, BUILD_A)
    dest = _path(store, record.install_id.value)
    original_bytes = dest.read_text(encoding="utf-8")
    copied = tmp_path / "installation-copy"
    shutil.copytree(tmp_path / "installation-a", copied)
    bind_copy = binder.bind(explicit=copied)
    with pytest.raises(ConflictError, match="copied marker"):
        marker.establish(bind_copy)
    assert dest.read_text(encoding="utf-8") == original_bytes
    assert list((store.root / KIND).glob("*.json")) == [dest]
    assert original.record.install_run_id.value.startswith("irun_")


def test_conflicting_install_run_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    first = runs.establish(record, store, BUILD_A)
    dest = _path(store, record.install_id.value)
    payload = json.loads(dest.read_text(encoding="utf-8"))
    payload["install_id"] = InstallId.generate().value
    payload["install_run_id"] = InstallRunId.generate().value
    dest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ConflictError, match="does not match"):
        runs.establish(record, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == before
    assert first.record.install_run_id.value.startswith("irun_")


def test_malformed_install_run_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    first = runs.establish(record, store, BUILD_A)
    dest = _path(store, record.install_id.value)
    dest.write_text("{broken\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="malformed JSON"):
        runs.establish(record, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == "{broken\n"
    assert first.record.install_run_id.value.startswith("irun_")


def test_unsupported_schema_fails_closed(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    dest_dir = store.root / KIND
    dest_dir.mkdir(parents=True)
    dest = dest_dir / f"{record.install_id.value}.json"
    dest.write_text(
        json.dumps(
            {
                "kind": KIND,
                "schema_version": 99,
                "record_key": record.install_id.value,
                "install_run_id": InstallRunId.generate().value,
                "install_id": record.install_id.value,
                "product": "machi",
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
        runs.establish(record, store, BUILD_A)
    assert dest.read_text(encoding="utf-8") == before


def test_invalid_install_record_input_fails_closed(
    runs: InstallRunStore,
    store: FileStore,
) -> None:
    with pytest.raises(ValidationError, match="valid InstallRecord"):
        runs.establish(object(), store, BUILD_A)  # type: ignore[arg-type]


def test_corruption_is_local_to_the_affected_record(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    records = []
    established = []
    for name in ("a", "b", "c"):
        record = _install(binder, marker, seeder, identity, store, tmp_path / name)
        records.append(record)
        established.append(runs.establish(record, store, BUILD_A))
    broken = _path(store, records[1].install_id.value)
    broken.write_text("{broken\n", encoding="utf-8")
    loaded_a = store.get(InstallRunRecord, records[0].install_id.value)
    assert loaded_a == established[0].record
    with pytest.raises(ValidationError, match="malformed JSON"):
        store.get(InstallRunRecord, records[1].install_id.value)
    loaded_c = store.get(InstallRunRecord, records[2].install_id.value)
    assert loaded_c == established[2].record


def test_event_resolves_install_and_run_and_keeps_host_unresolved(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    runs: InstallRunStore,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(
        binder, marker, seeder, identity, store, tmp_path / "installation-a"
    )
    result = runs.establish(record, store, BUILD_A)
    event = install_bound(result, record)
    assert event.event_type.value == INSTALL_BOUND_TYPE
    assert event.component_id.value == "1.4.1"
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, InstallBoundPayload)
    assert is_resolved(event.install_id)
    assert is_resolved(event.install_run_id)
    assert event.install_id == record.install_id
    assert event.install_run_id == result.record.install_run_id
    assert "host_id" in unresolved_fields(event)
    blob = json.dumps(to_dict(event))
    assert str((tmp_path / "installation-a").resolve()) not in blob
    assert str(store.root) not in blob
    assert "install.completed" not in blob
    assert "ownership.verified" not in blob
    assert event.payload.destructive_authorization is False
    assert event.payload.status == "install_bound"


def test_concurrent_first_create_converges_on_one_run(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    store: FileStore,
    tmp_path: Path,
) -> None:
    record = _install(binder, marker, seeder, identity, store, tmp_path / "race")
    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            results.append(InstallRunStore().establish(record, store, BUILD_A))
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=worker)
    second = threading.Thread(target=worker)
    first.start()
    second.start()
    first.join()
    second.join()
    assert errors == []
    assert len(results) == 2
    ids = {item.record.install_run_id for item in results}  # type: ignore[attr-defined]
    assert len(ids) == 1
    assert len(list((store.root / KIND).glob("*.json"))) == 1
    loaded = store.get(InstallRunRecord, record.install_id.value)
    assert loaded.install_run_id in ids


def test_conflict_on_create_returns_persisted_winner(
    binder: StateRootBinder,
    marker: SelfOwnershipMarker,
    seeder: RegistrySeed,
    identity: InstallIdentity,
    tmp_path: Path,
) -> None:
    inner = FileStore(tmp_path / "control-plane")
    record = _install(
        binder, marker, seeder, identity, inner, tmp_path / "installation-a"
    )
    winner = InstallRunRecord(
        install_run_id=InstallRunId.generate(),
        install_id=record.install_id,
        product="machi",
        created_at=FIXED,
        created_by_version=BUILD_A.version,
        created_by_origin=BUILD_A.origin.value,
        created_by_build_id=BUILD_A.build_id,
        created_by_source_commit=BUILD_A.source_commit,
        created_by_clean_source=BUILD_A.clean_source,
    )

    class RaceStore:
        def get(self, contract_type: type[RecordT], key: str) -> RecordT:
            if inner.root.joinpath(KIND, f"{key}.json").is_file():
                return inner.get(contract_type, key)
            raise NotFoundError("stored record does not exist", key=key)

        def create(self, key: str, record: Contract) -> StoreCreateResult:
            if not inner.root.joinpath(KIND, f"{key}.json").is_file():
                inner.create(key, winner)
            raise ConflictError(
                "stored record already exists and does not match; "
                "refusing to overwrite",
                key=key,
            )

    result = InstallRunStore(clock=FixedClock(FIXED)).establish(
        record, RaceStore(), BUILD_A
    )
    assert result.created is False
    assert result.existed is True
    assert result.record.install_run_id == winner.install_run_id
    persisted = inner.get(InstallRunRecord, record.install_id.value)
    assert persisted.install_run_id == winner.install_run_id
    assert len(list((inner.root / KIND).glob("*.json"))) == 1


def test_cli_establish_run_reentry_and_correlation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    control = tmp_path / "control-plane"
    assert (
        main(
            [
                "install",
                "establish-run",
                "--state-root",
                str(root),
                "--store-dir",
                str(control),
            ]
        )
        == 0
    )
    first = capsys.readouterr().out
    assert '"kind": "install_run"' in first
    assert '"status": "install_run_present"' in first
    assert '"event_type": "install.bound"' in first
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
    install_bound_event = next(
        item for item in events if item.get("event_type") == "install.bound"
    )
    assert "$unresolved" in json.dumps(bound["install_id"])
    assert "$unresolved" in json.dumps(bound["install_run_id"])
    assert isinstance(established["install_id"], str)
    assert established["install_id"].startswith("inst_")
    assert "$unresolved" in json.dumps(established["install_run_id"])
    assert isinstance(install_bound_event["install_id"], str)
    assert install_bound_event["install_id"].startswith("inst_")
    assert isinstance(install_bound_event["install_run_id"], str)
    assert install_bound_event["install_run_id"].startswith("irun_")
    assert "$unresolved" in json.dumps(install_bound_event["host_id"])
    first_run = next(
        line for line in first.splitlines() if line.startswith("run      ")
    ).split()[1]
    assert (
        main(
            [
                "install",
                "establish-run",
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
    second_run = next(
        line for line in second.splitlines() if line.startswith("run      ")
    ).split()[1]
    assert second_run == first_run
    later = [
        json.loads(line)
        for line in (root / "journal" / "events.jsonl").read_text().splitlines()
    ]
    first_bound = next(
        item for item in events if item.get("event_type") == "install.state_root.bound"
    )
    still_bound = next(
        item for item in later if item.get("event_type") == "install.state_root.bound"
    )
    assert still_bound["event_id"] == first_bound["event_id"]
    assert "$unresolved" in json.dumps(still_bound["install_run_id"])


def test_cli_copied_root_cannot_establish_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "installation-a"
    control = tmp_path / "control-plane"
    assert (
        main(
            [
                "install",
                "establish-run",
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
                "establish-run",
                "--state-root",
                str(copied),
                "--store-dir",
                str(control),
            ]
        )
        == 2
    )
    assert "copied marker" in capsys.readouterr().err
    assert len(list((control / KIND).glob("*.json"))) == 1
