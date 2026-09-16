"""Foreign keys, uniqueness, and requested/assigned/observed separation."""

from __future__ import annotations

import sqlite3

import pytest
from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.store import insert_row, set_superseded


def _campaign(
    connection: sqlite3.Connection, campaign_id: str = "camp_test0000000001"
) -> None:
    insert_row(
        connection,
        "campaign",
        {
            "campaign_id": campaign_id,
            "name": "fk",
            "purpose": "integrity",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "status": "planned",
            "provider_scope_json": {"nvidia": "ACTIVE"},
            "historical_import": 0,
        },
    )


def test_foreign_keys_reject_orphan_policy(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "policy_snapshot",
            {
                "policy_id": "pol_orphan",
                "campaign_id": "camp_missing",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
                "policy_json": {},
                "policy_sha256": "abc",
                "active_provider_set": ["nvidia"],
                "max_nvidia_hourly_usd": 1.5,
                "max_amd_hourly_usd": 4.0,
                "max_session_usd": 40.0,
                "max_daily_usd": 80.0,
                "balance_floor_usd": 20.0,
                "max_concurrent_pods": 1,
                "max_pod_lifetime_seconds": 5400,
                "max_provision_retries": 3,
                "max_nvidia_servers": 3,
                "max_amd_servers": 3,
                "allow_secure_cloud": 1,
                "allow_community_cloud": 1,
                "allow_network_volume": 0,
                "hang_action": "stop_and_ask",
                "success_teardown_action": "terminate",
                "product_failure_teardown_action": "terminate",
                "selection_strategy": "coverage_driven_random",
                "first_amd_target": "MI300X",
                "apple_policy": "deferred",
                "intel_policy": "out_of_scope",
            },
        )


def test_candidate_sha_unique(connection: sqlite3.Connection) -> None:
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_aaaa",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "artifact_sha256": "a" * 64,
            "historical_import": 0,
        },
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "candidate",
            {
                "candidate_id": "cand_bbbb",
                "created_at_utc": "2026-09-16T00:00:01.000Z",
                "artifact_sha256": "a" * 64,
                "historical_import": 0,
            },
        )


def test_pod_id_ownership_unique(connection: sqlite3.Connection) -> None:
    _campaign(connection)
    row = {
        "campaign_id": "camp_test0000000001",
        "ownership_token": "own_one",
        "runpod_pod_id": "pod_abc",
        "pod_name": "machi-acceptance-nvidia-test",
        "target_provider": "nvidia",
        "lifecycle_status": "created",
        "ownership_verified": 1,
        "historical_import": 0,
    }
    insert_row(
        connection,
        "server_instance",
        {"server_instance_id": "srv_one", **row},
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "server_instance",
            {"server_instance_id": "srv_two", **row, "ownership_token": "own_two"},
        )


def test_requested_assigned_observed_stay_independent(
    connection: sqlite3.Connection,
) -> None:
    _campaign(connection, "camp_req")
    insert_row(
        connection,
        "server_instance",
        {
            "server_instance_id": "srv_mismatch",
            "campaign_id": "camp_req",
            "ownership_token": "own_m",
            "runpod_pod_id": "pod_mismatch",
            "pod_name": "machi-acceptance-amd-demo",
            "target_provider": "amd",
            "requested_gpu_type": "AMD Instinct MI300X OAM",
            "assigned_gpu_type": "AMD Instinct MI300A",
            "requested_gpu_count": 1,
            "assigned_gpu_count": 1,
            "lifecycle_status": "running",
            "ownership_verified": 1,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "host_snapshot",
        {
            "host_snapshot_id": "host_mismatch",
            "server_instance_id": "srv_mismatch",
            "captured_at_utc": "2026-09-16T00:00:00.000Z",
            "os_family": "linux",
        },
    )
    insert_row(
        connection,
        "accelerator_device",
        {
            "accelerator_device_id": "adev_mismatch",
            "host_snapshot_id": "host_mismatch",
            "captured_at_utc": "2026-09-16T00:00:00.000Z",
            "vendor": "amd",
            "model": "AMD Instinct MI250",
            "notes": "observed differs from assigned",
        },
    )
    row = connection.execute(
        "SELECT requested_gpu_type, assigned_gpu_type FROM server_instance "
        "WHERE server_instance_id = 'srv_mismatch'"
    ).fetchone()
    observed = connection.execute(
        "SELECT model FROM accelerator_device "
        "WHERE accelerator_device_id = 'adev_mismatch'"
    ).fetchone()
    assert row["requested_gpu_type"] == "AMD Instinct MI300X OAM"
    assert row["assigned_gpu_type"] == "AMD Instinct MI300A"
    assert observed["model"] == "AMD Instinct MI250"
    assert row["requested_gpu_type"] != row["assigned_gpu_type"]
    assert row["assigned_gpu_type"] != observed["model"]


def test_migration_version_unique(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO schema_migration ("
            "version, migration_name, migration_sha256, applied_at_utc, "
            "tool_git_commit) VALUES (1, 'dup', 'x', "
            "'2026-09-16T00:00:00.000Z', 'deadbeef')"
        )


def test_supersession_does_not_delete_old_candidate(
    connection: sqlite3.Connection,
) -> None:
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_old",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "artifact_sha256": "b" * 64,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_new",
            "created_at_utc": "2026-09-16T00:00:01.000Z",
            "artifact_sha256": "c" * 64,
            "historical_import": 0,
        },
    )
    set_superseded(connection, old_candidate_id="cand_old", new_candidate_id="cand_new")
    old = connection.execute(
        "SELECT superseded_by_candidate_id FROM candidate "
        "WHERE candidate_id = 'cand_old'"
    ).fetchone()
    assert old["superseded_by_candidate_id"] == "cand_new"
    assert connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0] == 2


