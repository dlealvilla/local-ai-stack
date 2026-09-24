"""Historical evidence stays readable and does not become stronger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.machi.test_ollama_serve import _qualification
from tests.machi.test_qualification import _covers, _pass

import machi.foundation.fallback as foundation_fallback_module
from machi.adapters.persistence.file_store import FileStore, MigrationFault
from machi.kernel.errors import (
    PersistenceError,
    UnknownKindError,
    UnknownVersionError,
)
from machi.kernel.schema import from_dict, registered_contracts, to_dict
from machi.model.provider_qualification import (
    ProviderFitState,
    qualification_covers,
)
from machi.model.qualification import QualificationEvidence

PROMPT = "Reply with the customer secret."


def _historical_qualification() -> dict[str, object]:
    payload = to_dict(_pass())
    payload["schema_version"] = 1
    payload.pop("execution_environment_fingerprint")
    return payload


def _historical_provider() -> dict[str, object]:
    payload = to_dict(_qualification())
    payload["schema_version"] = 1
    payload.pop("context_binding")
    payload.pop("provider_fit")
    return payload


def test_qualification_v1_migrates_without_covering() -> None:
    restored = from_dict(_historical_qualification())
    assert isinstance(restored, QualificationEvidence)
    assert restored.schema_version == 2
    assert restored.execution_environment_fingerprint == "not_recorded"
    assert restored.outcome.value == "pass"
    assert not _covers(
        restored,
        execution_environment_fingerprint="not_recorded",
    )
    again = from_dict(to_dict(restored))
    assert again == restored


def test_provider_qualification_v1_migrates_without_covering() -> None:
    original = _qualification()
    restored = from_dict(_historical_provider())
    assert restored.schema_version == 2
    assert restored.context_binding == "not_sent"
    assert restored.provider_fit is ProviderFitState.UNRESOLVED
    assert restored.digest == original.digest
    assert restored.outcome == original.outcome
    assert restored.token_proved is original.token_proved
    assert not qualification_covers(
        restored,
        digest=restored.digest,
        generation_id=restored.generation_id,
        context=restored.context,
        concurrency=1,
    )
    assert qualification_covers(
        original,
        digest=original.digest,
        generation_id=original.generation_id,
        context=original.context,
        concurrency=1,
    )


def test_store_rewrites_once_and_records_the_migration(tmp_path: Path) -> None:
    payload = _historical_qualification()
    payload["record_key"] = "qev_hist"
    directory = tmp_path / "model.qualification"
    directory.mkdir()
    (directory / "qev_hist.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    store = FileStore(tmp_path)
    loaded = store.get(QualificationEvidence, "qev_hist")
    receipt_path = (
        tmp_path / "_schema_migration" / "model.qualification" / "qev_hist.json"
    )
    first = receipt_path.read_text(encoding="utf-8")
    again = store.get(QualificationEvidence, "qev_hist")
    assert loaded == again
    assert loaded.execution_environment_fingerprint == "not_recorded"
    recorded = json.loads(first)
    assert recorded == {
        "from_version": 1,
        "key": "qev_hist",
        "kind": "model.qualification",
        "phase": "complete",
        "to_version": 2,
    }
    assert receipt_path.read_text(encoding="utf-8") == first
    assert PROMPT not in first
    assert "rev" not in first
    assert not (tmp_path / "_schema_migrations.jsonl").exists()


def test_in_memory_migration_does_not_rewrite_a_file(tmp_path: Path) -> None:
    payload = _historical_provider()
    path = tmp_path / "historical.json"
    raw = json.dumps(payload, sort_keys=True)
    path.write_text(raw, encoding="utf-8")
    restored = from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert path.read_text(encoding="utf-8") == raw
    assert restored.context_binding == "not_sent"


def test_unknown_version_and_kind_fail_closed() -> None:
    payload = to_dict(_pass())
    payload["schema_version"] = 3
    with pytest.raises(UnknownVersionError):
        from_dict(payload)
    with pytest.raises(UnknownKindError):
        from_dict({"kind": "model.not_a_contract", "schema_version": 1})


def test_only_shipped_schema_bumps_have_upgrade_paths() -> None:
    assert foundation_fallback_module.RuntimeChoice.schema_version == 2
    bumped = sorted(
        f"{kind}@{version}" for kind, version in registered_contracts() if version > 1
    )
    assert bumped == [
        "foundation.runtime_choice@2",
        "model.ollama_qualification@2",
        "model.qualification@2",
    ]


def test_interrupted_migration_converges_without_a_false_receipt(
    tmp_path: Path,
) -> None:
    payload = _historical_qualification()
    payload["record_key"] = "qev_hist"
    directory = tmp_path / "model.qualification"
    directory.mkdir()
    record = directory / "qev_hist.json"
    record.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original = record.read_text(encoding="utf-8")
    intent_store = FileStore(tmp_path, migration_fault=MigrationFault(fail_intent=True))
    with pytest.raises(PersistenceError, match="intent"):
        intent_store.get(QualificationEvidence, "qev_hist")
    assert record.read_text(encoding="utf-8") == original
    assert not (tmp_path / "_schema_migration").exists()

    record_store = FileStore(tmp_path, migration_fault=MigrationFault(fail_record=True))
    with pytest.raises(PersistenceError, match="rewrite"):
        record_store.get(QualificationEvidence, "qev_hist")
    assert record.read_text(encoding="utf-8") == original
    intent = json.loads(
        (
            tmp_path / "_schema_migration" / "model.qualification" / "qev_hist.json"
        ).read_text(encoding="utf-8")
    )
    assert intent["phase"] == "intent"

    complete_store = FileStore(
        tmp_path, migration_fault=MigrationFault(fail_complete=True)
    )
    with pytest.raises(PersistenceError, match="completion"):
        complete_store.get(QualificationEvidence, "qev_hist")
    migrated = json.loads(record.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == 2
    open_receipt = json.loads(
        (
            tmp_path / "_schema_migration" / "model.qualification" / "qev_hist.json"
        ).read_text(encoding="utf-8")
    )
    assert open_receipt["phase"] == "intent"

    healed = FileStore(tmp_path).get(QualificationEvidence, "qev_hist")
    assert healed.schema_version == 2
    finished = json.loads(
        (
            tmp_path / "_schema_migration" / "model.qualification" / "qev_hist.json"
        ).read_text(encoding="utf-8")
    )
    assert finished["phase"] == "complete"
    again = FileStore(tmp_path).get(QualificationEvidence, "qev_hist")
    assert again == healed
    receipt_text = (
        tmp_path / "_schema_migration" / "model.qualification" / "qev_hist.json"
    ).read_text(encoding="utf-8")
    assert receipt_text == json.dumps(finished, indent=2, sort_keys=True) + "\n"


def test_complete_receipt_cannot_upgrade_a_historical_record(tmp_path: Path) -> None:
    payload = _historical_qualification()
    payload["record_key"] = "qev_hist"
    directory = tmp_path / "model.qualification"
    directory.mkdir(parents=True)
    record = directory / "qev_hist.json"
    record.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    receipt_dir = tmp_path / "_schema_migration" / "model.qualification"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "qev_hist.json").write_text(
        json.dumps(
            {
                "from_version": 1,
                "key": "qev_hist",
                "kind": "model.qualification",
                "phase": "complete",
                "to_version": 2,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(PersistenceError, match="claims completion"):
        FileStore(tmp_path).get(QualificationEvidence, "qev_hist")
    assert json.loads(record.read_text(encoding="utf-8"))["schema_version"] == 1
