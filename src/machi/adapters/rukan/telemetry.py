"""Local usage, outbox, and report composition. Not admission."""

from __future__ import annotations

import json
import sqlite3
import ssl
import threading
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from machi.adapters.journal.jsonl import JOURNAL_FILENAME
from machi.adapters.rukan.project import export_snapshot, project_admin
from machi.adapters.rukan.secrets import read_credential, write_credential
from machi.kernel.analytics import AnalyticsEvent
from machi.kernel.build import BuildIdentity
from machi.kernel.cadence import (
    DEVELOPMENT,
    interval_seconds,
    next_slot,
    phase_seconds,
)
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.report import (
    OperationalReport,
    UsageCumulative,
    UsageFailureCount,
    UsageRollup,
    dump_report,
    load_report,
    report_id_for,
)
from machi.kernel.schema import from_dict, to_dict
from machi.kernel.unresolved import is_resolved
from machi.kernel.usage import NOT_RECORDED, InferenceUsage
from machi.kernel.witness import WITNESS_COMPOSED_TYPE

_EXPORTABLE = frozenset({PrivacyClass.PUBLIC_OPS, PrivacyClass.OPERATIONAL})
MATERIAL = {
    "serve.ready": "deployment_ready",
    "serve.stopped": "deployment_stopped",
    "serve.failed": "deployment_failed",
    "admit.released": "reservation_released",
    "admit.rejected": "admission_rejected",
    "admit.reconciliation_detected": "reconciliation_mismatch",
    "plan.stale": "plan_stale",
    "plan.created": "plan_changed",
    "foundation.selected": "foundation_changed",
    "model.selected": "model_selected",
    "model.acquisition.completed": "model_acquired",
    "model.acquisition.failed": "model_acquire_failed",
    "model.qualification.compared": "qualification_changed",
    "capacity.safe_envelope.derived": "safe_capacity_changed",
}
IMMEDIATE = frozenset({"deployment_failed", "admission_rejected", "witness_attention"})
COALESCE_SECONDS = 45
MAX_EVENTS = 64
_SCHEMA = "1"

DATA_CATEGORIES = (
    "install and build identity",
    "support snapshot without customer content",
    "operational event envelopes without payloads",
    "usage rollups and cumulative counters",
)
EXCLUSIONS = (
    "prompts",
    "responses",
    "messages",
    "documents",
    "credentials",
    "absolute paths",
)


