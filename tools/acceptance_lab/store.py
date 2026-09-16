"""Parameterized inserts and reads. Table names are allowlisted."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any, cast

from tools.acceptance_lab.jsonutil import canonical_json
from tools.acceptance_lab.secrets import (
    SecretRejectedError,
    assert_mapping_safe,
    assert_text_safe,
)

_TABLES = frozenset(
    {
        "schema_migration",
        "campaign",
        "policy_snapshot",
        "git_snapshot",
        "candidate",
        "candidate_setting",
        "evidence_artifact",
        "control_plane_snapshot",
        "gpu_inventory_observation",
        "selection_event",
        "selection_candidate",
        "server_instance",
        "host_snapshot",
        "accelerator_device",
        "software_snapshot",
        "experiment_run",
        "probe_run",
        "machi_observation",
        "comparison",
        "test_result",
        "failure",
        "fix_iteration",
        "cost_record",
        "checkpoint",
    }
)
_COLUMN = frozenset(
    {
        "version",
        "migration_name",
        "migration_sha256",
        "applied_at_utc",
        "tool_git_commit",
        "campaign_id",
        "name",
        "purpose",
        "created_at_utc",
        "started_at_utc",
        "finished_at_utc",
        "status",
        "provider_scope_json",
        "notes",
        "historical_import",
        "policy_id",
        "policy_json",
        "policy_sha256",
        "active_provider_set",
        "max_nvidia_hourly_usd",
        "max_amd_hourly_usd",
        "max_session_usd",
        "max_daily_usd",
        "balance_floor_usd",
        "max_concurrent_pods",
        "max_pod_lifetime_seconds",
        "max_provision_retries",
        "max_nvidia_servers",
        "max_amd_servers",
        "allow_secure_cloud",
        "allow_community_cloud",
        "allow_network_volume",
        "hang_action",
        "success_teardown_action",
        "product_failure_teardown_action",
        "selection_strategy",
        "first_amd_target",
        "apple_policy",
        "intel_policy",
        "git_snapshot_id",
        "captured_at_utc",
        "repository_root",
        "branch",
        "head_commit",
        "origin_ref",
        "origin_commit",
        "local_remote_equal",
        "working_tree_clean",
        "tags_json",
        "candidate_id",
        "implementation_commit",
        "evidence_commit",
        "package_version",
        "build_id",
        "artifact_filename",
        "artifact_sha256",
        "artifact_size_bytes",
        "artifact_path",
        "built_at_utc",
        "provider_set_json",
        "accepted_provider_target_json",
        "qualification_state",
        "superseded_by_candidate_id",
        "candidate_setting_id",
        "setting_namespace",
        "setting_key",
        "value_json",
        "source",
        "recorded_at_utc",
        "evidence_artifact_id",
        "artifact_type",
        "path",
        "sha256",
        "size_bytes",
        "sanitized",
        "committed",
        "source_experiment_run_id",
        "source_probe_run_id",
        "control_plane_snapshot_id",
        "provider",
        "authentication_mode",
        "runpodctl_version",
        "mcp_connected",
        "cli_authenticated",
        "balance_exposed",
        "balance_usd",
        "existing_pod_count",
        "running_pod_count",
        "ssh_public_key_fingerprint",
        "observed_spend_usd",
        "observed_gpu_spend_usd",
        "raw_evidence_artifact_id",
        "gpu_inventory_observation_id",
        "gpu_type",
        "manufacturer",
        "cloud_type",
        "datacenter",
        "hourly_price_usd",
        "availability_state",
        "max_gpu_count",
        "eligible",
        "exclusion_reason",
        "selection_event_id",
        "policy_snapshot_id",
        "target_provider",
        "provider_target",
        "selected_at_utc",
        "algorithm_name",
        "algorithm_version",
        "random_seed",
        "selected_gpu_type",
        "selected_cloud_type",
        "selected_region",
        "selected_datacenter",
        "selected_hourly_price_usd",
        "selected_gpu_count",
        "selection_reason",
        "selection_candidate_id",
        "region",
        "coverage_score",
        "rank_or_order",
        "server_instance_id",
        "ownership_token",
        "runpod_pod_id",
        "pod_name",
        "requested_gpu_type",
        "assigned_gpu_type",
        "requested_gpu_count",
        "assigned_gpu_count",
        "image_or_template_id",
        "image_or_template_name",
        "requested_at_utc",
        "ready_at_utc",
        "ssh_ready_at_utc",
        "stopped_at_utc",
        "terminated_at_utc",
        "lifecycle_status",
        "ownership_verified",
        "host_snapshot_id",
        "os_family",
        "os_distribution",
        "os_version",
        "kernel_version",
        "architecture",
        "cpu_model",
        "cpu_physical_count",
        "cpu_logical_count",
        "physical_ram_bytes",
        "execution_memory_limit_bytes",
        "filesystem_type",
        "root_or_workspace_total_bytes",
        "root_or_workspace_available_bytes",
        "python_version",
        "container_context",
        "image_identity",
        "accelerator_device_id",
        "vendor",
        "tool_index",
        "provider_identity",
        "uuid",
        "model",
        "device_type",
        "memory_topology",
        "reported_memory_value",
        "reported_memory_unit",
        "canonical_memory_bytes",
        "driver_version",
        "vendor_cli_name",
        "vendor_cli_version",
        "visibility_scope",
        "software_snapshot_id",
        "pip_version",
        "machi_version",
        "machi_build_id",
        "candidate_sha256",
        "nvidia_smi_version",
        "nvidia_driver_version",
        "amd_smi_version",
        "rocm_version",
        "runtime_context",
        "additional_relevant_json",
        "experiment_run_id",
        "scenario_name",
        "phase",
        "retry_number",
        "predecessor_experiment_run_id",
        "ended_at_utc",
        "duration_ms",
        "operator_kind",
        "probe_run_id",
        "probe_name",
        "sanitized_argv_json",
        "execution_context",
        "exit_code",
        "timed_out",
        "result_classification",
        "stdout_evidence_artifact_id",
        "stderr_evidence_artifact_id",
        "machi_observation_id",
        "event_id",
        "event_occurred_at_utc",
        "observation_status",
        "observer",
        "provider_reports_json",
        "device_count",
        "observation_json",
        "accelerator_schema_version",
        "event_schema_version",
        "install_id",
        "install_run_id",
        "host_id_state",
        "comparison_id",
        "dimension",
        "expected_value_json",
        "actual_value_json",
        "unit",
        "comparison_rule",
        "matched",
        "absolute_delta",
        "relative_delta",
        "test_result_id",
        "test_name",
        "gate_name",
        "assertion_count",
        "failure_count",
        "failure_id",
        "classification",
        "severity",
        "detected_at_utc",
        "summary",
        "reproducible",
        "candidate_invalidated",
        "disposition",
        "closed_at_utc",
        "fix_iteration_id",
        "old_candidate_id",
        "fix_branch",
        "fix_commit",
        "description",
        "changed_modules_json",
        "local_tests_json",
        "local_result",
        "new_candidate_id",
        "cost_record_id",
        "runtime_seconds",
        "estimated_cost_usd",
        "actual_cost_usd",
        "account_balance_usd",
        "value_source",
        "currency",
        "checkpoint_id",
        "checkpoint_name",
        "checkpoint_type",
        "semantic_meaning",
        "required_provider_set_json",
        "git_tag",
        "git_commit",
    }
)

_JSON_COLUMNS = frozenset(
    {
        "provider_scope_json",
        "policy_json",
        "active_provider_set",
        "tags_json",
        "provider_set_json",
        "accepted_provider_target_json",
        "value_json",
        "sanitized_argv_json",
        "provider_reports_json",
        "observation_json",
        "expected_value_json",
        "actual_value_json",
        "changed_modules_json",
        "local_tests_json",
        "additional_relevant_json",
        "required_provider_set_json",
    }
)


def _prepare(values: Mapping[str, Any]) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    for key, value in values.items():
        if key not in _COLUMN:
            raise ValueError(f"unknown column {key}")
        if key == "ownership_token":
            prepared[key] = value
            continue
        if key in _JSON_COLUMNS:
            if isinstance(value, Mapping):
                assert_mapping_safe(value)
            if not isinstance(value, str):
                prepared[key] = canonical_json(value)
            else:
                assert_text_safe(value, what=key)
                prepared[key] = value
            continue
        if isinstance(value, str) and key in {"notes", "summary", "description"}:
            assert_text_safe(value, what=key)
        prepared[key] = value
    return prepared


def insert_row(
    connection: sqlite3.Connection, table: str, values: Mapping[str, Any]
) -> None:
    if table not in _TABLES:
        raise ValueError(f"unknown table {table}")
    prepared = _prepare(values)
    columns = list(prepared)
    placeholders = ", ".join("?" for _ in columns)
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    connection.execute(sql, [prepared[name] for name in columns])


def insert_or_ignore(
    connection: sqlite3.Connection, table: str, values: Mapping[str, Any]
) -> None:
    if table not in _TABLES:
        raise ValueError(f"unknown table {table}")
    prepared = _prepare(values)
    columns = list(prepared)
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    )
    connection.execute(sql, [prepared[name] for name in columns])


def fetch_one(
    connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()
) -> sqlite3.Row | None:
    if "INSERT" in sql.upper() or "UPDATE" in sql.upper() or "DELETE" in sql.upper():
        raise SecretRejectedError("fetch_one is read-only")
    return cast(sqlite3.Row | None, connection.execute(sql, params).fetchone())


def fetch_all(
    connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()
) -> list[sqlite3.Row]:
    if "INSERT" in sql.upper() or "UPDATE" in sql.upper() or "DELETE" in sql.upper():
        raise SecretRejectedError("fetch_all is read-only")
    return list(connection.execute(sql, params).fetchall())


def set_superseded(
    connection: sqlite3.Connection, *, old_candidate_id: str, new_candidate_id: str
) -> None:
    connection.execute(
        "UPDATE candidate SET superseded_by_candidate_id = ? WHERE candidate_id = ?",
        (new_candidate_id, old_candidate_id),
    )
