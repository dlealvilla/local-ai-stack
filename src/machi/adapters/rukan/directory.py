"""Customer-local people directory. One authority. No vendor export."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from machi.adapters.rukan.read import load_records
from machi.adapters.rukan.secrets import restrict_owned
from machi.install.contracts import InstallRecord
from machi.kernel.errors import PersistenceError, UnknownKindError, ValidationError
from machi.kernel.people import (
    CAPABILITIES,
    ENFORCEMENT,
    AccessIntent,
    DirectoryMembership,
    DirectoryTeam,
    DirectoryUser,
    EffectiveAccess,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CAPABILITIES = CAPABILITIES


class Directory:
    """SQLite directory beside the operational store. Not the telemetry database."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = Path(store_root)
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.store_root / "directory.sqlite", check_same_thread=False)  # noqa: E501
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=4000")
        self._migrate()
        self._bind_install()
        self._restrict()

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
                haystack = str(row["email_normalized"]) + " " + str(row["display_name"]).lower()  # noqa: E501
                if needle and needle not in haystack:
                    continue
                item = dict(row)
                user_id = str(row["user_id"])
                item["team_ids"] = self.memberships_for_user(user_id)
                intent = self._intent("user", user_id)
                item["intent"] = intent or dict.fromkeys(_CAPABILITIES, "inherit")
                found.append(item)
        for item in found:
            item["effective"] = self.effective(str(item["user_id"]))
            item["binding"] = self.binding_state(str(item["user_id"]))
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
            visible = [
                row for row in rows if not needle or needle in str(row["name"]).lower()
            ]
            counted = {
                str(row["team_id"]): int(row["n"])
                for row in self._db.execute(
                    """
                    SELECT team_id, COUNT(*) AS n FROM memberships
                    WHERE active = 1 GROUP BY team_id
                    """
                )
            }
            members = [
                (str(row["team_id"]), str(row["user_id"]))
                for row in self._db.execute(
                    "SELECT team_id, user_id FROM memberships WHERE active = 1"
                )
            ]
            listed = []
            for row in visible:
                team_id = str(row["team_id"])
                item = dict(row)
                item["member_count"] = counted.get(team_id, 0)
                item["member_ids"] = [
                    user_id for owner, user_id in members if owner == team_id
                ]
                intent = self._intent("team", team_id)
                item["intent"] = intent or dict.fromkeys(_CAPABILITIES, "deny")
                listed.append(item)
        return listed

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

    def accounting_team(self, user_id: str) -> str:
        """Earliest active membership. One request never fans out across teams."""
        with self._lock:
            row = self._db.execute(
                """
                SELECT m.team_id FROM memberships AS m
                JOIN teams AS t ON t.team_id = m.team_id
                WHERE m.user_id = ? AND m.active = 1 AND t.status = 'active'
                ORDER BY m.created_at, m.team_id
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return "unassigned"
        return str(row["team_id"])

    def resolve_oidc(
        self, *, issuer: str, subject: str, email: str, now: datetime
    ) -> dict[str, object]:
        """Bind issuer+subject once. A raw email never overrides a binding."""
        _text(issuer, "issuer")
        _text(subject, "subject")
        subject_hash = hashlib.sha256(subject.encode("utf-8")).hexdigest()
        normalized = ""
        if email.strip():
            normalized, _shown = _email(email)
        with self._lock:
            row = self._db.execute(
                """
                SELECT * FROM identity_bindings
                WHERE issuer = ? AND subject_hash = ?
                """,
                (issuer, subject_hash),
            ).fetchone()
            if row is not None:
                user = self._user(str(row["user_id"]))
                status = "bound"
                if normalized and normalized != user.email_normalized:
                    status = "mismatch"
                    self._db.execute(
                        """
                        UPDATE identity_bindings
                        SET status = 'mismatch', updated_at = ?
                        WHERE binding_id = ?
                        """,
                        (now.isoformat(), str(row["binding_id"])),
                    )
                    self._audit(now, "identity.mismatch", "gateway", user.user_id, "", "mismatch")  # noqa: E501
                    self._db.commit()
                if user.status != "active":
                    raise ValidationError("user_suspended")
                return _binding_result(user, status, str(row["binding_id"]))
            if not normalized:
                raise ValidationError("identity_not_provisioned")
            owner = self._email_owner(normalized)
            if owner is None:
                raise ValidationError("identity_not_provisioned")
            user = self._user(owner)
            if user.status != "active":
                raise ValidationError("user_suspended")
            taken = self._db.execute(
                """
                SELECT subject_hash FROM identity_bindings
                WHERE user_id = ? AND issuer = ? AND status = 'bound'
                """,
                (user.user_id, issuer),
            ).fetchone()
            if taken is not None and str(taken["subject_hash"]) != subject_hash:
                self._audit(now, "identity.conflict", "gateway", user.user_id, "", "conflict")  # noqa: E501
                self._db.commit()
                raise ValidationError("identity_binding_conflict")
            binding_id = "bind_" + secrets.token_hex(8)
            self._db.execute(
                """
                INSERT INTO identity_bindings(
                    binding_id, user_id, provider_kind, issuer, subject_hash,
                    email_seen, status, created_at, updated_at
                ) VALUES (?, ?, 'oidc', ?, ?, ?, 'bound', ?, ?)
                """,
                (
                    binding_id, user.user_id, issuer, subject_hash,
                    user.email_normalized, now.isoformat(), now.isoformat(),
                ),
            )
            self._audit(now, "identity.bound", "gateway", user.user_id, "", "bound")
            self._db.commit()
        return _binding_result(user, "bound", binding_id)

    def reset_binding(self, user_id: str, *, actor: str, now: datetime) -> dict[str, str]:  # noqa: E501
        with self._lock:
            self._user(user_id)
            self._db.execute("DELETE FROM identity_bindings WHERE user_id = ?", (user_id,))  # noqa: E501
            self._audit(now, "identity.reset", actor, user_id, "", "reset")
            self._db.commit()
        return {"user_id": user_id, "status": "reset"}

    def binding_state(self, user_id: str) -> dict[str, str]:
        with self._lock:
            row = self._db.execute(
                """
                SELECT binding_id, issuer, subject_hash, status, updated_at
                FROM identity_bindings WHERE user_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return {
                "status": "unbound",
                "issuer": "not_recorded",
                "subject_fingerprint": "not_recorded",
                "updated_at": "not_recorded",
            }
        return {
            "status": str(row["status"]),
            "issuer": str(row["issuer"]),
            "subject_fingerprint": str(row["subject_hash"])[:12],
            "updated_at": str(row["updated_at"]),
        }

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
        agent_use: str | None = None,
        api_credential: str | None = None,
        workspace: str | None = None,
        mcp_use: str | None = None,
        mcp_connect: str | None = None,
    ) -> dict[str, object]:
        fallback = "inherit" if subject_kind == "user" else "deny"
        intent = AccessIntent(
            subject_kind=subject_kind,
            subject_id=subject_id,
            platform_access=platform_access,
            inference_access=inference_access,
            model_selection=model_selection,
            agent_builder=agent_builder,
            updated_at=now.isoformat(),
            agent_use=agent_use or fallback,
            api_credential=api_credential or fallback,
            workspace=workspace or fallback,
            mcp_use=mcp_use or fallback,
            mcp_connect=mcp_connect or fallback,
        )
        with self._lock:
            if subject_kind == "user":
                self._user(subject_id)
            else:
                self._team(subject_id)
            columns = ", ".join(("subject_kind", "subject_id", *_CAPABILITIES, "updated_at"))  # noqa: E501
            placeholders = ", ".join("?" for _ in ("subject_kind", "subject_id", *_CAPABILITIES, "updated_at"))  # noqa: E501
            assignments = ", ".join(
                f"{name} = excluded.{name}" for name in (*_CAPABILITIES, "updated_at")
            )
            self._db.execute(
                f"""
                INSERT INTO intents({columns}) VALUES ({placeholders})
                ON CONFLICT(subject_kind, subject_id) DO UPDATE SET {assignments}
                """,
                (
                    intent.subject_kind,
                    intent.subject_id,
                    *(getattr(intent, name) for name in _CAPABILITIES),
                    intent.updated_at,
                ),
            )
            self._audit(now, "access_intent.changed", actor, subject_id if subject_kind == "user" else "", subject_id if subject_kind == "team" else "", platform_access)  # noqa: E501
            self._db.commit()
        saved = {name: getattr(intent, name) for name in _CAPABILITIES}
        saved.update({
            "subject_kind": subject_kind,
            "subject_id": subject_id,
            "enforcement": ENFORCEMENT,
        })
        return saved

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
        values, reasons = _resolve(user.status, user_intent, team_intents)
        projection = EffectiveAccess(
            user_id=user_id,
            status=user.status,
            team_ids=tuple(teams),
            platform_access=values["platform_access"],
            inference_access=values["inference_access"],
            model_selection=values["model_selection"],
            agent_builder=values["agent_builder"],
            platform_provenance=reasons["platform_access"],
            inference_provenance=reasons["inference_access"],
            model_selection_provenance=reasons["model_selection"],
            agent_builder_provenance=reasons["agent_builder"],
            configured=True,
            enforcement=ENFORCEMENT,
            agent_use=values["agent_use"],
            api_credential=values["api_credential"],
            workspace=values["workspace"],
            mcp_use=values["mcp_use"],
            mcp_connect=values["mcp_connect"],
            agent_use_provenance=reasons["agent_use"],
            api_credential_provenance=reasons["api_credential"],
            workspace_provenance=reasons["workspace"],
            mcp_use_provenance=reasons["mcp_use"],
            mcp_connect_provenance=reasons["mcp_connect"],
        )
        return {
            "user_id": projection.user_id,
            "status": projection.status,
            "team_ids": list(projection.team_ids),
            "configured": True,
            "enforcement": ENFORCEMENT,
            "accounting_team_id": self.accounting_team(user_id),
            "platform_access": projection.platform_access,
            "inference_access": projection.inference_access,
            "model_selection": projection.model_selection,
            "agent_builder": projection.agent_builder,
            "agent_use": projection.agent_use,
            "api_credential": projection.api_credential,
            "workspace": projection.workspace,
            "mcp_use": projection.mcp_use,
            "mcp_connect": projection.mcp_connect,
            "platform_provenance": projection.platform_provenance,
            "inference_provenance": projection.inference_provenance,
            "model_selection_provenance": projection.model_selection_provenance,
            "agent_builder_provenance": projection.agent_builder_provenance,
            "agent_use_provenance": projection.agent_use_provenance,
            "api_credential_provenance": projection.api_credential_provenance,
            "workspace_provenance": projection.workspace_provenance,
            "mcp_use_provenance": projection.mcp_use_provenance,
            "mcp_connect_provenance": projection.mcp_connect_provenance,
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
        return {name: str(row[name]) for name in _CAPABILITIES}

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
        if path.stat().st_size >= 200_000:
            kept = path.read_text(encoding="utf-8").splitlines()[-400:]
            path.write_text("".join(item + "\n" for item in kept), encoding="utf-8")
        restrict_owned(path)

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
            CREATE TABLE IF NOT EXISTS identity_bindings (
                binding_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider_kind TEXT NOT NULL,
                issuer TEXT NOT NULL,
                subject_hash TEXT NOT NULL,
                email_seen TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(issuer, subject_hash)
            );
            CREATE TABLE IF NOT EXISTS api_credentials (
                key_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                secret_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                scopes TEXT NOT NULL,
                client_label TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT NOT NULL,
                status TEXT NOT NULL,
                last_used_at TEXT NOT NULL
            );
            """
        )
        present = {
            str(row[1]) for row in self._db.execute("PRAGMA table_info(intents)")
        }
        added: list[str] = []
        for name in ("agent_use", "api_credential", "workspace", "mcp_use", "mcp_connect"):  # noqa: E501
            if name in present:
                continue
            self._db.execute(
                f"ALTER TABLE intents ADD COLUMN {name} TEXT NOT NULL DEFAULT 'inherit'"
            )
            added.append(name)
        if added:
            assignment = ", ".join(f"{name} = 'deny'" for name in added)
            self._db.execute(
                f"UPDATE intents SET {assignment} WHERE subject_kind = 'team'"
            )
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES ('schema', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = '2'"
        )
        self._db.commit()

    def _bind_install(self) -> None:
        resolved = _local_install_id(self.store_root)
        stored = self._meta("install_id")
        if stored in {None, "", "not_recorded"}:
            self._set_meta("install_id", resolved)
            self._db.commit()
            return
        if resolved in {"", "not_recorded"} or stored == resolved:
            return
        raise ValidationError("directory install binding does not match this store")

    def _restrict(self) -> None:
        restrict_owned(self.store_root)
        for name in (
            "directory.sqlite",
            "directory.sqlite-wal",
            "directory.sqlite-shm",
            "directory-audit.jsonl",
        ):
            restrict_owned(self.store_root / name)

    def _meta(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            """
            INSERT INTO meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def _local_install_id(root: Path) -> str:
    try:
        records = [
            item
            for item in load_records(root, InstallRecord)
            if isinstance(item, InstallRecord)
        ]
    except (OSError, ValidationError, PersistenceError, UnknownKindError) as exc:
        raise ValidationError("directory cannot read the install record") from exc
    if not records:
        return "not_recorded"
    latest = max(records, key=lambda item: item.created_at)
    return str(latest.install_id)


def _resolve(
    status: str,
    user_intent: dict[str, str] | None,
    team_intents: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Per-capability rule. Platform deny closes the other capabilities."""
    values: dict[str, str] = {}
    reasons: dict[str, str] = {}
    if status != "active":
        for name in _CAPABILITIES:
            values[name] = "deny"
            reasons[name] = "user_status"
        return values, reasons
    platform, platform_reason = _one(
        "platform_access", user_intent, team_intents, parent_allow=True
    )
    values["platform_access"] = platform
    reasons["platform_access"] = platform_reason
    for name in _CAPABILITIES:
        if name == "platform_access":
            continue
        if platform != "allow":
            values[name] = "deny"
            reasons[name] = "platform_parent"
            continue
        choice, reason = _one(name, user_intent, team_intents, parent_allow=True)
        values[name] = choice
        reasons[name] = reason
    return values, reasons


def _one(
    name: str,
    user_intent: dict[str, str] | None,
    team_intents: list[dict[str, str]],
    *,
    parent_allow: bool,
) -> tuple[str, str]:
    del parent_allow
    user_value = "inherit" if user_intent is None else user_intent.get(name, "inherit")
    if user_value == "deny":
        return "deny", "user_deny"
    if user_value == "allow":
        return "allow", "user_allow"
    if any(item.get(name) == "allow" for item in team_intents):
        return "allow", "team_grant"
    return "deny", "default_deny"


def _email(value: str) -> tuple[str, str]:
    shown = value.strip()
    if not _EMAIL.match(shown) or len(shown) > 240:
        raise ValidationError("directory email is not usable")
    return shown.lower(), shown


def _text(value: str, label: str) -> None:
    if not value.strip() or len(value) > 240 or any(char in value for char in "\n\r\x00"):  # noqa: E501
        raise ValidationError(f"directory {label} is empty or unsafe")


def _binding_result(user: DirectoryUser, status: str, binding_id: str) -> dict[str, object]:  # noqa: E501
    return {
        "user_id": user.user_id,
        "email_normalized": user.email_normalized,
        "display_name": user.display_name,
        "status": user.status,
        "binding_status": status,
        "binding_id": binding_id,
    }


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
