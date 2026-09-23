"""Migration initialize, idempotency, and hash stability."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from tools.acceptance_lab.db import (
    MigrationError,
    apply_migrations,
    initialize,
    schema_version,
)
from tools.acceptance_lab.jsonutil import sha256_bytes
from tools.acceptance_lab.paths import migrations_dir


def test_empty_db_applies_v1_once(connection: sqlite3.Connection) -> None:
    assert schema_version(connection) == 2
    rows = connection.execute(
        "SELECT version, migration_name, migration_sha256 FROM schema_migration "
        "ORDER BY version"
    ).fetchall()
    assert [int(row["version"]) for row in rows] == [1, 2]
    assert rows[0]["migration_name"] == "initial"
    assert rows[1]["migration_name"] == "empirical_case"
    expected = sha256_bytes((migrations_dir() / "0001_initial.sql").read_bytes())
    assert rows[0]["migration_sha256"] == expected


def test_repeated_initialize_is_idempotent(db_path: Path) -> None:
    first = initialize(db_path)
    count = int(first.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0])
    first.close()
    second = initialize(db_path)
    again = int(second.execute("SELECT COUNT(*) FROM schema_migration").fetchone()[0])
    tables = int(
        second.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'campaign'"
        ).fetchone()[0]
    )
    second.close()
    assert count == 2
    assert again == 2
    assert tables == 1


def test_hash_mismatch_fails(db_path: Path, tmp_path: Path) -> None:
    conn = initialize(db_path)
    conn.close()
    other = tmp_path / "migrations"
    other.mkdir()
    (other / "0001_initial.sql").write_text("-- tampered\nPRAGMA user_version = 1;\n")
    conn = initialize(db_path)
    with pytest.raises(MigrationError, match="hash mismatch"):
        apply_migrations(conn, migrations_path=other)
    conn.close()


def test_out_of_order_migration_fails(tmp_path: Path) -> None:
    db = tmp_path / "lab.sqlite3"
    conn = initialize(db)
    later = tmp_path / "migrations"
    later.mkdir()
    original = (migrations_dir() / "0001_initial.sql").read_text(encoding="utf-8")
    (later / "0001_initial.sql").write_text(original, encoding="utf-8")
    (later / "0003_skip.sql").write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(MigrationError, match="contiguous"):
        apply_migrations(conn, migrations_path=later)
    conn.close()
