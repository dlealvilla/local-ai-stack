"""Production-readiness checks for bounded Rukan v0.3."""

from __future__ import annotations

import json
import stat
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from machi.adapters.journal.jsonl import JOURNAL_FILENAME
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.hub import CommandHub
from machi.adapters.rukan.intake import accept_report, issue_credential
from machi.adapters.rukan.server import AdminApplication, bind_admin
from machi.adapters.rukan.telemetry import TelemetryStore
from machi.install.contracts import InstallRecord
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.errors import ValidationError
from machi.kernel.ids import InstallId, LocalOwnershipId
from machi.kernel.schema import to_dict
from machi.kernel.usage import InferenceUsage

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")
NOW = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)


def test_production_cadence_is_the_default_and_development_is_explicit(
    tmp_path: Path,
) -> None:
    store = TelemetryStore(tmp_path, None, BUILD)
    status = store.status(NOW)
    assert status["cadence_profile"] == "production"
    assert status["cadence_seconds"] == 21_600
    with pytest.raises(ValidationError, match="install"):
        store.configure(
            endpoint="https://command.example/v1/telemetry/reports",
            key_id="tkey_one",
            secret="secret-value",
            install_id="not_recorded",
            enabled=True,
            actor="local_cli",
            now=NOW,
        )
    store.configure(
        endpoint="http://127.0.0.1:9/v1/telemetry/reports",
        key_id="tkey_one",
        secret="secret-value",
        install_id="not_recorded",
        enabled=True,
        actor="local_cli",
        now=NOW,
        local_test=True,
        profile="development",
    )
    assert store.status(NOW)["cadence_seconds"] == 120
    store.close()