class TelemetryStore:
    """Durable usage and outbox beside the operational store."""

    def __init__(self, store_root: Path, journal_dir: Path | None, build: BuildIdentity) -> None:  # noqa: E501
        self.store_root = Path(store_root)
        self.journal_dir = Path(journal_dir) if journal_dir else None
        self.build = build
        self._lock = threading.RLock()
        self.store_root.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.store_root / "rukan-telemetry.sqlite", check_same_thread=False)  # noqa: E501
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=2000")
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def record_usage(self, usage: InferenceUsage) -> bool:
        """Persist one usage row. Failure returns false and does not raise."""
        try:
            encoded = to_dict(usage)
            if "prompt" in encoded or "response" in encoded:
                return False
            with self._lock:
                self._db.execute(
                    """
                    INSERT OR IGNORE INTO usage(
                        usage_id, request_id, occurred_at, purpose, install_id,
                        instance_id, plan_id, reservation_id, generation_id,
                        model_identity, model_identity_kind, macropath, outcome,
                        failure, status_code, input_tokens, output_tokens,
                        latency_ms, runtime_duration_ms, version, build_id
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        usage.usage_id, usage.request_id, usage.occurred_at, usage.purpose,  # noqa: E501
                        usage.install_id, usage.instance_id, usage.plan_id,
                        usage.reservation_id, usage.generation_id, usage.model_identity,
                        usage.model_identity_kind, usage.macropath, usage.outcome,
                        usage.failure, usage.status_code, usage.input_tokens,
                        usage.output_tokens, usage.latency_ms, usage.runtime_duration_ms,  # noqa: E501
                        usage.version, usage.build_id,
                    ),
                )
                self._db.commit()
            return True
        except (sqlite3.Error, ValidationError, TypeError, ValueError):
            return False

    def aggregate(self, *, start: str | None = None, end: str | None = None) -> dict[str, object]:  # noqa: E501
        with self._lock:
            rows = self._usage_rows(start, end)
        return _aggregate(rows)

    def configure(
        self,
        *,
        endpoint: str,
        key_id: str,
        secret: str,
        install_id: str,
        enabled: bool,
        actor: str,
        now: datetime,
        local_test: bool = False,
        profile: str = DEVELOPMENT,
        custom_seconds: int | None = None,
    ) -> dict[str, object]:
        _endpoint(endpoint, local_test=local_test)
        seconds = interval_seconds(profile, custom_seconds)
        write_credential(
            self.store_root,
            key_id=key_id,
            secret=secret,
            install_id=install_id,
            endpoint=endpoint,
        )
        reasons = ["telemetry_settings"]
        with self._lock:
            previous = self._meta("cadence_profile")
            previous_seconds = self._meta("cadence_seconds")
            self._set("endpoint", endpoint)
            self._set("key_id", key_id)
            self._set("install_id", install_id)
            self._set("enabled", "true" if enabled else "false")
            self._set("cadence_profile", profile)
            self._set("cadence_seconds", str(seconds))
            self._set("local_test", "true" if local_test else "false")
            changed = previous not in {None, profile} or (
                previous_seconds is not None and previous_seconds != str(seconds)
            )
            if self._meta("next_periodic_at") is None or changed:
                phase = phase_seconds(install_id, profile, seconds)
                self._set("cadence_phase_seconds", str(phase))
                self._set("next_periodic_at", next_slot(now, seconds, phase).isoformat())  # noqa: E501
            if changed:
                reasons.append("cadence_changed")
            self._note(reasons, now, immediate=True)
            self._action(now, "telemetry_settings", "pass", actor, key_id)
            self._db.commit()
        return self.status(now)

    def status(self, now: datetime) -> dict[str, object]:
        with self._lock:
            queued = self._db.execute(
                "SELECT COUNT(*) AS n FROM outbox WHERE state = 'queued'"
            ).fetchone()["n"]
            last = self._db.execute(
                """
                SELECT delivered_at, created_at, last_error FROM outbox
                WHERE state = 'delivered' ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            error = self._db.execute(
                """
                SELECT last_error FROM outbox
                WHERE state = 'queued' AND last_error != ''
                ORDER BY sequence DESC LIMIT 1
                """
            ).fetchone()
            body = {
                "enabled": self._meta("enabled") == "true",
                "endpoint": self._meta("endpoint") or "",
                "key_id": self._meta("key_id") or "not_configured",
                "credential_status": "configured" if self._meta("key_id") else "missing",  # noqa: E501
                "cadence_profile": self._meta("cadence_profile") or DEVELOPMENT,
                "cadence_seconds": int(self._meta("cadence_seconds") or str(interval_seconds(DEVELOPMENT))),  # noqa: E501
                "phase_seconds": int(self._meta("cadence_phase_seconds") or "0"),
                "next_report_at": self._meta("next_periodic_at") or "not_scheduled",
                "last_success_at": (
                    str(last["delivered_at"] or last["created_at"]) if last else "not_recorded"  # noqa: E501
                ),
                "queued": int(queued),
                "last_error": error["last_error"] if error else "",
                "categories": list(DATA_CATEGORIES),
                "exclusions": list(EXCLUSIONS),
                "live_claim": False,
            }
        del now
        return body

    def preview(self, now: datetime) -> dict[str, object]:
        report = self._build(now, ("preview",), persist=False)
        document = json.loads(dump_report(report))
        if not isinstance(document, dict):
            raise ValidationError("operational report preview is not an object")
        return {str(key): value for key, value in document.items()}

    def note(self, reasons: tuple[str, ...] | list[str], now: datetime, *, immediate: bool = False) -> None:  # noqa: E501
        with self._lock:
            self._note(reasons, now, immediate=immediate)
            self._db.commit()

    def tick(
        self, now: datetime, transport: Callable[..., str] | None = None
    ) -> dict[str, object]:
        """Compose at most one report and attempt one send. Never raises."""
        try:
            if self._flag("enabled"):
                self._scan(now)
                self._observe(now)
                if not self._queued():
                    self._maybe_compose(now)
            sent = self._send(now, transport) if self._flag("enabled") else False
            return {"composed": True, "sent": sent}
        except (sqlite3.Error, ValidationError, OSError, TypeError, ValueError):
            return {"composed": False, "sent": False}

    def send_test(self, now: datetime, transport: Callable[..., str] | None = None) -> dict[str, object]:  # noqa: E501
        self.note(("test_report",), now, immediate=True)
        with self._lock:
            self._set("enabled", self._meta("enabled") or "false")
        # A test is explicit even when periodic reporting is off.
        self._scan(now)
        if not self._queued():
            with self._lock:
                self._compose(now, self._due_reasons(now) or ("test_report",))
                self._db.commit()
        sent = self._send(now, transport, force=True)
        return {"sent": sent, **self.status(now)}

    def _scan(self, now: datetime) -> None:
        reasons: list[str] = []
        for event in self._raw_events():
            mapped = MATERIAL.get(str(event.event_type))
            if mapped:
                reasons.append(mapped)
            if str(event.event_type) == WITNESS_COMPOSED_TYPE:
                verdict = str(getattr(event.payload, "verdict", ""))
                if verdict in {"failed", "contradictory"}:
                    reasons.append("witness_attention")
        if reasons:
            immediate = any(item in IMMEDIATE for item in reasons)
            self.note(reasons, now, immediate=immediate)

    def _observe(self, now: datetime) -> None:
        view = project_admin(self.store_root, self.build, journal_dir=self.journal_dir)
        chain = view.chain
        reasons: list[str] = []
        with self._lock:
            previous_path = self._meta("last_macropath")
            previous_model = self._meta("last_model")
            previous_version = self._meta("last_version")
            previous_safe = self._meta("last_safe")
        if previous_path and previous_path != chain.macropath:
            if chain.macropath == "ollama":
                reasons.append("approved_fallback")
            else:
                reasons.append("foundation_changed")
        if previous_model and previous_model != chain.model_identity:
            reasons.append("model_selected")
        if previous_version and previous_version != self.build.version:
            reasons.append("rukan_version_changed")
        safe = view.safe_accelerator_bytes
        if previous_safe and previous_safe != safe:
            reasons.append("safe_capacity_changed")
        if reasons:
            self.note(reasons, now, immediate=False)

    def _maybe_compose(self, now: datetime) -> None:
        with self._lock:
            reasons = self._due_reasons(now)
            periodic = self._periodic_due(now)
            if periodic:
                reasons = tuple(dict.fromkeys((*reasons, "periodic")))
            if not reasons:
                return
            if not periodic and not self._flush_due(now):
                return
            self._compose(now, reasons)
            self._db.commit()

    def _build(self, now: datetime, reasons: tuple[str, ...], *, persist: bool) -> OperationalReport:  # noqa: E501
        view = project_admin(self.store_root, self.build, journal_dir=self.journal_dir)
        generated = now.astimezone(UTC).isoformat()
        snapshot = export_snapshot(view, exported_at=generated, journal_dir=self.journal_dir)  # noqa: E501
        with self._lock:
            sequence = int(self._meta("next_sequence") or "1")
            previous = self._meta("last_acked") or NOT_RECORDED
            window_start = self._meta("window_start") or generated
            profile = self._meta("cadence_profile") or DEVELOPMENT
            cadence = int(self._meta("cadence_seconds") or str(interval_seconds(DEVELOPMENT)))  # noqa: E501
            phase = int(self._meta("cadence_phase_seconds") or "0")
            events, offset, more = self._read_events_locked()
            rollups = _rollups(self._usage_rows(window_start, generated))
            cumulative = _cumulative(self._usage_rows(None, None))
        if more:
            reasons = tuple(dict.fromkeys((*reasons, "event_backlog")))
        report = OperationalReport(
            report_id=report_id_for(view.install_id, sequence, generated, reasons),
            schema_name="rukan.operational_report",
            install_id=view.install_id,
            sequence=sequence,
            generated_at=generated,
            cadence_profile=profile,
            cadence_seconds=cadence,
            cadence_phase_seconds=phase,
            trigger_reasons=reasons,
            version=self.build.version,
            build_id=self.build.build_id or NOT_RECORDED,
            source_commit=self.build.source_commit or NOT_RECORDED,
            previous_report_id=previous,
            window_start=window_start,
            window_end=generated,
            privacy_policy="rukan.telemetry.export.1",
            snapshot=snapshot,
            events=tuple(events[:MAX_EVENTS]),
            rollups=tuple(rollups[:32]),
            cumulative=cumulative,
            event_count=min(len(events), MAX_EVENTS),
            rollup_count=min(len(rollups), 32),
        )
        dump_report(report)
        if persist:
            self._proposed_offset = offset
        else:
            del offset
        return report

    def _compose(self, now: datetime, reasons: tuple[str, ...]) -> None:
        """Freeze one report. Authoritative cursors wait for a matching ACK."""
        queued = self._db.execute(
            "SELECT COUNT(*) AS n FROM outbox WHERE state = 'queued'"
        ).fetchone()["n"]
        if int(queued) > 0:
            return
        report = self._build(now, reasons, persist=True)
        body = dump_report(report)
        included = set(report.trigger_reasons)
        self._db.execute(
            """
            INSERT INTO outbox(
                report_id, sequence, body, state, attempts,
                next_attempt_at, last_error, created_at, delivered_at,
                proposed_journal_offset, proposed_window_start, includes_periodic
            ) VALUES (?, ?, ?, 'queued', 0, ?, '', ?, '', ?, ?, ?)
            """,
            (
                report.report_id,
                report.sequence,
                body,
                now.isoformat(),
                now.isoformat(),
                int(getattr(self, "_proposed_offset", 0)),
                report.window_end,
                1 if "periodic" in included else 0,
            ),
        )
        for reason in included:
            self._db.execute("DELETE FROM pending WHERE reason = ?", (reason,))

    def _send(self, now: datetime, transport: Callable[..., str] | None, *, force: bool = False) -> bool:  # noqa: E501
        with self._lock:
            row = self._db.execute(
                """
                SELECT report_id, body, attempts, next_attempt_at FROM outbox
                WHERE state = 'queued' ORDER BY sequence ASC LIMIT 1
                """
            ).fetchone()
            if row is None:
                return False
            due = datetime.fromisoformat(str(row["next_attempt_at"]))
            if not force and due > now:
                return False
            endpoint = self._meta("endpoint") or ""
            local_test = self._meta("local_test") == "true"
            secret = ""
        loaded = read_credential(self.store_root)
        if loaded is not None:
            secret = loaded["secret"]
            endpoint = loaded["endpoint"] or endpoint
        sender = transport if transport is not None else post_report
        expected = str(row["report_id"])
        try:
            acked = sender(endpoint, secret, str(row["body"]), local_test=local_test)
            ok = str(acked) == expected
            error = "" if ok else "acknowledgement report id does not match"
        except (ValidationError, OSError, urllib.error.URLError, TimeoutError) as exc:
            ok = False
            error = str(exc)[:240]
        with self._lock:
            if ok:
                self._apply_ack(now, expected)
                self._action(now, "report_uploaded", "pass", "telemetry_agent", expected)  # noqa: E501
            else:
                attempts = int(row["attempts"]) + 1
                delay = min(3600, 30 * (2 ** min(attempts, 6)))
                nxt = (now + timedelta(seconds=delay)).isoformat()
                self._db.execute(
                    """
                    UPDATE outbox SET attempts = ?, next_attempt_at = ?, last_error = ?
                    WHERE report_id = ?
                    """,
                    (attempts, nxt, error or "upload failed", row["report_id"]),
                )
                self._action(now, "report_upload_failed", "fail", "telemetry_agent", "upload")  # noqa: E501
            self._db.commit()
        return ok

    def _apply_ack(self, now: datetime, report_id: str) -> None:
        row = self._db.execute(
            """
            SELECT sequence, body, proposed_journal_offset, proposed_window_start,
                   includes_periodic
            FROM outbox WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()
        self._db.execute(
            """
            UPDATE outbox
            SET state = 'delivered', last_error = '', delivered_at = ?
            WHERE report_id = ?
            """,
            (now.isoformat(), report_id),
        )
        if row is None:
            return
        report = load_report(str(row["body"]))
        self._set("last_acked", report_id)
        self._set("next_sequence", str(int(row["sequence"]) + 1))
        self._set("window_start", str(row["proposed_window_start"]))
        self._set("journal_offset", str(int(row["proposed_journal_offset"])))
        self._set("last_macropath", report.snapshot.macropath)
        self._set("last_model", report.snapshot.model_identity)
        self._set("last_version", report.version)
        self._set("last_safe", report.snapshot.safe_accelerator_bytes)
        if int(row["includes_periodic"]):
            nxt = next_slot(now, report.cadence_seconds, report.cadence_phase_seconds)
            self._set("next_periodic_at", nxt.isoformat())

    def _raw_events(self) -> list[EventRecord]:
        if self.journal_dir is None:
            return []
        path = self.journal_dir / JOURNAL_FILENAME
        if not path.is_file():
            return []
        with self._lock:
            offset = int(self._meta("journal_offset") or "0")
        found: list[EventRecord] = []
        for line in path.read_bytes()[offset:].splitlines():
            try:
                event = from_dict(json.loads(line.decode("utf-8")))
            except (json.JSONDecodeError, TypeError, ValueError, ValidationError, UnicodeError):  # noqa: E501
                continue
            if isinstance(event, EventRecord):
                found.append(event)
            if len(found) >= 200:
                break
        return found

    def _read_events(self) -> tuple[list[AnalyticsEvent], int, bool]:
        with self._lock:
            return self._read_events_locked()

    def _read_events_locked(self) -> tuple[list[AnalyticsEvent], int, bool]:
        if self.journal_dir is None:
            return [], 0, False
        path = self.journal_dir / JOURNAL_FILENAME
        if not path.is_file():
            return [], 0, False
        offset = int(self._meta("journal_offset") or "0")
        data = path.read_bytes()
        chunk = data[offset:]
        events: list[AnalyticsEvent] = []
        consumed = offset
        more = False
        install_id = self._meta("install_id") or NOT_RECORDED
        for line in chunk.splitlines(keepends=True):
            consumed += len(line)
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            projected = _project_event(text, install_id)
            if projected is None:
                continue
            if len(events) >= MAX_EVENTS:
                more = True
                consumed -= len(line)
                break
            events.append(projected)
        return events, consumed, more

    def _due_reasons(self, now: datetime) -> tuple[str, ...]:
        rows = self._db.execute("SELECT reason, flush_at FROM pending").fetchall()
        chosen = [str(row["reason"]) for row in rows if datetime.fromisoformat(str(row["flush_at"])) <= now]  # noqa: E501
        return tuple(dict.fromkeys(chosen))

    def _flush_due(self, now: datetime) -> bool:
        return bool(self._due_reasons(now))

    def _periodic_due(self, now: datetime) -> bool:
        raw = self._meta("next_periodic_at")
        if not raw:
            return False
        return datetime.fromisoformat(raw) <= now

    def _queued(self) -> bool:
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM outbox WHERE state = 'queued'"
            ).fetchone()
        return int(row["n"]) > 0

    def _note(self, reasons: tuple[str, ...] | list[str], now: datetime, *, immediate: bool) -> None:  # noqa: E501
        for reason in reasons:
            if not reason or len(reason) > 80:
                continue
            existing = self._db.execute(
                "SELECT flush_at FROM pending WHERE reason = ?", (reason,)
            ).fetchone()
            if existing is not None and not immediate:
                continue
            flush = now if immediate or reason in IMMEDIATE else now + timedelta(seconds=COALESCE_SECONDS)  # noqa: E501
            if existing is not None and immediate:
                flush = now
            self._db.execute(
                """
                INSERT INTO pending(reason, flush_at) VALUES (?, ?)
                ON CONFLICT(reason) DO UPDATE SET flush_at = excluded.flush_at
                """,
                (reason, flush.isoformat()),
            )

    def _flag(self, key: str) -> bool:
        with self._lock:
            return self._meta(key) == "true"

    def _usage_rows(self, start: str | None, end: str | None) -> list[sqlite3.Row]:
        query = "SELECT * FROM usage WHERE 1 = 1"
        values: list[str] = []
        if start is not None:
            query += " AND occurred_at >= ?"
            values.append(start)
        if end is not None:
            query += " AND occurred_at <= ?"
            values.append(end)
        return list(self._db.execute(query, values))

    def _action(self, now: datetime, action: str, outcome: str, actor: str, subject: str) -> None:  # noqa: E501
        path = self.store_root / "telemetry-actions.jsonl"
        line = json.dumps(
            {
                "occurred_at": now.astimezone(UTC).isoformat(),
                "action": action,
                "outcome": outcome,
                "actor_origin": actor,
                "subject": subject,
            }
        )
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _migrate(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage (
                usage_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                purpose TEXT NOT NULL,
                install_id TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                reservation_id TEXT NOT NULL,
                generation_id TEXT NOT NULL,
                model_identity TEXT NOT NULL,
                model_identity_kind TEXT NOT NULL,
                macropath TEXT NOT NULL,
                outcome TEXT NOT NULL,
                failure TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                input_tokens TEXT NOT NULL,
                output_tokens TEXT NOT NULL,
                latency_ms TEXT NOT NULL,
                runtime_duration_ms TEXT NOT NULL,
                version TEXT NOT NULL,
                build_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox (
                report_id TEXT PRIMARY KEY,
                sequence INTEGER NOT NULL,
                body TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT NOT NULL DEFAULT '',
                proposed_journal_offset INTEGER NOT NULL DEFAULT 0,
                proposed_window_start TEXT NOT NULL DEFAULT '',
                includes_periodic INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS pending (
                reason TEXT PRIMARY KEY,
                flush_at TEXT NOT NULL
            );
            """
        )
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(outbox)")}
        for name, ddl in (
            ("delivered_at", "ALTER TABLE outbox ADD COLUMN delivered_at TEXT NOT NULL DEFAULT ''"),  # noqa: E501
            (
                "proposed_journal_offset",
                "ALTER TABLE outbox ADD COLUMN proposed_journal_offset INTEGER NOT NULL DEFAULT 0",  # noqa: E501
            ),
            (
                "proposed_window_start",
                "ALTER TABLE outbox ADD COLUMN proposed_window_start TEXT NOT NULL DEFAULT ''",  # noqa: E501
            ),
            (
                "includes_periodic",
                "ALTER TABLE outbox ADD COLUMN includes_periodic INTEGER NOT NULL DEFAULT 0",  # noqa: E501
            ),
        ):
            if name not in columns:
                self._db.execute(ddl)
        if self._meta("schema") is None:
            self._set("schema", _SCHEMA)
            self._set("cadence_profile", DEVELOPMENT)
            self._set("cadence_seconds", str(interval_seconds(DEVELOPMENT)))
            self._set("cadence_phase_seconds", "0")
            self._set("enabled", "false")
            self._set("next_sequence", "1")
            self._db.commit()

    def _meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()  # noqa: E501
        if row is None:
            return None
        return str(row["value"])

    def _set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",  # noqa: E501
            (key, value),
        )


