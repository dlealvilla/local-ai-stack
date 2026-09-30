"""Employee-access backup, provider settings, and preflight. Not a workspace UI."""

from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from machi.kernel.errors import ValidationError

_BACKUP_NAMES = (
    "directory.sqlite",
    "gateway.sqlite",
    "rukan-telemetry.sqlite",
    "workspace.sqlite",
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
    """SQLite backup API. A live file copy of a WAL database is not used."""
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in _BACKUP_NAMES:
        source = Path(store_root) / name
        if not source.is_file():
            continue
        _sqlite_backup(source, destination / name)
        copied.append(name)
    if not copied:
        raise ValidationError("employee backup found no ledgers")
    (destination / "manifest.json").write_text(
        '{"kind":"rukan.employee_backup","names":'
        + str(copied).replace("'", '"')
        + "}\n",
        encoding="utf-8",
    )
    return copied


def restore_employee_state(store_root: Path, source: Path) -> list[str]:
    Path(store_root).mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    for name in _BACKUP_NAMES:
        item = Path(source) / name
        if not item.is_file():
            continue
        _sqlite_backup(item, Path(store_root) / name)
        restored.append(name)
    if not restored:
        raise ValidationError("employee restore found no ledgers")
    return restored


def employee_preflight(
    store_root: Path,
    *,
    static_dir: Path | None = None,
    allow_http: bool = False,
) -> dict[str, object]:
    """Non-mutating checks. A missing model does not start one."""
    root = Path(store_root)
    directory = (root / "directory.sqlite").is_file()
    gateway = (root / "gateway.sqlite").is_file()
    provider = _enabled_provider(root)
    discovery_ok, discovery_text = _probe_discovery(provider, allow_http)
    assets = static_dir or (
        Path(__file__).resolve().parent / "static" / "workspace"
    )
    ready = _ready_instance(root)
    checks = [
        _check("people_store", directory, "people directory"),
        _check("usage_store", gateway or directory, "usage or directory ledger"),
        _check(
            "enabled_provider",
            provider is not None,
            "one enabled identity provider",
        ),
        _check("discovery", discovery_ok, discovery_text),
        _check(
            "workspace_assets",
            (assets / "index.html").is_file(),
            "packaged workspace index",
        ),
        _check("ready_instance", ready, "one READY serving instance"),
        _check("tls_material", True, "TLS is optional and is not invented here"),
    ]
    blocked = [item for item in checks if item["status"] != "pass"]
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "outcome": "blocked" if blocked else "pass",
        "checks": checks,
    }


def load_provider(store_root: Path, provider_id: str) -> dict[str, str]:
    """The stored provider is the production verifier configuration."""
    database = _open(store_root)
    try:
        row = database.execute(
            """
            SELECT provider_id, issuer, audience, discovery_url, enabled
            FROM identity_providers WHERE provider_id = ?
            """,
            (provider_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        raise ValidationError("identity provider is unknown") from exc
    finally:
        database.close()
    if row is None:
        raise ValidationError("identity provider is unknown")
    if not int(row[4]):
        raise ValidationError("identity provider is disabled")
    return {
        "provider_id": str(row[0]),
        "issuer": str(row[1]),
        "audience": str(row[2]),
        "discovery_url": str(row[3]),
        "source": "stored_provider",
    }


def _sqlite_backup(source: Path, destination: Path) -> None:
    origin = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        target = sqlite3.connect(destination)
        try:
            origin.backup(target)
        finally:
            target.close()
    finally:
        origin.close()


def _enabled_provider(root: Path) -> dict[str, str] | None:
    path = root / "gateway.sqlite"
    if not path.is_file():
        return None
    database = sqlite3.connect(path)
    try:
        row = database.execute(
            """
            SELECT issuer, discovery_url FROM identity_providers
            WHERE enabled = 1 ORDER BY provider_id LIMIT 1
            """
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        database.close()
    if row is None:
        return None
    return {"issuer": str(row[0]), "discovery_url": str(row[1])}


def _probe_discovery(
    provider: dict[str, str] | None, allow_http: bool
) -> tuple[bool, str]:
    if provider is None:
        return False, "no enabled provider"
    url = provider["discovery_url"]
    if url.startswith("http://") and not allow_http:
        return False, "discovery is not https"
    try:
        document = _fetch_json(url)
        if document.get("issuer") != provider["issuer"].rstrip("/"):
            return False, "discovery issuer does not match"
        for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            if not isinstance(document.get(name), str):
                return False, f"discovery missing {name}"
        keys = _fetch_json(str(document["jwks_uri"]))
        found = keys.get("keys")
        if not isinstance(found, list) or not found:
            return False, "jwks has no keys"
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
        ValidationError,
    ):
        return False, "discovery did not answer"
    return True, "issuer, authorize, token, and jwks match"


def _fetch_json(url: str) -> dict[str, object]:
    if not url.startswith(("https://", "http://")):
        raise ValidationError("discovery url is incomplete")
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValidationError("discovery document is incomplete")
    return payload


def _ready_instance(root: Path) -> bool:
    try:
        from machi.adapters.rukan.project import project_admin
        from machi.kernel.build import identity

        view = project_admin(root, identity())
    except Exception:
        return False
    return view.chain.instance_state == "ready" and not view.chain.contradictory


def _check(name: str, ok: bool, text: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if ok else "blocked", "text": text}


def _open(store_root: Path) -> sqlite3.Connection:
    root = Path(store_root)
    root.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(root / "gateway.sqlite")
    database.execute("PRAGMA busy_timeout=4000")
    return database
