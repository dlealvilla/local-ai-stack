"""Loopback HTTP seam for Rukan Admin. Not a shell and not a runtime picker."""

from __future__ import annotations

import hashlib
import json
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from machi.adapters.rukan.complete import Completion
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.library import model_library
from machi.adapters.rukan.lifecycle import LifecycleOwner
from machi.adapters.rukan.local_analytics import local_analytics
from machi.adapters.rukan.project import (
    AdminProjection,
    export_snapshot,
    project_admin,
    projection_document,
    snapshot_document,
)
from machi.adapters.rukan.telemetry import (
    TelemetryAgent,
    TelemetryStore,
    activity_feed,
)
from machi.kernel.build import BuildIdentity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.snapshot import reject_customer_content
from machi.kernel.usage import NOT_RECORDED, InferenceUsage

API_NAME = "rukan.admin.v1"
_MAX_BODY = 65_536
_MAX_PROMPT = 2_000
_LOOPBACK = "127.0.0.1"
_OVERRIDES = frozenset({"pid", "provider", "port", "runtime"})

ModelHandler = Callable[[dict[str, object]], tuple[str, str, dict[str, object]]]
StopHandler = Callable[[str], tuple[str, str]]
ReleaseHandler = Callable[[str], tuple[str, str]]


@dataclass(frozen=True, slots=True)
class AdminHandlers:
    """Optional mutations. Absence is a typed refusal, not a hidden success."""

    complete: Callable[..., Completion] | None = None
    stop: StopHandler | None = None
    release: ReleaseHandler | None = None
    inspect_model: ModelHandler | None = None
    import_model: ModelHandler | None = None
    acquire_model: ModelHandler | None = None


