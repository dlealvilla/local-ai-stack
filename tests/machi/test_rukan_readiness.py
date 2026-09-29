"""Production-readiness checks for bounded Rukan v0.3."""

from __future__ import annotations

import json
import sqlite3
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
    assert hub._meta("schema_version") == "6"
    hub.close()


def test_schema_four_upgrades_to_five(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path)
    hub._db.execute("UPDATE meta SET value = '4' WHERE key = 'schema_version'")
    hub._db.commit()
    hub.close()
    upgraded = CommandHub(tmp_path)
    assert upgraded._meta("schema_version") == "6"
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


def test_cumulative_does_not_regress_when_usage_is_compacted(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    for index in range(2005):
        assert store.record_usage(_usage(index, tokens=3)) is True
    store.note(("test_report",), NOW, immediate=True)
    assert store.tick(NOW, transport=_ack)["sent"] is True
    before = json.loads(
        store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    )["cumulative"]
    store._retain()
    assert store.record_usage(_usage(3000, tokens=5)) is True
    store.note(("test_report",), NOW + timedelta(seconds=1), immediate=True)
    assert store.tick(NOW + timedelta(seconds=1), transport=_ack)["sent"] is True
    after = json.loads(
        store._db.execute(
            "SELECT body FROM outbox ORDER BY sequence DESC"
        ).fetchone()["body"]
    )["cumulative"]
    assert before["requests"] == 2005
    assert after["requests"] == 2006
    assert int(after["output_tokens_total"]) == 2005 * 3 + 5
    assert after["succeeded"] == 2006
    store._retain()
    assert int(store._meta("compacted_requests") or "0") >= 5
    store.close()
    restored = TelemetryStore(tmp_path, None, BUILD)
    again = restored._cumulative_through_locked(2006)
    assert again.requests == 2006
    restored.close()


def test_rollup_limit_does_not_acknowledge_omitted_groups(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    for index in range(33):
        assert store.record_usage(_usage(index, model=f"mart_{index:02d}")) is True
    store.note(("test_report",), NOW, immediate=True)
    refused = store.tick(NOW, transport=_refuse)
    assert refused["sent"] is False
    body = json.loads(
        store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    )
    assert body["rollup_count"] == 32
    assert "usage_backlog" in body["trigger_reasons"]
    assert int(store._meta("ack_usage_seq") or "0") == 0
    assert store.tick(NOW + timedelta(seconds=61), transport=_ack)["sent"] is True
    store.close()
    restored = TelemetryStore(tmp_path, None, BUILD)
    restored._set("enabled", "true")
    restored._db.commit()
    restored.note(("test_report",), NOW + timedelta(seconds=2), immediate=True)
    assert restored.tick(NOW + timedelta(seconds=2), transport=_ack)["sent"] is True
    bodies = [
        json.loads(row["body"])
        for row in restored._db.execute("SELECT body FROM outbox ORDER BY sequence")
    ]
    assert bodies[1]["rollup_count"] == 1
    sent = sum(item["requests"] for body in bodies for item in body["rollups"])
    assert sent == 33
    restored.close()


def test_legacy_usage_rows_receive_unique_sequences(tmp_path: Path) -> None:
    path = tmp_path / "rukan-telemetry.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO meta(key, value) VALUES ('schema', '1');
        INSERT INTO meta(key, value)
        VALUES ('window_start', '2026-09-29T04:30:00+00:00');
        CREATE TABLE usage (
            usage_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            purpose TEXT NOT NULL,
            install_id TEXT NOT NULL,
            instance_id TEXT NOT NULL,
            plan_id TEXT NOT NULL,
            reservation_id TEXT NOT NULL,
            generation_id TEXT NOT NULL,
            model_identity TEXT NOT NULL,
            model_identity_kind TEXT NOT NULL,
            macropath TEXT NOT NULL,
            outcome TEXT NOT NULL,
            failure TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            input_tokens TEXT NOT NULL,
            output_tokens TEXT NOT NULL,
            latency_ms TEXT NOT NULL,
            runtime_duration_ms TEXT NOT NULL,
            version TEXT NOT NULL,
            build_id TEXT NOT NULL
        );
        """
    )
    stamps = ("2026-09-29T04:00:00+00:00", "2026-09-29T05:00:00+00:00")
    for index, stamp in enumerate(stamps):
        connection.execute(
            """
            INSERT INTO usage(
                usage_id, request_id, occurred_at, purpose, install_id, instance_id,
                plan_id, reservation_id, generation_id, model_identity,
                model_identity_kind, macropath, outcome, failure, status_code,
                input_tokens, output_tokens, latency_ms, runtime_duration_ms,
                version, build_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"usg_legacy_{index}", f"req_{index}", stamp, "operator_test",
                "not_recorded", "srv", "not_recorded", "not_recorded", "not_recorded",
                "mart_one", "warehouse_artifact", "vllm", "completed", "none", 200,
                "1", "1", "10", "not_recorded", "0.1.0", "0.1.0+test",
            ),
        )
    connection.commit()
    connection.close()
    store = TelemetryStore(tmp_path, None, BUILD)
    sequences = [
        int(row["usage_seq"])
        for row in store._db.execute("SELECT usage_seq FROM usage ORDER BY usage_seq")
    ]
    assert sequences == [1, 2]
    assert store._meta("ack_usage_seq") == "1"
    assert store._meta("legacy_usage_migration_uncertain") == "true"
    store.close()
    again = TelemetryStore(tmp_path, None, BUILD)
    assert [
        int(row["usage_seq"])
        for row in again._db.execute("SELECT usage_seq FROM usage ORDER BY usage_seq")
    ] == [1, 2]
    again.close()


def test_new_telemetry_stream_becomes_current(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    record = _install(tmp_path / "deploy")
    issued = issue_credential(hub, str(record.install_id), NOW)
    store = _enabled(tmp_path / "deploy", install_id=str(record.install_id))
    store.note(("test_report",), NOW, immediate=True)
    assert store.tick(NOW, transport=_ack)["sent"] is True
    first = store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    accept_report(hub, first, issued["secret"], received_at=NOW)
    stream_a = json.loads(first)["telemetry_stream_id"]
    hub._db.execute(
        "UPDATE deployments SET last_report_sequence = 100 WHERE install_id = ?",
        (str(record.install_id),),
    )
    hub._db.commit()
    store.close()
    for suffix in ("", "-wal", "-shm"):
        leftover = tmp_path / "deploy" / f"rukan-telemetry.sqlite{suffix}"
        if leftover.exists():
            leftover.unlink()
    reset = _enabled(tmp_path / "deploy", install_id=str(record.install_id))
    reset.note(("test_report",), NOW + timedelta(seconds=1), immediate=True)
    assert reset.tick(NOW + timedelta(seconds=1), transport=_ack)["sent"] is True
    second = reset._db.execute("SELECT body FROM outbox").fetchone()["body"]
    accept_report(hub, second, issued["secret"], received_at=NOW + timedelta(seconds=1))
    stream_b = json.loads(second)["telemetry_stream_id"]
    assert stream_b != stream_a
    current = hub._db.execute(
        "SELECT telemetry_stream_id, last_report_sequence FROM deployments"
    ).fetchone()
    assert current["telemetry_stream_id"] == stream_b
    assert int(current["last_report_sequence"]) == 1
    late = json.loads(first)
    late["report_id"] = "rpt_latehistorylate"
    late["sequence"] = 100
    accept_report(
        hub, json.dumps(late), issued["secret"], received_at=NOW + timedelta(seconds=2)
    )
    after = hub._db.execute(
        "SELECT telemetry_stream_id, last_report_sequence, report_gap FROM deployments"
    ).fetchone()
    assert after["telemetry_stream_id"] == stream_b
    assert int(after["last_report_sequence"]) == 1
    cursors = hub._db.execute(
        "SELECT stream_id, high_sequence FROM report_cursors ORDER BY stream_id"
    ).fetchall()
    assert {str(row["stream_id"]) for row in cursors} == {stream_a, stream_b}
    hub.close()
    reset.close()


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


def _usage(index: int, *, model: str = "mart_one", tokens: int = 2) -> InferenceUsage:
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
        model_identity=model,
        model_identity_kind="warehouse_artifact",
        macropath="vllm",
        outcome="completed",
        failure="none",
        status_code=200,
        input_tokens="4",
        output_tokens=str(tokens),
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
