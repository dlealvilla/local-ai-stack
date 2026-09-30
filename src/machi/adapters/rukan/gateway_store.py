"""Customer-local gateway ledger. It is not the vendor export."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from machi.adapters.rukan.secrets import restrict_owned
from machi.kernel.errors import ValidationError
from machi.kernel.gateway import PrincipalUsage

_PERIODS = {"24h": 1, "7d": 7, "30d": 30}


class GatewayLedger:
    """Principal usage, MCP catalog, and non-content gateway audit."""

    def __init__(self, store_root: Path) -> None:
        self.store_root = Path(store_root)
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.store_root / "gateway.sqlite", check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=4000")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS principal_usage (
                usage_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                accounting_team_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                auth_method TEXT NOT NULL,
                model_identity TEXT NOT NULL,
                macropath TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                input_tokens TEXT NOT NULL,
                output_tokens TEXT NOT NULL,
                latency_ms TEXT NOT NULL,
                outcome TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gateway_events (
                usage_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                accounting_team_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                auth_method TEXT NOT NULL,
                model_identity TEXT NOT NULL,
                macropath TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                input_tokens TEXT NOT NULL,
                output_tokens TEXT NOT NULL,
                latency_ms TEXT NOT NULL,
                outcome TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                install_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                failure TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                version TEXT NOT NULL,
                build_id TEXT NOT NULL,
                telemetry_projected INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mcp_servers (
                server_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                transport TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                approved INTEGER NOT NULL,
                auth_method TEXT NOT NULL,
                sensitivity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._db.commit()
        self.fail_append = False
        self.fail_projection = False
        self.degraded = 0
        restrict_owned(self.store_root)
        restrict_owned(self.store_root / "gateway.sqlite")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def record(self, usage: PrincipalUsage) -> None:
        with self._lock:
            self._db.execute(
                """
                INSERT OR IGNORE INTO principal_usage(
                    usage_id, request_id, user_id, accounting_team_id, client_id,
                    auth_method, model_identity, macropath, instance_id,
                    input_tokens, output_tokens, latency_ms, outcome, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage.usage_id, usage.request_id, usage.user_id,
                    usage.accounting_team_id, usage.client_id, usage.auth_method,
                    usage.model_identity, usage.macropath, usage.instance_id,
                    usage.input_tokens, usage.output_tokens, usage.latency_ms,
                    usage.outcome, usage.occurred_at,
                ),
            )
            self._db.commit()

    def append_canonical(self, usage: PrincipalUsage, **extra: str | int) -> bool:
        """One durable employee fact. Projection to telemetry is separate."""
        if self.fail_append:
            self.degraded += 1
            return False
        with self._lock:
            self._db.execute(
                """
                INSERT OR IGNORE INTO gateway_events(
                    usage_id, request_id, user_id, accounting_team_id, client_id,
                    auth_method, model_identity, macropath, instance_id,
                    input_tokens, output_tokens, latency_ms, outcome, occurred_at,
                    install_id, plan_id, reservation_id, generation_id, failure,
                    status_code, version, build_id, telemetry_projected
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    usage.usage_id, usage.request_id, usage.user_id,
                    usage.accounting_team_id, usage.client_id, usage.auth_method,
                    usage.model_identity, usage.macropath, usage.instance_id,
                    usage.input_tokens, usage.output_tokens, usage.latency_ms,
                    usage.outcome, usage.occurred_at,
                    str(extra.get("install_id", "not_recorded")),
                    str(extra.get("plan_id", "not_recorded")),
                    str(extra.get("reservation_id", "not_recorded")),
                    str(extra.get("generation_id", "not_recorded")),
                    str(extra.get("failure", "none")),
                    int(extra.get("status_code", 0)),
                    str(extra.get("version", "0")),
                    str(extra.get("build_id", "not_recorded")),
                ),
            )
            self._db.commit()
        return True

    def unprojected(self) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._db.execute(
                "SELECT * FROM gateway_events WHERE telemetry_projected = 0"
            ))

    def mark_projected(self, usage_id: str) -> None:
        if self.fail_projection:
            return
        with self._lock:
            self._db.execute(
                """
                UPDATE gateway_events SET telemetry_projected = 1
                WHERE usage_id = ?
                """,
                (usage_id,),
            )
            self._db.commit()

    def accounting_state(self, deployment_requests: int, deployment_input: str, deployment_output: str) -> str:  # noqa: E501
        with self._lock:
            pending = self._db.execute(
                "SELECT COUNT(*) AS n FROM gateway_events WHERE telemetry_projected = 0"
            ).fetchone()
            rows = list(self._db.execute(
                "SELECT input_tokens, output_tokens FROM gateway_events"
            ))
        if self.degraded:
            return "degraded"
        if pending is not None and int(pending["n"]) > 0:
            return "projection_pending"
        requests = len(rows)
        unresolved = any(
            str(row["input_tokens"]) == "not_recorded"
            or str(row["output_tokens"]) == "not_recorded"
            for row in rows
        )
        if unresolved:
            inputs = "not_recorded"
            outputs = "not_recorded"
        else:
            inputs = str(sum(int(row["input_tokens"]) for row in rows))
            outputs = str(sum(int(row["output_tokens"]) for row in rows))
        if (
            requests == deployment_requests
            and inputs == deployment_input
            and outputs == deployment_output
        ):
            return "match"
        return "mismatch"

    def user_usage(self, user_id: str, *, period: str, now: datetime) -> dict[str, object]:  # noqa: E501
        if period not in {"24h", "7d", "30d", "all"}:
            raise ValidationError("usage period is unknown")
        cutoff = ""
        if period != "all":
            cutoff = (now - timedelta(days=_PERIODS[period])).isoformat()
        with self._lock:
            rows = self._db.execute(
                """
                SELECT * FROM gateway_events
                WHERE user_id = ? AND (? = '' OR occurred_at >= ?)
                ORDER BY occurred_at
                """,
                (user_id, cutoff, cutoff),
            ).fetchall()
        return _sum_rows(rows, period)

    def approve_server(
        self,
        *,
        server_id: str,
        display_name: str,
        endpoint: str,
        auth_method: str,
        sensitivity: str,
        now: datetime,
    ) -> dict[str, object]:
        with self._lock:
            self._db.execute(
                """
                INSERT INTO mcp_servers(
                    server_id, display_name, transport, endpoint, approved,
                    auth_method, sensitivity, created_at, updated_at
                ) VALUES (?, ?, 'streamable_http', ?, 1, ?, ?, ?, ?)
                ON CONFLICT(server_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    endpoint = excluded.endpoint,
                    approved = 1,
                    auth_method = excluded.auth_method,
                    sensitivity = excluded.sensitivity,
                    updated_at = excluded.updated_at
                """,
                (
                    server_id, display_name, endpoint, auth_method, sensitivity,
                    now.isoformat(), now.isoformat(),
                ),
            )
            self._db.commit()
        self.audit(now, "mcp.connection_added", server_id, "approved")
        return {"server_id": server_id, "endpoint": endpoint, "approved": True}

    def server(self, server_id: str) -> dict[str, object] | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM mcp_servers WHERE server_id = ? AND approved = 1",
                (server_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "server_id": str(row["server_id"]),
            "display_name": str(row["display_name"]),
            "endpoint": str(row["endpoint"]),
            "auth_method": str(row["auth_method"]),
            "sensitivity": str(row["sensitivity"]),
        }

    def servers(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM mcp_servers WHERE approved = 1 ORDER BY display_name"
            ).fetchall()
        return [
            {
                "server_id": str(row["server_id"]),
                "display_name": str(row["display_name"]),
                "endpoint": str(row["endpoint"]),
                "transport": str(row["transport"]),
                "auth_method": str(row["auth_method"]),
                "sensitivity": str(row["sensitivity"]),
            }
            for row in rows
        ]

    def audit(self, now: datetime, action: str, subject: str, outcome: str) -> None:
        path = self.store_root / "gateway-audit.jsonl"
        line = json.dumps(
            {
                "occurred_at": now.isoformat(),
                "action": action,
                "subject": subject,
                "outcome": outcome,
            }
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        restrict_owned(path)

    def analytics(self) -> dict[str, object]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM gateway_events ORDER BY user_id, occurred_at"
            ).fetchall()
        by_user: dict[str, list[sqlite3.Row]] = {}
        by_team: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            by_user.setdefault(str(row["user_id"]), []).append(row)
            by_team.setdefault(str(row["accounting_team_id"]), []).append(row)
        users = [
            {"user_id": user_id, **_sum_rows(items, "all")}
            for user_id, items in sorted(by_user.items())
        ]
        teams = [
            {"accounting_team_id": team_id, **_sum_rows(items, "all")}
            for team_id, items in sorted(by_team.items())
        ]
        return {"users": users, "teams": teams, "employee": _sum_rows(rows, "all")}


def _sum_rows(rows: list[sqlite3.Row], period: str) -> dict[str, object]:
    requests = len(rows)
    failures = sum(1 for row in rows if str(row["outcome"]) != "completed")
    inputs = _total(rows, "input_tokens")
    outputs = _total(rows, "output_tokens")
    models: dict[str, int] = {}
    for row in rows:
        name = str(row["model_identity"])
        models[name] = models.get(name, 0) + 1
    total = "not_recorded"
    if inputs != "not_recorded" and outputs != "not_recorded":
        total = str(int(inputs) + int(outputs))
    return {
        "period": period,
        "requests": requests,
        "failures": failures,
        "successes": requests - failures,
        "input_tokens": inputs,
        "output_tokens": outputs,
        "total_tokens": total,
        "models": models,
    }


def _total(rows: list[sqlite3.Row], column: str) -> str:
    if not rows:
        return "0"
    values = [str(row[column]) for row in rows]
    if any(item == "not_recorded" or not item.isdigit() for item in values):
        return "not_recorded"
    return str(sum(int(item) for item in values))
