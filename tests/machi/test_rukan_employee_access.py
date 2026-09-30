"""Employee-access product closure: credentials, backup, MCP redirects, clients."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from machi.adapters.rukan.credentials import issue_credential
from machi.adapters.rukan.directory import Directory
from machi.adapters.rukan.employee_ops import (
    backup_employee_state,
    employee_preflight,
    restore_employee_state,
    save_provider,
)
from machi.adapters.rukan.gateway_http import _client_id
from machi.adapters.rukan.mcp_policy import assert_endpoint, forward_json
from machi.kernel.errors import ValidationError

NOW = datetime.now(UTC).replace(microsecond=0)


def test_client_labels_cannot_multiply() -> None:
    assert _client_id("LibreChat") == "librechat"
    assert _client_id("generic_api") == "generic_api"
    assert _client_id("x" * 500) == "generic_api"
    assert _client_id("attacker-label") == "generic_api"


def test_credential_lifetime_is_bounded(tmp_path: Path) -> None:
    directory = Directory(tmp_path)
    user = directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    directory.set_intent(
        subject_kind="user",
        subject_id=str(user["user_id"]),
        platform_access="allow",
        inference_access="allow",
        model_selection="allow",
        agent_builder="allow",
        api_credential="allow",
        actor="local_admin_ui",
        now=NOW,
    )
    with pytest.raises(ValidationError, match="lifetime"):
        issue_credential(
            directory,
            user_id=str(user["user_id"]),
            label="forever",
            scopes=("inference",),
            ttl_seconds=10,
            now=NOW,
            actor="local_admin_ui",
        )
    issued = issue_credential(
        directory,
        user_id=str(user["user_id"]),
        label="curl",
        scopes=("inference", "mcp"),
        ttl_seconds=3600,
        now=NOW,
        actor="local_admin_ui",
    )
    assert "secret" in issued
    directory.close()


def test_backup_restores_people(tmp_path: Path) -> None:
    directory = Directory(tmp_path / "live")
    directory.create_user(
        email="ada@example.invalid", display_name="Ada", actor="local_admin_ui", now=NOW
    )
    directory.close()
    copied = backup_employee_state(tmp_path / "live", tmp_path / "backup")
    assert "directory.sqlite" in copied
    restore_employee_state(tmp_path / "restored", tmp_path / "backup")
    again = Directory(tmp_path / "restored")
    assert len(again.list_users()) == 1
    again.close()


def test_provider_and_preflight(tmp_path: Path) -> None:
    save_provider(
        tmp_path,
        provider_id="primary",
        label="Example",
        issuer="https://idp.example.invalid",
        audience="rukan",
        discovery_url="https://idp.example.invalid/.well-known/openid-configuration",
        enabled=True,
        now=NOW,
    )
    Directory(tmp_path).close()
    report = employee_preflight(tmp_path)
    raw = report["checks"]
    assert isinstance(raw, list)
    checks = {str(item["name"]): str(item["status"]) for item in raw}
    assert checks["people_store"] == "pass"
    assert checks["enabled_provider"] == "pass"
    assert checks["discovery"] == "blocked"
    assert report["outcome"] == "blocked"


def test_mcp_redirect_cannot_escape(tmp_path: Path) -> None:
    del tmp_path

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.send_response(302)
            self.send_header("location", "http://169.254.169.254/latest")
            self.end_headers()

        def log_message(self, *_args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    url = f"http://127.0.0.1:{port}/mcp"
    with pytest.raises(ValidationError, match="mcp_target_denied"):
        forward_json(url, {"method": "tools/list"}, None)
    with pytest.raises(ValidationError, match="mcp_target_denied"):
        assert_endpoint(
            "http://169.254.169.254/latest",
            approved_urls=frozenset({url}),
            approved_authorities=frozenset(),
        )
    httpd.shutdown()
