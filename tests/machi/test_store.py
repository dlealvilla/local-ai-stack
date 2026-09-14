"""Kernel Store (MACHI 0.4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.install.defaults import store_dir
from machi.kernel.errors import (
    ConflictError,
    NotFoundError,
    PersistenceError,
    ValidationError,
)
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict, unresolved_fields
from machi.kernel.store import Store, validate_record_key
from machi.kernel.store_proof import (
    STORE_PROVED_TYPE,
    StoreProof,
    StoreProvedPayload,
    store_proved,
)
from machi.main import main


@pytest.fixture
def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "store")


def test_file_store_satisfies_the_port(store: FileStore) -> None:
    assert isinstance(store, Store)


def test_create_then_get_round_trips(store: FileStore) -> None:
    proof = StoreProof(token="alpha")
    result = store.create("proof-a", proof)
    assert result.created is True
    assert result.existed is False
    loaded = store.get(StoreProof, "proof-a")
    assert loaded == proof
    document = json.loads(
        (store.root / "kernel.store.proof" / "proof-a.json").read_text(encoding="utf-8")
    )
    assert document["kind"] == "kernel.store.proof"
    assert document["schema_version"] == 1
    assert document["record_key"] == "proof-a"
    assert document["token"] == "alpha"


def test_fresh_adapter_instance_reads_what_another_wrote(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    FileStore(root).create("proof-a", StoreProof(token="shared"))
    loaded = FileStore(root).get(StoreProof, "proof-a")
    assert loaded == StoreProof(token="shared")


def test_missing_entity_is_not_found(store: FileStore) -> None:
    with pytest.raises(NotFoundError, match="does not exist"):
        store.get(StoreProof, "never-written")


def test_identical_reentry_does_not_overwrite(store: FileStore) -> None:
    first = store.create("proof-a", StoreProof(token="same"))
    original = (store.root / "kernel.store.proof" / "proof-a.json").read_text(
        encoding="utf-8"
    )
    second = store.create("proof-a", StoreProof(token="same"))
    assert second.created is False
    assert second.existed is True
    assert second.record == first.record
    assert (store.root / "kernel.store.proof" / "proof-a.json").read_text(
        encoding="utf-8"
    ) == original


def test_conflicting_same_key_fails_closed(store: FileStore) -> None:
    store.create("proof-a", StoreProof(token="one"))
    before = (store.root / "kernel.store.proof" / "proof-a.json").read_text(
        encoding="utf-8"
    )
    with pytest.raises(ConflictError, match="does not match"):
        store.create("proof-a", StoreProof(token="two"))
    assert (store.root / "kernel.store.proof" / "proof-a.json").read_text(
        encoding="utf-8"
    ) == before


def test_malformed_existing_entity_fails_closed(store: FileStore) -> None:
    store.create("proof-a", StoreProof(token="ok"))
    dest = store.root / "kernel.store.proof" / "proof-a.json"
    dest.write_text("{not-json\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="malformed JSON"):
        store.get(StoreProof, "proof-a")
    with pytest.raises(ValidationError, match="malformed JSON"):
        store.create("proof-a", StoreProof(token="repair"))
    assert dest.read_text(encoding="utf-8") == "{not-json\n"


def test_unsupported_schema_fails_closed(store: FileStore) -> None:
    dest_dir = store.root / "kernel.store.proof"
    dest_dir.mkdir(parents=True)
    dest = dest_dir / "future.json"
    dest.write_text(
        json.dumps(
            {
                "kind": "kernel.store.proof",
                "schema_version": 99,
                "record_key": "future",
                "token": "x",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = dest.read_text(encoding="utf-8")
    with pytest.raises(ValidationError, match="refusing to repair"):
        store.get(StoreProof, "future")
    assert dest.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    "key",
    ["../escape", "nested/key", "..", ".hidden", "with space", "", "/etc/passwd"],
)
def test_unsafe_keys_are_refused_not_sanitized(store: FileStore, key: str) -> None:
    with pytest.raises(ValidationError):
        validate_record_key(key)
    with pytest.raises(ValidationError):
        store.create(key, StoreProof(token="nope"))


def test_two_store_roots_are_isolated(tmp_path: Path) -> None:
    store_a = FileStore(tmp_path / "a")
    store_b = FileStore(tmp_path / "b")
    store_a.create("shared-key", StoreProof(token="from-a"))
    store_b.create("shared-key", StoreProof(token="from-b"))
    assert store_a.get(StoreProof, "shared-key").token == "from-a"
    assert store_b.get(StoreProof, "shared-key").token == "from-b"
    assert not (store_b.root / "only-a").exists()
    (store_a.root / "only-a").write_text("a", encoding="utf-8")
    assert not (store_b.root / "only-a").exists()


def test_corruption_is_local_to_the_affected_entity(store: FileStore) -> None:
    store.create("a", StoreProof(token="A"))
    store.create("b", StoreProof(token="B"))
    store.create("c", StoreProof(token="C"))
    (store.root / "kernel.store.proof" / "b.json").write_text("{broken\n")
    assert store.get(StoreProof, "a").token == "A"
    with pytest.raises(ValidationError, match="malformed JSON"):
        store.get(StoreProof, "b")
    assert store.get(StoreProof, "c").token == "C"


def test_failed_publish_does_not_leave_a_visible_record(
    store: FileStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("forced publish failure")

    monkeypatch.setattr("machi.adapters.persistence.file_store.os.link", boom)
    with pytest.raises(PersistenceError, match="failed to write"):
        store.create("proof-a", StoreProof(token="ghost"))
    dest = store.root / "kernel.store.proof" / "proof-a.json"
    assert not dest.exists()
    leftovers = list((store.root / "kernel.store.proof").glob(".writing-*"))
    assert leftovers == []


def test_orphan_temporary_is_not_a_record(store: FileStore) -> None:
    store.create("proof-a", StoreProof(token="keep"))
    kind = store.root / "kernel.store.proof"
    (kind / ".writing-proof-b.json.deadbeef").write_text("{", encoding="utf-8")
    assert store.get(StoreProof, "proof-a").token == "keep"
    with pytest.raises(NotFoundError):
        store.get(StoreProof, "proof-b")


def test_proof_event_is_restricted_and_omits_path_and_payload(
    store: FileStore, tmp_path: Path
) -> None:
    result = store.create("secret-org-key", StoreProof(token="payload-secret"))
    event = store_proved(result, key="secret-org-key")
    assert event.event_type.value == STORE_PROVED_TYPE
    assert event.component_id.value == "0.4.1"
    assert event.privacy is PrivacyClass.RESTRICTED
    assert isinstance(event.payload, StoreProvedPayload)
    blob = json.dumps(to_dict(event))
    assert "secret-org-key" not in blob
    assert "payload-secret" not in blob
    assert str(store.root) not in blob
    assert "install_run_id" in unresolved_fields(event)
    assert event.payload.created is True


def test_cli_store_put_get_and_reentry(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "cli-store"
    journal = tmp_path / "journal"
    assert (
        main(
            [
                "kernel",
                "store-put",
                "--store-dir",
                str(store_root),
                "--key",
                "proof-a",
                "--token",
                "cli",
                "--journal-dir",
                str(journal),
            ]
        )
        == 0
    )
    first = capsys.readouterr().out
    assert '"kind": "kernel.store.proof"' in first
    assert '"created": true' in first
    assert "kernel.store.proved" in first
    assert '"privacy": "restricted"' in first
    assert str(store_root) not in first[first.find('"kind": "event_record"') :]
    assert (
        main(
            [
                "kernel",
                "store-put",
                "--store-dir",
                str(store_root),
                "--key",
                "proof-a",
                "--token",
                "cli",
            ]
        )
        == 0
    )
    second = capsys.readouterr().out
    assert '"created": false' in second or "created  false" in second
    assert (
        main(
            ["kernel", "store-get", "--store-dir", str(store_root), "--key", "proof-a"]
        )
        == 0
    )
    loaded = capsys.readouterr().out
    assert '"token": "cli"' in loaded


def test_cli_conflict_and_unsafe_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store_root = tmp_path / "cli-store"
    assert (
        main(
            [
                "kernel",
                "store-put",
                "--store-dir",
                str(store_root),
                "--key",
                "proof-a",
                "--token",
                "one",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "kernel",
                "store-put",
                "--store-dir",
                str(store_root),
                "--key",
                "proof-a",
                "--token",
                "other",
            ]
        )
        == 2
    )
    assert "does not match" in capsys.readouterr().err
    assert (
        main(
            [
                "kernel",
                "store-put",
                "--store-dir",
                str(store_root),
                "--key",
                "../escape",
                "--token",
                "nope",
            ]
        )
        == 2
    )
    assert "record key" in capsys.readouterr().err


def test_install_layout_convention_is_not_kernel_policy(tmp_path: Path) -> None:
    assert store_dir(tmp_path / "root") == tmp_path / "root" / "store"
