"""Workspace session, conversations, backup, and the bounded tool loop."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.employee_ops import backup_employee_state, load_provider
from machi.adapters.rukan.gateway import GatewayService, StreamPiece, UpstreamResult
from machi.adapters.rukan.mcp_policy import _pin
from machi.adapters.rukan.oidc import OidcDiscoveryVerifier
from machi.adapters.rukan.workspace_http import WorkspaceServer, bind_workspace
from machi.adapters.rukan.workspace_store import WorkspaceStore
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.errors import ValidationError

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")
NOW = datetime.now(UTC).replace(microsecond=0)
AUDIENCE = "rukan"


class FakeChat:
    def __init__(self) -> None:
        self.model_id: str | None = "mart_test"
        self.instance_id = "sin_test"
        self.macropath = "vllm"
        self.calls = 0

    def refresh(self) -> None:
        return None

    def complete(self, *, model: str, messages: list[dict[str, str]], max_tokens: int, stream: bool, tools: object = None) -> UpstreamResult:  # noqa: E501
        del messages, max_tokens, stream, model, tools
        raise ValidationError("upstream_failure")

    def iter_stream(self, *, model: str, messages: list[dict[str, str]], max_tokens: int, tools: object = None):  # noqa: E501
        del messages, max_tokens, tools
        self.calls += 1
        if model != self.model_id:
            raise ValidationError("model_not_allowed")
        yield StreamPiece("delta", "ok")
        yield StreamPiece("usage", "", 3, 5)
        yield StreamPiece("done")


class ToolChat(FakeChat):
    def iter_stream(self, *, model: str, messages: list[dict[str, str]], max_tokens: int, tools: object = None):  # noqa: E501
        del messages, max_tokens, tools
        self.calls += 1
        if model != self.model_id:
            raise ValidationError("model_not_allowed")
        if self.calls == 1:
            yield StreamPiece(
                "tool_delta", "{}", tool_id="call_1", tool_name="ping"
            )
        else:
            yield StreamPiece("delta", "pong")
        yield StreamPiece("usage", "", 1, 1)
        yield StreamPiece("done")


def _allow(directory: Directory, user_id: str) -> None:
    directory.set_intent(
        subject_kind="user",
        subject_id=user_id,
        platform_access="allow",
        inference_access="allow",
        model_selection="allow",
        agent_builder="allow",
        agent_use="allow",
        api_credential="allow",
        workspace="allow",
        mcp_use="allow",
        mcp_connect="deny",
        actor="local_admin_ui",
        now=NOW,
    )


def test_https_mcp_keeps_the_hostname(monkeypatch: pytest.MonkeyPatch) -> None:
    import ipaddress

    monkeypatch.setattr(
        "machi.adapters.rukan.mcp_policy._addresses",
        lambda _host: (ipaddress.ip_address("1.2.3.4"),),
    )
    assert _pin("https://mcp.example/rpc") == "https://mcp.example/rpc"


def test_conversation_returns_the_agent_snapshot(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    created = store.create_conversation(
        "usr_a",
        title="Add",
        model_id="mart_test",
        agent_id="agt_add",
        now=NOW,
        agent_revision="2",
        instruction_snapshot="Call the add tool.",
        tool_refs="acceptance/add",
    )
    store.add_message(
        "usr_a",
        created["conversation_id"],
        role="assistant",
        content="5",
        now=NOW,
        usage_id="usg_test",
    )
    document = store.conversation("usr_a", created["conversation_id"])
    store.close()
    assert document["tool_refs"] == "acceptance/add"
    assert document["instruction_snapshot"] == "Call the add tool."
    assert document["agent_revision"] == "2"
    messages = document["messages"]
    assert isinstance(messages, list)
    assert messages[0]["usage_id"] == "usg_test"


def test_backup_uses_sqlite_and_keeps_workspace_text(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    created = store.create_conversation(
        "usr_a", title="Notes", model_id="mart_test", agent_id="", now=NOW
    )
    store.add_message(
        "usr_a", created["conversation_id"], role="user", content="local only", now=NOW
    )
    store.close()
    copied = backup_employee_state(tmp_path, tmp_path / "backup")
    assert "workspace.sqlite" in copied
    assert (tmp_path / "backup" / "manifest.json").is_file()
    restored = WorkspaceStore(tmp_path / "backup")
    document = restored.conversation("usr_a", created["conversation_id"])
    restored.close()
    messages = document["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == "local only"


def test_other_user_cannot_read_a_conversation(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    created = store.create_conversation(
        "usr_a", title="Private", model_id="mart_test", agent_id="", now=NOW
    )
    with pytest.raises(ValidationError, match="conversation_not_found"):
        store.conversation("usr_b", created["conversation_id"])
    store.close()


def test_login_streams_and_suspension_denies_the_next_call(tmp_path: Path) -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public.update({"kid": "test", "alg": "RS256", "use": "sig"})
    holder: dict[str, str] = {}

    class IdP(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            issuer = holder["issuer"]
            if "/authorize" in self.path:
                query = urllib.parse.urlparse(self.path).query
                params = urllib.parse.parse_qs(query)
                holder["nonce"] = params.get("nonce", [""])[0]
                target = params["redirect_uri"][0] + "?" + urllib.parse.urlencode({
                    "code": "one-time", "state": params["state"][0]
                })
                self.send_response(302)
                self.send_header("location", target)
                self.end_headers()
                return
            if self.path.endswith("jwks"):
                payload = {"keys": [public]}
            else:
                payload = {
                    "issuer": issuer,
                    "authorization_endpoint": issuer + "/authorize",
                    "token_endpoint": issuer + "/token",
                    "jwks_uri": issuer + "/jwks",
                }
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self) -> None:
            token = jwt.encode(
                {
                    "iss": holder["issuer"],
                    "aud": AUDIENCE,
                    "sub": "subject-ada",
                    "email": "ada@example.invalid",
                    "nonce": holder.get("nonce", ""),
                    "exp": int((NOW + timedelta(minutes=5)).timestamp()),
                },
                key,
                algorithm="RS256",
                headers={"kid": "test"},
            )
            raw = json.dumps({"id_token": token}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args: object) -> None:
            return

    idp = ThreadingHTTPServer(("127.0.0.1", 0), IdP)
    threading.Thread(target=idp.serve_forever, daemon=True).start()
    issuer = f"http://127.0.0.1:{idp.server_address[1]}/realms/rukan"
    holder["issuer"] = issuer
    chat = FakeChat()
    service = GatewayService(
        tmp_path,
        BUILD,
        OidcDiscoveryVerifier(issuer=issuer, audience=AUDIENCE, allow_http=True),
        chat,
    )
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    server = WorkspaceServer(
        service,
        public_base="http://127.0.0.1",
        client_id=AUDIENCE,
        static_dir=tmp_path / "ui",
    )
    httpd = bind_workspace(server, host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = int(httpd.server_address[1])
    server.public_base = f"http://127.0.0.1:{port}"
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar())
    )
    opener.open(server.public_base + "/api/workspace/v1/login")
    me = json.loads(opener.open(server.public_base + "/api/workspace/v1/me").read())
    assert me["user_id"] == ada["user_id"]
    created = json.loads(opener.open(urllib.request.Request(
        server.public_base + "/api/workspace/v1/conversations",
        data=json.dumps({"title": "Hello", "model_id": "mart_test"}).encode(),
        headers={"content-type": "application/json", "X-Rukan-CSRF": me["csrf"]},
        method="POST",
    )).read())
    body = opener.open(urllib.request.Request(
        (
            server.public_base
            + "/api/workspace/v1/conversations/"
            + created["conversation_id"]
            + "/messages"
        ),
        data=json.dumps({"content": "Hi"}).encode(),
        headers={"content-type": "application/json", "X-Rukan-CSRF": me["csrf"]},
        method="POST",
    )).read().decode()
    assert "ok" in body
    service.directory.set_status(
        str(ada["user_id"]), "suspended", actor="local_admin_ui", now=NOW
    )
    with pytest.raises(urllib.error.HTTPError) as caught:
        opener.open(server.public_base + "/api/workspace/v1/me")
    assert b"user_suspended" in caught.value.read()
    httpd.shutdown()
    idp.shutdown()
    server.close()


def test_tool_loop_calls_mcp_then_the_model_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Tool(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            self.rfile.read(length)
            raw = b'{"result":"pong"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *_args: object) -> None:
            return

    tool = ThreadingHTTPServer(("127.0.0.1", 0), Tool)
    threading.Thread(target=tool.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{tool.server_address[1]}/mcp"
    chat = ToolChat()
    service = GatewayService(
        tmp_path, BUILD,
        OidcDiscoveryVerifier(issuer="https://idp.example.invalid", audience=AUDIENCE),
        chat,
    )
    service.ledger.approve_server(
        server_id="local", display_name="Local", endpoint=endpoint,
        auth_method="none", sensitivity="internal", now=NOW,
    )
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    from machi.adapters.rukan.gateway import Principal

    principal = Principal(str(ada["user_id"]), "oidc", ("inference", "models", "self_usage", "mcp"), "rukan_workspace")  # noqa: E501
    store = WorkspaceStore(tmp_path)
    monkeypatch.setattr(
        "machi.adapters.rukan.workspace_http._agent_tools",
        lambda *_args, **_kwargs: [{
            "type": "function",
            "function": {"name": "ping", "parameters": {"type": "object"}},
        }],
    )
    monkeypatch.setattr(
        "machi.adapters.rukan.mcp_host.call_tool",
        lambda *_args, **_kwargs: "pong",
    )
    created = store.create_conversation(
        principal.user_id, title="Tool", model_id="mart_test", agent_id="", now=NOW,
        tool_refs="local/ping",
    )
    server = WorkspaceServer(
        service, public_base="http://127.0.0.1", client_id=AUDIENCE, static_dir=tmp_path
    )
    server.store.close()
    server.store = store
    httpd = bind_workspace(server, host="127.0.0.1", port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = int(httpd.server_address[1])
    opened = store.open_session(principal.user_id, now=NOW, ttl_seconds=600)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/workspace/v1/conversations/{created['conversation_id']}/messages",
        data=json.dumps({"content": "use the tool"}).encode(),
        headers={
            "content-type": "application/json",
            "X-Rukan-CSRF": opened["csrf"],
            "Cookie": f"rukan_session={opened['session_id']}",
        },
        method="POST",
    )
    body = urllib.request.urlopen(request).read().decode()
    assert "pong" in body
    assert chat.calls == 2
    httpd.shutdown()
    tool.shutdown()
    server.close()


def test_official_mcp_sdk_lists_and_calls_ping() -> None:
    from machi.adapters.rukan.mcp_host import (
        call_tool,
        list_tool_names,
        serve_acceptance,
    )

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = int(probe.getsockname()[1])
    probe.close()
    thread = threading.Thread(
        target=serve_acceptance, kwargs={"port": port}, daemon=True
    )
    thread.start()
    url = f"http://127.0.0.1:{port}/mcp"
    deadline = datetime.now(UTC) + timedelta(seconds=15)
    names: list[str] = []
    while datetime.now(UTC) < deadline:
        try:
            names = list_tool_names(url)
            break
        except Exception:
            threading.Event().wait(0.2)
    assert names == ["ping", "add"]
    assert call_tool(url, "ping", {}) == "pong"


def test_unknown_provider_is_not_invented(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="identity provider is unknown"):
        load_provider(tmp_path, "missing")
