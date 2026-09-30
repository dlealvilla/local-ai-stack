"""Customer-local conversations. Not vendor telemetry."""

from __future__ import annotations

import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from machi.kernel.errors import ValidationError


class WorkspaceStore:
    """Conversations, sessions, and agents for one Rukan install."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = Path(store_root)
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.store_root / "workspace.sqlite", check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                csrf TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                model_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                input_tokens TEXT NOT NULL,
                output_tokens TEXT NOT NULL,
                usage_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                owner_user_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                instructions TEXT NOT NULL,
                model_id TEXT NOT NULL,
                mcp_server_ids TEXT NOT NULL,
                status TEXT NOT NULL,
                revision INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._db.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', '1')"
        )
        self._migrate()
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def open_session(
        self, user_id: str, *, now: datetime, ttl_seconds: int
    ) -> dict[str, str]:
        session_id = "wses_" + secrets.token_urlsafe(24)
        csrf = secrets.token_urlsafe(18)
        expires = _plus(now, ttl_seconds)
        with self._lock:
            self._db.execute(
                """
                INSERT INTO sessions(session_id, user_id, csrf, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, csrf, expires, now.isoformat()),
            )
            self._db.commit()
        return {"session_id": session_id, "csrf": csrf, "expires_at": expires}

    def session(self, session_id: str, now: datetime) -> dict[str, str] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None or str(row["expires_at"]) <= now.isoformat():
            return None
        return {
            "session_id": str(row["session_id"]),
            "user_id": str(row["user_id"]),
            "csrf": str(row["csrf"]),
        }

    def drop_session(self, session_id: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._db.commit()

    def create_conversation(
        self,
        user_id: str,
        *,
        title: str,
        model_id: str,
        agent_id: str,
        now: datetime,
        agent_revision: str = "",
        instruction_snapshot: str = "",
        tool_refs: str = "",
    ) -> dict[str, str]:
        identity = "conv_" + secrets.token_hex(8)
        with self._lock:
            self._db.execute(
                """
                INSERT INTO conversations(
                    conversation_id, user_id, title, model_id, agent_id, status,
                    created_at, updated_at, agent_revision,
                    instruction_snapshot, tool_refs
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                """,
                (
                    identity,
                    user_id,
                    title[:80] or "New chat",
                    model_id,
                    agent_id,
                    now.isoformat(),
                    now.isoformat(),
                    agent_revision,
                    instruction_snapshot[:4000],
                    tool_refs[:800],
                ),
            )
            self._db.commit()
        return {"conversation_id": identity, "title": title[:80] or "New chat"}

    def list_conversations(self, user_id: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT conversation_id, title, model_id, agent_id, updated_at
                FROM conversations
                WHERE user_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [{key: str(row[key]) for key in row.keys()} for row in rows]  # noqa: SIM118

    def conversation(self, user_id: str, conversation_id: str) -> dict[str, object]:
        with self._lock:
            row = self._db.execute(
                """
                SELECT * FROM conversations
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id),
            ).fetchone()
            if row is None:
                raise ValidationError("conversation_not_found")
            messages = self._db.execute(
                """
                SELECT role, content, input_tokens, output_tokens, usage_id
                FROM messages WHERE conversation_id = ? ORDER BY ordinal
                """,
                (conversation_id,),
            ).fetchall()
        return {
            "conversation_id": str(row["conversation_id"]),
            "title": str(row["title"]),
            "model_id": str(row["model_id"]),
            "agent_id": str(row["agent_id"]),
            "messages": [
                {
                    "role": str(item["role"]),
                    "content": str(item["content"]),
                    "input_tokens": str(item["input_tokens"]),
                    "output_tokens": str(item["output_tokens"]),
                }
                for item in messages
            ],
        }

    def rename(
        self, user_id: str, conversation_id: str, title: str, now: datetime
    ) -> None:
        self._touch(user_id, conversation_id, now, title=title[:80] or "New chat")

    def archive(self, user_id: str, conversation_id: str, now: datetime) -> None:
        with self._lock:
            changed = self._db.execute(
                """
                UPDATE conversations SET status = 'archived', updated_at = ?
                WHERE conversation_id = ? AND user_id = ?
                """,
                (now.isoformat(), conversation_id, user_id),
            ).rowcount
            self._db.commit()
        if not changed:
            raise ValidationError("conversation_not_found")

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        *,
        role: str,
        content: str,
        now: datetime,
        input_tokens: str = "not_recorded",
        output_tokens: str = "not_recorded",
        usage_id: str = "not_recorded",
    ) -> None:
        self.conversation(user_id, conversation_id)
        with self._lock:
            ordinal = self._db.execute(
                """
                SELECT COALESCE(MAX(ordinal), 0) + 1 AS n
                FROM messages WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
            self._db.execute(
                """
                INSERT INTO messages(
                    message_id, conversation_id, ordinal, role, content, status,
                    created_at, input_tokens, output_tokens, usage_id
                ) VALUES (?, ?, ?, ?, ?, 'complete', ?, ?, ?, ?)
                """,
                (
                    "msg_" + secrets.token_hex(8),
                    conversation_id,
                    int(ordinal["n"]),
                    role,
                    content,
                    now.isoformat(),
                    input_tokens,
                    output_tokens,
                    usage_id,
                ),
            )
            self._db.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (now.isoformat(), conversation_id),
            )
            self._db.commit()

    def drop_last_assistant(self, user_id: str, conversation_id: str) -> None:
        self.conversation(user_id, conversation_id)
        with self._lock:
            row = self._db.execute(
                """
                SELECT message_id, role FROM messages
                WHERE conversation_id = ? ORDER BY ordinal DESC LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
            if row is not None and str(row["role"]) == "assistant":
                self._db.execute(
                    "DELETE FROM messages WHERE message_id = ?",
                    (str(row["message_id"]),),
                )
                self._db.commit()

    def set_model(
        self, user_id: str, conversation_id: str, model_id: str, now: datetime
    ) -> None:
        with self._lock:
            changed = self._db.execute(
                """
                UPDATE conversations SET model_id = ?, updated_at = ?
                WHERE conversation_id = ? AND user_id = ? AND status = 'active'
                """,
                (model_id, now.isoformat(), conversation_id, user_id),
            ).rowcount
            self._db.commit()
        if not changed:
            raise ValidationError("conversation_not_found")

    def save_agent(
        self,
        user_id: str,
        *,
        display_name: str,
        instructions: str,
        model_id: str,
        mcp_server_ids: str,
        now: datetime,
        description: str = "",
        max_tokens: int = 64,
        tool_refs: str = "",
    ) -> dict[str, str]:
        identity = "agt_" + secrets.token_hex(8)
        with self._lock:
            self._db.execute(
                """
                INSERT INTO agents(
                    agent_id, owner_user_id, display_name, instructions, model_id,
                    mcp_server_ids, status, revision, created_at, updated_at,
                    description, max_tokens, tool_refs
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, ?, ?, ?, ?)
                """,
                (
                    identity, user_id, display_name[:80], instructions[:4000],
                    model_id, mcp_server_ids[:240], now.isoformat(), now.isoformat(),
                    description[:240], max(1, min(max_tokens, 256)), tool_refs[:800],
                ),
            )
            self._db.commit()
        return {
            "agent_id": identity,
            "display_name": display_name[:80],
            "revision": "1",
        }

    def revise_agent(
        self,
        user_id: str,
        agent_id: str,
        *,
        display_name: str,
        instructions: str,
        model_id: str,
        description: str,
        max_tokens: int,
        tool_refs: str,
        now: datetime,
    ) -> dict[str, str]:
        current = self.agent(user_id, agent_id)
        revision = int(current["revision"]) + 1
        with self._lock:
            self._db.execute(
                """
                UPDATE agents SET
                    display_name = ?, instructions = ?, model_id = ?, description = ?,
                    max_tokens = ?, tool_refs = ?, revision = ?, updated_at = ?
                WHERE agent_id = ? AND owner_user_id = ? AND status = 'active'
                """,
                (
                    display_name[:80], instructions[:4000], model_id, description[:240],
                    max(1, min(max_tokens, 256)), tool_refs[:800], revision,
                    now.isoformat(), agent_id, user_id,
                ),
            )
            self._db.commit()
        return {"agent_id": agent_id, "revision": str(revision)}

    def list_agents(self, user_id: str) -> list[dict[str, str]]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT agent_id, display_name, model_id, status
                FROM agents WHERE owner_user_id = ? AND status = 'active'
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [{key: str(row[key]) for key in row.keys()} for row in rows]  # noqa: SIM118

    def agent(self, user_id: str, agent_id: str) -> dict[str, str]:
        with self._lock:
            row = self._db.execute(
                """
                SELECT * FROM agents
                WHERE agent_id = ? AND owner_user_id = ? AND status = 'active'
                """,
                (agent_id, user_id),
            ).fetchone()
        if row is None:
            raise ValidationError("agent_not_found")
        return {key: str(row[key]) for key in row.keys()}  # noqa: SIM118

    def archive_agent(self, user_id: str, agent_id: str, now: datetime) -> None:
        with self._lock:
            changed = self._db.execute(
                """
                UPDATE agents SET status = 'archived', updated_at = ?
                WHERE agent_id = ? AND owner_user_id = ?
                """,
                (now.isoformat(), agent_id, user_id),
            ).rowcount
            self._db.commit()
        if not changed:
            raise ValidationError("agent_not_found")

    def _migrate(self) -> None:
        version = self._meta("schema") or "1"
        if version == "2":
            return
        if version != "1":
            raise ValidationError("workspace schema is unknown")
        self._column("conversations", "agent_revision", "TEXT NOT NULL DEFAULT ''")
        self._column(
            "conversations", "instruction_snapshot", "TEXT NOT NULL DEFAULT ''"
        )
        self._column("conversations", "tool_refs", "TEXT NOT NULL DEFAULT ''")
        self._column("agents", "description", "TEXT NOT NULL DEFAULT ''")
        self._column("agents", "max_tokens", "INTEGER NOT NULL DEFAULT 64")
        self._column("agents", "tool_refs", "TEXT NOT NULL DEFAULT ''")
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES ('schema', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = '2'"
        )

    def _column(self, table: str, name: str, declaration: str) -> None:
        present = {
            str(row[1]) for row in self._db.execute(f"PRAGMA table_info({table})")
        }
        if name in present:
            return
        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def _meta(self, key: str) -> str:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return "" if row is None else str(row[0])

    def _touch(
        self, user_id: str, conversation_id: str, now: datetime, *, title: str
    ) -> None:
        with self._lock:
            changed = self._db.execute(
                """
                UPDATE conversations SET title = ?, updated_at = ?
                WHERE conversation_id = ? AND user_id = ?
                """,
                (title, now.isoformat(), conversation_id, user_id),
            ).rowcount
            self._db.commit()
        if not changed:
            raise ValidationError("conversation_not_found")


def _plus(now: datetime, seconds: int) -> str:
    from datetime import timedelta

    return (now + timedelta(seconds=seconds)).isoformat()
