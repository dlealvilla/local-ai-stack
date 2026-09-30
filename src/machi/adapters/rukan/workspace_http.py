"""Rukan Workspace: one process for the employee UI, session, and gateway."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from machi.adapters.rukan.credentials import issue_credential
from machi.adapters.rukan.gateway import GatewayService, Principal, status_for
from machi.adapters.rukan.gateway_http import _route
from machi.adapters.rukan.oidc import OidcDiscoveryVerifier
from machi.adapters.rukan.workspace_store import WorkspaceStore
from machi.kernel.errors import ValidationError

_MAX_BODY = 1_000_000
_SESSION = "rukan_session"
_SESSION_TTL = 8 * 3600
_SCOPES = ("inference", "models", "self_usage", "mcp")


class WorkspaceServer:
    """Browser session in front of the user gateway. Tokens are not stored."""

    def __init__(
        self,
        service: GatewayService,
        *,
        public_base: str,
        client_id: str,
        static_dir: Path,
        tls: bool = False,
    ) -> None:
        self.service = service
        self.public_base = public_base.rstrip("/")
        self.client_id = client_id
        self.static_dir = Path(static_dir)
        self.tls = tls
        self.store = WorkspaceStore(service.store_root)
        self._pending: dict[str, tuple[str, float]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self.store.close()
        self.service.close()


def bind_workspace(
    server: WorkspaceServer,
    *,
    host: str,
    port: int,
    clock: Callable[[], datetime] | None = None,
) -> ThreadingHTTPServer:
    return _httpd(server, host, port, clock or (lambda: datetime.now(UTC)))


def serve_workspace(
    server: WorkspaceServer,
    *,
    host: str,
    port: int,
    tls_cert: Path | None = None,
    tls_key: Path | None = None,
    clock: Callable[[], datetime] | None = None,
) -> None:
    httpd = _httpd(server, host, port, clock or (lambda: datetime.now(UTC)))
    if tls_cert is not None and tls_key is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls_cert, tls_key)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        server.close()


def _httpd(
    server: WorkspaceServer,
    host: str,
    port: int,
    clock: Callable[[], datetime],
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            _dispatch(self, server, "GET", clock)

        def do_POST(self) -> None:
            _dispatch(self, server, "POST", clock)

        def log_message(self, *_args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def _dispatch(
    handler: BaseHTTPRequestHandler,
    server: WorkspaceServer,
    method: str,
    clock: Callable[[], datetime],
) -> None:
    path = urllib.parse.urlsplit(handler.path).path
    if path.startswith("/v1") or path == "/me":
        _route(handler, server.service, method, frozenset(), clock)
        return
    length = int(handler.headers.get("content-length", "0") or "0")
    if length > _MAX_BODY:
        _fail(handler, "overloaded")
        return
    raw = handler.rfile.read(length) if length else b""
    now = clock()
    try:
        if path.startswith("/api/workspace/v1"):
            _api(handler, server, method, path, raw, now)
            return
        _static(handler, server, path)
    except ValidationError as exc:
        _fail(handler, exc.message)
    except (BrokenPipeError, ConnectionResetError):
        return


def _api(
    handler: BaseHTTPRequestHandler,
    server: WorkspaceServer,
    method: str,
    path: str,
    raw: bytes,
    now: datetime,
) -> None:
    if method == "GET" and path == "/api/workspace/v1/login":
        _redirect(handler, _authorize_url(server))
        return
    if method == "GET" and path == "/api/workspace/v1/callback":
        _callback(handler, server, now)
        return
    if method == "POST" and path == "/api/workspace/v1/logout":
        session = _session(handler, server, now)
        _csrf(handler, session)
        server.store.drop_session(session["session_id"])
        _json(handler, 200, {"ok": True}, _clear_cookie())
        return
    if method == "GET" and path == "/api/workspace/v1/me":
        session = _session(handler, server, now)
        principal = _principal(server, session)
        _json(handler, 200, {
            "user_id": principal.user_id,
            "csrf": session["csrf"],
            "client": "rukan_workspace",
        })
        return
    session = _session(handler, server, now)
    if method == "POST":
        _csrf(handler, session)
        _origin(handler, server)
    principal = _principal(server, session)
    body = _object(raw) if raw else {}
    _workspace(handler, server, method, path, principal, body, now)


def _workspace(
    handler: BaseHTTPRequestHandler,
    server: WorkspaceServer,
    method: str,
    path: str,
    principal: Principal,
    body: dict[str, object],
    now: datetime,
) -> None:
    user_id = principal.user_id
    parts = [item for item in path.split("/") if item]
    if method == "GET" and path == "/api/workspace/v1/models":
        _json(handler, 200, server.service.models(principal))
        return
    if method == "GET" and path == "/api/workspace/v1/usage":
        period = str(body.get("period", "all")) if body else "all"
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
        chosen = query.get("period", [period])[0]
        _json(handler, 200, server.service.my_usage(principal, chosen, now))
        return
    if method == "GET" and path == "/api/workspace/v1/conversations":
        _json(handler, 200, {"conversations": server.store.list_conversations(user_id)})
        return
    if method == "POST" and path == "/api/workspace/v1/conversations":
        created = server.store.create_conversation(
            user_id,
            title=str(body.get("title", "New chat")),
            model_id=str(body.get("model_id", "")),
            agent_id=str(body.get("agent_id", "")),
            now=now,
        )
        _json(handler, 200, created)
        return
    if method == "GET" and path == "/api/workspace/v1/agents":
        _json(handler, 200, {"agents": server.store.list_agents(user_id)})
        return
    if method == "POST" and path == "/api/workspace/v1/agents":
        _capability(server, user_id, "agent_builder")
        saved = server.store.save_agent(
            user_id,
            display_name=str(body.get("display_name", "Agent")),
            instructions=str(body.get("instructions", "")),
            model_id=str(body.get("model_id", "")),
            mcp_server_ids=str(body.get("mcp_server_ids", "")),
            now=now,
        )
        _json(handler, 200, saved)
        return
    if method == "GET" and path == "/api/workspace/v1/tools":
        _json(handler, 200, {"servers": _tools(server, principal, now)})
        return
    if len(parts) >= 5 and parts[3] == "conversations":
        _conversation(handler, server, method, parts, principal, body, now)
        return
    if (
        method == "POST"
        and len(parts) >= 5
        and parts[3] == "agents"
        and parts[-1] == "archive"
    ):
        server.store.archive_agent(user_id, parts[4], now)
        _json(handler, 200, {"ok": True})
        return
    if len(parts) >= 6 and parts[3] == "tools" and parts[5] == "call":
        _capability(server, user_id, "mcp_use")
        approved = server.service.ledger.server(parts[4])
        if approved is None:
            raise ValidationError("mcp_access_denied")
        name = body.get("name")
        if isinstance(name, str) and name:
            from machi.adapters.rukan.mcp_host import call_tool

            try:
                text = call_tool(str(approved["endpoint"]), name, {})
            except Exception as exc:
                raise ValidationError("mcp_unavailable") from exc
            _json(handler, 200, {"text": text})
            return
        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValidationError("mcp_unavailable")
        result = server.service.mcp_call(principal, parts[4], payload, now=now)
        _json(handler, 200, result)
        return
    if method == "POST" and path == "/api/workspace/v1/credentials":
        issued = issue_credential(
            server.service.directory,
            user_id=user_id,
            label=str(body.get("label", "workspace")),
            scopes=_SCOPES,
            ttl_seconds=_ttl(body.get("ttl_seconds", 30 * 24 * 3600)),
            now=now,
            actor="self",
        )
        _json(handler, 200, issued)
        return
    if method == "POST" and path == "/api/workspace/v1/credentials/revoke":
        revoked = server.service.revoke_own(
            principal, str(body.get("key_id", "")), now
        )
        _json(handler, 200, revoked)
        return
    raise ValidationError("workspace_conflict")


def _conversation(
    handler: BaseHTTPRequestHandler,
    server: WorkspaceServer,
    method: str,
    parts: list[str],
    principal: Principal,
    body: dict[str, object],
    now: datetime,
) -> None:
    identity = parts[4]
    user_id = principal.user_id
    action = parts[5] if len(parts) > 5 else ""
    if method == "GET" and not action:
        _json(handler, 200, server.store.conversation(user_id, identity))
        return
    if method == "POST" and action == "title":
        server.store.rename(user_id, identity, str(body.get("title", "")), now)
        _json(handler, 200, {"ok": True})
        return
    if method == "POST" and action == "archive":
        server.store.archive(user_id, identity, now)
        _json(handler, 200, {"ok": True})
        return
    if method == "POST" and action == "stop":
        event = server._cancel.get(identity)
        if event is not None:
            event.set()
        _json(handler, 200, {"ok": True})
        return
    if method == "POST" and action == "regenerate":
        server.store.drop_last_assistant(user_id, identity)
        document = server.store.conversation(user_id, identity)
        messages = document["messages"]
        if not isinstance(messages, list) or not messages:
            raise ValidationError("conversation_not_found")
        last = messages[-1]
        if not isinstance(last, dict) or last.get("role") != "user":
            raise ValidationError("workspace_conflict")
        _stream(handler, server, principal, identity, str(last.get("content", "")), now)
        return
    if method == "POST" and action == "messages":
        _stream(handler, server, principal, identity, str(body.get("content", "")), now)
        return
    raise ValidationError("conversation_not_found")


def _stream(
    handler: BaseHTTPRequestHandler,
    server: WorkspaceServer,
    principal: Principal,
    conversation_id: str,
    content: str,
    now: datetime,
) -> None:
    if not content.strip():
        raise ValidationError("workspace_conflict")
    document = server.store.conversation(principal.user_id, conversation_id)
    prior = document["messages"]
    history: list[dict[str, str]] = []
    agent_id = str(document["agent_id"])
    if agent_id:
        _capability(server, principal.user_id, "agent_use")
        agent = server.store.agent(principal.user_id, agent_id)
        history.append({"role": "system", "content": agent["instructions"]})
    if isinstance(prior, list):
        for item in prior:
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
                history.append({
                    "role": str(item["role"]),
                    "content": str(item["content"]),
                })
    if not history or history[-1].get("content") != content:
        server.store.add_message(
            principal.user_id, conversation_id, role="user", content=content, now=now
        )
        history.append({"role": "user", "content": content})
    server.service.upstream.refresh()
    model = str(document["model_id"]) or (server.service.upstream.model_id or "")
    cancel = threading.Event()
    server._cancel[conversation_id] = cancel
    text: list[str] = []
    inputs = "not_recorded"
    outputs = "not_recorded"
    started = False
    try:
        for _round in range(2):
            iterator = server.service.stream(
                principal,
                {"model": model, "messages": history, "max_tokens": 64},
                now=now,
            )
            try:
                try:
                    first = next(iterator)
                except StopIteration:
                    first = b""
                except ValidationError:
                    _close(iterator)
                    raise
                if not started:
                    handler.send_response(200)
                    handler.send_header("content-type", "text/event-stream")
                    handler.send_header("cache-control", "no-cache")
                    handler.end_headers()
                    started = True
                tool_payload, round_in, round_out = _forward(
                    handler, iterator, first, cancel, text
                )
                if round_in is not None:
                    inputs = str(round_in)
                if round_out is not None:
                    outputs = str(round_out)
            finally:
                _close(iterator)
            if not tool_payload or cancel.is_set():
                break
            result = _invoke_tool(server, principal, tool_payload, now)
            history.append({"role": "assistant", "content": tool_payload})
            history.append({"role": "user", "content": json.dumps(result)})
        if started:
            handler.wfile.write(b"data: {\"done\": true}\n\n")
            handler.wfile.flush()
    finally:
        server._cancel.pop(conversation_id, None)
        if text:
            server.store.add_message(
                principal.user_id,
                conversation_id,
                role="assistant",
                content="".join(text),
                now=now,
                input_tokens=inputs,
                output_tokens=outputs,
            )


def _ttl(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("workspace_conflict")
    return value


def _close(iterator: Iterator[bytes]) -> None:
    closer = getattr(iterator, "close", None)
    if callable(closer):
        closer()


def _forward(
    handler: BaseHTTPRequestHandler,
    iterator: Iterator[bytes],
    first: bytes,
    cancel: threading.Event,
    text: list[str],
) -> tuple[str, int | None, int | None]:
    tool = ""
    inputs: int | None = None
    outputs: int | None = None
    pending = first
    while True:
        raw = pending if pending else next(iterator, b"")
        pending = b""
        if not raw or cancel.is_set():
            break
        piece = _delta(raw)
        if piece:
            text.append(piece)
            handler.wfile.write(
                f"data: {json.dumps({'delta': piece})}\n\n".encode()
            )
            handler.wfile.flush()
        requested = _tool_call(raw)
        if requested:
            tool = requested
        found_in, found_out = _usage(raw)
        if found_in is not None:
            inputs = found_in
        if found_out is not None:
            outputs = found_out
    return tool, inputs, outputs


def _tool_call(raw: bytes) -> str:
    payload = _data(raw)
    if isinstance(payload, dict) and isinstance(payload.get("tool_call"), str):
        return str(payload["tool_call"])
    return ""


def _invoke_tool(
    server: WorkspaceServer,
    principal: Principal,
    payload: str,
    now: datetime,
) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValidationError("mcp_unavailable") from exc
    if not isinstance(document, dict):
        raise ValidationError("mcp_unavailable")
    arguments = document.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    return server.service.mcp_call(
        principal,
        str(document.get("server_id", "")),
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": str(document.get("name", "")), "arguments": arguments},
        },
        now=now,
    )


def _tools(
    server: WorkspaceServer, principal: Principal, now: datetime
) -> list[dict[str, object]]:
    del now
    from machi.adapters.rukan.mcp_host import tool_names

    _capability(server, principal.user_id, "mcp_use")
    found: list[dict[str, object]] = []
    for item in server.service.ledger.servers():
        endpoint = str(item.get("endpoint", ""))
        found.append({
            "server_id": str(item.get("server_id", "")),
            "display_name": item.get("display_name", ""),
            "tools": tool_names(endpoint),
        })
    return found


def _authorize_url(server: WorkspaceServer) -> str:
    verifier = server.service.verifier
    if not isinstance(verifier, OidcDiscoveryVerifier):
        raise ValidationError("authentication_required")
    verifier._ensure()
    if not verifier.authorization_endpoint or not verifier.token_endpoint:
        raise ValidationError("authentication_required")
    verifier_text = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    with server._lock:
        server._pending[state] = (verifier_text, time.monotonic() + 600)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier_text.encode()).digest()
    ).decode().rstrip("=")
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": server.client_id,
        "redirect_uri": server.public_base + "/api/workspace/v1/callback",
        "scope": "openid email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return verifier.authorization_endpoint + "?" + query


def _callback(
    handler: BaseHTTPRequestHandler, server: WorkspaceServer, now: datetime
) -> None:
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(handler.path).query)
    state = query.get("state", [""])[0]
    code = query.get("code", [""])[0]
    with server._lock:
        pending = server._pending.pop(state, None)
    if pending is None or pending[1] < time.monotonic() or not code:
        raise ValidationError("authentication_required")
    verifier = server.service.verifier
    if not isinstance(verifier, OidcDiscoveryVerifier):
        raise ValidationError("authentication_required")
    token = _exchange(server, verifier.token_endpoint, code, pending[0])
    claims = verifier.verify(token)
    bound = server.service.directory.resolve_oidc(
        issuer=claims["issuer"],
        subject=claims["subject"],
        email=claims["email"],
        now=now,
    )
    opened = server.store.open_session(
        str(bound["user_id"]), now=now, ttl_seconds=_SESSION_TTL
    )
    _redirect(
        handler,
        server.public_base + "/",
        _set_cookie(opened["session_id"], server.tls),
    )


def _exchange(server: WorkspaceServer, endpoint: str, code: str, verifier: str) -> str:
    form = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": server.public_base + "/api/workspace/v1/callback",
        "client_id": server.client_id,
        "code_verifier": verifier,
    }).encode()
    request = urllib.request.Request(
        endpoint,
        data=form,
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ValidationError("authentication_required") from exc
    if not isinstance(payload, dict):
        raise ValidationError("authentication_required")
    token = payload.get("id_token") or payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValidationError("authentication_required")
    return token


def _session(
    handler: BaseHTTPRequestHandler, server: WorkspaceServer, now: datetime
) -> dict[str, str]:
    raw = handler.headers.get("Cookie", "")
    found = ""
    for part in raw.split(";"):
        name, _, value = part.strip().partition("=")
        if name == _SESSION:
            found = value
    opened = server.store.session(found, now) if found else None
    if opened is None:
        raise ValidationError("session_expired")
    return opened


def _principal(server: WorkspaceServer, session: dict[str, str]) -> Principal:
    access = server.service.directory.effective(session["user_id"])
    if access["status"] != "active":
        raise ValidationError("user_suspended")
    if access["platform_access"] != "allow" or access["workspace"] != "allow":
        raise ValidationError("scope_denied")
    return Principal(session["user_id"], "oidc", _SCOPES, "rukan_workspace")


def _capability(server: WorkspaceServer, user_id: str, name: str) -> None:
    access = server.service.directory.effective(user_id)
    if access.get(name) != "allow":
        raise ValidationError("scope_denied")


def _csrf(handler: BaseHTTPRequestHandler, session: dict[str, str]) -> None:
    if handler.headers.get("X-Rukan-CSRF", "") != session["csrf"]:
        raise ValidationError("session_expired")


def _origin(handler: BaseHTTPRequestHandler, server: WorkspaceServer) -> None:
    origin = handler.headers.get("Origin", "")
    if origin and origin.rstrip("/") != server.public_base:
        raise ValidationError("session_expired")


def _static(
    handler: BaseHTTPRequestHandler, server: WorkspaceServer, path: str
) -> None:
    relative = "index.html" if path in {"", "/"} else path.lstrip("/")
    target = (server.static_dir / relative).resolve()
    root = server.static_dir.resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        target = server.static_dir / "index.html"
    if not target.is_file():
        _bytes(handler, 200, _FALLBACK.encode(), "text/html; charset=utf-8")
        return
    kind = "text/html; charset=utf-8"
    if target.suffix == ".js":
        kind = "text/javascript; charset=utf-8"
    elif target.suffix == ".css":
        kind = "text/css; charset=utf-8"
    _bytes(handler, 200, target.read_bytes(), kind)


def _delta(raw: bytes) -> str:
    payload = _data(raw)
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return ""
    text = delta.get("content")
    return text if isinstance(text, str) else ""


def _usage(raw: bytes) -> tuple[int | None, int | None]:
    payload = _data(raw)
    if not isinstance(payload, dict):
        return None, None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if isinstance(prompt, int) else None,
        completion if isinstance(completion, int) else None,
    )


def _data(raw: bytes) -> object:
    line = raw.decode("utf-8", "replace").strip()
    if not line.startswith("data:"):
        return None
    text = line[5:].strip()
    if text == "[DONE]":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _object(raw: bytes) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("workspace_conflict") from exc
    if not isinstance(payload, dict):
        raise ValidationError("workspace_conflict")
    return payload


def _set_cookie(session_id: str, tls: bool) -> str:
    suffix = "; Secure" if tls else ""
    return f"{_SESSION}={session_id}; HttpOnly; SameSite=Lax; Path=/{suffix}"


def _clear_cookie() -> str:
    return f"{_SESSION}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"


def _redirect(handler: BaseHTTPRequestHandler, location: str, cookie: str = "") -> None:
    handler.send_response(302)
    handler.send_header("location", location)
    if cookie:
        handler.send_header("set-cookie", cookie)
    handler.end_headers()


def _json(
    handler: BaseHTTPRequestHandler, status: int, payload: object, cookie: str = ""
) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json")
    handler.send_header("content-length", str(len(encoded)))
    if cookie:
        handler.send_header("set-cookie", cookie)
    handler.end_headers()
    handler.wfile.write(encoded)


def _bytes(
    handler: BaseHTTPRequestHandler, status: int, payload: bytes, kind: str
) -> None:
    handler.send_response(status)
    handler.send_header("content-type", kind)
    handler.send_header("content-length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def _fail(handler: BaseHTTPRequestHandler, code: str) -> None:
    _json(handler, status_for(code), {"error": code})


_FALLBACK = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Rukan Workspace</title></head>
<body><p>Rukan Workspace assets are not built into this process.</p>
<p><a href="/api/workspace/v1/login">Sign in</a></p></body></html>
"""
