"""Loopback Command Center store. SQLite is the durable authority, not the browser."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from machi.kernel.analytics import AnalyticsBundle, load_bundle
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.kernel.snapshot import SupportSnapshot, accept_snapshot

API_NAME = "rukan.command.v1"
SCHEMA_VERSION = "2"
_LOOPBACK = "127.0.0.1"
_MAX_BODY = 64_000


class CommandHub:
    """Inbox plus SQLite. Import is explicit and idempotent."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.inbox = self.data_dir / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(
            self.data_dir / "command.sqlite", check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._migrate()
        self.refresh()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def status(self) -> dict[str, object]:
        with self._lock:
            last = self._meta("last_refresh")
            imported = self._meta("last_imported")
            rejected = self._meta("last_rejected")
            deployments = self._db.execute("SELECT COUNT(*) AS n FROM deployments").fetchone()  # noqa: E501
        return _envelope(
            "ok",
            "command center is local",
            {
                "service": "loopback",
                "live_claim": False,
                "schema_version": SCHEMA_VERSION,
                "last_refresh": last or "not_recorded",
                "last_imported": int(imported or "0"),
                "last_rejected": int(rejected or "0"),
                "deployments": int(deployments["n"]),
                "inbox": "inbox",
            },
        )

    def refresh(self) -> dict[str, object]:
        """Scan the inbox. One bad file does not block the others."""
        imported = 0
        skipped = 0
        rejected: list[dict[str, str]] = []
        with self._lock:
            for path in sorted(self.inbox.iterdir()):
                if not path.is_file() or path.name.startswith("."):
                    continue
                if path.suffix not in {".json", ".jsonl"}:
                    continue
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if self._source_hash(digest) is not None:
                    skipped += 1
                    continue
                try:
                    kind, install_id, logical_id, parsed = self._identify(path)
                except (ValidationError, json.JSONDecodeError, UnicodeError, OSError) as exc:  # noqa: E501
                    self._reject(path.name, exc)
                    rejected.append(
                        {"name": path.name, "reason": _reason(exc)}
                    )
                    continue
                if self._source_logical(install_id, logical_id) is not None:
                    skipped += 1
                    continue
                try:
                    self._import_parsed(
                        path, digest, kind, install_id, logical_id, parsed
                    )
                except (ValidationError, json.JSONDecodeError, UnicodeError, OSError) as exc:  # noqa: E501
                    self._reject(path.name, exc)
                    rejected.append({"name": path.name, "reason": _reason(exc)})
                    continue
                imported += 1
            self._set_meta("last_refresh", _now())
            self._set_meta("last_imported", str(imported))
            self._set_meta("last_rejected", str(len(rejected)))
            self._db.commit()
        return _envelope(
            "ok",
            "inbox scanned",
            {
                "imported": imported,
                "skipped": skipped,
                "rejected": len(rejected),
                "rejections": rejected,
                "live_claim": False,
            },
        )

    def deployments(self) -> dict[str, object]:
        with self._lock:
            rows = self._db.execute(
                """
                SELECT install_id, latest_exported_at, version, os_family,
                       architecture, accelerator_summary, macropath,
                       model_identity, witness_verdict, snapshot_count
                FROM deployments
                ORDER BY latest_exported_at DESC
                """
            ).fetchall()
        return _envelope("ok", "imported deployments", {"deployments": [dict(row) for row in rows], "live_claim": False})  # noqa: E501

    def detail(self, install_id: str) -> dict[str, object]:
        with self._lock:
            deployment = self._db.execute(
                "SELECT * FROM deployments WHERE install_id = ?", (install_id,)
            ).fetchone()
            if deployment is None:
                return _envelope("refused", "deployment is not imported", {})
            snapshots = [
                json.loads(row["document"])
                for row in self._db.execute(
                    """
                    SELECT document FROM snapshots
                    WHERE install_id = ? ORDER BY exported_at DESC
                    """,
                    (install_id,),
                )
            ]
            events = [
                dict(row)
                for row in self._db.execute(
                    """
                    SELECT event_id, event_type, occurred_at, block_id,
                           component_id, outcome, privacy
                    FROM events WHERE install_id = ?
                    ORDER BY occurred_at
                    """,
                    (install_id,),
                )
            ]
            inferences = [
                dict(row)
                for row in self._db.execute(
                    "SELECT * FROM inferences WHERE install_id = ? ORDER BY proof_id",
                    (install_id,),
                )
            ]
        body = dict(deployment)
        body["snapshots"] = snapshots
        body["events"] = events
        body["inferences"] = inferences
        body["live_claim"] = False
        return _envelope("ok", "imported deployment", body)

    def analytics(self) -> dict[str, object]:
        with self._lock:
            versions = _grouped(self._db, "version")
            os_rows = _grouped(self._db, "os_family")
            arch = _grouped(self._db, "architecture")
            accelerators = _grouped(self._db, "accelerator_summary")
            paths = _grouped(self._db, "macropath")
            models = _grouped(self._db, "model_identity")
            witness = _grouped(self._db, "witness_verdict")
            failures = self._db.execute(
                """
                SELECT event_type, COUNT(*) AS n FROM events
                WHERE outcome = 'fail' GROUP BY event_type ORDER BY n DESC
                """
            ).fetchall()
            inference = self._db.execute(
                """
                SELECT outcome, COUNT(*) AS n,
                       SUM(CASE WHEN completion_tokens = 'not_recorded' THEN 0
                           ELSE CAST(completion_tokens AS INTEGER) END) AS tokens,
                       SUM(CASE
                           WHEN completion_tokens = 'not_recorded' THEN 0
                           ELSE 1 END)
                           AS reported
                FROM inferences GROUP BY outcome
                """
            ).fetchall()
        return _envelope(
            "ok",
            "imported analytics",
            {
                "live_claim": False,
                "versions": versions,
                "os_family": os_rows,
                "architecture": arch,
                "accelerators": accelerators,
                "macropaths": paths,
                "models": models,
                "witness": witness,
                "event_failures": [dict(row) for row in failures],
                "inferences": [dict(row) for row in inference],
                "missing": [
                    "input tokens",
                    "TTFT",
                    "queue time",
                    "historical request latency",
                    "cost",
                    "user or team usage",
                    "utilization",
                    "SLA",
                ],
            },
        )

    def remove(self, install_id: str) -> dict[str, object]:
        """Delete the local copy. Inbox files stay where the operator put them."""
        with self._lock:
            self._db.execute("DELETE FROM snapshots WHERE install_id = ?", (install_id,))  # noqa: E501
            self._db.execute("DELETE FROM events WHERE install_id = ?", (install_id,))
            self._db.execute("DELETE FROM inferences WHERE install_id = ?", (install_id,))  # noqa: E501
            self._db.execute("DELETE FROM deployments WHERE install_id = ?", (install_id,))  # noqa: E501
            self._db.execute("DELETE FROM sources WHERE install_id = ?", (install_id,))
            self._db.commit()
        return _envelope("ok", "local copy removed", {"install_id": install_id})

    def _identify(
        self, path: Path
    ) -> tuple[str, str, str, AnalyticsBundle | SupportSnapshot]:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            bundle = load_bundle(text)
            return (
                "rukan.analytics_bundle",
                bundle.manifest.install_id,
                bundle.manifest.bundle_id,
                bundle,
            )
        snapshot = accept_snapshot(json.loads(text))
        return (
            "rukan.support_snapshot",
            snapshot.install_id,
            snapshot.snapshot_id,
            snapshot,
        )

    def _import_parsed(
        self,
        path: Path,
        digest: str,
        kind: str,
        install_id: str,
        logical_id: str,
        parsed: AnalyticsBundle | SupportSnapshot,
    ) -> None:
        self._db.execute("BEGIN")
        try:
            if isinstance(parsed, AnalyticsBundle):
                self._apply_bundle(parsed)
            else:
                self._apply_snapshot(parsed, logical_id)
            self._db.execute(
                """
                INSERT INTO sources(
                    sha256, name, kind, install_id, logical_id, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (digest, path.name, kind, install_id, logical_id, _now()),
            )
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise

    def _source_hash(self, digest: str) -> str | None:
        row = self._db.execute(
            "SELECT sha256 FROM sources WHERE sha256 = ?", (digest,)
        ).fetchone()
        if row is None:
            return None
        return str(row["sha256"])

    def _source_logical(self, install_id: str, logical_id: str) -> str | None:
        row = self._db.execute(
            """
            SELECT logical_id FROM sources
            WHERE install_id = ? AND logical_id = ?
            """,
            (install_id, logical_id),
        ).fetchone()
        if row is None:
            return None
        return str(row["logical_id"])

    def _reject(self, name: str, exc: Exception) -> None:
        self._db.execute(
            "INSERT INTO rejections(name, reason, seen_at) VALUES (?, ?, ?)",
            (name, _reason(exc), _now()),
        )
        self._db.commit()

    def _apply_bundle(self, bundle: AnalyticsBundle) -> None:
        for snapshot in bundle.snapshots:
            self._apply_snapshot(snapshot, bundle.manifest.bundle_id)
        for event in bundle.events:
            self._db.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_id, install_id, bundle_id, event_type, occurred_at,
                    block_id, component_id, outcome, privacy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.install_id,
                    bundle.manifest.bundle_id,
                    event.event_type,
                    event.occurred_at,
                    event.block_id,
                    event.component_id,
                    event.outcome,
                    event.privacy,
                ),
            )
        for item in bundle.inferences:
            self._db.execute(
                """
                INSERT OR IGNORE INTO inferences(
                    proof_id, install_id, bundle_id, instance_id, plan_id,
                    reservation_id, generation_id, model_identity,
                    model_identity_kind, request_kind, status_code,
                    completion_tokens, structurally_valid, failure, outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.proof_id,
                    item.install_id,
                    bundle.manifest.bundle_id,
                    item.instance_id,
                    item.plan_id,
                    item.reservation_id,
                    item.generation_id,
                    item.model_identity,
                    item.model_identity_kind,
                    item.request_kind,
                    item.status_code,
                    item.completion_tokens,
                    1 if item.structurally_valid else 0,
                    item.failure,
                    item.outcome,
                ),
            )

    def _apply_snapshot(self, snapshot: SupportSnapshot, bundle_id: str) -> None:
        self._db.execute(
            """
            INSERT OR IGNORE INTO snapshots(
                snapshot_id, install_id, exported_at, document
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.install_id,
                snapshot.exported_at,
                json.dumps(to_dict(snapshot), sort_keys=True),
            ),
        )
        count = self._db.execute(
            "SELECT COUNT(*) AS n FROM snapshots WHERE install_id = ?",
            (snapshot.install_id,),
        ).fetchone()["n"]
        self._db.execute(
            """
            INSERT INTO deployments(
                install_id, latest_exported_at, version, os_family, architecture,
                accelerator_summary, macropath, model_identity, witness_verdict,
                snapshot_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(install_id) DO UPDATE SET
                latest_exported_at = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.latest_exported_at
                    ELSE deployments.latest_exported_at
                END,
                version = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.version ELSE deployments.version
                END,
                os_family = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.os_family ELSE deployments.os_family
                END,
                architecture = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.architecture ELSE deployments.architecture
                END,
                accelerator_summary = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.accelerator_summary
                    ELSE deployments.accelerator_summary
                END,
                macropath = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.macropath ELSE deployments.macropath
                END,
                model_identity = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.model_identity ELSE deployments.model_identity
                END,
                witness_verdict = CASE
                    WHEN excluded.latest_exported_at >= deployments.latest_exported_at
                    THEN excluded.witness_verdict ELSE deployments.witness_verdict
                END,
                snapshot_count = excluded.snapshot_count
            """,
            (
                snapshot.install_id,
                snapshot.exported_at,
                snapshot.version,
                snapshot.os_family,
                snapshot.architecture,
                snapshot.accelerator_summary,
                snapshot.macropath,
                snapshot.model_identity,
                snapshot.witness_verdict,
                count,
            ),
        )
        del bundle_id

    def _migrate(self) -> None:
        self._db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")  # noqa: E501
        version = self._meta("schema_version")
        if version is None:
            self._db.executescript(
                """
                CREATE TABLE sources (
                    sha256 TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    install_id TEXT NOT NULL,
                    logical_id TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX sources_logical
                    ON sources(install_id, logical_id);
                CREATE TABLE rejections (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    seen_at TEXT NOT NULL
                );
                CREATE TABLE deployments (
                    install_id TEXT PRIMARY KEY,
                    latest_exported_at TEXT NOT NULL,
                    version TEXT NOT NULL,
                    os_family TEXT NOT NULL,
                    architecture TEXT NOT NULL,
                    accelerator_summary TEXT NOT NULL,
                    macropath TEXT NOT NULL,
                    model_identity TEXT NOT NULL,
                    witness_verdict TEXT NOT NULL,
                    snapshot_count INTEGER NOT NULL
                );
                CREATE TABLE snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    install_id TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    document TEXT NOT NULL
                );
                CREATE TABLE events (
                    event_id TEXT PRIMARY KEY,
                    install_id TEXT NOT NULL,
                    bundle_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    block_id TEXT NOT NULL,
                    component_id TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    privacy TEXT NOT NULL
                );
                CREATE TABLE inferences (
                    proof_id TEXT PRIMARY KEY,
                    install_id TEXT NOT NULL,
                    bundle_id TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    reservation_id TEXT NOT NULL,
                    generation_id TEXT NOT NULL,
                    model_identity TEXT NOT NULL,
                    model_identity_kind TEXT NOT NULL,
                    request_kind TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    completion_tokens TEXT NOT NULL,
                    structurally_valid INTEGER NOT NULL,
                    failure TEXT NOT NULL,
                    outcome TEXT NOT NULL
                );
                """
            )
            self._set_meta("schema_version", SCHEMA_VERSION)
            self._db.commit()
            return
        if version == "1":
            self._db.execute("DROP TABLE IF EXISTS sources")
            self._db.executescript(
                """
                CREATE TABLE sources (
                    sha256 TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    install_id TEXT NOT NULL,
                    logical_id TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX sources_logical
                    ON sources(install_id, logical_id);
                """
            )
            self._set_meta("schema_version", SCHEMA_VERSION)
            self._db.commit()
            return
        if version != SCHEMA_VERSION:
            raise ValidationError("command center schema version is not supported")

    def _meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()  # noqa: E501
        if row is None:
            return None
        return str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",  # noqa: E501
            (key, value),
        )


def serve_command_center(
    hub: CommandHub, *, host: str = _LOOPBACK, port: int = 8780, static_dir: Path | None = None  # noqa: E501
) -> None:
    """Bind loopback and serve the hub until interrupted."""
    if host != _LOOPBACK:
        raise ValidationError("Rukan Command Center binds to loopback only")
    httpd = _server(hub, host, port, static_dir)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        hub.close()


def bind_command_center(
    hub: CommandHub, *, host: str = _LOOPBACK, port: int = 0
) -> ThreadingHTTPServer:
    return _server(hub, host, port, None)


def _server(
    hub: CommandHub, host: str, port: int, static_dir: Path | None
) -> ThreadingHTTPServer:
    if host != _LOOPBACK:
        raise ValidationError("Rukan Command Center binds to loopback only")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            _dispatch(self, hub, "GET", static_dir)

        def do_POST(self) -> None:
            _dispatch(self, hub, "POST", static_dir)

        def do_DELETE(self) -> None:
            _dispatch(self, hub, "DELETE", static_dir)

        def log_message(self, *_args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def _dispatch(
    handler: BaseHTTPRequestHandler,
    hub: CommandHub,
    method: str,
    static_dir: Path | None,
) -> None:
    origin = handler.headers.get("Origin")
    local = origin is None or origin.startswith("http://127.0.0.1")
    local = local or (origin is not None and origin.startswith("http://localhost"))
    if not local:
        _write(handler, 403, _envelope("refused", "origin is not loopback", {}))
        return
    path = urlparse(handler.path).path
    if method == "GET" and path == "/v1/status":
        _write(handler, 200, hub.status())
        return
    if method == "POST" and path == "/v1/refresh":
        _write(handler, 200, hub.refresh())
        return
    if method == "GET" and path == "/v1/deployments":
        _write(handler, 200, hub.deployments())
        return
    if method == "GET" and path == "/v1/analytics":
        _write(handler, 200, hub.analytics())
        return
    if path.startswith("/v1/deployments/"):
        install_id = unquote(path.removeprefix("/v1/deployments/"))
        if not install_id or "/" in install_id:
            _write(handler, 404, _envelope("refused", "unknown route", {}))
            return
        if method == "GET":
            _write(handler, 200, hub.detail(install_id))
            return
        if method == "DELETE":
            _write(handler, 200, hub.remove(install_id))
            return
    if method == "GET" and static_dir is not None and _static(handler, static_dir, path):  # noqa: E501
        return
    _write(handler, 404, _envelope("refused", "unknown route", {}))


def _grouped(db: sqlite3.Connection, column: str) -> list[dict[str, object]]:
    if column not in {
        "version",
        "os_family",
        "architecture",
        "accelerator_summary",
        "macropath",
        "model_identity",
        "witness_verdict",
    }:
        raise ValidationError("analytics group is not allow-listed")
    rows = db.execute(
        f"SELECT {column} AS label, COUNT(*) AS n FROM deployments GROUP BY {column}"
    ).fetchall()
    return [dict(row) for row in rows]


def _static(handler: BaseHTTPRequestHandler, root: Path, path: str) -> bool:
    relative = "index.html" if path in {"", "/"} else path.lstrip("/")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    data = candidate.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html" if candidate.suffix == ".html" else "application/octet-stream")  # noqa: E501
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)
    return True


def _write(handler: BaseHTTPRequestHandler, status: int, body: dict[str, object]) -> None:  # noqa: E501
    encoded = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(encoded)


def _envelope(outcome: str, reason: str, body: dict[str, object]) -> dict[str, object]:
    return {"api": API_NAME, "outcome": outcome, "reason": reason, "body": body}


def _reason(exc: Exception) -> str:
    message = exc.message if isinstance(exc, ValidationError) else "unreadable"
    return message[:240]


def _now() -> str:
    return datetime.now(UTC).isoformat()
