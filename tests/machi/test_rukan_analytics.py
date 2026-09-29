"""Analytics export, privacy allow-list, and Command Center inbox refresh."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from machi.adapters.journal.jsonl import JsonlJournal
from machi.adapters.rukan.analytics_export import export_analytics
from machi.adapters.rukan.hub import CommandHub, bind_command_center
from machi.adapters.rukan.local_analytics import local_analytics
from machi.kernel.alive import kernel_alive, payload_from_identity
from machi.kernel.analytics import AnalyticsInference, load_bundle
from machi.kernel.build import BuildIdentity, BuildOrigin, identity
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import to_dict
from machi.kernel.snapshot import accept_snapshot

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")


def _journal(path: Path) -> None:
    journal = JsonlJournal(path)
    journal.append(kernel_alive())
    journal.append(
        EventRecord.create(
            event_type="kernel.alive",
            block_id="0",
            component_id="0.1.1",
            outcome=EventOutcome.INFO,
            privacy=PrivacyClass.RESTRICTED,
            payload=payload_from_identity(identity()),
        )
    )
    journal.append(
        EventRecord.create(
            event_type="kernel.alive",
            block_id="0",
            component_id="0.1.1",
            outcome=EventOutcome.INFO,
            privacy=PrivacyClass.CUSTOMER_CONTENT,
            payload=payload_from_identity(identity()),
        )
    )


def test_export_allow_list_omits_restricted_and_content(tmp_path: Path) -> None:
    _journal(tmp_path / "journal")
    text = export_analytics(
        tmp_path / "store",
        tmp_path / "journal",
        BUILD,
        exported_at="2026-09-28T00:00:00+00:00",
    )
    bundle = load_bundle(text)
    assert bundle.manifest.schema_name == "rukan.analytics_bundle"
    assert bundle.manifest.event_count == 1
    assert bundle.events[0].privacy == "public_ops"
    assert "prompt" not in text
    assert "payload" not in text
    poisoned = text.replace('"public_ops"', '"public_ops","prompt":"secret"')
    with pytest.raises(ValidationError, match="prohibited"):
        load_bundle(poisoned)


def test_bundle_count_mismatch_fails_closed() -> None:
    text = export_analytics(
        Path("/tmp/rukan-empty-analytics"),
        None,
        BUILD,
        exported_at="2026-09-28T00:00:00+00:00",
    )
    Path("/tmp/rukan-empty-analytics").mkdir(exist_ok=True)
    document = json.loads(text.splitlines()[0])
    document["event_count"] = 9
    with pytest.raises(ValidationError, match="event count"):
        load_bundle(json.dumps(document) + "\n" + "\n".join(text.splitlines()[1:]) + "\n")  # noqa: E501


def test_inbox_refresh_is_idempotent_and_isolates_bad_files(tmp_path: Path) -> None:
    store = tmp_path / "store"
    journal = tmp_path / "journal"
    _journal(journal)
    text = export_analytics(store, journal, BUILD, exported_at="2026-09-28T00:00:00+00:00")  # noqa: E501
    data = tmp_path / "hub"
    inbox = data / "inbox"
    hub = CommandHub(data)
    (inbox / "bundle.jsonl").write_text(text, encoding="utf-8")
    snapshot = json.loads(text.splitlines()[1])
    (inbox / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    (inbox / "bad.json").write_text("{", encoding="utf-8")
    first = hub.refresh()
    assert first["body"]["imported"] == 2
    assert first["body"]["rejected"] == 1
    second = hub.refresh()
    assert second["body"]["imported"] == 0
    assert second["body"]["skipped"] == 2
    document = hub.deployments()
    listed = document["body"]["deployments"]
    assert len(listed) == 1
    assert document["body"]["live_claim"] is False
    hub.close()
    again = CommandHub(data)
    assert again.deployments()["body"]["deployments"][0]["install_id"] == listed[0]["install_id"]  # noqa: E501
    again.close()


def test_existing_snapshot_json_imports(tmp_path: Path) -> None:
    text = export_analytics(tmp_path / "store", None, BUILD, exported_at="2026-09-28T01:00:00+00:00")  # noqa: E501
    snapshot = json.loads(text.splitlines()[1])
    assert accept_snapshot(snapshot).product_name == "Rukan"
    hub = CommandHub(tmp_path / "hub")
    (hub.inbox / "one.json").write_text(json.dumps(snapshot), encoding="utf-8")
    result = hub.refresh()
    assert result["body"]["imported"] == 1
    detail = hub.detail(snapshot["install_id"])
    assert detail["body"]["snapshots"]
    assert detail["body"]["live_claim"] is False
    hub.remove(snapshot["install_id"])
    assert hub.deployments()["body"]["deployments"] == []
    hub.close()


def test_unsupported_schema_version_fails_closed(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    hub._db.execute("UPDATE meta SET value = '9' WHERE key = 'schema_version'")
    hub._db.commit()
    hub.close()
    with pytest.raises(ValidationError, match="schema version"):
        CommandHub(tmp_path / "hub")


def test_local_analytics_keeps_restricted_out_of_the_export_surface(tmp_path: Path) -> None:  # noqa: E501
    _journal(tmp_path / "journal")
    view = local_analytics(tmp_path / "store", tmp_path / "journal")
    assert view["omitted_customer_content_events"] == 1
    assert view["live_claim"] is False
    assert any("TTFT" in item for item in view["missing"])
    privacies = {item["privacy"] for item in view["timeline"]}
    assert "customer_content" not in privacies
    assert "restricted" in privacies


def test_command_center_refuses_non_loopback(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    with pytest.raises(ValidationError, match="loopback"):
        bind_command_center(hub, host="0.0.0.0", port=9)
    hub.close()


def test_manifest_round_trip_has_no_payload_key() -> None:
    text = export_analytics(
        Path("/tmp/rukan-empty-analytics-2"),
        None,
        BUILD,
        exported_at="2026-09-28T02:00:00+00:00",
    )
    Path("/tmp/rukan-empty-analytics-2").mkdir(exist_ok=True)
    bundle = load_bundle(text)
    encoded = to_dict(bundle.manifest)
    assert "payload" not in encoded
    assert encoded["privacy_policy"] == "rukan.analytics.export.1"


def _lines(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _dump(documents: list[dict[str, object]]) -> str:
    return "".join(json.dumps(item) + "\n" for item in documents)


def _with_bad_identity(text: str, kind: str) -> str:
    documents = _lines(text)
    if kind == "kernel.analytics_inference":
        documents[0]["inference_count"] = int(documents[0]["inference_count"]) + 1
        inference = to_dict(
            AnalyticsInference(
                proof_id="inf_bad",
                install_id="inst_other",
                instance_id="srv_bad",
                plan_id="plan_bad",
                reservation_id="rsv_bad",
                generation_id="fgen_bad",
                model_identity="mart_bad",
                model_identity_kind="warehouse_artifact",
                request_kind="completion",
                status_code=200,
                completion_tokens="1",
                structurally_valid=True,
                failure="none",
                outcome="proven",
            )
        )
        documents.append(inference)
    else:
        found = False
        for document in documents:
            if document.get("kind") == kind:
                document["install_id"] = "inst_other"
                found = True
        if not found:
            raise AssertionError(f"bundle has no {kind}")
    return _dump(documents)


def _table_count(hub: CommandHub, table: str) -> int:
    row = hub._db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    return int(row["n"])


def test_mismatched_event_and_inference_fail_before_import(tmp_path: Path) -> None:
    _journal(tmp_path / "journal")
    text = export_analytics(
        tmp_path / "store",
        tmp_path / "journal",
        BUILD,
        exported_at="2026-09-28T03:00:00+00:00",
    )
    for kind, match in (
        ("kernel.support_snapshot", "snapshot install id"),
        ("kernel.analytics_event", "event install id"),
        ("kernel.analytics_inference", "inference install id"),
    ):
        bad = _with_bad_identity(text, kind)
        with pytest.raises(ValidationError, match=match):
            load_bundle(bad)
        hub = CommandHub(tmp_path / f"hub-{kind.split('.')[-1]}")
        (hub.inbox / "bad.jsonl").write_text(bad, encoding="utf-8")
        result = hub.refresh()
        assert result["body"]["rejected"] == 1
        assert result["body"]["imported"] == 0
        for table in ("deployments", "snapshots", "events", "inferences", "sources"):
            assert _table_count(hub, table) == 0
        hub.close()


def _snapshot_file(base: dict[str, object], **changes: str) -> dict[str, object]:
    document = json.loads(json.dumps(base))
    document.update(changes)
    accept_snapshot(document)
    return document


def _history_state(tmp_path: Path, order: tuple[str, ...]) -> dict[str, object]:
    text = export_analytics(
        tmp_path / "store",
        None,
        BUILD,
        exported_at="2026-09-28T00:00:00+00:00",
    )
    base = _lines(text)[1]
    variants = {
        "old": _snapshot_file(
            base,
            snapshot_id="snap_old",
            exported_at="2026-09-28T00:00:00+00:00",
            version="0.1.0",
            model_identity="mart_old",
            witness_verdict="incomplete",
        ),
        "mid": _snapshot_file(
            base,
            snapshot_id="snap_mid",
            exported_at="2026-09-28T01:00:00+00:00",
            version="0.1.1",
            model_identity="mart_mid",
            witness_verdict="failed",
        ),
        "new": _snapshot_file(
            base,
            snapshot_id="snap_new",
            exported_at="2026-09-28T02:00:00+00:00",
            version="0.2.0",
            model_identity="mart_new",
            witness_verdict="supported",
        ),
    }
    hub = CommandHub(tmp_path / "hub")
    for index, name in enumerate(order):
        (hub.inbox / f"{index}-{name}.json").write_text(
            json.dumps(variants[name]), encoding="utf-8"
        )
    hub.refresh()
    row = hub.deployments()["body"]["deployments"][0]
    hub.close()
    return row


def test_snapshot_history_converges_regardless_of_import_order(tmp_path: Path) -> None:
    pairs = [
        _history_state(tmp_path / f"pair-{index}", order)
        for index, order in enumerate((("new", "old"), ("old", "new")))
    ]
    assert pairs[0] == pairs[1]
    assert pairs[0]["snapshot_count"] == 2
    assert pairs[0]["version"] == "0.2.0"
    assert pairs[0]["model_identity"] == "mart_new"
    assert pairs[0]["witness_verdict"] == "supported"
    assert pairs[0]["latest_exported_at"] == "2026-09-28T02:00:00+00:00"
    triples = [
        _history_state(tmp_path / f"triple-{index}", order)
        for index, order in enumerate(
            (("mid", "new", "old"), ("old", "mid", "new"), ("new", "mid", "old"))
        )
    ]
    assert triples[0] == triples[1] == triples[2]
    assert triples[0]["snapshot_count"] == 3
    assert triples[0]["version"] == "0.2.0"
    assert triples[0]["model_identity"] == "mart_new"
    assert triples[0]["witness_verdict"] == "supported"


def test_remove_then_refresh_rebuilds_from_inbox(tmp_path: Path) -> None:
    _journal(tmp_path / "journal")
    bundle = export_analytics(
        tmp_path / "store",
        tmp_path / "journal",
        BUILD,
        exported_at="2026-09-28T04:00:00+00:00",
    )
    snapshot = _lines(bundle)[1]
    other = _snapshot_file(
        snapshot,
        snapshot_id="snap_b",
        install_id="inst_b",
        exported_at="2026-09-28T05:00:00+00:00",
    )
    hub = CommandHub(tmp_path / "hub")
    bundle_path = hub.inbox / "a.jsonl"
    snapshot_path = hub.inbox / "b.json"
    bundle_path.write_text(bundle, encoding="utf-8")
    snapshot_path.write_text(json.dumps(other), encoding="utf-8")
    hub.refresh()
    install_id = str(snapshot["install_id"])
    hub.remove(install_id)
    assert bundle_path.is_file()
    assert snapshot_path.is_file()
    remaining = hub.deployments()["body"]["deployments"]
    assert [row["install_id"] for row in remaining] == ["inst_b"]
    assert remaining[0]["snapshot_count"] == 1
    rebuilt = hub.refresh()
    assert rebuilt["body"]["imported"] == 1
    rows = {
        row["install_id"]: row["snapshot_count"]
        for row in hub.deployments()["body"]["deployments"]
    }
    assert rows[install_id] == 1
    assert rows["inst_b"] == 1
    again = hub.refresh()
    assert again["body"]["imported"] == 0
    assert again["body"]["skipped"] == 2
    hub.remove("inst_b")
    assert snapshot_path.is_file()
    assert [row["install_id"] for row in hub.deployments()["body"]["deployments"]] == [
        install_id
    ]
    restored = hub.refresh()
    assert restored["body"]["imported"] == 1
    restored_rows = {
        row["install_id"]: row["snapshot_count"]
        for row in hub.deployments()["body"]["deployments"]
    }
    assert restored_rows[install_id] == 1
    assert restored_rows["inst_b"] == 1
    rewritten = json.dumps(other, sort_keys=True, indent=2)
    (hub.inbox / "b-again.json").write_text(rewritten, encoding="utf-8")
    spaced = "\n".join(line if line else "" for line in bundle.splitlines()) + "\n\n"
    (hub.inbox / "a-again.jsonl").write_text(spaced, encoding="utf-8")
    logical = hub.refresh()
    assert logical["body"]["imported"] == 0
    assert logical["body"]["skipped"] >= 2
    assert _table_count(hub, "sources") == 2
    hub.close()


def test_schema_v1_sources_gain_install_identity(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    hub._db.execute("DROP TABLE sources")
    hub._db.execute(
        """
        CREATE TABLE sources (
            sha256 TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )
    hub._db.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    hub._db.commit()
    hub.close()
    upgraded = CommandHub(tmp_path / "hub")
    assert upgraded._meta("schema_version") == "5"
    columns = [
        row[1] for row in upgraded._db.execute("PRAGMA table_info(sources)")
    ]
    assert "install_id" in columns
    assert "logical_id" in columns
    upgraded.close()
