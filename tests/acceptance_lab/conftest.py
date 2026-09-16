"""Acceptance-lab test fixtures."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from tools.acceptance_lab.db import initialize


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "lab.sqlite3"


@pytest.fixture
def connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = initialize(db_path)
    try:
        yield conn
    finally:
        conn.close()
