"""Secret rejection uses synthetic values only."""

from __future__ import annotations

import sqlite3

import pytest
from tools.acceptance_lab.secrets import SecretRejectedError, redact_text
from tools.acceptance_lab.store import insert_row


def test_secret_field_is_rejected(connection: sqlite3.Connection) -> None:
    with pytest.raises(SecretRejectedError):
        insert_row(
            connection,
            "campaign",
            {
                "campaign_id": "camp_secret",
                "name": "x",
                "purpose": "x",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
                "status": "planned",
                "provider_scope_json": {"api_key": "synthetic-test-value-not-real"},
                "historical_import": 0,
            },
        )


def test_secret_assignment_in_notes_is_rejected(connection: sqlite3.Connection) -> None:
    with pytest.raises(SecretRejectedError):
        insert_row(
            connection,
            "campaign",
            {
                "campaign_id": "camp_notes",
                "name": "x",
                "purpose": "x",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
                "status": "planned",
                "provider_scope_json": {"nvidia": "ACTIVE"},
                "notes": "PASSWORD=synthetic-test-value-not-real",
                "historical_import": 0,
            },
        )


def test_redaction_masks_assignments() -> None:
    text = redact_text("RUNPOD_API_KEY=synthetic-test-value-not-real")
    assert "synthetic-test-value-not-real" not in text
    assert "REDACTED" in text
