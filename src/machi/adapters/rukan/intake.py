"""Write-only telemetry intake. It does not operate a deployment."""

from __future__ import annotations

import hashlib
import json
import secrets
import ssl
from collections import deque
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from machi.adapters.rukan.hub import CommandHub
from machi.adapters.rukan.secrets import secret_hash
from machi.kernel.errors import ValidationError
from machi.kernel.report import MAX_REPORT_BYTES, load_report

API_NAME = "rukan.telemetry_intake.v1"
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


def issue_credential(hub: CommandHub, install_id: str, now: datetime) -> dict[str, str]:
    """Create a key. The secret is returned only by this call."""
    key_id = "tkey_" + secrets.token_hex(8)
    secret = secrets.token_urlsafe(32)
    with hub._lock:
        hub._db.execute(
            """
            INSERT INTO credentials(
                key_id, install_id, secret_sha256, status, created_at, revoked_at
            )
            VALUES (?, ?, ?, 'active', ?, '')
            """,
            (key_id, install_id, secret_hash(secret), now.isoformat()),
        )
        hub._db.commit()
    return {"key_id": key_id, "secret": secret, "install_id": install_id, "status": "active"}  # noqa: E501


def revoke_credential(hub: CommandHub, key_id: str, now: datetime) -> dict[str, str]:
    with hub._lock:
        hub._db.execute(
            """
            UPDATE credentials SET status = 'revoked', revoked_at = ? WHERE key_id = ?
            """,
            (now.isoformat(), key_id),
        )
        hub._db.commit()
    return {"key_id": key_id, "status": "revoked"}


def rotate_credential(hub: CommandHub, key_id: str, now: datetime) -> dict[str, str]:
    with hub._lock:
        row = hub._db.execute(
            "SELECT install_id FROM credentials WHERE key_id = ?", (key_id,)
        ).fetchone()
    if row is None:
        raise ValidationError("telemetry credential is unknown")
    revoke_credential(hub, key_id, now)
    issued = issue_credential(hub, str(row["install_id"]), now)
    issued["rotated_from"] = key_id
    return issued


