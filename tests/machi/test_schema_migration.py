"""Historical evidence stays readable and does not become stronger."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.machi.test_ollama_serve import _qualification
from tests.machi.test_qualification import _covers, _pass

from machi.adapters.persistence.file_store import FileStore
from machi.kernel.errors import UnknownKindError, UnknownVersionError
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
    again = store.get(QualificationEvidence, "qev_hist")
    assert loaded == again
    assert loaded.execution_environment_fingerprint == "not_recorded"
    notes = (tmp_path / "_schema_migrations.jsonl").read_text(encoding="utf-8")
    assert notes.count("\n") == 1
    recorded = json.loads(notes)
    assert recorded == {
        "from_version": 1,
        "key": "qev_hist",
        "kind": "model.qualification",
        "to_version": 2,
    }
    assert PROMPT not in notes
    assert "rev" not in notes


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
    bumped = sorted(
        f"{kind}@{version}" for kind, version in registered_contracts() if version > 1
    )
    assert bumped == [
        "model.ollama_qualification@2",
        "model.qualification@2",
    ]
