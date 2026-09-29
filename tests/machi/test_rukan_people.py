"""Customer-local people directory. PII stays off the vendor report."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.hub import CommandHub
from machi.adapters.rukan.intake import accept_report, issue_credential
from machi.adapters.rukan.server import AdminApplication
from machi.adapters.rukan.telemetry import TelemetryStore
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.errors import ValidationError

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")
NOW = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
CANARY_EMAIL = "canary.person@example.test"
CANARY_NAME = "Canary Person"


def test_directory_users_teams_and_effective_access(tmp_path: Path) -> None:
    directory = Directory(tmp_path)
    ada = directory.create_user(email="Ada@Example.test", display_name="Ada", actor="local_admin_ui", now=NOW)  # noqa: E501
    with pytest.raises(ValidationError, match="email"):
        directory.create_user(email="ada@example.test", display_name="Other", actor="local_cli", now=NOW)  # noqa: E501
    directory.update_user(str(ada["user_id"]), email="ada.renamed@example.test", display_name=None, actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.set_status(str(ada["user_id"]), "suspended", actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.set_status(str(ada["user_id"]), "active", actor="local_admin_ui", now=NOW)
    grace = directory.create_user(email=CANARY_EMAIL, display_name=CANARY_NAME, actor="local_admin_ui", now=NOW)  # noqa: E501
    platform = directory.create_team(name="Platform", description="", actor="local_admin_ui", now=NOW)  # noqa: E501
    research = directory.create_team(name="Research", description="lab", actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.add_membership(str(grace["user_id"]), str(platform["team_id"]), actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.add_membership(str(grace["user_id"]), str(research["team_id"]), actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.remove_membership(str(grace["user_id"]), str(research["team_id"]), actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.set_team_status(str(platform["team_id"]), "archived", actor="local_admin_ui", now=NOW)  # noqa: E501
    directory.set_intent(
        subject_kind="team",
        subject_id=str(platform["team_id"]),
        platform_access="allow",
        inference_access="allow",
        model_selection="deny",
        agent_builder="deny",
        actor="local_admin_ui",
        now=NOW,
    )
    archived = directory.effective(str(grace["user_id"]))
    assert archived["inference_access"] == "deny"
    directory.set_team_status(str(platform["team_id"]), "active", actor="local_admin_ui", now=NOW)  # noqa: E501
    granted = directory.effective(str(grace["user_id"]))
    assert granted["inference_access"] == "allow"
    assert granted["enforcement"] == "rukan_user_gateway"
    directory.set_intent(
        subject_kind="user",
        subject_id=str(grace["user_id"]),
        platform_access="allow",
        inference_access="deny",
        model_selection="allow",
        agent_builder="deny",
        actor="local_admin_ui",
        now=NOW,
    )
    overridden = directory.effective(str(grace["user_id"]))
    assert overridden["inference_access"] == "deny"
    assert overridden["model_selection"] == "allow"
    directory.set_status(str(grace["user_id"]), "deactivated", actor="local_admin_ui", now=NOW)  # noqa: E501
    denied = directory.effective(str(grace["user_id"]))
    assert denied["platform_access"] == "deny"
    directory.close()
    again = Directory(tmp_path)
    assert len(again.list_users()) == 2
    again.close()


def test_people_pii_does_not_enter_vendor_report(tmp_path: Path) -> None:
    app = AdminApplication(tmp_path / "store", BUILD)
    app.people({
        "action": "create_user",
        "email": CANARY_EMAIL,
        "display_name": CANARY_NAME,
    })
    store = TelemetryStore(tmp_path / "store", None, BUILD)
    store.configure(
        endpoint="http://127.0.0.1:9/v1/telemetry/reports",
        key_id="tkey_local",
        secret="secret-value",
        install_id="not_recorded",
        enabled=True,
        actor="local_cli",
        now=NOW,
        local_test=True,
        profile="development",
    )
    store.note(("test_report",), NOW, immediate=True)
    store.tick(NOW, transport=lambda *_a, **_k: "rpt_wrong")
    body = store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    assert CANARY_EMAIL not in body
    assert CANARY_NAME not in body
    assert "operator prompt" not in body
    hub = CommandHub(tmp_path / "hub")
    issued = issue_credential(hub, "not_recorded", NOW)
    accept_report(hub, body, issued["secret"], received_at=NOW)
    raw = (tmp_path / "hub" / "command.sqlite").read_bytes()
    assert CANARY_EMAIL.encode() not in raw
    assert CANARY_NAME.encode() not in raw
    audit = (tmp_path / "store" / "directory-audit.jsonl").read_text(encoding="utf-8")
    assert CANARY_EMAIL not in audit
    hub.close()
    store.close()


def test_people_api_round_trip(tmp_path: Path) -> None:
    app = AdminApplication(tmp_path, BUILD)
    created = app.people({"action": "create_user", "email": "a@example.test", "display_name": "A"})  # noqa: E501
    assert created["outcome"] == "ok"
    listed = app.people(None)
    assert listed["body"]["users"]
    assert listed["body"]["enforcement"] == "rukan_user_gateway"
    dumped = json.dumps(listed)
    assert "password" not in dumped
