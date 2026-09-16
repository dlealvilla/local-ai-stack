"""Cost estimate vs actual."""

from __future__ import annotations

import sqlite3

from tools.acceptance_lab.recording import estimated_cost_usd
from tools.acceptance_lab.store import insert_row


def test_estimated_cost_is_not_labeled_actual(connection: sqlite3.Connection) -> None:
    insert_row(
        connection,
        "campaign",
        {
            "campaign_id": "camp_cost",
            "name": "cost",
            "purpose": "cost modelling",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "status": "active",
            "provider_scope_json": {"nvidia": "ACTIVE"},
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_cost",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "artifact_sha256": "33" * 32,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "server_instance",
        {
            "server_instance_id": "srv_cost",
            "campaign_id": "camp_cost",
            "ownership_token": "own_cost",
            "runpod_pod_id": "pod_cost",
            "pod_name": "machi-acceptance-nvidia-cost",
            "target_provider": "nvidia",
            "hourly_price_usd": 0.24,
            "lifecycle_status": "terminated",
            "ownership_verified": 1,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "cost_record",
        {
            "cost_record_id": "cost_est",
            "campaign_id": "camp_cost",
            "candidate_id": "cand_cost",
            "server_instance_id": "srv_cost",
            "captured_at_utc": "2026-09-16T01:00:00.000Z",
            "hourly_price_usd": 0.24,
            "runtime_seconds": 3600,
            "estimated_cost_usd": estimated_cost_usd(0.24, 3600),
            "actual_cost_usd": None,
            "account_balance_usd": None,
            "value_source": "calculated",
            "currency": "USD",
        },
    )
    row = connection.execute(
        "SELECT estimated_cost_usd, actual_cost_usd, value_source FROM cost_record "
        "WHERE cost_record_id = 'cost_est'"
    ).fetchone()
    assert row["estimated_cost_usd"] == 0.24
    assert row["actual_cost_usd"] is None
    assert row["value_source"] == "calculated"
    summary = connection.execute(
        "SELECT estimated_cost_usd, actual_cost_usd FROM v_cost_summary "
        "WHERE campaign_id = 'camp_cost'"
    ).fetchone()
    assert summary["estimated_cost_usd"] == 0.24
    assert summary["actual_cost_usd"] is None