def test_usage_sequence_is_delivered_once(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait()
            assert store.record_usage(_usage(index)) is True
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    rows = store._db.execute(
        "SELECT usage_seq FROM usage ORDER BY usage_seq"
    ).fetchall()
    sequences = [int(row["usage_seq"]) for row in rows]
    assert sequences == list(range(1, 9))
    store.note(("test_report",), NOW, immediate=True)
    assert store.tick(NOW, transport=_ack)["sent"] is True
    first = store._db.execute(
        "SELECT body FROM outbox WHERE sequence = 1"
    ).fetchone()["body"]
    assert json.loads(first)["cumulative"]["requests"] == 8
    assert store.record_usage(_usage(9)) is True
    store.note(("test_report",), NOW + timedelta(seconds=1), immediate=True)
    assert store.tick(NOW + timedelta(seconds=1), transport=_ack)["sent"] is True
    second = store._db.execute(
        "SELECT body FROM outbox WHERE sequence = 2"
    ).fetchone()["body"]
    document = json.loads(second)
    assert document["cumulative"]["requests"] == 9
    assert document["rollups"][0]["requests"] == 1
    store.close()


def test_frozen_trigger_is_not_resurrected_while_awaiting_ack(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    store.note(("deployment_ready",), NOW, immediate=True)
    refused = store.tick(NOW, transport=_refuse)
    assert refused["sent"] is False
    again = store.tick(NOW + timedelta(seconds=5), transport=_refuse)
    assert again["sent"] is False
    queued = store._db.execute(
        "SELECT body FROM outbox WHERE state = 'queued'"
    ).fetchall()
    assert len(queued) == 1
    assert "deployment_ready" in queued[0]["body"]
    pending = {row["reason"] for row in store._db.execute("SELECT reason FROM pending")}
    assert "deployment_ready" not in pending
    store.note(("model_selected",), NOW + timedelta(seconds=6), immediate=True)
    assert store.tick(NOW + timedelta(minutes=2), transport=_ack)["sent"] is True
    follow = store.tick(NOW + timedelta(minutes=3), transport=_ack)
    assert follow["sent"] is True
    bodies = [
        row["body"]
        for row in store._db.execute("SELECT body FROM outbox ORDER BY sequence")
    ]
    assert "model_selected" not in bodies[0]
    assert "model_selected" in bodies[1]
    assert "deployment_ready" not in bodies[1]
    store.close()


def test_platform_parent_and_per_capability_inherit(tmp_path: Path) -> None:
    directory = Directory(tmp_path)
    user = directory.create_user(
        email="ada@example.test", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    team = directory.create_team(
        name="Platform", description="", actor="local_admin_ui", now=NOW
    )
    directory.add_membership(
        str(user["user_id"]), str(team["team_id"]), actor="local_admin_ui", now=NOW
    )
    directory.set_intent(
        subject_kind="team",
        subject_id=str(team["team_id"]),
        platform_access="allow",
        inference_access="allow",
        model_selection="deny",
        agent_builder="deny",
        actor="local_admin_ui",
        now=NOW,
    )
    inherited = directory.effective(str(user["user_id"]))
    assert inherited["inference_access"] == "allow"
    assert inherited["inference_provenance"] == "team_grant"
    assert inherited["model_selection_provenance"] == "default_deny"
    directory.set_intent(
        subject_kind="user",
        subject_id=str(user["user_id"]),
        platform_access="deny",
        inference_access="inherit",
        model_selection="allow",
        agent_builder="inherit",
        actor="local_admin_ui",
        now=NOW,
    )
    closed = directory.effective(str(user["user_id"]))
    assert closed["platform_access"] == "deny"
    assert closed["inference_access"] == "deny"
    assert closed["model_selection"] == "deny"
    assert closed["inference_provenance"] == "platform_parent"
    assert closed["model_selection_provenance"] == "platform_parent"
    directory.set_intent(
        subject_kind="user",
        subject_id=str(user["user_id"]),
        platform_access="allow",
        inference_access="inherit",
        model_selection="deny",
        agent_builder="inherit",
        actor="local_admin_ui",
        now=NOW,
    )
    mixed = directory.effective(str(user["user_id"]))
    assert mixed["inference_access"] == "allow"
    assert mixed["inference_provenance"] == "team_grant"
    assert mixed["model_selection"] == "deny"
    assert mixed["model_selection_provenance"] == "user_deny"
    with pytest.raises(ValidationError, match="unknown"):
        directory.set_intent(
            subject_kind="team",
            subject_id=str(team["team_id"]),
            platform_access="inherit",
            inference_access="allow",
            model_selection="allow",
            agent_builder="allow",
            actor="local_admin_ui",
            now=NOW,
        )
    directory.close()


def test_report_collision_skew_and_stream_gap(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    record = _install(tmp_path / "deploy")
    issued = issue_credential(hub, str(record.install_id), NOW)
    store = _enabled(tmp_path / "deploy", install_id=str(record.install_id))
    store.note(("test_report",), NOW, immediate=True)
    assert store.tick(NOW, transport=_ack)["sent"] is True
    body = store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    first = accept_report(hub, body, issued["secret"], received_at=NOW)
    assert first["duplicate"] is False
    replay = accept_report(hub, body, issued["secret"], received_at=NOW)
    assert replay["duplicate"] is True
    changed = json.loads(body)
    changed["report_id"] = "rpt_collisioncollision"
    changed["source_commit"] = "abcd"
    with pytest.raises(ValidationError, match="collided"):
        accept_report(hub, json.dumps(changed), issued["secret"], received_at=NOW)
    skewed = json.loads(body)
    skewed["report_id"] = "rpt_skewedskewedskew"
    skewed["sequence"] = 2
    skewed["generated_at"] = (NOW + timedelta(hours=3)).isoformat()
    skewed["previous_report_id"] = json.loads(body)["report_id"]
    accepted = accept_report(
        hub, json.dumps(skewed), issued["secret"], received_at=NOW
    )
    assert accepted["duplicate"] is False
    row = hub._db.execute(
        "SELECT clock_skew, telemetry_stream_id FROM deployments"
    ).fetchone()
    assert row["clock_skew"] == "source_clock_ahead"
    assert str(row["telemetry_stream_id"]).startswith("tstream_")
    hub.close()
    store.close()


def test_concurrent_command_center_open_migrates_once(tmp_path: Path) -> None:
    errors: list[BaseException] = []

    def open_hub() -> None:
        try:
            hub = CommandHub(tmp_path)
            hub.close()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=open_hub) for _index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    hub = CommandHub(tmp_path)
    assert hub._meta("schema_version") == "5"
    hub.close()


def test_schema_four_upgrades_to_five(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path)
    hub._db.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
    hub._db.commit()
    hub.close()
    upgraded = CommandHub(tmp_path)
    assert upgraded._meta("schema_version") == "5"
    columns = {row[1] for row in upgraded._db.execute("PRAGMA table_info(reports)")}
    assert "stream_id" in columns
    upgraded.close()


def test_partial_journal_line_is_not_consumed(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / JOURNAL_FILENAME).write_bytes(b'{"incomplete"')
    store = TelemetryStore(tmp_path, journal, BUILD)
    _events, offset, _more = store._read_events_locked()
    assert offset == 0
    (journal / JOURNAL_FILENAME).write_bytes(b"")
    store._set("journal_offset", "20")
    store._db.commit()
    _events, offset, _more = store._read_events_locked()
    assert offset == 20
    assert store._journal_defect == "journal_truncated"
    store.close()


def test_retention_keeps_unacknowledged_usage(tmp_path: Path) -> None:
    store = TelemetryStore(tmp_path, None, BUILD)
    for index in range(2005):
        assert store.record_usage(_usage(index)) is True
    store._set("ack_usage_seq", "2005")
    store._db.commit()
    store._retain()
    kept = store._db.execute(
        "SELECT COUNT(*) AS n FROM usage WHERE usage_seq <= 2005"
    ).fetchone()["n"]
    assert kept == 2000
    assert store.record_usage(_usage(3000)) is True
    store._retain()
    live = store._db.execute(
        "SELECT usage_seq FROM usage WHERE usage_seq > 2005"
    ).fetchone()
    assert int(live["usage_seq"]) > 2005
    for index in range(60):
        store._db.execute(
            """
            INSERT INTO outbox(
                report_id, sequence, body, state, attempts, next_attempt_at,
                last_error, created_at, delivered_at
            ) VALUES (?, ?, '{}', 'delivered', 1, '', '', '', '')
            """,
            (f"rpt_{index:04d}", index + 1),
        )
    store._db.execute(
        """
        INSERT INTO outbox(
            report_id, sequence, body, state, attempts, next_attempt_at,
            last_error, created_at
        ) VALUES ('rpt_queued', 99, '{}', 'queued', 0, '', '', '')
        """
    )
    store._db.commit()
    store._retain()
    delivered = store._db.execute(
        "SELECT COUNT(*) AS n FROM outbox WHERE state = 'delivered'"
    ).fetchone()["n"]
    queued = store._db.execute(
        "SELECT COUNT(*) AS n FROM outbox WHERE state = 'queued'"
    ).fetchone()["n"]
    assert delivered == 48
    assert queued == 1
    store.close()


def test_sensitive_files_are_owner_only(tmp_path: Path) -> None:
    store = TelemetryStore(tmp_path / "telemetry", None, BUILD)
    directory = Directory(tmp_path / "people")
    hub = CommandHub(tmp_path / "hub")
    for path in (
        tmp_path / "telemetry" / "rukan-telemetry.sqlite",
        tmp_path / "people" / "directory.sqlite",
        tmp_path / "hub" / "command.sqlite",
    ):
        mode = path.stat().st_mode & 0o777
        assert mode == stat.S_IRUSR | stat.S_IWUSR
    store.close()
    directory.close()
    hub.close()


def test_directory_install_binding_fails_closed(tmp_path: Path) -> None:
    first = _install(tmp_path)
    directory = Directory(tmp_path)
    assert directory._meta("install_id") == str(first.install_id)
    directory.close()
    _install(tmp_path)
    with pytest.raises(ValidationError, match="binding"):
        Directory(tmp_path)


def test_admin_stays_loopback_and_rejects_foreign_origin(tmp_path: Path) -> None:
    app = AdminApplication(tmp_path, BUILD)
    with pytest.raises(ValidationError, match="loopback"):
        bind_admin(app, host="0.0.0.0", port=0)
    httpd = bind_admin(app, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        import urllib.request

        port = httpd.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/people",
            data=b"{}",
            headers={
                "Origin": "https://evil.example",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=2)
        assert caught.value.code == 403
    finally:
        httpd.shutdown()
        httpd.server_close()
        app.telemetry.close()
        app.directory.close()


def test_ten_deployments_report_without_crossing_usage(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    credentials = []
    for index in range(10):
        record = _install(tmp_path / f"deploy-{index}")
        credentials.append(issue_credential(hub, str(record.install_id), NOW))
    errors: list[BaseException] = []

    def worker(index: int, issued: dict[str, str]) -> None:
        try:
            root = tmp_path / f"deploy-{index}"
            store = _enabled(root, install_id=issued["install_id"])
            store.configure(
                endpoint="http://127.0.0.1:9/v1/telemetry/reports",
                key_id=issued["key_id"],
                secret=issued["secret"],
                install_id=issued["install_id"],
                enabled=True,
                actor="scheduler",
                now=NOW,
                local_test=True,
                profile="development",
            )
            assert store.record_usage(_usage(index)) is True
            store.note(("test_report",), NOW, immediate=True)

            def transport(
                _endpoint: str, secret: str, body: str, local_test: bool = False
            ) -> str:
                del _endpoint, local_test
                if index == 3:
                    secret = "not-the-secret"
                result = accept_report(hub, body, secret, received_at=NOW)
                return str(result["report_id"])

            sent = store.tick(NOW, transport=transport)
            if index == 3:
                assert sent["sent"] is False
            else:
                assert sent["sent"] is True
            store.close()
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(index, issued))
        for index, issued in enumerate(credentials)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    accepted = hub._db.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]
    installs = hub._db.execute(
        "SELECT COUNT(DISTINCT install_id) AS n FROM reports"
    ).fetchone()["n"]
    requests = hub._db.execute("SELECT SUM(requests) AS n FROM reports").fetchone()["n"]
    assert accepted == 9
    assert installs == 9
    assert requests == 9
    hub.close()


def _enabled(path: Path, install_id: str = "not_recorded") -> TelemetryStore:
    store = TelemetryStore(path, None, BUILD)
    store._set("enabled", "true")
    store._set("install_id", install_id)
    store._set("cadence_profile", "development")
    store._set("cadence_seconds", "120")
    store._set("cadence_phase_seconds", "0")
    store._set("next_periodic_at", (NOW + timedelta(hours=6)).isoformat())
    store._db.commit()
    return store


def _usage(index: int) -> InferenceUsage:
    return InferenceUsage(
        usage_id=f"usg_{index:04d}",
        request_id=f"req_{index:04d}",
        occurred_at="2026-09-29T04:00:00+00:00",
        purpose="operator_test",
        install_id="not_recorded",
        instance_id="srv_one",
        plan_id="not_recorded",
        reservation_id="not_recorded",
        generation_id="not_recorded",
        model_identity="mart_one",
        model_identity_kind="warehouse_artifact",
        macropath="vllm",
        outcome="completed",
        failure="none",
        status_code=200,
        input_tokens="4",
        output_tokens="2",
        latency_ms="18",
        runtime_duration_ms="not_recorded",
        version="0.1.0",
        build_id="0.1.0+test",
    )


def _ack(_endpoint: str, _secret: str, body: str, local_test: bool = False) -> str:
    del _endpoint, _secret, local_test
    return str(json.loads(body)["report_id"])


def _refuse(_endpoint: str, _secret: str, _body: str, local_test: bool = False) -> str:
    del _endpoint, _secret, _body, local_test
    raise ValidationError("refused")


def _install(root: Path) -> InstallRecord:
    record = InstallRecord(
        install_id=InstallId.generate(),
        product="machi",
        marker_id=LocalOwnershipId.generate(),
        root_fingerprint="ab" * 32,
        created_at=NOW,
        created_by_version="0.1.0",
        created_by_origin="source",
    )
    directory = root / InstallRecord.kind
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.json"):
        path.unlink()
    (directory / "record.json").write_text(
        json.dumps(to_dict(record)), encoding="utf-8"
    )
    return record
