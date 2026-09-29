"""User gateway, identity binding, usage conservation, and the LibreChat adapter."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from machi.adapters.rukan.credentials import issue_credential, verify_credential
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.gateway import GatewayService, UpstreamResult, _chat_body
from machi.adapters.rukan.gateway_http import _server
from machi.adapters.rukan.librechat import (
    LIBRECHAT_DIGEST,
    LIBRECHAT_VERSION,
    capability_profile,
    render_config,
    require_supported,
)
from machi.adapters.rukan.mcp_policy import assert_endpoint
from machi.adapters.rukan.oidc import OIDCBearerVerifier
from machi.adapters.rukan.server import AdminApplication
from machi.kernel.build import BuildIdentity, BuildOrigin
from machi.kernel.errors import ValidationError
from machi.kernel.usage import InferenceUsage

BUILD = BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="0.1.0+test")
NOW = datetime.now(UTC).replace(microsecond=0)
ISSUER = "https://idp.example.invalid/realms/rukan"
AUDIENCE = "rukan"


class FakeChat:
    def __init__(self) -> None:
        self.model_id: str | None = "mart_test"
        self.instance_id = "sin_test"
        self.macropath = "vllm"
        self.calls = 0

    def refresh(self) -> None:
        return None

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        stream: bool,
    ) -> UpstreamResult:
        del messages, max_tokens, stream
        self.calls += 1
        if self.model_id is None:
            raise ValidationError("no_ready_model")
        if model != self.model_id:
            raise ValidationError("model_not_allowed")
        return UpstreamResult("completed", "ok", 3, 5, ("ok",))


def _material() -> tuple[rsa.RSAPrivateKey, dict[str, object]]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    public["kid"] = "test"
    public["alg"] = "RS256"
    public["use"] = "sig"
    return key, {"keys": [public]}


def _token(
    key: rsa.RSAPrivateKey,
    *,
    email: str = "ada@example.invalid",
    subject: str = "subject-ada",
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    exp: datetime | None = None,
    nbf: datetime | None = None,
    kid: str = "test",
) -> str:
    payload: dict[str, object] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "exp": int((exp or (NOW + timedelta(minutes=5))).timestamp()),
    }
    if email:
        payload["email"] = email
    if nbf is not None:
        payload["nbf"] = int(nbf.timestamp())
    encoded = jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid})
    return encoded if isinstance(encoded, str) else encoded.decode("utf-8")


def _service(tmp_path: Path) -> tuple[GatewayService, FakeChat, rsa.RSAPrivateKey]:
    key, jwks = _material()
    chat = FakeChat()
    service = GatewayService(
        tmp_path,
        BUILD,
        OIDCBearerVerifier(issuer=ISSUER, audience=AUDIENCE, jwks=jwks),
        chat,  # type: ignore[arg-type]
    )
    return service, chat, key


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


def test_binding_denies_unprovisioned_and_conflicts(tmp_path: Path) -> None:
    service, _chat, key = _service(tmp_path)
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    missing = _token(key, email="")
    with pytest.raises(ValidationError, match="identity_not_provisioned"):
        service.authenticate(f"Bearer {missing}", client_id="generic", now=NOW)
    first = _token(key)
    principal = service.authenticate(f"Bearer {first}", client_id="librechat", now=NOW)
    assert principal.user_id == ada["user_id"]
    again = service.authenticate(
        f"Bearer {_token(key, email='')}", client_id="librechat", now=NOW
    )
    assert again.user_id == ada["user_id"]
    with pytest.raises(ValidationError, match="identity_binding_conflict"):
        service.authenticate(
            f"Bearer {_token(key, subject='other-subject')}",
            client_id="generic",
            now=NOW,
        )
    service.directory.set_status(str(ada["user_id"]), "suspended", actor="local_admin_ui", now=NOW)  # noqa: E501
    with pytest.raises(ValidationError, match="user_suspended"):
        service.authenticate(f"Bearer {first}", client_id="generic", now=NOW)
    service.close()


def test_verifier_rejects_bad_tokens(tmp_path: Path) -> None:
    service, _chat, key = _service(tmp_path)
    other, _jwks = _material()
    samples = [
        _token(other),
        _token(key, issuer="https://evil.example.invalid"),
        _token(key, audience="elsewhere"),
        _token(key, exp=NOW - timedelta(minutes=5)),
        _token(key, nbf=NOW + timedelta(hours=1)),
        _token(key, kid="missing"),
    ]
    for sample in samples:
        with pytest.raises(ValidationError, match="authentication_required"):
            service.authenticate(f"Bearer {sample}", client_id="generic", now=NOW)
    service.close()


def test_two_users_conserve_tokens_and_ignore_operator_tests(tmp_path: Path) -> None:
    service, chat, key = _service(tmp_path)
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    bob = service.directory.create_user(
        email="bob@example.invalid", display_name="Bob", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    _allow(service.directory, str(bob["user_id"]))
    alpha = service.directory.create_team(
        name="Alpha", description="", actor="local_admin_ui", now=NOW
    )
    service.directory.add_membership(
        str(ada["user_id"]), str(alpha["team_id"]), actor="local_admin_ui", now=NOW
    )
    ada_token = _token(key)
    bob_token = _token(key, email="bob@example.invalid", subject="subject-bob")
    body = {"model": "mart_test", "messages": [{"role": "user", "content": "hi"}]}
    service.authenticate(f"Bearer {ada_token}", client_id="librechat", now=NOW)
    for offset in range(2):
        when = NOW + timedelta(seconds=offset)
        principal = service.authenticate(f"Bearer {ada_token}", client_id="librechat", now=when)  # noqa: E501
        service.chat(principal, body, now=when, stream=False)
        streamed = list(service.stream(principal, {**body, "stream": True}, now=when))
        assert any(b"[DONE]" in item for item in streamed)
    bob_principal = service.authenticate(
        f"Bearer {bob_token}", client_id="generic", now=NOW
    )
    service.chat(bob_principal, body, now=NOW, stream=False)
    assert chat.calls == 5
    ada_usage = service.my_usage(
        service.authenticate(f"Bearer {ada_token}", client_id="librechat", now=NOW),
        "all",
        NOW,
    )
    with pytest.raises(ValidationError, match="unknown"):
        service.ledger.user_usage(str(bob["user_id"]), period="nope", now=NOW)
    bob_usage = service.my_usage(bob_principal, "all", NOW)
    assert ada_usage["requests"] == 4
    assert bob_usage["requests"] == 1
    assert ada_usage["input_tokens"] == "12"
    assert bob_usage["input_tokens"] == "3"
    operator = InferenceUsage(
        usage_id="usg_operator",
        request_id="req_operator",
        occurred_at=NOW.isoformat(),
        purpose="operator_test",
        install_id="not_recorded",
        instance_id="sin_test",
        plan_id="not_recorded",
        reservation_id="not_recorded",
        generation_id="not_recorded",
        model_identity="mart_test",
        model_identity_kind="warehouse_artifact",
        macropath="vllm",
        outcome="completed",
        failure="none",
        status_code=200,
        input_tokens="9",
        output_tokens="9",
        latency_ms="1",
        runtime_duration_ms="not_recorded",
        version="0.1.0",
        build_id="0.1.0+test",
    )
    assert service.telemetry.record_usage(operator) is True
    app = AdminApplication(tmp_path, BUILD)
    analytics = app.analytics()
    recon = analytics["body"]["reconciliation"]
    assert recon["match"] is True
    assert recon["deployment_requests"] == 5
    assert recon["deployment_input_tokens"] == "15"
    assert "ada@example.invalid" not in json.dumps(analytics["body"]["gateway_users"])
    preview = service.telemetry.preview(NOW)
    encoded = json.dumps(preview)
    assert "ada@example.invalid" not in encoded
    assert str(ada["user_id"]) not in encoded
    service.close()


def test_credentials_are_hashed_and_revocable(tmp_path: Path) -> None:
    service, _chat, _key = _service(tmp_path)
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    issued = issue_credential(
        service.directory,
        user_id=str(ada["user_id"]),
        label="curl",
        scopes=("inference", "models", "self_usage"),
        ttl_seconds=3600,
        now=NOW,
        actor="local_admin_ui",
    )
    secret = str(issued["secret"])
    assert secret not in (tmp_path / "directory.sqlite").read_bytes().decode("utf-8", "ignore")  # noqa: E501
    principal = service.authenticate(f"Bearer {secret}", client_id="generic", now=NOW)
    service.chat(
        principal,
        {"model": "mart_test", "messages": [{"role": "user", "content": "hi"}]},
        now=NOW,
        stream=False,
    )
    from machi.adapters.rukan.credentials import revoke_credential

    revoke_credential(
        service.directory,
        user_id=str(ada["user_id"]),
        key_id=str(issued["key_id"]),
        now=NOW,
        actor="local_admin_ui",
    )
    with pytest.raises(ValidationError, match="authentication_required"):
        verify_credential(service.directory, secret, NOW)
    service.directory.set_status(str(ada["user_id"]), "suspended", actor="local_admin_ui", now=NOW)  # noqa: E501
    service.close()


def test_mcp_policy_and_librechat_boundary(tmp_path: Path) -> None:
    service, _chat, key = _service(tmp_path)
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    bob = service.directory.create_user(
        email="bob@example.invalid", display_name="Bob", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    service.directory.set_intent(
        subject_kind="user",
        subject_id=str(bob["user_id"]),
        platform_access="allow",
        inference_access="allow",
        model_selection="allow",
        agent_builder="deny",
        agent_use="deny",
        api_credential="deny",
        workspace="allow",
        mcp_use="deny",
        mcp_connect="deny",
        actor="local_admin_ui",
        now=NOW,
    )

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            self.rfile.read(length)
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}).encode()  # noqa: E501
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    endpoint = f"http://127.0.0.1:{port}/mcp"
    service.ledger.approve_server(
        server_id="status",
        display_name="Status",
        endpoint=endpoint,
        auth_method="none",
        sensitivity="internal",
        now=NOW,
    )
    ada_principal = service.authenticate(
        f"Bearer {_token(key)}", client_id="librechat", now=NOW
    )
    result = service.mcp_call(
        ada_principal, "status", {"jsonrpc": "2.0", "id": 1, "method": "tools/call"}, now=NOW  # noqa: E501
    )
    assert result["result"] == {"ok": True}
    bob_principal = service.authenticate(
        f"Bearer {_token(key, email='bob@example.invalid', subject='subject-bob')}",
        client_id="librechat",
        now=NOW,
    )
    with pytest.raises(ValidationError, match="mcp_access_denied"):
        service.mcp_call(bob_principal, "status", {"method": "tools/call"}, now=NOW)
    service.chat(
        bob_principal,
        {"model": "mart_test", "messages": [{"role": "user", "content": "hi"}]},
        now=NOW,
        stream=False,
    )
    with pytest.raises(ValidationError, match="mcp_target_denied"):
        assert_endpoint(
            "http://169.254.169.254/latest",
            approved_urls=frozenset(),
            approved_authorities=frozenset(),
        )
    with pytest.raises(ValidationError, match="mcp_target_denied"):
        assert_endpoint(
            "http://127.0.0.1:9/mcp",
            approved_urls=frozenset(),
            approved_authorities=frozenset(),
        )
    assert_endpoint(
        endpoint,
        approved_urls=frozenset({endpoint}),
        approved_authorities=frozenset(),
    )
    rendered = render_config(
        gateway_url="https://gateway.example.invalid",
        mcp_servers=(
            {
                "server_id": "status",
                "broker_url": "https://gateway.example.invalid/mcp/status",
            },
        ),
    )
    assert "{{LIBRECHAT_OPENID_ACCESS_TOKEN}}" in rendered
    assert "127.0.0.1:" not in rendered
    assert "vllm" not in rendered
    profile = capability_profile()
    assert profile["capabilities"]["direct_serve_endpoint"] is False
    assert profile["capabilities"]["agents"] == "client_local"
    with pytest.raises(ValidationError, match="pinned"):
        require_supported("v0.0.0", "sha256:nope")
    assert LIBRECHAT_VERSION == "v0.8.8-rc4"
    assert LIBRECHAT_DIGEST.startswith("sha256:")
    httpd.shutdown()
    service.close()


def test_gateway_http_hides_other_users(tmp_path: Path) -> None:
    service, _chat, key = _service(tmp_path)
    ada = service.directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    _allow(service.directory, str(ada["user_id"]))
    httpd = _server(service, "127.0.0.1", 0, frozenset(), lambda: NOW)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    import urllib.request

    token = _token(key)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(
            {"model": "mart_test", "messages": [{"role": "user", "content": "hi"}]}
        ).encode(),
        headers={"authorization": f"Bearer {token}", "content-type": "application/json"},  # noqa: E501
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["usage"]["total_tokens"] == 8
    usage = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/me/usage?period=all",
        headers={"authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(usage, timeout=10) as response:
        mine = json.loads(response.read().decode("utf-8"))
    assert mine["requests"] == 1
    page = urllib.request.urlopen(f"http://127.0.0.1:{port}/me", timeout=10)
    assert b"My Usage" in page.read()
    httpd.shutdown()
    service.close()


def test_directory_migration_keeps_team_grants(tmp_path: Path) -> None:
    directory = Directory(tmp_path)
    directory.close()
    import sqlite3

    database = sqlite3.connect(tmp_path / "directory.sqlite")
    for name in ("agent_use", "api_credential", "workspace", "mcp_use", "mcp_connect"):
        database.execute(f"ALTER TABLE intents DROP COLUMN {name}")
    database.execute(
        """
        INSERT INTO intents(
            subject_kind, subject_id, platform_access, inference_access,
            model_selection, agent_builder, updated_at
        ) VALUES ('team', 'team_old', 'allow', 'allow', 'deny', 'deny', ?)
        """,
        (NOW.isoformat(),),
    )
    database.commit()
    database.close()
    migrated = Directory(tmp_path)
    stored = migrated._intent("team", "team_old")
    assert stored is not None
    assert stored["inference_access"] == "allow"
    assert stored["agent_use"] == "deny"
    migrated.close()


def test_non_streaming_request_omits_stream_options() -> None:
    quiet = _chat_body("mart_test", [{"role": "user", "content": "hi"}], 8, False)
    flowing = _chat_body("mart_test", [{"role": "user", "content": "hi"}], 8, True)
    assert "stream_options" not in quiet
    assert quiet["stream"] is False
    assert flowing["stream_options"] == {"include_usage": True}
