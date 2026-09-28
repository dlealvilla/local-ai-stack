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
from machi.kernel.analytics import load_bundle
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
