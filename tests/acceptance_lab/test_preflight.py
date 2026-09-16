"""Control-plane preflight import."""

from __future__ import annotations

import sqlite3

from tools.acceptance_lab.import_historical import import_historical_nvidia
from tools.acceptance_lab.import_preflight import import_control_plane_preflight


def test_preflight_import_is_idempotent_and_stores_no_balance(
    connection: sqlite3.Connection,
) -> None:
    first = import_control_plane_preflight(connection)
    second = import_control_plane_preflight(connection)
    assert first == second
    row = connection.execute(
        "SELECT mcp_connected, cli_authenticated, balance_exposed, balance_usd, "
        "existing_pod_count, running_pod_count FROM control_plane_snapshot "
        "WHERE control_plane_snapshot_id = ?",
        (first["control_plane_snapshot_id"],),
    ).fetchone()
    assert int(row["mcp_connected"]) == 1
    assert int(row["cli_authenticated"]) == 0
    assert int(row["balance_exposed"]) == 0
    assert row["balance_usd"] is None
    assert int(row["existing_pod_count"]) == 23
    assert int(row["running_pod_count"]) == 0
    mi300 = connection.execute(
        "SELECT hourly_price_usd, eligible, datacenter FROM gpu_inventory_observation "
        "WHERE gpu_type = 'AMD Instinct MI300X OAM'"
    ).fetchone()
    assert mi300["hourly_price_usd"] == 2.39
    assert int(mi300["eligible"]) == 1
    assert mi300["datacenter"] == "EU-RO-1"
    blob = connection.execute(
        "SELECT COUNT(*) FROM gpu_inventory_observation WHERE eligible = 1 "
        "AND manufacturer = 'NVIDIA'"
    ).fetchone()[0]
    assert int(blob) >= 10
    text = str(
        connection.execute(
            "SELECT notes FROM control_plane_snapshot WHERE campaign_id = ?",
            (first["campaign_id"],),
        ).fetchone()["notes"]
    )
    assert "rpa_" not in text
    assert "BEGIN OPENSSH" not in text


def test_historical_nvidia_import_idempotent(connection: sqlite3.Connection) -> None:
    first = import_historical_nvidia(connection)
    second = import_historical_nvidia(connection)
    assert first == second
    count = connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0]
    assert int(count) == 1
    providers = connection.execute(
        "SELECT provider_set_json FROM candidate"
    ).fetchone()["provider_set_json"]
    assert "intel" not in providers
    assert "amd" not in providers
    assert "nvidia" in providers