class TelemetryAgent:
    """Background tick. The browser is not the scheduler."""

    def __init__(self, store: TelemetryStore) -> None:
        self.store = store
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="rukan-telemetry", daemon=True)  # noqa: E501
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(5):
            self.store.tick(datetime.now(UTC))


def activity_feed(store_root: Path, journal_dir: Path | None) -> list[dict[str, str]]:
    """Local accountability rows. Payloads and secrets are not included."""
    rows: list[dict[str, str]] = []
    actions = Path(store_root) / "telemetry-actions.jsonl"
    if actions.is_file():
        for line in actions.read_text(encoding="utf-8").splitlines():
            try:
                document = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(document, dict):
                rows.append({key: str(document.get(key, "")) for key in (
                    "occurred_at", "action", "outcome", "actor_origin", "subject"
                )})
    if journal_dir is not None:
        path = Path(journal_dir) / JOURNAL_FILENAME
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                item = _activity_event(line)
                if item is not None:
                    rows.append(item)
    return rows[-50:]


def post_report(endpoint: str, secret: str, body: str, *, local_test: bool = False) -> str:  # noqa: E501
    """Upload one frozen report. The return value is the ACK report id."""
    _endpoint(endpoint, local_test=local_test)
    if not secret:
        raise ValidationError("telemetry credential is missing")
    sent = json.loads(body)
    expected = sent.get("report_id") if isinstance(sent, dict) else None
    request = urllib.request.Request(
        endpoint,
        data=body.encode("utf-8"),
        headers={
            "authorization": f"Bearer {secret}",
            "content-type": "application/json",
        },
        method="POST",
    )
    context = None
    if local_test and endpoint.startswith("https://127.0.0.1"):
        context = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=5, context=context) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ValidationError("telemetry upload was refused") from exc
    if not isinstance(payload, dict):
        raise ValidationError("telemetry acknowledgement does not name this report")
    nested = payload.get("body")
    acked = nested.get("report_id") if isinstance(nested, dict) else None
    if payload.get("outcome") != "accepted" or acked != expected:
        raise ValidationError("telemetry acknowledgement does not name this report")
    return str(acked)


