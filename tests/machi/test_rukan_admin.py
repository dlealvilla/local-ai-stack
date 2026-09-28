"""Rukan Admin loopback seam. It projects stored truth and does not pick a runtime."""

from __future__ import annotations

import datetime as dt
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from machi.adapters.persistence.file_store import FileStore
from machi.adapters.rukan.complete import Completion, complete_openai, complete_provider
from machi.adapters.rukan.project import export_snapshot, project_admin
from machi.adapters.rukan.server import (
    AdminApplication,
    AdminHandlers,
    bind_admin,
)
from machi.admit.contracts import ReservationState, ResourceReservation
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.clock import FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.kernel.snapshot import accept_snapshot, reject_customer_content
from machi.serve.contracts import (
    HealthState,
    InstanceState,
    ServingInstance,
)

FIXED = "2026-09-28T00:00:00+00:00"
BUILD = BuildIdentity(
    version="0.1.0",
    origin=BuildOrigin.SOURCE,
    build_id=None,
    source_commit="4cb89622a4cd",
)


def _app(root: Path, handlers: AdminHandlers | None = None) -> AdminApplication:
    return AdminApplication(
        root,
        BUILD,
        handlers=handlers,
        clock=FixedClock(dt.datetime.fromisoformat(FIXED)),
    )


def _instance(store: Path, *, instance_id: str, state: InstanceState) -> None:
    FileStore(store).create(
        instance_id,
        ServingInstance(
            instance_id=instance_id,
            plan_id="plan_native",
            fingerprint="finger",
            reservation_id="rsv_native",
            generation_id="fgen_native",
            artifact_id="mart_native",
            serve_provider="vllm",
            executor_kind="native_process",
            endpoint_id="endpoint_native",
            state=state,
            health=HealthState.READY
            if state is InstanceState.READY
            else HealthState.UNREADY,
            evidence_id="evidence_native",
            policy_version="m9.serve.1",
        ),
    )


def test_empty_store_is_not_a_fake_success(tmp_path: Path) -> None:
    body = _app(tmp_path).summary()
    assert body["outcome"] == "ok"
    assert body["body"]["live_claim"] is False
    assert body["body"]["witness"]["verdict"] == "incomplete"
    assert body["body"]["chain"]["basis"] == "no_instance"
    assert body["body"]["model_operations"]["inspect_local"] is False
    assert "prompt" not in json.dumps(body)


def test_inference_requires_one_ready_instance(tmp_path: Path) -> None:
    called = {"n": 0}

    def complete(**_kwargs: object) -> Completion:
        called["n"] += 1
        return Completion("completed", "ok", "hello", 2, "vllm", "srv", "mart")

    app = _app(tmp_path, AdminHandlers(complete=complete))
    refused = app.infer({"prompt": "hello", "max_tokens": 8})
    assert refused["outcome"] == "refused"
    assert called["n"] == 0
    _instance(tmp_path, instance_id="srv_a", state=InstanceState.READY)
    _instance(tmp_path, instance_id="srv_b", state=InstanceState.READY)
    both = app.infer({"prompt": "hello", "max_tokens": 8})
    assert both["outcome"] == "refused"
    assert "READY" in str(both["reason"])
    assert called["n"] == 0


def test_ready_instance_returns_text_without_storing_it(tmp_path: Path) -> None:
    _instance(tmp_path, instance_id="srv_native", state=InstanceState.READY)

    def complete(**kwargs: object) -> Completion:
        assert kwargs["provider"] == "vllm"
        assert kwargs["model_identity"] == "mart_native"
        return Completion(
            "completed",
            "runtime returned text",
            "stored-secret-answer",
            3,
            "vllm",
            "srv_native",
            "mart_native",
        )

    app = _app(tmp_path, AdminHandlers(complete=complete))
    result = app.infer({"prompt": "operator prompt", "max_tokens": 8})
    assert result["outcome"] == "completed"
    assert result["body"]["text"] == "stored-secret-answer"
    assert result["body"]["stored"] is False
    dumped = "\n".join(path.read_text() for path in tmp_path.rglob("*.json"))
    assert "operator prompt" not in dumped
    assert "stored-secret-answer" not in dumped
    snapshot = app.snapshot()
    assert "operator prompt" not in json.dumps(snapshot)
    assert snapshot["body"]["product_name"] == "Rukan"


