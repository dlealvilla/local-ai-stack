"""Loopback HTTP seam for Rukan Admin. Not a shell and not a runtime picker."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from machi.adapters.rukan.complete import Completion
from machi.adapters.rukan.project import (
    export_snapshot,
    project_admin,
    projection_document,
    snapshot_document,
)
from machi.kernel.build import BuildIdentity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.snapshot import reject_customer_content

API_NAME = "rukan.admin.v1"
_MAX_BODY = 65_536
_MAX_PROMPT = 2_000
_LOOPBACK = "127.0.0.1"

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
    ) -> None:
        self.store_root = Path(store_root)
        self.build = build
        self.journal_dir = journal_dir
        self.handlers = handlers or AdminHandlers()
        self.static_dir = static_dir
        self.clock = clock or SystemClock()

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
        body["lifecycle"] = {
            "stop_attached": self.handlers.stop is not None,
            "release_attached": self.handlers.release is not None,
        }
        return _envelope("ok", "stored evidence", body)

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
        result = self.handlers.complete(
            provider=chain.macropath,
            model_identity=chain.model_identity,
            instance_id=chain.instance_id,
            prompt=prompt,
            max_tokens=max_tokens,
        )
        return _envelope(
            result.outcome,
            result.reason,
            {
                "text": result.text,
                "completion_tokens": result.completion_tokens,
                "provider": result.provider,
                "instance_id": result.instance_id,
                "model_identity": result.model_identity,
                "stored": False,
            },
        )

    def stop(self, body: dict[str, object]) -> dict[str, object]:
        view = project_admin(
            self.store_root, self.build, journal_dir=self.journal_dir
        )
        instance_id = body.get("instance_id", view.chain.instance_id)
        if not isinstance(instance_id, str) or instance_id != view.chain.instance_id:
            return _envelope("refused", "instance is not the current chain", {})
        if view.chain.instance_state == "not_recorded":
            return _envelope("refused", "no serving instance is stored", {})
        if self.handlers.stop is None:
            return _envelope("refused", "lifecycle runtime is not attached", {})
        outcome, reason = self.handlers.stop(instance_id)
        return _envelope(outcome, reason, {"instance_id": instance_id})

    def release(self, body: dict[str, object]) -> dict[str, object]:
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


def serve_admin(
    application: AdminApplication,
    *,
    host: str = _LOOPBACK,
    port: int = 8765,
) -> None:
    """Bind loopback and serve until interrupted."""
    if host != _LOOPBACK:
        raise ValidationError("Rukan Admin binds to loopback only")
    httpd = _server(application, host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


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

    return ThreadingHTTPServer((host, port), Handler)


def _dispatch(
    handler: BaseHTTPRequestHandler, application: AdminApplication, method: str
) -> None:
    if not _origin_ok(handler):
        _write(handler, 403, _envelope("refused", "origin is not loopback", {}))
        return
    path = urlparse(handler.path).path
    if method == "GET" and path in {"/v1/summary", "/v1/overview"}:
        _write(handler, 200, application.summary())
        return
    if method == "GET" and path == "/v1/snapshot":
        _write(handler, 200, application.snapshot())
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


def _envelope(outcome: str, reason: str, body: dict[str, object]) -> dict[str, object]:
    return {"api": API_NAME, "outcome": outcome, "reason": reason, "body": body}


def _contains_path(payload: dict[str, object]) -> bool:
    for key, value in payload.items():
        if key in {"path", "file_path", "absolute_path"}:
            return True
        if isinstance(value, str) and value.startswith("/"):
            return True
    return False