def _endpoint(endpoint: str, *, local_test: bool) -> None:
    if endpoint.startswith("https://"):
        return
    loopback = endpoint.startswith(("http://127.0.0.1", "http://localhost"))
    if loopback and local_test:
        return
    raise ValidationError("telemetry upload requires HTTPS")


def _activity_event(text: str) -> dict[str, str] | None:
    try:
        event = from_dict(json.loads(text))
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        return None
    if not isinstance(event, EventRecord) or event.privacy not in _EXPORTABLE:
        return None
    return {
        "occurred_at": event.occurred_at.isoformat(),
        "action": str(event.event_type),
        "outcome": str(event.outcome.value),
        "actor_origin": "system",
        "subject": str(event.event_id),
    }


def _project_event(text: str, install_id: str) -> AnalyticsEvent | None:
    try:
        event = from_dict(json.loads(text))
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        return None
    if not isinstance(event, EventRecord) or event.privacy not in _EXPORTABLE:
        return None
    shown = str(event.install_id) if is_resolved(event.install_id) else install_id
    if shown != install_id:
        return None
    return AnalyticsEvent(
        event_id=str(event.event_id),
        event_type=str(event.event_type),
        occurred_at=event.occurred_at.isoformat(),
        install_id=shown,
        block_id=str(event.block_id),
        component_id=str(event.component_id),
        outcome=str(event.outcome.value),
        privacy=event.privacy.value,
    )