def test_release_waits_for_stop(tmp_path: Path) -> None:
    _instance(tmp_path, instance_id="srv_native", state=InstanceState.READY)
    released = {"n": 0}

    def release(_reservation_id: str) -> tuple[str, str]:
        released["n"] += 1
        return "ok", "released"

    app = _app(tmp_path, AdminHandlers(release=release))
    blocked = app.release({})
    assert blocked["outcome"] == "refused"
    assert blocked["reason"] == "stop before release"
    assert released["n"] == 0
    stopped = _app(tmp_path).stop({})
    assert stopped["outcome"] == "refused"
    assert "not attached" in stopped["reason"]


def test_stopped_release_uses_the_injected_service(tmp_path: Path) -> None:
    _instance(tmp_path, instance_id="srv_native", state=InstanceState.STOPPED)
    FileStore(tmp_path).create(
        "rsv_native",
        ResourceReservation(
            reservation_id="rsv_native",
            plan_id="plan_native",
            fingerprint="finger",
            request_id="req_native",
            capacity_evidence_id="cap_native",
            accelerator_identity="accel_native",
            accelerator_memory_bytes=1,
            host_memory_bytes=1,
            persistent_bytes=0,
            transient_bytes=0,
            cpu_count=1,
            policy_version="m8.admit.1",
            state=ReservationState.RESERVED,
        ),
    )

    def release(reservation_id: str) -> tuple[str, str]:
        assert reservation_id == "rsv_native"
        return "ok", "released"

    app = _app(tmp_path, AdminHandlers(release=release))
    result = app.release({})
    assert result["outcome"] == "ok"


def test_loopback_policy_and_origin(tmp_path: Path) -> None:
    app = _app(tmp_path)
    with pytest.raises(ValidationError, match="loopback"):
        bind_admin(app, host="0.0.0.0", port=9)
    httpd = bind_admin(app, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        request = Request(
            f"http://127.0.0.1:{port}/v1/summary",
            headers={"Origin": "http://evil.example"},
        )
        try:
            urlopen(request, timeout=2)
            raise AssertionError("non-loopback origin was accepted")
        except urllib.error.HTTPError as exc:
            payload = json.loads(exc.read().decode())
        assert payload["outcome"] == "refused"
    finally:
        httpd.shutdown()


def test_snapshot_round_trip_rejects_customer_content(tmp_path: Path) -> None:
    view = project_admin(tmp_path, BUILD)
    snapshot = export_snapshot(view, exported_at=FIXED)
    document = to_dict(snapshot)
    restored = accept_snapshot(document)
    assert restored.snapshot_id == snapshot.snapshot_id
    assert restored.package_name == "machi"
    poisoned = dict(document)
    poisoned["prompt"] = "secret"
    with pytest.raises(ValidationError, match="prohibited"):
        reject_customer_content(poisoned)
    with pytest.raises(ValidationError, match="prohibited"):
        accept_snapshot(poisoned)


def test_openai_completion_stays_in_the_return_value() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            body = json.dumps(
                {"choices": [{"text": "pong"}], "usage": {"completion_tokens": 1}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = complete_openai(
            port=server.server_address[1],
            model="mart_native",
            prompt="ping",
            max_tokens=4,
            provider="vllm",
            instance_id="srv_native",
        )
    finally:
        server.shutdown()
    assert result.outcome == "completed"
    assert result.text == "pong"
    assert result.completion_tokens == 1
    refused = complete_provider(
        base_url="http://example.com",
        name="tag",
        prompt="ping",
        max_tokens=4,
        context=2048,
        provider="ollama",
        instance_id="srv",
        model_identity="digest",
    )
    assert refused.outcome == "failed"
    assert "loopback" in refused.reason
