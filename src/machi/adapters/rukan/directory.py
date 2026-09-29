"""Customer-local people directory. One authority. No vendor export."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from machi.kernel.errors import ValidationError
from machi.kernel.people import (
    AccessIntent,
    DirectoryMembership,
    DirectoryTeam,
    DirectoryUser,
    EffectiveAccess,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CAPABILITIES = ("platform_access", "inference_access", "model_selection", "agent_builder")  # noqa: E501


class Directory:
    """SQLite directory beside the operational store. Not the telemetry database."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = Path(store_root)
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.store_root / "directory.sqlite", check_same_thread=False)  # noqa: E501
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def create_user(
        self, *, email: str, display_name: str, actor: str, now: datetime
    ) -> dict[str, object]:
        normalized, shown = _email(email)
        _text(display_name, "display name")
        user = DirectoryUser(
            user_id="usr_" + secrets.token_hex(8),
            email_normalized=normalized,
            email_display=shown,
            display_name=display_name.strip(),
            status="active",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            external_ref="not_recorded",
            actor_origin=actor,
        )
        with self._lock:
            if self._email_owner(normalized) is not None:
                raise ValidationError("directory email is already in use")
            self._insert_user(user)
            self._audit(now, "user.created", actor, user.user_id, "", "active")
            self._db.commit()
        return _user_row(user)

    def update_user(
        self,
        user_id: str,
        *,
        email: str | None,
        display_name: str | None,
        actor: str,
        now: datetime,
    ) -> dict[str, object]:
        with self._lock:
            current = self._user(user_id)
            normalized = current.email_normalized
            shown = current.email_display
            name = current.display_name
            if email is not None:
                normalized, shown = _email(email)
                owner = self._email_owner(normalized)
                if owner is not None and owner != user_id:
                    raise ValidationError("directory email is already in use")
            if display_name is not None:
                _text(display_name, "display name")
                name = display_name.strip()
            updated = DirectoryUser(
                user_id=current.user_id,
                email_normalized=normalized,
                email_display=shown,
                display_name=name,
                status=current.status,
                created_at=current.created_at,
                updated_at=now.isoformat(),
                external_ref=current.external_ref,
                actor_origin=actor,
            )
            self._insert_user(updated, replace=True)
            self._audit(now, "user.updated", actor, user_id, "", "updated")
            self._db.commit()
        return _user_row(updated)

    def set_status(self, user_id: str, status: str, *, actor: str, now: datetime) -> dict[str, object]:  # noqa: E501
        if status not in {"active", "suspended", "deactivated"}:
            raise ValidationError("directory user status is unknown")
        with self._lock:
            current = self._user(user_id)
            if current.status == "deactivated" and status != "deactivated":
                raise ValidationError("a deactivated user is not reactivated")
            updated = DirectoryUser(
                user_id=current.user_id,
                email_normalized=current.email_normalized,
                email_display=current.email_display,
                display_name=current.display_name,
                status=status,
                created_at=current.created_at,
                updated_at=now.isoformat(),
                external_ref=current.external_ref,
                actor_origin=actor,
            )
            self._insert_user(updated, replace=True)
            self._audit(now, "user.status_changed", actor, user_id, current.status, status)  # noqa: E501
            self._db.commit()
        return _user_row(updated)

    def list_users(self, query: str = "") -> list[dict[str, object]]:
        needle = query.strip().lower()
        with self._lock:
            rows = self._db.execute("SELECT * FROM users ORDER BY display_name").fetchall()  # noqa: E501
        found = []
        for row in rows:
            if needle and needle not in str(row["email_normalized"]) and needle not in str(row["display_name"]).lower():  # noqa: E501
                continue
            found.append(dict(row))
        return found

    def create_team(self, *, name: str, description: str, actor: str, now: datetime) -> dict[str, object]:  # noqa: E501
        _text(name, "team name")
        team = DirectoryTeam(
            team_id="team_" + secrets.token_hex(8),
            name=name.strip(),
            description=description.strip(),
            status="active",
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        with self._lock:
            self._db.execute(
                """
                INSERT INTO teams(
                    team_id, name, description, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (team.team_id, team.name, team.description, team.status, team.created_at, team.updated_at),  # noqa: E501
            )
            self._audit(now, "team.created", actor, "", team.team_id, "active")
            self._db.commit()
        return _team_row(team)

    def update_team(
        self, team_id: str, *, name: str | None, description: str | None, actor: str, now: datetime  # noqa: E501
    ) -> dict[str, object]:
        with self._lock:
            current = self._team(team_id)
            renamed = current.name if name is None else name.strip()
            described = current.description if description is None else description.strip()  # noqa: E501
            _text(renamed, "team name")
            updated = DirectoryTeam(
                team_id=current.team_id,
                name=renamed,
                description=described,
                status=current.status,
                created_at=current.created_at,
                updated_at=now.isoformat(),
            )
            self._db.execute(
                """
                UPDATE teams
                SET name = ?, description = ?, updated_at = ?
                WHERE team_id = ?
                """,
                (updated.name, updated.description, updated.updated_at, team_id),
            )
            self._audit(now, "team.updated", actor, "", team_id, "updated")
            self._db.commit()
        return _team_row(updated)

    def set_team_status(self, team_id: str, status: str, *, actor: str, now: datetime) -> dict[str, object]:  # noqa: E501
        if status not in {"active", "archived"}:
            raise ValidationError("directory team status is unknown")
        with self._lock:
            current = self._team(team_id)
            self._db.execute(
                "UPDATE teams SET status = ?, updated_at = ? WHERE team_id = ?",
                (status, now.isoformat(), team_id),
            )
            action = "team.archived" if status == "archived" else "team.reactivated"
            self._audit(now, action, actor, "", team_id, status)
            self._db.commit()
            current_status = current.status
        del current_status
        return self.team(team_id)

    def list_teams(self, query: str = "") -> list[dict[str, object]]:
        needle = query.strip().lower()
        with self._lock:
            rows = self._db.execute("SELECT * FROM teams ORDER BY name").fetchall()
        return [dict(row) for row in rows if not needle or needle in str(row["name"]).lower()]  # noqa: E501

    def add_membership(self, user_id: str, team_id: str, *, actor: str, now: datetime) -> dict[str, object]:  # noqa: E501
        with self._lock:
            self._user(user_id)
            self._team(team_id)
            membership = DirectoryMembership(user_id, team_id, True, now.isoformat(), actor)  # noqa: E501
            self._db.execute(
                """
                INSERT INTO memberships(
                    user_id, team_id, active, created_at, actor_origin
                )
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(user_id, team_id) DO UPDATE SET
                    active = 1,
                    actor_origin = excluded.actor_origin
                """,
                (user_id, team_id, membership.created_at, actor),
            )
            self._audit(now, "membership.added", actor, user_id, team_id, "active")
            self._db.commit()
        return {"user_id": user_id, "team_id": team_id, "active": True}

    def remove_membership(self, user_id: str, team_id: str, *, actor: str, now: datetime) -> dict[str, object]:  # noqa: E501
        with self._lock:
            self._db.execute(
                "UPDATE memberships SET active = 0 WHERE user_id = ? AND team_id = ?",
                (user_id, team_id),
            )
            self._audit(now, "membership.removed", actor, user_id, team_id, "inactive")
            self._db.commit()
        return {"user_id": user_id, "team_id": team_id, "active": False}

    def memberships_for_user(self, user_id: str) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT team_id FROM memberships
                WHERE user_id = ? AND active = 1 ORDER BY team_id
                """,
                (user_id,),
            ).fetchall()
        return [str(row["team_id"]) for row in rows]

    def set_intent(
        self,
        *,
        subject_kind: str,
        subject_id: str,
        platform_access: str,
        inference_access: str,
        model_selection: str,
        agent_builder: str,
        actor: str,
        now: datetime,
    ) -> dict[str, object]:
        intent = AccessIntent(
            subject_kind=subject_kind,
            subject_id=subject_id,
            platform_access=platform_access,
            inference_access=inference_access,
            model_selection=model_selection,
            agent_builder=agent_builder,
            updated_at=now.isoformat(),
        )
        with self._lock:
            if subject_kind == "user":
                self._user(subject_id)
            else:
                self._team(subject_id)
            self._db.execute(
                """
                INSERT INTO intents(
                    subject_kind, subject_id, platform_access, inference_access,
                    model_selection, agent_builder, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(subject_kind, subject_id) DO UPDATE SET
                    platform_access = excluded.platform_access,
                    inference_access = excluded.inference_access,
                    model_selection = excluded.model_selection,
                    agent_builder = excluded.agent_builder,
                    updated_at = excluded.updated_at
                """,
                (
                    intent.subject_kind, intent.subject_id, intent.platform_access,
                    intent.inference_access, intent.model_selection, intent.agent_builder,  # noqa: E501
                    intent.updated_at,
                ),
            )
            self._audit(now, "access_intent.changed", actor, subject_id if subject_kind == "user" else "", subject_id if subject_kind == "team" else "", platform_access)  # noqa: E501
            self._db.commit()
        return {
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "platform_access": platform_access,
            "inference_access": inference_access,
            "model_selection": model_selection,
            "agent_builder": agent_builder,
            "enforcement": "gateway_not_available",
        }

    def effective(self, user_id: str) -> dict[str, object]:
        with self._lock:
            user = self._user(user_id)
            teams = [
                team_id
                for team_id in self.memberships_for_user(user_id)
                if self._team(team_id).status == "active"
            ]
            user_intent = self._intent("user", user_id)
            team_intents = [
                item
                for team_id in teams
                if (item := self._intent("team", team_id)) is not None
            ]
        if user.status != "active":
            values = dict.fromkeys(_CAPABILITIES, "deny")
            provenance = "user_status"
        elif user_intent is not None and user_intent["platform_access"] == "deny":
            values = dict.fromkeys(_CAPABILITIES, "deny")
            provenance = "user_platform_deny"
        else:
            values = {}
            provenance = "default_deny"
            for name in _CAPABILITIES:
                user_value = user_intent[name] if user_intent else ""
                if user_value == "deny":
                    values[name] = "deny"
                    provenance = "user_deny"
                elif user_value == "allow":
                    values[name] = "allow"
                    provenance = "user_allow"
                elif any(item[name] == "allow" for item in team_intents):
                    values[name] = "allow"
                    provenance = "team_grant"
                else:
                    values[name] = "deny"
        projection = EffectiveAccess(
            user_id=user_id,
            status=user.status,
            team_ids=tuple(teams),
            platform_access=values["platform_access"],
            inference_access=values["inference_access"],
            model_selection=values["model_selection"],
            agent_builder=values["agent_builder"],
            provenance=provenance,
            configured=True,
            enforcement="gateway_not_available",
        )
        return {
            "user_id": projection.user_id,
            "status": projection.status,
            "team_ids": list(projection.team_ids),
            "platform_access": projection.platform_access,
            "inference_access": projection.inference_access,
            "model_selection": projection.model_selection,
            "agent_builder": projection.agent_builder,
            "provenance": projection.provenance,
            "configured": True,
            "enforcement": "gateway_not_available",
        }

    def audit_rows(self) -> list[dict[str, str]]:
        path = self.store_root / "directory-audit.jsonl"
        if not path.is_file():
            return []
        rows: list[dict[str, str]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                document = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                rows.append({key: str(document.get(key, "")) for key in (
                    "occurred_at", "action", "outcome", "actor_origin", "subject"
                )})
        return rows

    def team(self, team_id: str) -> dict[str, object]:
        with self._lock:
            return _team_row(self._team(team_id))

    def _user(self, user_id: str) -> DirectoryUser:
        row = self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()  # noqa: E501
        if row is None:
            raise ValidationError("directory user is unknown")
        return DirectoryUser(
            user_id=str(row["user_id"]),
            email_normalized=str(row["email_normalized"]),
            email_display=str(row["email_display"]),
            display_name=str(row["display_name"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            external_ref=str(row["external_ref"]),
            actor_origin=str(row["actor_origin"]),
        )

    def _team(self, team_id: str) -> DirectoryTeam:
        row = self._db.execute("SELECT * FROM teams WHERE team_id = ?", (team_id,)).fetchone()  # noqa: E501
        if row is None:
            raise ValidationError("directory team is unknown")
        return DirectoryTeam(
            team_id=str(row["team_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _intent(self, kind: str, subject_id: str) -> dict[str, str] | None:
        row = self._db.execute(
            """
            SELECT * FROM intents WHERE subject_kind = ? AND subject_id = ?
            """,
            (kind, subject_id),
        ).fetchone()
        if row is None:
            return None
        return {name: str(row[name]) for name in ("platform_access", "inference_access", "model_selection", "agent_builder")}  # noqa: E501

    def _email_owner(self, normalized: str) -> str | None:
        row = self._db.execute(
            "SELECT user_id FROM users WHERE email_normalized = ?", (normalized,)
        ).fetchone()
        if row is None:
            return None
        return str(row["user_id"])

    def _insert_user(self, user: DirectoryUser, *, replace: bool = False) -> None:
        verb = "REPLACE" if replace else "INSERT"
        self._db.execute(
            f"""
            {verb} INTO users(
                user_id, email_normalized, email_display, display_name, status,
                created_at, updated_at, external_ref, actor_origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user.user_id, user.email_normalized, user.email_display, user.display_name,  # noqa: E501
                user.status, user.created_at, user.updated_at, user.external_ref, user.actor_origin,  # noqa: E501
            ),
        )

    def _audit(self, now: datetime, action: str, actor: str, user_id: str, team_id: str, outcome: str) -> None:  # noqa: E501
        subject = user_id or team_id
        line = json.dumps(
            {
                "occurred_at": now.astimezone(UTC).isoformat(),
                "action": action,
                "outcome": outcome,
                "actor_origin": actor,
                "subject": subject,
            }
        )
        path = self.store_root / "directory-audit.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                email_normalized TEXT NOT NULL UNIQUE,
                email_display TEXT NOT NULL,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                external_ref TEXT NOT NULL,
                actor_origin TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teams (
                team_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memberships (
                user_id TEXT NOT NULL,
                team_id TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                actor_origin TEXT NOT NULL,
                PRIMARY KEY (user_id, team_id)
            );
            CREATE TABLE IF NOT EXISTS intents (
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                platform_access TEXT NOT NULL,
                inference_access TEXT NOT NULL,
                model_selection TEXT NOT NULL,
                agent_builder TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (subject_kind, subject_id)
            );
            """
        )
        self._db.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', '1')"
        )
        self._db.commit()


def _email(value: str) -> tuple[str, str]:
    shown = value.strip()
    if not _EMAIL.match(shown) or len(shown) > 240:
        raise ValidationError("directory email is not usable")
    return shown.lower(), shown


def _text(value: str, label: str) -> None:
    if not value.strip() or len(value) > 240 or any(char in value for char in "\n\r\x00"):  # noqa: E501
        raise ValidationError(f"directory {label} is empty or unsafe")


def _user_row(user: DirectoryUser) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "email_display": user.email_display,
        "display_name": user.display_name,
        "status": user.status,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "external_ref": user.external_ref,
    }


def _team_row(team: DirectoryTeam) -> dict[str, object]:
    return {
        "team_id": team.team_id,
        "name": team.name,
        "description": team.description,
        "status": team.status,
        "created_at": team.created_at,
        "updated_at": team.updated_at,
    }