def _aggregate(rows: list[sqlite3.Row]) -> dict[str, object]:
    return {
        "summary": _public_cumulative(_cumulative(rows)),
        "groups": [_public_rollup(item) for item in _rollups(rows)],
        "live_claim": False,
    }


def _public_cumulative(item: UsageCumulative) -> dict[str, object]:
    return {
        "requests": item.requests,
        "succeeded": item.succeeded,
        "failed": item.failed,
        "input_tokens_total": item.input_tokens_total,
        "input_sample_count": item.input_sample_count,
        "output_tokens_total": item.output_tokens_total,
        "output_sample_count": item.output_sample_count,
        "latency_ms_sum": item.latency_ms_sum,
        "latency_sample_count": item.latency_sample_count,
        "average_latency_ms": _average(item.latency_ms_sum, item.latency_sample_count),
    }


def _public_rollup(item: UsageRollup) -> dict[str, object]:
    return {
        "model_identity": item.model_identity,
        "macropath": item.macropath,
        "purpose": item.purpose,
        "outcome": item.outcome,
        "requests": item.requests,
        "input_tokens_total": item.input_tokens_total,
        "output_tokens_total": item.output_tokens_total,
        "average_latency_ms": _average(item.latency_ms_sum, item.latency_sample_count),
        "failures": [{"failure": failure.failure, "count": failure.count} for failure in item.failures],  # noqa: E501
    }