class AdminApplication:
    """Read the store and invoke injected services. The browser sends no runtime."""

    def __init__(
        self,
        store_root: Path,
        build: BuildIdentity,
        *,
        journal_dir: Path | None = None,
        handlers: AdminHandlers | None = None,
        static_dir: Path | None = None,
        clock: Clock | None = None,
        lifecycle: LifecycleOwner | None = None,
    ) -> None:
        self.store_root = Path(store_root)
        self.build = build
        self.journal_dir = journal_dir
        self.handlers = handlers or AdminHandlers()
        self.static_dir = static_dir
        self.clock = clock or SystemClock()
        self.lifecycle = lifecycle
        self.telemetry = TelemetryStore(self.store_root, self.journal_dir, build)
        self.directory = Directory(self.store_root)
        from machi.adapters.rukan.deploy import DeploymentCoordinator

        self.coordinator = DeploymentCoordinator(
            self.store_root,
            state_root=(
                lifecycle.state_root if lifecycle is not None else self.store_root
            ),
            serve=lifecycle.native if lifecycle is not None else None,
            manager=lifecycle.manager if lifecycle is not None else None,
            note=self.telemetry,
        )

    def summary(self) -> dict[str, object]:
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        body = projection_document(view)
        body["model_operations"] = {
            "inspect_local": self.handlers.inspect_model is not None,
            "import_local": self.handlers.import_model is not None,
            "acquire_hub": self.handlers.acquire_model is not None,
        }
        attached = self.lifecycle is not None
        body["lifecycle"] = {
            "stop_attached": attached or self.handlers.stop is not None,
            "release_attached": attached or self.handlers.release is not None,
        }
        return _envelope("ok", "stored evidence", body)

    def usage(self, span: str) -> dict[str, object]:
        if span not in {"24h", "7d", "30d", "all"}:
            return _envelope("refused", "usage range is not supported", {})
        end = self.clock.now()
        hours = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}.get(span)
        start = None if hours is None else (end - timedelta(hours=hours)).isoformat()
        body = self.telemetry.aggregate(start=start, end=end.isoformat())
        body["range"] = span
        return _envelope("ok", "usage", body)

    def activity(self) -> dict[str, object]:
        rows = activity_feed(self.store_root, self.journal_dir)
        rows.extend(self.directory.audit_rows())
        return _envelope("ok", "activity", {"rows": rows[-50:], "live_claim": False})

    def people(self, body: dict[str, object] | None = None) -> dict[str, object]:
        from machi.adapters.rukan.directory_api import people_action

        outcome, reason, payload = people_action(self.directory, body, self.clock.now())
        return _envelope(outcome, reason, payload)

    def deploy(self, body: dict[str, object]) -> dict[str, object]:
        from machi.adapters.rukan.deploy import public_view, reject_deploy_body

        refused = reject_deploy_body(body)
        if refused is not None:
            return _envelope("refused", refused, {})
        try:
            view = self.coordinator.deploy(
                artifact_id=str(body["artifact_id"]),
                request_key=str(body["request_key"]),
                actor="local_admin_ui",
                now=self.clock.now(),
            )
        except ValidationError as exc:
            return _envelope("refused", exc.message, {})
        outcome = "ok" if view.state != "failed" else "failed"
        return _envelope(outcome, view.reason or view.state, public_view(view))

    def deployment(self) -> dict[str, object]:
        from machi.adapters.rukan.deploy import public_view

        view = self.coordinator.current()
        if view is None:
            return _envelope("ok", "no deployment operation", {})
        return _envelope("ok", view.state, public_view(view))

    def library(self) -> dict[str, object]:
        return _envelope(
            "ok",
            "model library",
            model_library(self.store_root, self.build, self.journal_dir),
        )

    def monitoring(self) -> dict[str, object]:
        body = self.telemetry.status(self.clock.now())
        body["deployment_settings"] = "read_only"
        body["deployment_settings_reason"] = (
            "Plan recomputation is not exposed on this Admin seam"
        )
        return _envelope("ok", "monitoring", body)

    def configure_monitoring(self, body: dict[str, object]) -> dict[str, object]:
        view = project_admin(self.store_root, self.build, journal_dir=self.journal_dir)
        endpoint = body.get("endpoint")
        key_id = body.get("key_id")
        secret = body.get("secret")
        if not all(isinstance(item, str) and item for item in (endpoint, key_id, secret)):  # noqa: E501
            return _envelope("refused", "endpoint, key id, and secret are required", {})
        profile = body.get("profile", "production")
        custom = body.get("custom_seconds")
        if not isinstance(profile, str):
            return _envelope("refused", "telemetry profile is unknown", {})
        if custom is not None and (isinstance(custom, bool) or not isinstance(custom, int)):  # noqa: E501
            return _envelope("refused", "custom telemetry cadence is invalid", {})
        enabled = body.get("enabled") is True
        local_test = body.get("local_test") is True
        try:
            status = self.telemetry.configure(
                endpoint=str(endpoint),
                key_id=str(key_id),
                secret=str(secret),
                install_id=view.install_id,
                enabled=enabled,
                actor="local_admin_ui",
                now=self.clock.now(),
                local_test=local_test,
                profile=profile,
                custom_seconds=custom if isinstance(custom, int) else None,
            )
        except ValidationError as exc:
            return _envelope("refused", exc.message, {})
        return _envelope("ok", "monitoring saved", status)

    def preview_report(self) -> dict[str, object]:
        try:
            document = self.telemetry.preview(self.clock.now())
        except ValidationError as exc:
            return _envelope("refused", exc.message, {})
        return _envelope("ok", "preview", document)

    def test_report(self, body: dict[str, object] | None = None) -> dict[str, object]:
        del body
        result = self.telemetry.send_test(self.clock.now())
        return _envelope("ok" if result.get("sent") else "refused", "test report", result)  # noqa: E501

    def _remember(self, view: AdminProjection, result: Completion, elapsed: float, purpose: str) -> bool:  # noqa: E501
        try:
            chain = view.chain
            occurred = self.clock.now().isoformat()
            request_id = "req_" + hashlib.sha256(
                f"{result.instance_id}|{occurred}|{elapsed}".encode()
            ).hexdigest()[:16]
            kind = chain.model_identity_kind
            if kind not in {"warehouse_artifact", "provider_digest", "not_recorded"}:
                kind = NOT_RECORDED
            failure = "none" if result.outcome == "completed" else result.reason.replace("\n", " ")[:240]  # noqa: E501
            usage = InferenceUsage(
                usage_id="usg_" + hashlib.sha256(request_id.encode()).hexdigest()[:16],
                request_id=request_id,
                occurred_at=occurred,
                purpose=purpose,
                install_id=view.install_id or NOT_RECORDED,
                instance_id=result.instance_id or NOT_RECORDED,
                plan_id=chain.plan_id,
                reservation_id=chain.reservation_id,
                generation_id=chain.generation_id,
                model_identity=result.model_identity or NOT_RECORDED,
                model_identity_kind=str(kind),
                macropath=result.provider or NOT_RECORDED,
                outcome="completed" if result.outcome == "completed" else "failed",
                failure=failure or "none",
                status_code=result.status_code,
                input_tokens=_count(result.input_tokens),
                output_tokens=_count(result.completion_tokens),
                latency_ms=str(max(0, int(elapsed * 1000))),
                runtime_duration_ms=_count(result.runtime_duration_ms),
                version=self.build.version,
                build_id=self.build.build_id or NOT_RECORDED,
            )
            return self.telemetry.record_usage(usage)
        except (ValidationError, TypeError, ValueError):
            return False

    def analytics(self) -> dict[str, object]:
        """Customer-local facts. This is not the vendor export."""
        body = local_analytics(self.store_root, self.journal_dir)
        from machi.adapters.rukan.gateway_store import GatewayLedger

        ledger = GatewayLedger(self.store_root)
        try:
            users = ledger.analytics()
            recon = _reconcile(self.store_root, users["employee"])
            requests = recon["deployment_requests"]
            state = ledger.accounting_state(
                requests if isinstance(requests, int) else 0,
                str(recon["deployment_input_tokens"]),
                str(recon["deployment_output_tokens"]),
            )
        finally:
            ledger.close()
        if state == "projection_pending":
            recon["match"] = False
            recon["statement"] = "projection pending"
        elif state == "partial_token_coverage":
            recon["match"] = False
            recon["statement"] = "token coverage incomplete"
        elif state == "degraded":
            recon["match"] = False
            recon["statement"] = "accounting degraded"
        elif state == "mismatch":
            recon["match"] = False
            recon["statement"] = "accounting gap"
        recon["accounting_state"] = state
        body["gateway_users"] = users["users"]
        body["gateway_teams"] = users["teams"]
        body["employee_usage"] = users["employee"]
        body["reconciliation"] = recon
        raw_missing = body["missing"]
        if isinstance(raw_missing, list):
            body["missing"] = [
                item.replace("cost, users, and utilization", "cost and utilization")
                for item in raw_missing
                if isinstance(item, str)
            ]
        return _envelope("ok", "local analytics", body)

    def snapshot(self) -> dict[str, object]:
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        exported = self.clock.now().isoformat()
        document = snapshot_document(
            export_snapshot(view, exported_at=exported, journal_dir=self.journal_dir)
        )
        reject_customer_content(document)
        return _envelope("ok", "snapshot exported", document)

    def infer(self, body: dict[str, object]) -> dict[str, object]:
        if _overrides(body):
            return _envelope("refused", "runtime selection is not accepted", {})
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        chain = view.chain
        if chain.contradictory or chain.basis != "authorised_ready_instance":
            return _envelope(
                "refused",
                "no single authorised READY instance",
                {"instance_state": chain.instance_state, "basis": chain.basis},
            )
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return _envelope("refused", "prompt is missing or too long", {})
        if len(prompt) > _MAX_PROMPT:
            return _envelope("refused", "prompt is missing or too long", {})
        max_tokens = body.get("max_tokens", 16)
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            return _envelope("refused", "max_tokens is outside 1..64", {})
        if max_tokens < 1 or max_tokens > 64:
            return _envelope("refused", "max_tokens is outside 1..64", {})
        if self.handlers.complete is None:
            return _envelope("refused", "interactive completer is not attached", {})
        started = time.monotonic()
        result = self.handlers.complete(
            provider=chain.macropath,
            model_identity=chain.model_identity,
            instance_id=chain.instance_id,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        elapsed = round(time.monotonic() - started, 3)
        purpose = body.get("purpose")
        if purpose != "acceptance_probe":
            purpose = "operator_test"
        recorded = self._remember(view, result, elapsed, purpose)
        return _envelope(
            result.outcome,
            result.reason,
            {
                "text": result.text,
                "completion_tokens": result.completion_tokens,
                "input_tokens": result.input_tokens,
                "elapsed_seconds": elapsed,
                "provider": result.provider,
                "instance_id": result.instance_id,
                "model_identity": result.model_identity,
                "stored": False,
                "usage_recorded": recorded,
                "purpose": purpose,
            },
        )

    def stop(self, body: dict[str, object]) -> dict[str, object]:
        if _overrides(body):
            return _envelope("refused", "runtime selection is not accepted", {})
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        instance_id = body.get("instance_id", view.chain.instance_id)
        if not isinstance(instance_id, str) or instance_id != view.chain.instance_id:
            return _envelope("refused", "instance is not the current chain", {})
        if view.chain.instance_state == "not_recorded":
            return _envelope("refused", "no serving instance is stored", {})
        if self.lifecycle is not None:
            outcome, reason = self.lifecycle.stop(
                instance_id, view.chain.model_identity_kind
            )
            if outcome == "ok":
                self.coordinator.mark_stopped(self.clock.now())
            return _envelope(outcome, reason, {"instance_id": instance_id})
        if self.handlers.stop is None:
            return _envelope("refused", "lifecycle runtime is not attached", {})
        outcome, reason = self.handlers.stop(instance_id)
        return _envelope(outcome, reason, {"instance_id": instance_id})

    def release(self, body: dict[str, object]) -> dict[str, object]:
        if _overrides(body):
            return _envelope("refused", "runtime selection is not accepted", {})
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        if view.chain.instance_state in {"starting", "ready", "stopping"}:
            return _envelope("refused", "stop before release", {})
        reservation_id = body.get("reservation_id", view.chain.reservation_id)
        if (
            not isinstance(reservation_id, str)
            or reservation_id != view.chain.reservation_id
        ):
            return _envelope("refused", "reservation is not the current chain", {})
        if view.chain.reservation_state == "not_recorded":
            return _envelope("refused", "no reservation is stored", {})
        if self.lifecycle is not None:
            outcome, reason = self.lifecycle.release(
                view.chain.instance_id, view.chain.model_identity_kind
            )
            if outcome == "ok":
                self.coordinator.mark_released(self.clock.now())
            return _envelope(outcome, reason, {"reservation_id": reservation_id})
        if self.handlers.release is None:
            return _envelope("refused", "lifecycle runtime is not attached", {})
        outcome, reason = self.handlers.release(reservation_id)
        return _envelope(outcome, reason, {"reservation_id": reservation_id})

    def model_action(self, name: str, body: dict[str, object]) -> dict[str, object]:
        handler = {
            "inspect": self.handlers.inspect_model,
            "import": self.handlers.import_model,
            "acquire": self.handlers.acquire_model,
        }[name]
        if handler is None:
            return _envelope("refused", f"{name} is not attached", {})
        outcome, reason, payload = handler(body)
        if _contains_path(payload):
            return _envelope("refused", "model result included a filesystem path", {})
        return _envelope(outcome, reason, payload)


def bind_admin(
    application: AdminApplication,
    *,
    host: str = _LOOPBACK,
    port: int = 0,
) -> ThreadingHTTPServer:
    """Bind without serving. Tests use this; production calls serve_admin."""
    return _server(application, host, port)


def serve_until_stopped(httpd: ThreadingHTTPServer) -> None:
    """Serve until SIGINT or SIGTERM. The handler does not print a traceback."""

    def _stop(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    previous = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGINT, previous[signal.SIGINT])
        signal.signal(signal.SIGTERM, previous[signal.SIGTERM])


def serve_admin(
    application: AdminApplication,
    *,
    host: str = _LOOPBACK,
    port: int = 8765,
) -> None:
    """Bind loopback and serve until interrupted."""
    if host != _LOOPBACK:
        raise ValidationError("Rukan Admin binds to loopback only")
    agent = TelemetryAgent(application.telemetry)
    agent.start()
    httpd = _server(application, host, port)
    try:
        serve_until_stopped(httpd)
    finally:
        agent.stop()
        httpd.server_close()
        application.telemetry.close()
        application.directory.close()
        application.coordinator.close()


def _server(
    application: AdminApplication, host: str, port: int
) -> ThreadingHTTPServer:
    if host != _LOOPBACK:
        raise ValidationError("Rukan Admin binds to loopback only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            _dispatch(self, application, "GET")

        def do_POST(self) -> None:
            _dispatch(self, application, "POST")

        def log_message(self, *_args: object) -> None:
            return

        def handle_error(self, _request: object, _client: object) -> None:
            _quiet_failure(self)

    return ThreadingHTTPServer((host, port), Handler)


def _dispatch(
    handler: BaseHTTPRequestHandler, application: AdminApplication, method: str
) -> None:
    if not _origin_ok(handler):
        _write(handler, 403, _envelope("refused", "origin is not loopback", {}))
        return
    path = urlparse(handler.path).path
    if method == "GET" and path == "/v1/analytics":
        _write(handler, 200, application.analytics())
        return
    if method == "GET" and path in {"/v1/summary", "/v1/overview"}:
        _write(handler, 200, application.summary())
        return
    if method == "GET" and path == "/v1/snapshot":
        _write(handler, 200, application.snapshot())
        return
    if method == "GET" and path == "/v1/usage":
        span = parse_qs(urlparse(handler.path).query).get("range", ["24h"])[0]
        _write(handler, 200, application.usage(span))
        return
    if method == "GET" and path == "/v1/activity":
        _write(handler, 200, application.activity())
        return
    if method == "GET" and path == "/v1/models/library":
        _write(handler, 200, application.library())
        return
    if method == "GET" and path == "/v1/deployment":
        _write(handler, 200, application.deployment())
        return
    if method == "GET" and path == "/v1/monitoring":
        _write(handler, 200, application.monitoring())
        return
    if method == "GET" and path == "/v1/people":
        _write(handler, 200, application.people(None))
        return
    if method == "GET" and path == "/v1/monitoring/preview":
        _write(handler, 200, application.preview_report())
        return
    static = application.static_dir
    if method == "GET" and static is not None and _serve_static(handler, static, path):
        return
    if method != "POST":
        _write(handler, 404, _envelope("refused", "unknown route", {}))
        return
    body, error = _read_body(handler)
    if error is not None:
        _write(handler, error[0], _envelope("refused", error[1], {}))
        return
    routes = {
        "/v1/inference": application.infer,
        "/v1/lifecycle/stop": application.stop,
        "/v1/lifecycle/release": application.release,
        "/v1/monitoring": application.configure_monitoring,
        "/v1/monitoring/test": application.test_report,
        "/v1/people": application.people,
        "/v1/deployment": application.deploy,
    }
    if path in routes:
        _write(handler, 200, routes[path](body))
        return
    models = {
        "/v1/models/inspect": "inspect",
        "/v1/models/import": "import",
        "/v1/models/acquire": "acquire",
    }
    if path in models:
        _write(handler, 200, application.model_action(models[path], body))
        return
    _write(handler, 404, _envelope("refused", "unknown route", {}))


def _origin_ok(handler: BaseHTTPRequestHandler) -> bool:
    origin = handler.headers.get("Origin")
    if origin is None:
        return True
    host = handler.headers.get("Host", "")
    allowed = {f"http://{_LOOPBACK}", "http://localhost"}
    if ":" in host:
        port = host.rsplit(":", 1)[-1]
        allowed.add(f"http://{_LOOPBACK}:{port}")
        allowed.add(f"http://localhost:{port}")
    return origin in allowed or origin.startswith(f"http://{_LOOPBACK}:")


def _read_body(
    handler: BaseHTTPRequestHandler,
) -> tuple[dict[str, object], tuple[int, str] | None]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length > _MAX_BODY:
        return {}, (413, "body is too large")
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {}, (400, "body is not json")
    if not isinstance(document, dict):
        return {}, (400, "body is not an object")
    return document, None


def _serve_static(handler: BaseHTTPRequestHandler, root: Path, path: str) -> bool:
    relative = "index.html" if path in {"", "/"} else path.lstrip("/")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        _write(handler, 403, _envelope("refused", "static path escaped", {}))
        return True
    if not candidate.is_file():
        return False
    data = candidate.read_bytes()
    kind = "text/html" if candidate.suffix == ".html" else "application/octet-stream"
    if candidate.suffix == ".js":
        kind = "text/javascript"
    if candidate.suffix == ".css":
        kind = "text/css"
    handler.send_response(200)
    handler.send_header("Content-Type", kind)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)
    return True


def _quiet_failure(handler: BaseHTTPRequestHandler) -> None:
    try:
        _write(handler, 500, _envelope("refused", "request failed", {}))
    except (OSError, RuntimeError):
        return


def _write(
    handler: BaseHTTPRequestHandler, status: int, body: dict[str, object]
) -> None:
    encoded = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def _count(value: int | None) -> str:
    if value is None or value < 0:
        return NOT_RECORDED
    return str(value)


def _overrides(body: dict[str, object]) -> bool:
    return any(key in body for key in _OVERRIDES)


def _reconcile(store_root: Path, principal: object) -> dict[str, object]:
    import sqlite3

    requests = 0
    inputs = 0
    outputs = 0
    unresolved = False
    path = Path(store_root) / "rukan-telemetry.sqlite"
    if path.is_file():
        database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = database.execute(
                """
                SELECT input_tokens, output_tokens FROM usage
                WHERE purpose = 'user_request'
                """
            ).fetchall()
        except sqlite3.Error:
            rows = []
        finally:
            database.close()
        requests = len(rows)
        for item in rows:
            if str(item[0]).isdigit() and str(item[1]).isdigit():
                inputs += int(item[0])
                outputs += int(item[1])
            else:
                unresolved = True
    facts = principal if isinstance(principal, dict) else {}
    same = (
        not unresolved
        and facts.get("requests") == requests
        and facts.get("input_tokens") == str(inputs)
        and facts.get("output_tokens") == str(outputs)
    )
    recorded = "not_recorded" if unresolved else str(inputs)
    produced = "not_recorded" if unresolved else str(outputs)
    return {
        "match": same,
        "deployment_requests": requests,
        "deployment_input_tokens": recorded,
        "deployment_output_tokens": produced,
        "statement": (
            "Sum of user traffic equals employee deployment traffic"
            if same
            else "accounting gap"
        ),
    }


def _envelope(outcome: str, reason: str, body: dict[str, object]) -> dict[str, object]:
    return {"api": API_NAME, "outcome": outcome, "reason": reason, "body": body}


def _contains_path(payload: dict[str, object]) -> bool:
    for key, value in payload.items():
        if key in {"path", "file_path", "absolute_path"}:
            return True
        if isinstance(value, str) and value.startswith("/"):
            return True
    return False
