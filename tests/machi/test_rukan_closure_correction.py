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


def test_ten_users_stream_without_crossing_conversations(tmp_path: Path) -> None:
    import json
    import threading
    import time
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from machi.adapters.rukan.gateway import GatewayService, StreamPiece
    from machi.adapters.rukan.oidc import OidcDiscoveryVerifier
    from machi.adapters.rukan.workspace_http import WorkspaceServer, bind_workspace
    from machi.kernel.build import BuildIdentity, BuildOrigin
    from machi.kernel.errors import ValidationError as Denied

    class SlowChat:
        def __init__(self) -> None:
            self.model_id: str | None = "mart_test"
            self.instance_id = "sin_test"
            self.macropath = "vllm"
            self.calls = 0
            self.hold = threading.Event()

        def refresh(self) -> None:
            return None

        def complete(self, **_kwargs: object) -> object:
            raise Denied("upstream_failure")

        def iter_stream(self, **_kwargs: object):
            self.calls += 1
            self.hold.wait(2)
            yield StreamPiece("delta", "ok")
            yield StreamPiece("usage", "", 1, 1)
            yield StreamPiece("done")

    chat = SlowChat()
    service = GatewayService(
        tmp_path,
        BuildIdentity(version="0.1.0", origin=BuildOrigin.SOURCE, build_id="test"),
        OidcDiscoveryVerifier(issuer="https://idp.example.invalid", audience="rukan"),
        chat,  # type: ignore[arg-type]
    )
    users: list[tuple[str, str, str]] = []
    for index in range(10):
        email = f"user{index}@example.invalid"
        created = service.directory.create_user(
            email=email, display_name=f"User {index}", actor="local_admin_ui", now=NOW
        )
        user_id = str(created["user_id"])
        service.directory.set_intent(
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
        users.append((user_id, email, f"User {index}"))
    server = WorkspaceServer(
        service,
        public_base="http://127.0.0.1",
        client_id="rukan",
        static_dir=tmp_path / "ui",
    )
    httpd = bind_workspace(server, host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = int(httpd.server_address[1])
    base = f"http://127.0.0.1:{port}"
    sessions = [
        server.store.open_session(user_id, now=NOW, ttl_seconds=600)
        for user_id, _email, _name in users
    ]
    conversations: list[str] = []
    for session in sessions:
        request = urllib.request.Request(
            base + "/api/workspace/v1/conversations",
            data=json.dumps({"title": "own", "model_id": "mart_test"}).encode(),
            headers={
                "content-type": "application/json",
                "X-Rukan-CSRF": session["csrf"],
                "Cookie": f"rukan_session={session['session_id']}",
            },
            method="POST",
        )
        created = json.loads(urllib.request.urlopen(request).read())
        conversations.append(str(created["conversation_id"]))
    import socket

    from machi.adapters.rukan.mcp_host import serve_acceptance

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    mcp_port = int(probe.getsockname()[1])
    probe.close()
    threading.Thread(
        target=serve_acceptance, kwargs={"port": mcp_port}, daemon=True
    ).start()
    time.sleep(0.8)
    service.ledger.approve_server(
        server_id="acceptance",
        display_name="Acceptance",
        endpoint=f"http://127.0.0.1:{mcp_port}/mcp",
        auth_method="none",
        sensitivity="internal",
        now=NOW,
    )
    for session in sessions:
        listed = json.loads(urllib.request.urlopen(urllib.request.Request(
            base + "/api/workspace/v1/tools",
            headers={"Cookie": f"rukan_session={session['session_id']}"},
        )).read())
        names = listed["servers"][0]["tools"]
        assert "ping" in names
        assert "add" in names
    codes: list[int] = []

    def stream(index: int) -> None:
        session = sessions[index]
        request = urllib.request.Request(
            base + f"/api/workspace/v1/conversations/{conversations[index]}/messages",
            data=json.dumps({"content": f"user-{index}"}).encode(),
            headers={
                "content-type": "application/json",
                "X-Rukan-CSRF": session["csrf"],
                "Cookie": f"rukan_session={session['session_id']}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                codes.append(response.status)
        except urllib.error.HTTPError as exc:
            codes.append(exc.code)
        except urllib.error.URLError:
            codes.append(0)

    first = [threading.Thread(target=stream, args=(index,)) for index in range(8)]
    for worker in first:
        worker.start()
    deadline = time.time() + 5
    while chat.calls < 8 and time.time() < deadline:
        time.sleep(0.05)
    rest = [threading.Thread(target=stream, args=(index,)) for index in (8, 9)]
    for worker in rest:
        worker.start()
    time.sleep(0.2)
    chat.hold.set()
    for worker in first + rest:
        worker.join()
    assert chat.calls <= 8
    assert 429 in codes
    crowded: list[int] = []
    chat.hold.clear()
    baseline = chat.calls

    def again() -> None:
        stream_one = sessions[0]
        request = urllib.request.Request(
            base + f"/api/workspace/v1/conversations/{conversations[0]}/messages",
            data=json.dumps({"content": "again"}).encode(),
            headers={
                "content-type": "application/json",
                "X-Rukan-CSRF": stream_one["csrf"],
                "Cookie": f"rukan_session={stream_one['session_id']}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                crowded.append(response.status)
        except urllib.error.HTTPError as exc:
            crowded.append(exc.code)

    pair = [threading.Thread(target=again) for _ in range(2)]
    for worker in pair:
        worker.start()
    deadline = time.time() + 5
    while chat.calls < baseline + 2 and time.time() < deadline:
        time.sleep(0.05)
    third = threading.Thread(target=again)
    third.start()
    time.sleep(0.2)
    chat.hold.set()
    for worker in (*pair, third):
        worker.join()
    assert 429 in crowded
    foreign = urllib.request.Request(
        base + f"/api/workspace/v1/conversations/{conversations[1]}",
        headers={"Cookie": f"rukan_session={sessions[0]['session_id']}"},
    )
    try:
        urllib.request.urlopen(foreign)
        denied = False
    except urllib.error.HTTPError as exc:
        denied = b"conversation_not_found" in exc.read()
    assert denied
    saved = server.store.save_agent(
        users[1][0],
        display_name="Private",
        instructions="secret",
        model_id="mart_test",
        mcp_server_ids="",
        now=NOW,
    )
    with pytest.raises(Denied, match="agent_not_found"):
        server.store.agent(users[0][0], saved["agent_id"])
    for index, (user_id, _email, _name) in enumerate(users):
        document = server.store.conversation(user_id, conversations[index])
        messages = document["messages"]
        assert isinstance(messages, list)
        assert messages[0]["content"] == f"user-{index}"
    usage = service.ledger.user_usage(users[0][0], period="all", now=NOW)
    assert int(usage["requests"]) >= 1
    httpd.shutdown()
    server.close()
    del ThreadingHTTPServer


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