def credential_status(hub: CommandHub) -> list[dict[str, str]]:
    with hub._lock:
        rows = hub._db.execute(
            """
            SELECT key_id, install_id, status, created_at, revoked_at
            FROM credentials ORDER BY created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def accept_report(
    hub: CommandHub, body: str, secret: str, *, received_at: datetime
) -> dict[str, object]:
    """Authenticate, validate, and store. The raw body is not kept on failure."""
    digest = secret_hash(secret)
    with hub._lock:
        row = hub._db.execute(
            """
            SELECT key_id, install_id, status FROM credentials WHERE secret_sha256 = ?
            """,
            (digest,),
        ).fetchone()
        if row is None or str(row["status"]) != "active":
            _reject(hub, str(row["key_id"]) if row else "unknown", "credential rejected")  # noqa: E501
            raise ValidationError("telemetry credential was rejected")
        key_id = str(row["key_id"])
        bound = str(row["install_id"])
        try:
            report = load_report(body)
        except ValidationError as exc:
            _reject(hub, key_id, exc.message)
            raise
        if report.install_id != bound:
            _reject(hub, key_id, "install id does not match the credential")
            raise ValidationError("telemetry install id does not match the credential")
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        existing = hub._db.execute(
            "SELECT body_sha256 FROM reports WHERE report_id = ?", (report.report_id,)
        ).fetchone()
        if existing is not None:
            if str(existing["body_sha256"]) != body_sha:
                _reject(hub, key_id, "report id was reused with a different body")
                raise ValidationError("telemetry report id was reused")
            return {"report_id": report.report_id, "duplicate": True, "key_id": key_id}
        gap, high = _sequence(hub, report.install_id, report.sequence)
        hub._db.execute("BEGIN")
        try:
            hub._apply_snapshot(report.snapshot, report.report_id)
            hub._db.execute(
                """
                INSERT INTO reports(
                    report_id, install_id, sequence, generated_at, received_at,
                    triggers, version, build_id, key_id, body_sha256, outcome,
                    event_count, rollup_count, requests, output_tokens, input_tokens,
                    latency_ms_sum, latency_sample_count, gap, document
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    report.report_id, report.install_id, report.sequence, report.generated_at,  # noqa: E501
                    received_at.isoformat(), ",".join(report.trigger_reasons), report.version,  # noqa: E501
                    report.build_id, key_id, body_sha, "accepted", report.event_count,
                    report.rollup_count, report.cumulative.requests,
                    report.cumulative.output_tokens_total, report.cumulative.input_tokens_total,  # noqa: E501
                    report.cumulative.latency_ms_sum, report.cumulative.latency_sample_count,  # noqa: E501
                    gap, body,
                ),
            )
            for item in report.rollups:
                hub._db.execute(
                    """
                    INSERT OR IGNORE INTO usage_rollups(
                        report_id, install_id, model_identity, model_identity_kind,
                        macropath, purpose, outcome, requests,
                        input_tokens, input_samples,
                        output_tokens, output_samples, latency_ms_sum, latency_samples,
                        latency_min_ms, latency_max_ms
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        report.report_id, report.install_id, item.model_identity,
                        item.model_identity_kind, item.macropath, item.purpose, item.outcome,  # noqa: E501
                        item.requests, item.input_tokens_total, item.input_sample_count,
                        item.output_tokens_total, item.output_sample_count, item.latency_ms_sum,  # noqa: E501
                        item.latency_sample_count, item.latency_min_ms, item.latency_max_ms,  # noqa: E501
                    ),
                )
            hub._db.execute(
                """
                INSERT INTO report_cursors(install_id, high_sequence, gap)
                VALUES (?, ?, ?)
                ON CONFLICT(install_id) DO UPDATE SET
                    high_sequence = excluded.high_sequence,
                    gap = excluded.gap
                """,
                (report.install_id, high, gap),
            )
            hub._db.execute(
                """
                UPDATE deployments SET
                    last_report_received_at = ?,
                    last_report_sequence = ?,
                    last_trigger = ?,
                    report_gap = ?
                WHERE install_id = ?
                """,
                (
                    received_at.isoformat(), report.sequence,
                    report.trigger_reasons[0], gap, report.install_id,
                ),
            )
            hub._db.commit()
        except Exception:
            hub._db.rollback()
            raise
    return {"report_id": report.report_id, "duplicate": False, "key_id": key_id, "gap": gap}  # noqa: E501


def reporting_view(hub: CommandHub, now: datetime) -> dict[str, object]:
    with hub._lock:
        accepted = hub._db.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"]
        rejected = hub._db.execute("SELECT COUNT(*) AS n FROM intake_rejections").fetchone()["n"]  # noqa: E501
        gaps = hub._db.execute(
            "SELECT COUNT(*) AS n FROM report_cursors WHERE gap != 'none'"
        ).fetchone()["n"]
        recent = [
            dict(row)
            for row in hub._db.execute(
                """
                SELECT report_id, install_id, sequence, generated_at, received_at,
                       triggers, version, key_id, gap, event_count, rollup_count
                FROM reports ORDER BY received_at DESC LIMIT 20
                """
            )
        ]
        reasons = [
            dict(row)
            for row in hub._db.execute(
                """
                SELECT reason, COUNT(*) AS n FROM intake_rejections
                GROUP BY reason ORDER BY n DESC
                """
            )
        ]
        credentials = [
            dict(row)
            for row in hub._db.execute(
                """
                SELECT key_id, install_id, status, created_at, revoked_at
                FROM credentials ORDER BY created_at
                """
            )
        ]
    return {
        "accepted": int(accepted),
        "rejected": int(rejected),
        "gaps": int(gaps),
        "recent": recent,
        "rejection_reasons": reasons,
        "credentials": credentials,
        "checked_at": now.isoformat(),
        "live_claim": False,
    }


def portfolio_view(hub: CommandHub, now: datetime) -> dict[str, object]:
    with hub._lock:
        deployments = hub._db.execute("SELECT COUNT(*) AS n FROM deployments").fetchone()["n"]  # noqa: E501
        day = (now - timedelta(hours=24)).isoformat()
        week = (now - timedelta(days=7)).isoformat()
        reports_day = _count_since(hub, day)
        reports_week = _count_since(hub, week)
        later = 0
        within = 0
        for row in hub._db.execute(
            "SELECT last_report_received_at FROM deployments"
        ):
            stamp = str(row["last_report_received_at"])
            if stamp in {"", "not_recorded"}:
                later += 1
                continue
            age = now - datetime.fromisoformat(stamp)
            if age > timedelta(hours=6, minutes=15):
                later += 1
            else:
                within += 1
        requests = hub._db.execute(
            "SELECT COALESCE(SUM(requests), 0) AS n FROM usage_rollups"
        ).fetchone()["n"]
        rejected = hub._db.execute("SELECT COUNT(*) AS n FROM intake_rejections").fetchone()["n"]  # noqa: E501
    return {
        "deployments": int(deployments),
        "reports_24h": reports_day,
        "reports_7d": reports_week,
        "within_cadence": within,
        "later_than_scheduled": later,
        "requests": int(requests),
        "rejected_reports": int(rejected),
        "live_claim": False,
        "wording": "report age is not online or offline status",
    }


def landscape(hub: CommandHub) -> dict[str, object]:
    with hub._lock:
        rows = hub._db.execute(
            """
            SELECT model_identity,
                   COUNT(DISTINCT install_id) AS deployments,
                   SUM(requests) AS requests,
                   SUM(CASE WHEN input_tokens = 'not_recorded' THEN 0
                       ELSE CAST(input_tokens AS INTEGER) END) AS input_tokens,
                   SUM(CASE WHEN output_tokens = 'not_recorded' THEN 0
                       ELSE CAST(output_tokens AS INTEGER) END) AS output_tokens,
                   SUM(CASE WHEN latency_ms_sum = 'not_recorded' THEN 0
                       ELSE CAST(latency_ms_sum AS INTEGER) END) AS latency_ms,
                   SUM(latency_samples) AS latency_samples,
                   SUM(CASE WHEN outcome = 'failed' THEN requests ELSE 0 END)
                       AS failures
            FROM usage_rollups GROUP BY model_identity ORDER BY requests DESC
            """
        ).fetchall()
    return {"models": [dict(row) for row in rows], "live_claim": False}


def set_alias(hub: CommandHub, install_id: str, label: str) -> dict[str, str]:
    if not label or len(label) > 80 or any(char in label for char in "\n\r\x00"):
        raise ValidationError("deployment alias is empty or unsafe")
    with hub._lock:
        hub._db.execute(
            """
            INSERT INTO aliases(install_id, label) VALUES (?, ?)
            ON CONFLICT(install_id) DO UPDATE SET label = excluded.label
            """,
            (install_id, label),
        )
        hub._db.commit()
    return {"install_id": install_id, "label": label}


def bind_intake(
    hub: CommandHub,
    host: str,
    port: int,
    *,
    certfile: str | None = None,
    keyfile: str | None = None,
    local_test: bool = False,
    rate_limit: int = 60,
) -> ThreadingHTTPServer:
    """Bind the write-only intake. Plaintext off loopback is refused."""
    if host not in _LOOPBACK and not certfile:
        raise ValidationError("non-loopback telemetry intake requires HTTPS")
    if host in _LOOPBACK and not certfile and not local_test:
        raise ValidationError("plaintext telemetry intake requires explicit local-test mode")  # noqa: E501
    hits: dict[str, deque[datetime]] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            if urlparse(self.path).path != "/v1/telemetry/reports":
                _write(self, 404, "unknown route")
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0 or length > MAX_REPORT_BYTES:
                _write(self, 413, "report is too large")
                return
            raw = self.rfile.read(length)
            header = self.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                _write(self, 401, "credential missing")
                return
            secret = header.removeprefix("Bearer ").strip()
            if not _allow(hits, secret_hash(secret), rate_limit):
                _write(self, 429, "credential rate exceeded")
                return
            try:
                result = accept_report(
                    hub, raw.decode("utf-8"), secret, received_at=datetime.now(UTC)
                )
            except (ValidationError, UnicodeError):
                _write(self, 400, "report rejected")
                return
            _write(self, 200, "accepted", {**result, "duplicate": result["duplicate"]})

        def do_GET(self) -> None:
            _write(self, 404, "intake is write-only")

        def log_message(self, *_args: object) -> None:
            return

    httpd = ThreadingHTTPServer((host, port), Handler)
    if certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile or certfile)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    return httpd


def _sequence(hub: CommandHub, install_id: str, sequence: int) -> tuple[str, int]:
    row = hub._db.execute(
        "SELECT high_sequence FROM report_cursors WHERE install_id = ?", (install_id,)
    ).fetchone()
    high = int(row["high_sequence"]) if row else 0
    if sequence > high + 1 and high > 0:
        return f"gap_after:{high}", sequence
    if sequence <= high:
        return "out_of_order", high
    return "none", sequence


def _reject(hub: CommandHub, key_id: str, reason: str) -> None:
    hub._db.execute(
        "INSERT INTO intake_rejections(seen_at, key_id, reason) VALUES (?, ?, ?)",
        (datetime.now(UTC).isoformat(), key_id, reason[:240]),
    )
    hub._db.commit()


def _count_since(hub: CommandHub, stamp: str) -> int:
    row = hub._db.execute(
        "SELECT COUNT(*) AS n FROM reports WHERE received_at >= ?", (stamp,)
    ).fetchone()
    return int(row["n"])


def _allow(hits: dict[str, deque[datetime]], key: str, limit: int) -> bool:
    now = datetime.now(UTC)
    window = hits.setdefault(key, deque())
    while window and now - window[0] > timedelta(minutes=1):
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def _write(
    handler: BaseHTTPRequestHandler,
    status: int,
    reason: str,
    body: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "api": API_NAME,
        "outcome": "accepted" if status == 200 else "refused",
        "reason": reason,
    }
    if body:
        payload["body"] = body
    encoded = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)

