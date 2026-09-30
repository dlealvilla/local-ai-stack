"""Lead-correction checks for path, cookie, schema, and model denial."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from machi.adapters.rukan.workspace_http import WorkspaceServer, _cookie_secure
from machi.adapters.rukan.workspace_store import WorkspaceStore
from machi.kernel.errors import ValidationError

NOW = datetime.now(UTC).replace(microsecond=0)


def test_https_public_base_marks_the_cookie_secure(tmp_path: Path) -> None:
    server = WorkspaceServer(
        _unused(tmp_path),
        public_base="https://rukan.example",
        client_id="rukan",
        static_dir=tmp_path,
    )
    assert _cookie_secure(server) is True
    server.store.close()


def test_local_http_cookie_is_not_secure(tmp_path: Path) -> None:
    server = WorkspaceServer(
        _unused(tmp_path),
        public_base="http://127.0.0.1:8790",
        client_id="rukan",
        static_dir=tmp_path,
    )
    assert _cookie_secure(server) is False
    server.store.close()


def test_invalid_public_base_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="workspace public address"):
        WorkspaceServer(
            _unused(tmp_path),
            public_base="rukan.example",
            client_id="rukan",
            static_dir=tmp_path,
        )


def test_schema_one_migrates_without_dropping_messages(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    created = store.create_conversation(
        "usr_a", title="Keep", model_id="mart_test", agent_id="", now=NOW
    )
    store.add_message(
        "usr_a", created["conversation_id"], role="user", content="stay", now=NOW
    )
    store.close()
    import sqlite3

    database = sqlite3.connect(tmp_path / "workspace.sqlite")
    database.execute("UPDATE meta SET value = '1' WHERE key = 'schema'")
    database.commit()
    database.close()
    again = WorkspaceStore(tmp_path)
    document = again.conversation("usr_a", created["conversation_id"])
    again.close()
    messages = document["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == "stay"


def test_ten_users_cannot_read_each_others_conversations(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path)
    created = []
    for index in range(10):
        user = f"usr_{index}"
        row = store.create_conversation(
            user, title=user, model_id="mart_test", agent_id="", now=NOW
        )
        store.add_message(
            user, row["conversation_id"], role="user", content=user, now=NOW
        )
        created.append((user, row["conversation_id"]))
    for user, identity in created:
        document = store.conversation(user, identity)
        messages = document["messages"]
        assert isinstance(messages, list)
        assert messages[0]["content"] == user
        other = "usr_0" if user != "usr_0" else "usr_1"
        with pytest.raises(ValidationError, match="conversation_not_found"):
            store.conversation(other, identity)
    store.close()


def test_static_sibling_prefix_is_not_served(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "index.html").write_text("home", encoding="utf-8")
    sibling = tmp_path / "workspace-evil"
    sibling.mkdir()
    secret = sibling / "index.html"
    secret.write_text("secret", encoding="utf-8")
    target = (root / "../workspace-evil/index.html").resolve()
    assert not target.is_relative_to(root.resolve())


def _unused(tmp_path: Path) -> object:
    from machi.adapters.rukan.gateway import GatewayService
    from machi.adapters.rukan.oidc import OidcDiscoveryVerifier
    from machi.kernel.build import BuildIdentity, BuildOrigin

    class Chat:
        model_id = "mart_test"

        def refresh(self) -> None:
            return None

    return GatewayService(
        tmp_path / "gateway",
        BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="test"),
        OidcDiscoveryVerifier(
            issuer="https://idp.example.invalid", audience="rukan"
        ),
        Chat(),  # type: ignore[arg-type]
    )
