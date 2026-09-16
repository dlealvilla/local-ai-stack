"""Candidate registration does not overwrite historical NVIDIA PASS."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.recording import record_campaign
from tools.acceptance_lab.register_candidate import (
    NVIDIA_AMD_SETTINGS,
    record_checkpoint,
    record_local_gate_run,
    register_candidate,
)
from tools.acceptance_lab.store import fetch_all, fetch_one, insert_row
from tools.acceptance_lab.timeutil import parse_utc


def test_new_candidate_does_not_supersede_historical(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    when = parse_utc("2026-09-16T12:00:00.000Z")
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_historical",
            "created_at_utc": "2026-09-15T00:00:00.000Z",
            "artifact_sha256": "aa" * 32,
            "qualification_state": "nvidia_physical_pass_apple_pending",
            "historical_import": 1,
            "notes": "historical NVIDIA candidate",
        },
    )
    wheel = tmp_path / "machi-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    campaign_id = stable_id("camp", "poc", "test")
    record_campaign(
        connection,
        campaign_id=campaign_id,
        name="NVIDIA+AMD planned POC",
        purpose="local candidate freeze",
        status="planned",
        when=when,
        provider_scope={"nvidia": "ACTIVE", "amd": "ACTIVE", "intel": "OUT"},
        notes="planned; no Pod created",
        historical_import=False,
    )
    candidate_id = register_candidate(
        connection,
        wheel=wheel,
        implementation_commit="abc123",
        evidence_commit=None,
        branch="m2/2.3-accelerator-discovery-nvidia-amd",
        package_version="0.1.0",
        build_id="build-test",
        qualification_state="local_candidate_ready_nvidia_amd",
        provider_set=["nvidia", "amd", "apple"],
        accepted_provider_target=["nvidia", "amd"],
        notes="new NVIDIA+AMD candidate",
        when=when,
        artifact_path="dist/machi/candidates/abc123/machi-0.1.0-py3-none-any.whl",
    )
    historical = fetch_one(
        connection,
        "SELECT * FROM candidate WHERE candidate_id = ?",
        ("cand_historical",),
    )
    assert historical is not None
    assert historical["superseded_by_candidate_id"] is None
    row = fetch_one(
        connection,
        "SELECT * FROM candidate WHERE candidate_id = ?",
        (candidate_id,),
    )
    assert row is not None
    assert row["artifact_sha256"] != "aa" * 32
    assert row["qualification_state"] == "local_candidate_ready_nvidia_amd"
    settings = fetch_all(
        connection,
        "SELECT setting_key FROM candidate_setting WHERE candidate_id = ?",
        (candidate_id,),
    )
    keys = {item["setting_key"] for item in settings}
    assert "memory_unit_rule" in keys
    assert "topology_rule" in keys
    assert "accepted_provider_target" in keys
    assert len(NVIDIA_AMD_SETTINGS) == len(settings)
    run_id = record_local_gate_run(
        connection,
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        scenario_name="local-gates",
        status="pass",
        gates=[{"name": "tests/machi", "status": "pass", "failure_count": 0}],
        when=when,
    )
    assert run_id.startswith("erun_")
    server = fetch_one(connection, "SELECT COUNT(*) AS n FROM server_instance")
    assert server is not None
    assert server["n"] == 0
    checkpoint_id = record_checkpoint(
        connection,
        campaign_id=campaign_id,
        candidate_id=candidate_id,
        name="machi-2.3-nvidia-amd-candidate",
        git_tag="checkpoint/machi-2.3-nvidia-amd-candidate-abc123",
        git_commit="abc123",
        semantic_meaning="local freeze only; not physical PASS",
        when=when,
    )
    assert checkpoint_id.startswith("chk_")
