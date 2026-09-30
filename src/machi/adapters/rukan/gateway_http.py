"""HTTP edge for the user gateway. It does not publish a runtime port."""

from __future__ import annotations

import json
import ssl
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from machi.adapters.rukan.gateway import GatewayService, status_for
from machi.kernel.errors import ValidationError

_MAX_BODY = 1_000_000
_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>My Usage</title></head>
<body>
<h1>My Usage</h1>
<p>This page is Rukan. The workspace chat is a separate adapter.</p>
<label>Access token <input id="token" type="password"></label>
<button type="button" id="load">Show my usage</button>
<pre id="out"></pre>
<script>
document.getElementById("load").onclick = async () => {
  const token = document.getElementById("token").value;
  const response = await fetch("/v1/me/usage?period=all", {
    headers: {authorization: "Bearer " + token}
  });
  document.getElementById("out").textContent = await response.text();
};
</script>
</body></html>
"""


def serve_gateway(
    service: GatewayService,
    *,
    host: str,
    port: int,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
    trusted_peers: frozenset[str] = frozenset(),
    clock: Callable[[], datetime] | None = None,
) -> None:
    httpd = _server(service, host, port, trusted_peers, clock or (lambda: datetime.now(UTC)))  # noqa: E501
    if tls_cert is not None and tls_key is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls_cert, tls_key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        service.close()


def _server(
    service: GatewayService,
    host: str,
    port: int,
    trusted_peers: frozenset[str],
    clock: Callable[[], datetime],
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            _route(self, service, "GET", trusted_peers, clock)

        def do_POST(self) -> None:
            _route(self, service, "POST", trusted_peers, clock)

        def log_message(self, *_args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def _route(
    handler: BaseHTTPRequestHandler,
    service: GatewayService,
    method: str,
    trusted_peers: frozenset[str],
    clock: Callable[[], datetime],
) -> None:
    peer = handler.client_address[0]
    if peer not in trusted_peers:
        for name in ("X-Forwarded-For", "X-Real-IP", "Forwarded"):
            if name in handler.headers:
                del handler.headers[name]
    length = int(handler.headers.get("content-length", "0") or "0")
    if length > _MAX_BODY:
        _error(handler, "overloaded")
        return
    raw = handler.rfile.read(length) if length else b""
    now = clock()
    path = urlsplit(handler.path).path
    query = parse_qs(urlsplit(handler.path).query)
    client = _client_id(handler.headers.get("X-Rukan-Client", ""))
    try:
        if method == "GET" and path == "/v1/version":
            _json(handler, 200, {
                "api": "rukan.user_gateway.v0.4",
                "version": service.build.version,
                "build_id": service.build.build_id or "not_recorded",
                "supported": [
                    "GET /v1/models",
                    "POST /v1/chat/completions",
                    "GET /v1/me",
                    "GET /v1/me/usage",
                ],
            })
            return
        if method == "GET" and path == "/me":
            _bytes(handler, 200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        header = handler.headers.get("Authorization")
        principal = service.authenticate(header, client_id=client, now=now)
        if method == "GET" and path == "/v1/models":
            _json(handler, 200, service.models(principal))
            return
        if method == "GET" and path == "/v1/me":
            _json(handler, 200, service.me(principal))
            return
        if method == "POST" and path == "/v1/me/credentials/revoke":
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                raise ValidationError("overloaded")
            revoked = service.revoke_own(
                principal, str(body.get("key_id", "")), now
            )
            _json(handler, 200, dict(revoked))
            return
        if method == "GET" and path == "/v1/me/usage":
            period = query.get("period", ["all"])[0]
            _json(handler, 200, service.my_usage(principal, period, now))
            return
        if method == "POST" and path == "/v1/chat/completions":
            body = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(body, dict):
                raise ValidationError("overloaded")
            if body.get("stream") is True:
                handler.send_response(200)
                handler.send_header("content-type", "text/event-stream")
                handler.end_headers()
                for chunk in service.stream(principal, body, now=now):
                    handler.wfile.write(chunk)
                return
            _json(handler, 200, service.chat(principal, body, now=now, stream=False))
            return
        parts = path.strip("/").split("/")
        if method == "POST" and len(parts) == 2 and parts[0] == "mcp":
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(payload, dict):
                raise ValidationError("mcp_access_denied")
            _json(handler, 200, service.mcp_call(principal, parts[1], payload, now=now))
            return
        _error(handler, "authentication_required")
    except ValidationError as exc:
        _error(handler, exc.message)
    except json.JSONDecodeError:
        _error(handler, "overloaded")


def _client_id(value: str) -> str:
    """Approved client names only. Unknown labels cannot inflate analytics."""
    cleaned = "".join(
        char for char in value.lower() if char.isalnum() or char == "_"
    )[:40]
    if cleaned in {"librechat", "generic_api", "rukan_future_workspace"}:
        return cleaned
    return "generic_api"


def _json(
    handler: BaseHTTPRequestHandler, status: int, body: dict[str, object]
) -> None:
    _bytes(handler, status, json.dumps(body).encode("utf-8"), "application/json")


def _error(handler: BaseHTTPRequestHandler, code: str) -> None:
    _json(
        handler,
        status_for(code),
        {"error": {"message": code, "type": code, "code": code}},
    )


def _bytes(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:  # noqa: E501
    handler.send_response(status)
    handler.send_header("content-type", content_type)
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