def _rollups(rows: list[sqlite3.Row]) -> list[UsageRollup]:
    grouped: dict[tuple[str, str, str, str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        key = (
            str(row["model_identity"]),
            str(row["model_identity_kind"]),
            str(row["macropath"]),
            str(row["purpose"]),
            str(row["outcome"]),
        )
        grouped[key].append(row)
    found: list[UsageRollup] = []
    for key, members in grouped.items():
        found.append(_one_rollup(key, members))
    return found


def _one_rollup(key: tuple[str, str, str, str, str], rows: list[sqlite3.Row]) -> UsageRollup:  # noqa: E501
    failures: dict[str, int] = defaultdict(int)
    for row in rows:
        if str(row["outcome"]) == "failed" and str(row["failure"]) not in {"", "none"}:
            failures[str(row["failure"])] += 1
    counts = tuple(
        UsageFailureCount(failure=name, count=count)
        for name, count in sorted(failures.items())[:8]
    )
    return UsageRollup(
        model_identity=key[0],
        model_identity_kind=key[1],
        macropath=key[2],
        purpose=key[3],
        outcome=key[4],
        requests=len(rows),
        input_tokens_total=_sum(rows, "input_tokens"),
        input_sample_count=_samples(rows, "input_tokens"),
        output_tokens_total=_sum(rows, "output_tokens"),
        output_sample_count=_samples(rows, "output_tokens"),
        latency_ms_sum=_sum(rows, "latency_ms"),
        latency_sample_count=_samples(rows, "latency_ms"),
        latency_min_ms=_bound(rows, "latency_ms", minimum=True),
        latency_max_ms=_bound(rows, "latency_ms", minimum=False),
        failures=counts,
    )


def _cumulative(rows: list[sqlite3.Row]) -> UsageCumulative:
    succeeded = sum(1 for row in rows if str(row["outcome"]) == "completed")
    failed = sum(1 for row in rows if str(row["outcome"]) == "failed")
    return UsageCumulative(
        requests=len(rows),
        succeeded=succeeded,
        failed=failed,
        input_tokens_total=_sum(rows, "input_tokens"),
        input_sample_count=_samples(rows, "input_tokens"),
        output_tokens_total=_sum(rows, "output_tokens"),
        output_sample_count=_samples(rows, "output_tokens"),
        latency_ms_sum=_sum(rows, "latency_ms"),
        latency_sample_count=_samples(rows, "latency_ms"),
    )


def _sum(rows: list[sqlite3.Row], column: str) -> str:
    total = 0
    seen = False
    for row in rows:
        value = str(row[column])
        if value == NOT_RECORDED:
            continue
        total += int(value)
        seen = True
    return str(total) if seen else NOT_RECORDED


def _samples(rows: list[sqlite3.Row], column: str) -> int:
    return sum(1 for row in rows if str(row[column]) != NOT_RECORDED)


def _bound(rows: list[sqlite3.Row], column: str, *, minimum: bool) -> str:
    values = [int(str(row[column])) for row in rows if str(row[column]) != NOT_RECORDED]
    if not values:
        return NOT_RECORDED
    return str(min(values) if minimum else max(values))


def _average(total: str, samples: int) -> str:
    if total == NOT_RECORDED or samples < 1:
        return NOT_RECORDED
    return str(int(total) // samples)