def test_stable_ids_are_readable() -> None:
    assert stable_id("camp", "x").startswith("camp_")
    assert len(stable_id("cand", "y")) == 4 + 1 + 16


def test_restrict_delete_keeps_history(connection: sqlite3.Connection) -> None:
    _campaign(connection, "camp_del")
    insert_row(
        connection,
        "policy_snapshot",
        {
            "policy_id": "pol_del",
            "campaign_id": "camp_del",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "policy_json": {},
            "policy_sha256": "00",
            "active_provider_set": ["nvidia"],
            "max_nvidia_hourly_usd": 1.5,
            "max_amd_hourly_usd": 4.0,
            "max_session_usd": 40.0,
            "max_daily_usd": 80.0,
            "balance_floor_usd": 20.0,
            "max_concurrent_pods": 1,
            "max_pod_lifetime_seconds": 5400,
            "max_provision_retries": 3,
            "max_nvidia_servers": 3,
            "max_amd_servers": 3,
            "allow_secure_cloud": 1,
            "allow_community_cloud": 1,
            "allow_network_volume": 0,
            "hang_action": "stop_and_ask",
            "success_teardown_action": "terminate",
            "product_failure_teardown_action": "terminate",
            "selection_strategy": "coverage_driven_random",
            "first_amd_target": "MI300X",
            "apple_policy": "deferred",
            "intel_policy": "out_of_scope",
        },
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM campaign WHERE campaign_id = 'camp_del'")


def test_candidate_git_snapshot_fk(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "candidate",
            {
                "candidate_id": "cand_git",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
                "git_snapshot_id": "git_missing",
                "artifact_sha256": "d" * 64,
                "historical_import": 0,
            },
        )


def test_experiment_run_requires_campaign_and_candidate(
    connection: sqlite3.Connection,
) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "experiment_run",
            {
                "experiment_run_id": "run_orphan",
                "campaign_id": "camp_missing",
                "candidate_id": "cand_missing",
                "provider_target": "nvidia",
                "scenario_name": "x",
                "status": "planned",
                "historical_import": 0,
            },
        )


def test_probe_observation_comparison_failure_fix_checkpoint_fks(
    connection: sqlite3.Connection,
) -> None:
    _campaign(connection, "camp_chain")
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": "cand_chain",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "artifact_sha256": "e" * 64,
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "experiment_run",
        {
            "experiment_run_id": "run_chain",
            "campaign_id": "camp_chain",
            "candidate_id": "cand_chain",
            "provider_target": "nvidia",
            "scenario_name": "x",
            "status": "fail_product",
            "historical_import": 0,
        },
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "probe_run",
            {
                "probe_run_id": "probe_bad",
                "experiment_run_id": "run_missing",
                "probe_name": "x",
                "sanitized_argv_json": ["echo"],
                "timed_out": 0,
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "machi_observation",
            {
                "machi_observation_id": "mobs_bad",
                "experiment_run_id": "run_missing",
                "captured_at_utc": "2026-09-16T00:00:00.000Z",
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "comparison",
            {
                "comparison_id": "cmp_bad",
                "experiment_run_id": "run_missing",
                "dimension": "count",
                "matched": 0,
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "failure",
            {
                "failure_id": "fail_bad",
                "campaign_id": "camp_chain",
                "candidate_id": "cand_missing",
                "classification": "PRODUCT",
                "detected_at_utc": "2026-09-16T00:00:00.000Z",
                "summary": "orphan candidate",
            },
        )
    insert_row(
        connection,
        "failure",
        {
            "failure_id": "fail_ok",
            "campaign_id": "camp_chain",
            "candidate_id": "cand_chain",
            "experiment_run_id": "run_chain",
            "classification": "HARNESS",
            "detected_at_utc": "2026-09-16T00:00:00.000Z",
            "summary": "fixture harness failure",
        },
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "fix_iteration",
            {
                "fix_iteration_id": "fix_bad",
                "failure_id": "fail_missing",
                "old_candidate_id": "cand_chain",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "checkpoint",
            {
                "checkpoint_id": "chk_bad",
                "campaign_id": "camp_chain",
                "candidate_id": "cand_missing",
                "checkpoint_name": "x",
                "semantic_meaning": "x",
                "created_at_utc": "2026-09-16T00:00:00.000Z",
                "historical_import": 0,
            },
        )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "probe_run",
            {
                "probe_run_id": "probe_art",
                "experiment_run_id": "run_chain",
                "probe_name": "x",
                "sanitized_argv_json": ["echo"],
                "timed_out": 0,
                "stdout_evidence_artifact_id": "evid_missing",
            },
        )


def test_evidence_sha_path_unique(connection: sqlite3.Connection) -> None:
    row = {
        "artifact_type": "test_log",
        "path": "docs/machi/example.md",
        "sha256": "f" * 64,
        "captured_at_utc": "2026-09-16T00:00:00.000Z",
        "sanitized": 1,
        "committed": 1,
        "historical_import": 0,
    }
    insert_row(
        connection,
        "evidence_artifact",
        {"evidence_artifact_id": "evid_one", **row},
    )
    with pytest.raises(sqlite3.IntegrityError):
        insert_row(
            connection,
            "evidence_artifact",
            {"evidence_artifact_id": "evid_two", **row},
        )
