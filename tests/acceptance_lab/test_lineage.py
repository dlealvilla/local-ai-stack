"""Failure → fix → replacement candidate lineage."""

from __future__ import annotations

import sqlite3

from tools.acceptance_lab.store import insert_row, set_superseded


def test_fix_lineage_view(connection: sqlite3.Connection) -> None:
    insert_row(
        connection,
        "campaign",
        {
            "campaign_id": "camp_fix",
            "name": "lineage",
            "purpose": "failure chain",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "status": "active",
            "provider_scope_json": {"nvidia": "ACTIVE", "amd": "ACTIVE"},
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_a",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "artifact_sha256": "11" * 32,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_b",
            "created_at_utc": "2026-09-16T01:00:00.000Z",
            "artifact_sha256": "22" * 32,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "experiment_run",
        {
            "experiment_run_id": "run_a",
            "campaign_id": "camp_fix",
            "candidate_id": "cand_a",
            "provider_target": "amd",
            "scenario_name": "physical",
            "retry_number": 0,
            "status": "fail_product",
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "failure",
        {
            "failure_id": "fail_a",
            "campaign_id": "camp_fix",
            "candidate_id": "cand_a",
            "experiment_run_id": "run_a",
            "provider": "amd",
            "classification": "PRODUCT",
            "detected_at_utc": "2026-09-16T00:30:00.000Z",
            "summary": "synthetic product failure for lineage fixture",
            "candidate_invalidated": 1,
            "disposition": "fixed",
        },
    )
    insert_row(
        connection,
        "fix_iteration",
        {
            "fix_iteration_id": "fix_a",
            "failure_id": "fail_a",
            "old_candidate_id": "cand_a",
            "fix_branch": "m2/2.3-accelerator-discovery-nvidia-amd",
            "fix_commit": "abc123",
            "created_at_utc": "2026-09-16T00:45:00.000Z",
            "description": "smallest correct parser fix",
            "changed_modules_json": ["src/machi/adapters/discover/amd_accelerator.py"],
            "local_tests_json": ["tests/machi/test_amd_accelerator.py"],
            "local_result": "pass",
            "new_candidate_id": "cand_b",
            "closed_at_utc": "2026-09-16T01:00:00.000Z",
        },
    )
    set_superseded(connection, old_candidate_id="cand_a", new_candidate_id="cand_b")
    connection.commit()
    row = connection.execute(
        "SELECT old_artifact_sha256, new_artifact_sha256, fix_commit, classification "
        "FROM v_fix_lineage WHERE fix_iteration_id = 'fix_a'"
    ).fetchone()
    assert row["old_artifact_sha256"] == "11" * 32
    assert row["new_artifact_sha256"] == "22" * 32
    assert row["fix_commit"] == "abc123"
    assert row["classification"] == "PRODUCT"
