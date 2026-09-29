"""Connected monitoring: usage, outbox, intake, and privacy."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from machi.adapters.rukan.complete import Completion
from machi.adapters.rukan.hub import CommandHub
from machi.adapters.rukan.intake import (
    accept_report,
    bind_intake,
    issue_credential,
    revoke_credential,
)
from machi.adapters.rukan.server import AdminApplication, AdminHandlers
from machi.adapters.rukan.telemetry import TelemetryStore, jitter_seconds, post_report
from machi.adapters.rukan.tokens import ollama_usage, openai_usage
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.errors import ValidationError
from machi.kernel.report import load_report
from machi.kernel.usage import InferenceUsage

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")
NOW = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)


def test_openai_and_ollama_token_counts_stay_unresolved_when_absent() -> None:
    assert openai_usage({"usage": {"prompt_tokens": 4, "completion_tokens": 2}}) == (4, 2)  # noqa: E501
    assert openai_usage({"choices": []}) == (None, None)
    assert ollama_usage({"prompt_eval_count": 3, "eval_count": 5, "total_duration": 2_000_000}) == (3, 5, 2)  # noqa: E501
    assert ollama_usage({"response": "hello"}) == (None, None, None)


def test_usage_record_omits_prompt_and_separates_purpose(tmp_path: Path) -> None:
    store = TelemetryStore(tmp_path, None, BUILD)
    usage = _usage(purpose="operator_test")
    assert store.record_usage(usage) is True
    probe = _usage(purpose="acceptance_probe", usage_id="usg_probe", request_id="req_probe")  # noqa: E501
    assert store.record_usage(probe) is True
    raw = (tmp_path / "rukan-telemetry.sqlite").read_bytes()
    assert b"operator prompt" not in raw
    assert b"generated answer" not in raw
    grouped = store.aggregate()
    purposes = {item["purpose"] for item in grouped["groups"]}
    assert purposes == {"operator_test", "acceptance_probe"}
    store.close()
    again = TelemetryStore(tmp_path, None, BUILD)
    assert again.aggregate()["summary"]["requests"] == 2
    again.close()


def test_recording_failure_does_not_fail_inference(tmp_path: Path) -> None:
    app = AdminApplication(tmp_path / "store", BUILD)

    def complete(**_kwargs: object) -> Completion:
        return Completion(
            "completed", "runtime returned text", "secret-answer", 2, "vllm", "srv", "mart",  # noqa: E501
            input_tokens=4, status_code=200,
        )

    app.handlers = AdminHandlers(complete=complete)
    app.telemetry.close()
    result = app.infer({"prompt": "operator prompt", "max_tokens": 8})
    assert result["outcome"] in {"completed", "refused"}


def test_jitter_is_stable_and_bounded() -> None:
    assert jitter_seconds("inst_a") == jitter_seconds("inst_a")
    assert 0 <= jitter_seconds("inst_a") < 900
    assert jitter_seconds("inst_a") != jitter_seconds("inst_b")


def test_material_trigger_coalesces_and_failure_flushes(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    store.note(("deployment_ready", "plan_changed"), NOW)
    quiet = store.tick(NOW + timedelta(seconds=10), transport=lambda *_a, **_k: True)
    assert quiet["sent"] is False
    store.note(("deployment_failed",), NOW + timedelta(seconds=11), immediate=True)
    flushed = store.tick(NOW + timedelta(seconds=11), transport=lambda *_a, **_k: False)
    assert flushed["sent"] is False
    queued = store._db.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()["n"]
    assert queued == 1
    store.close()


def test_outbox_retries_and_survives_restart(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    store.note(("test_report",), NOW, immediate=True)
    store.tick(NOW, transport=lambda *_a, **_k: False)
    store.close()
    restored = TelemetryStore(tmp_path, None, BUILD)
    restored._set("enabled", "true")
    restored._db.commit()
    sent = restored.tick(NOW + timedelta(minutes=2), transport=lambda *_a, **_k: True)
    assert sent["sent"] is True
    state = restored._db.execute("SELECT state FROM outbox").fetchone()["state"]
    assert state == "delivered"
    restored.close()


def test_intake_auth_gap_and_idempotency(tmp_path: Path) -> None:
    hub = CommandHub(tmp_path / "hub")
    issued = issue_credential(hub, "not_recorded", NOW)
    store = _enabled(tmp_path / "deploy")
    store.configure(
        endpoint="http://127.0.0.1:9/v1/telemetry/reports",
        key_id=issued["key_id"],
        secret=issued["secret"],
        install_id="not_recorded",
        enabled=True,
        cadence_hours=6,
        actor="local_cli",
        now=NOW,
        local_test=True,
    )
    store.record_usage(_usage())
    store.note(("deployment_ready",), NOW, immediate=True)
    store.tick(NOW, transport=lambda *_a, **_k: False)
    body = store._db.execute("SELECT body FROM outbox").fetchone()["body"]
    first = accept_report(hub, body, issued["secret"], received_at=NOW)
    second = accept_report(hub, body, issued["secret"], received_at=NOW)
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    with pytest.raises(ValidationError, match="credential"):
        accept_report(hub, body, "wrong-secret", received_at=NOW)
    revoke_credential(hub, issued["key_id"], NOW)
    with pytest.raises(ValidationError, match="credential"):
        accept_report(hub, body, issued["secret"], received_at=NOW)
    other = issue_credential(hub, "inst_other", NOW)
    with pytest.raises(ValidationError, match="install"):
        accept_report(hub, body, other["secret"], received_at=NOW)
    gapped = _gap(body)
    fresh = issue_credential(hub, "not_recorded", NOW)
    # The first key was revoked. Issue a new key for the same install.
    accepted = accept_report(hub, gapped, fresh["secret"], received_at=NOW)
    assert accepted["gap"] == "gap_after:1"
    poisoned = body.replace(
        '"privacy_policy": "rukan.telemetry.export.1"',
        '"privacy_policy": "rukan.telemetry.export.1", "prompt": "secret"',
    )
    with pytest.raises(ValidationError):
        load_report(poisoned)
    listed = hub.deployments()["body"]["deployments"]
    assert listed
    assert "offline" not in json.dumps(listed).lower()
    assert listed[0]["last_report_received_at"] != "not_recorded"
    hub.close()
    store.close()


def test_plaintext_intake_fails_closed_and_local_test_is_explicit(tmp_path: Path) -> None:  # noqa: E501
    hub = CommandHub(tmp_path / "hub")
    with pytest.raises(ValidationError, match="HTTPS"):
        bind_intake(hub, "0.0.0.0", 0)
    with pytest.raises(ValidationError, match="local-test"):
        bind_intake(hub, "127.0.0.1", 0)
    httpd = bind_intake(hub, "127.0.0.1", 0, local_test=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        issued = issue_credential(hub, "not_recorded", NOW)
        store = _enabled(tmp_path / "deploy")
        port = httpd.server_address[1]
        store.configure(
            endpoint=f"http://127.0.0.1:{port}/v1/telemetry/reports",
            key_id=issued["key_id"],
            secret=issued["secret"],
            install_id="not_recorded",
            enabled=True,
            cadence_hours=6,
            actor="local_cli",
            now=NOW,
            local_test=True,
        )
        store.record_usage(_usage())
        result = store.send_test(NOW, transport=post_report)
        assert result["sent"] is True
        store.close()
    finally:
        httpd.shutdown()
        hub.close()


def test_https_loopback_intake(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    completed = subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(key),
            "-out", str(cert), "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        pytest.skip("openssl is not available")
    hub = CommandHub(tmp_path / "hub")
    httpd = bind_intake(hub, "127.0.0.1", 0, certfile=str(cert), keyfile=str(key))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        issued = issue_credential(hub, "not_recorded", NOW)
        store = _enabled(tmp_path / "deploy")
        port = httpd.server_address[1]
        store.configure(
            endpoint=f"https://127.0.0.1:{port}/v1/telemetry/reports",
            key_id=issued["key_id"],
            secret=issued["secret"],
            install_id="not_recorded",
            enabled=True,
            cadence_hours=6,
            actor="scheduler",
            now=NOW,
            local_test=True,
        )
        store.record_usage(_usage())
        assert store.send_test(NOW)["sent"] is True
        store.close()
    finally:
        httpd.shutdown()
        hub.close()


def test_queue_is_bounded(tmp_path: Path) -> None:
    store = _enabled(tmp_path)
    for index in range(26):
        store.note((f"settings_{index}"[:40],), NOW, immediate=True)
        store._compose(NOW + timedelta(seconds=index), (f"settings_{index}"[:40],))
    count = store._db.execute("SELECT COUNT(*) AS n FROM outbox WHERE state = 'queued'").fetchone()["n"]  # noqa: E501
    assert count <= 24
    store.close()


def _enabled(path: Path) -> TelemetryStore:
    store = TelemetryStore(path, None, BUILD)
    store._set("enabled", "true")
    store._set("install_id", "not_recorded")
    store._set("cadence_hours", "6")
    store._set("next_periodic_at", (NOW + timedelta(hours=6)).isoformat())
    store._db.commit()
    return store


def _usage(*, purpose: str = "operator_test", usage_id: str = "usg_one", request_id: str = "req_one") -> InferenceUsage:  # noqa: E501
    return InferenceUsage(
        usage_id=usage_id,
        request_id=request_id,
        occurred_at="2026-09-29T00:00:00+00:00",
        purpose=purpose,
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


def _gap(body: str) -> str:
    document = json.loads(body)
    document["sequence"] = 3
    document["report_id"] = "rpt_gapgapgapgapga"
    text = json.dumps(document)
    load_report(text)
    return text


def _touch_db(path: Path) -> None:
    sqlite3.connect(path).close()
