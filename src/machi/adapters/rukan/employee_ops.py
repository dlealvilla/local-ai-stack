"""Employee-access backup, provider settings, and preflight. Not a workspace UI."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from machi.kernel.errors import ValidationError

_BACKUP_NAMES = (
    "directory.sqlite",
    "gateway.sqlite",
    "rukan-telemetry.sqlite",
)


def save_provider(
    store_root: Path,
    *,
    provider_id: str,
    label: str,
    issuer: str,
    audience: str,
    discovery_url: str,
    enabled: bool,
    now: datetime,
) -> dict[str, object]:
    """One configured issuer. Several rows may exist; one may be enabled."""
    database = _open(store_root)
    try:
        database.execute(
            """
            CREATE TABLE IF NOT EXISTS identity_providers (
                provider_id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                issuer TEXT NOT NULL,
                audience TEXT NOT NULL,
                discovery_url TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                algorithms TEXT NOT NULL,
                clock_skew INTEGER NOT NULL,
                trust_metadata TEXT NOT NULL,
                last_discovery TEXT NOT NULL,
                last_jwks_refresh TEXT NOT NULL,
                last_error TEXT NOT NULL
            )
            """
        )
        if enabled:
            database.execute("UPDATE identity_providers SET enabled = 0")
        database.execute(
            """
            INSERT INTO identity_providers(
                provider_id, label, issuer, audience, discovery_url, enabled,
                algorithms, clock_skew, trust_metadata, last_discovery,
                last_jwks_refresh, last_error
            ) VALUES (
                ?, ?, ?, ?, ?, ?, 'RS256', 60, 'platform_ca', ?, 'not_recorded', ''
            )
            ON CONFLICT(provider_id) DO UPDATE SET
                label = excluded.label,
                issuer = excluded.issuer,
                audience = excluded.audience,
                discovery_url = excluded.discovery_url,
                enabled = excluded.enabled,
                last_discovery = excluded.last_discovery
            """,
            (
                provider_id, label, issuer, audience, discovery_url,
                1 if enabled else 0, now.isoformat(),
            ),
        )
        database.commit()
    finally:
        database.close()
    return {"provider_id": provider_id, "enabled": enabled, "issuer": issuer}


def list_providers(store_root: Path) -> list[dict[str, object]]:
    database = _open(store_root)
    try:
        rows = database.execute(
            "SELECT name FROM sqlite_master WHERE name = 'identity_providers'"
        ).fetchall()
        if not rows:
            return []
        found = database.execute(
            """
            SELECT provider_id, label, issuer, audience, enabled, last_error
            FROM identity_providers ORDER BY provider_id
            """
        ).fetchall()
    finally:
        database.close()
    return [
        {
            "provider_id": str(row[0]),
            "label": str(row[1]),
            "issuer": str(row[2]),
            "audience": str(row[3]),
            "enabled": bool(row[4]),
            "last_error": str(row[5]),
            "state": "ready" if row[4] and not row[5] else "configured",
        }
        for row in found
    ]


def backup_employee_state(store_root: Path, destination: Path) -> list[str]:
    """Copy customer-local ledgers. Machine telemetry secrets are not included."""
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in _BACKUP_NAMES:
        source = Path(store_root) / name
        if not source.is_file():
            continue
        shutil.copy2(source, destination / name)
        copied.append(name)
    if not copied:
        raise ValidationError("employee backup found no ledgers")
    return copied


def restore_employee_state(store_root: Path, source: Path) -> list[str]:
    Path(store_root).mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    for name in _BACKUP_NAMES:
        item = Path(source) / name
        if not item.is_file():
            continue
        shutil.copy2(item, Path(store_root) / name)
        restored.append(name)
    if not restored:
        raise ValidationError("employee restore found no ledgers")
    return restored


def employee_preflight(store_root: Path) -> dict[str, object]:
    """Non-mutating checks. A missing model does not start one."""
    root = Path(store_root)
    directory = (root / "directory.sqlite").is_file()
    usage_ok = (root / "gateway.sqlite").is_file() or directory
    checks = [
        _check("usage_store", usage_ok, "usage or directory ledger"),
        _check("people_store", directory, "people directory"),
        _check("tls_material", True, "TLS is optional and is not invented here"),
    ]
    blocked = [item for item in checks if item["status"] != "pass"]
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "outcome": "blocked" if blocked else "pass",
        "checks": checks,
    }


def _check(name: str, ok: bool, text: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if ok else "blocked", "text": text}


def _open(store_root: Path) -> sqlite3.Connection:
    root = Path(store_root)
    root.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(root / "gateway.sqlite")
    database.execute("PRAGMA busy_timeout=4000")
    return database
