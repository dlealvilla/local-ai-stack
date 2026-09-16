"""Deterministic reports from a fixed database."""

from __future__ import annotations

import sqlite3

from tools.acceptance_lab.import_historical import (
    WHEEL_SHA256,
    import_historical_nvidia,
)
from tools.acceptance_lab.report import campaign_report, render_json, render_markdown


def test_historical_import_and_deterministic_report(
    connection: sqlite3.Connection,
) -> None:
    ids = import_historical_nvidia(connection)
    first = campaign_report(
        connection, ids["campaign_id"], generated_at="2026-09-16T12:00:00.000Z"
    )
    second = campaign_report(
        connection, ids["campaign_id"], generated_at="2026-09-16T12:00:00.000Z"
    )
    assert render_json(first) == render_json(second)
    markdown = render_markdown(first)
    assert WHEEL_SHA256 in markdown
    assert "nvidia_physical_pass_apple_pending" in markdown
    assert first["campaign"]["historical_import"] == 1
    assert first["candidates"][0]["artifact_sha256"] == WHEEL_SHA256
    assert '"amd"' not in str(first["policy"].get("active_provider_set"))
    assert "nvidia" in str(first["policy"].get("active_provider_set"))
    servers = first["server_matrix"]
    assert servers[0]["requested_gpu_type"] is None
    assert servers[0]["assigned_gpu_type"] is None
    assert servers[0]["observed_gpu_model"] == (
        "NVIDIA RTX PRO 4500 Blackwell Server Edition"
    )
    assert all(
        "api_key" not in render_json(first).lower()
        or "synthetic" in render_json(first).lower()
        for _ in [0]
    )
    assert "PASSWORD=" not in markdown


def test_preflight_report_does_not_include_nvidia_wheel(
    connection: sqlite3.Connection,
) -> None:
    nvidia = import_historical_nvidia(connection)
    from tools.acceptance_lab.import_preflight import import_control_plane_preflight

    preflight = import_control_plane_preflight(connection)
    payload = campaign_report(
        connection,
        preflight["campaign_id"],
        generated_at="2026-09-16T12:00:00.000Z",
    )
    blob = render_json(payload)
    assert WHEEL_SHA256 not in blob
    assert nvidia["campaign_id"] != preflight["campaign_id"]
    assert payload["control_plane"][0]["balance_usd"] is None
