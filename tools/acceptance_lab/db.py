"""SQLite connection, pragmas, and deterministic migrations."""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
import subprocess
from pathlib import Path

from tools.acceptance_lab.jsonutil import sha256_bytes
from tools.acceptance_lab.paths import default_db_path, migrations_dir, repository_root
from tools.acceptance_lab.timeutil import UTC, format_utc

_MIGRATION_NAME = re.compile(r"^(\d{4})_(.+)\.sql$")
BUSY_TIMEOUT_MS = 5000
SCHEMA_VERSION = 1


class MigrationError(RuntimeError):
    """A migration could not be applied or verified."""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def _git_commit(root: Path) -> str:
    try:
        finished = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    if finished.returncode != 0:
        return "unknown"
    return finished.stdout.strip() or "unknown"


def _migration_files(directory: Path) -> list[tuple[int, str, Path, str]]:
    found: list[tuple[int, str, Path, str]] = []
    if not directory.is_dir():
        raise MigrationError(f"missing migrations directory: {directory}")
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise MigrationError(f"unexpected migration filename: {path.name}")
        version = int(match.group(1))
        name = match.group(2)
        digest = sha256_bytes(path.read_bytes())
        found.append((version, name, path, digest))
    return found


def applied_migrations(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    existing = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name = 'schema_migration'"
    ).fetchone()
    if existing is None:
        return {}
    rows = connection.execute(
        "SELECT version, migration_name, migration_sha256, applied_at_utc, "
        "tool_git_commit FROM schema_migration ORDER BY version"
    ).fetchall()
    return {int(row["version"]): row for row in rows}


def initialize(
    path: Path | None = None,
    *,
    migrations: Path | None = None,
    now: dt.datetime | None = None,
) -> sqlite3.Connection:
    """Apply pending migrations to an empty or existing database.

    Re-running is idempotent: already-applied versions are verified by
    SHA-256 and not duplicated.
    """
    db_path = path or default_db_path()
    connection = connect(db_path)
    try:
        repo = repository_root(db_path.parent)
    except FileNotFoundError:
        repo = db_path.parent
    apply_migrations(
        connection,
        migrations_path=migrations or migrations_dir(),
        now=now,
        repo=repo,
    )
    return connection


def apply_migrations(
    connection: sqlite3.Connection,
    *,
    migrations_path: Path,
    now: dt.datetime | None = None,
    repo: Path | None = None,
) -> None:
    files = _migration_files(migrations_path)
    if not files:
        raise MigrationError("no migration files found")
    versions = [item[0] for item in files]
    expected = list(range(1, len(files) + 1))
    if versions != expected:
        raise MigrationError(f"migrations must be contiguous from 1, got {versions}")
    applied = applied_migrations(connection)
    expected_next = 1 if not applied else max(applied) + 1
    when = format_utc(now or dt.datetime.now(UTC))
    commit = _git_commit(repo or Path.cwd())
    for version, name, path, digest in files:
        if version in applied:
            recorded = str(applied[version]["migration_sha256"])
            if recorded != digest:
                raise MigrationError(
                    f"migration {version} hash mismatch: "
                    f"ledger {recorded} file {digest}"
                )
            continue
        if version != expected_next:
            raise MigrationError(
                f"refusing out-of-order migration {version}; expected {expected_next}"
            )
        script = path.read_text(encoding="utf-8")
        connection.executescript(script)
        connection.execute(
            "INSERT INTO schema_migration ("
            "version, migration_name, migration_sha256, applied_at_utc, "
            "tool_git_commit) VALUES (?, ?, ?, ?, ?)",
            (version, name, digest, when, commit),
        )
        connection.commit()
        expected_next = version + 1
        applied = applied_migrations(connection)
    connection.execute("PRAGMA foreign_keys = ON")


def schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    pragma_version = int(row[0]) if row is not None else 0
    applied = applied_migrations(connection)
    ledger = max(applied) if applied else 0
    if pragma_version != ledger:
        raise MigrationError(f"PRAGMA user_version {pragma_version} != ledger {ledger}")
    return ledger
