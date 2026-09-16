"""Import historical NVIDIA physical acceptance from repository evidence.

Facts come from ``docs/machi/M2-2.3-NVIDIA-PHYSICAL.md`` and
``docs/machi/M2-2.3-LOCAL.md``. Missing fields stay NULL.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.jsonutil import sha256_text
from tools.acceptance_lab.policy import HISTORICAL_NVIDIA_PHYSICAL_POLICY
from tools.acceptance_lab.recording import record_campaign, record_policy
from tools.acceptance_lab.store import insert_or_ignore
from tools.acceptance_lab.timeutil import UTC, format_utc

WHEEL_SHA256 = "351cee818c2a41ed84b3c8708e957c950c3676e555e1c32aa1793bfeec1a99f3"
IMPLEMENTATION_COMMIT = "1c774a0ca49d318d1cb85fe8b5263f4aebd84774"
EVIDENCE_COMMIT = "636dfa0e3bfe91f5620ce1c4667d9f7026e3e1b7"
LOCAL_EVIDENCE_COMMIT = "56bd66bcecec3f633b9b9452dd6689baa6b66780"
CANONICAL_MACHI = "1db764607a5806d080cc138932002760bad113ad"
BUILD_ID = "0.1.0+1c774a0ca49d"
ARTIFACT_NAME = "machi-0.1.0-py3-none-any.whl"
ARTIFACT_SIZE = 77398
NVIDIA_UUID = "GPU-7bf409d1-5dcd-39f8-b9cb-ecb1db83c8cd"
NVIDIA_MODEL = "NVIDIA RTX PRO 4500 Blackwell Server Edition"
MEMORY_MIB = 32623
MEMORY_BYTES = MEMORY_MIB * 1024 * 1024
PHYSICAL_AT = dt.datetime(2026, 9, 15, 6, 44, 11, tzinfo=UTC)
IMPL_AT = dt.datetime(2026, 9, 15, 5, 50, 8, tzinfo=UTC)
SOURCE_DOC = "docs/machi/M2-2.3-NVIDIA-PHYSICAL.md"

PROVIDER_SCOPE = {
    "nvidia": "ACTIVE",
    "amd": "not_implemented_on_this_candidate",
    "intel": "OUT",
    "apple": "CODE_RETAINED_NOT_ACCEPTED_PHYSICAL_DEFERRED",
}


def import_historical_nvidia(connection: sqlite3.Connection) -> dict[str, str]:
    campaign_id = stable_id("camp", "historical-nvidia-physical", IMPLEMENTATION_COMMIT)
    git_id = stable_id("git", EVIDENCE_COMMIT)
    impl_git_id = stable_id("git", IMPLEMENTATION_COMMIT)
    candidate_id = stable_id("cand", WHEEL_SHA256)
    server_id = stable_id("srv", "historical-linux-nvidia", NVIDIA_UUID)
    host_id = stable_id("host", server_id, "physical")
    device_id = stable_id("adev", NVIDIA_UUID)
    run_id = stable_id("run", campaign_id, "nvidia-physical")
    probe_smi = stable_id("probe", run_id, "nvidia-smi")
    probe_machi = stable_id("probe", run_id, "machi-discover-accelerator")
    obs_id = stable_id("mobs", "evt_6c18a141e1dffb33")
    evid_id = stable_id("evid", SOURCE_DOC)
    chk_id = stable_id("chk", "historical-nvidia-physical-pass", WHEEL_SHA256)
    token = stable_id("own", "historical-not-runpod", NVIDIA_UUID)

    record_campaign(
        connection,
        campaign_id=campaign_id,
        name="historical-nvidia-physical-1c774a0",
        purpose="Backfill repository NVIDIA physical acceptance of wheel 351cee81",
        status="completed",
        when=PHYSICAL_AT,
        started=PHYSICAL_AT,
        finished=PHYSICAL_AT,
        provider_scope=PROVIDER_SCOPE,
        notes=(
            "Imported from repository evidence. This campaign did not use the "
            "RunPod acceptance lab. Pod ID, price, cloud, and datacenter are "
            "unknown and left NULL. Checkpoint A was not created."
        ),
        historical_import=True,
    )
    record_policy(
        connection,
        campaign_id=campaign_id,
        policy=HISTORICAL_NVIDIA_PHYSICAL_POLICY,
        when=PHYSICAL_AT,
        historical_import=True,
    )
    insert_or_ignore(
        connection,
        "git_snapshot",
        {
            "git_snapshot_id": impl_git_id,
            "captured_at_utc": format_utc(IMPL_AT),
            "branch": "m2/2.3-accelerator-discovery-nvidia-apple",
            "head_commit": IMPLEMENTATION_COMMIT,
            "origin_ref": "origin/m2/2.3-accelerator-discovery-nvidia-apple",
            "origin_commit": None,
            "local_remote_equal": None,
            "working_tree_clean": 1,
            "tags_json": [],
            "notes": "Implementation commit for the 351cee81 wheel.",
            "historical_import": 1,
        },
    )
    insert_or_ignore(
        connection,
        "git_snapshot",
        {
            "git_snapshot_id": git_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "branch": "m2/2.3-accelerator-discovery-nvidia-apple",
            "head_commit": EVIDENCE_COMMIT,
            "origin_ref": "origin/m2/2.3-accelerator-discovery-nvidia-apple",
            "origin_commit": EVIDENCE_COMMIT,
            "local_remote_equal": 1,
            "working_tree_clean": 1,
            "tags_json": [],
            "notes": (
                f"Physical evidence commit. Local acceptance also recorded at "
                f"{LOCAL_EVIDENCE_COMMIT}. Canonical machi remains {CANONICAL_MACHI}."
            ),
            "historical_import": 1,
        },
    )
    insert_or_ignore(
        connection,
        "evidence_artifact",
        {
            "evidence_artifact_id": evid_id,
            "artifact_type": "acceptance_summary",
            "path": SOURCE_DOC,
            "sha256": sha256_text(SOURCE_DOC + WHEEL_SHA256),
            "size_bytes": None,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "sanitized": 1,
            "committed": 1,
            "notes": (
                "Repository markdown evidence; content hash is of path+SHA identity."
            ),
            "historical_import": 1,
        },
    )
    insert_or_ignore(
        connection,
        "candidate",
        {
            "candidate_id": candidate_id,
            "created_at_utc": format_utc(IMPL_AT),
            "git_snapshot_id": impl_git_id,
            "implementation_commit": IMPLEMENTATION_COMMIT,
            "evidence_commit": EVIDENCE_COMMIT,
            "branch": "m2/2.3-accelerator-discovery-nvidia-apple",
            "package_version": "0.1.0",
            "build_id": BUILD_ID,
            "artifact_filename": ARTIFACT_NAME,
            "artifact_sha256": WHEEL_SHA256,
            "artifact_size_bytes": ARTIFACT_SIZE,
            "artifact_path": (
                f"dist/machi/candidates/{IMPLEMENTATION_COMMIT}/{ARTIFACT_NAME}"
            ),
            "built_at_utc": format_utc(IMPL_AT),
            "provider_set_json": ["nvidia", "apple"],
            "accepted_provider_target_json": ["nvidia", "apple"],
            "qualification_state": "nvidia_physical_pass_apple_pending",
            "historical_import": 1,
            "notes": (
                "Exact combined NVIDIA+Apple candidate. Does not qualify a later "
                "NVIDIA+AMD wheel. AMD and Intel were not implemented on this artifact."
            ),
        },
    )
    settings = (
        ("observer", "provider_order", ["nvidia", "apple"], "native_accelerator.py"),
        ("nvidia", "timeout_seconds", 8.0, "nvidia_accelerator.py"),
        ("apple", "timeout_seconds", 45.0, "apple_accelerator.py"),
        ("accelerator", "max_devices", 64, "discover/contracts.py"),
        ("accelerator", "parser_source", "nvidia-smi-csv", "nvidia_accelerator.py"),
        ("schema", "accelerator_observation", 1, "discover/contracts.py"),
        ("schema", "discover.accelerator.observed", 1, "discover/events.py"),
        ("runtime", "requires_python", ">=3.11", "pyproject.machi.toml"),
        ("composition", "apple_retained", True, "native_accelerator.py"),
        ("composition", "amd_implemented", False, "source_tree_636dfa0"),
        ("composition", "intel_implemented", False, "source_tree_636dfa0"),
    )
    for namespace, key, value, source in settings:
        insert_or_ignore(
            connection,
            "candidate_setting",
            {
                "candidate_setting_id": stable_id("cset", candidate_id, namespace, key),
                "candidate_id": candidate_id,
                "setting_namespace": namespace,
                "setting_key": key,
                "value_json": value,
                "source": source,
                "recorded_at_utc": format_utc(IMPL_AT),
            },
        )
    insert_or_ignore(
        connection,
        "server_instance",
        {
            "server_instance_id": server_id,
            "campaign_id": campaign_id,
            "ownership_token": token,
            "runpod_pod_id": None,
            "pod_name": None,
            "target_provider": "nvidia",
            "requested_gpu_type": None,
            "assigned_gpu_type": None,
            "requested_gpu_count": None,
            "assigned_gpu_count": 1,
            "cloud_type": None,
            "region": None,
            "datacenter": None,
            "image_or_template_id": None,
            "image_or_template_name": None,
            "hourly_price_usd": None,
            "lifecycle_status": "historical",
            "ownership_verified": 0,
            "historical_import": 1,
            "notes": (
                "Disposable Linux/NVIDIA host hostname 63429c2e22fb from physical "
                "evidence. Not identified as a RunPod Pod. SSH target omitted."
            ),
        },
    )
    insert_or_ignore(
        connection,
        "host_snapshot",
        {
            "host_snapshot_id": host_id,
            "server_instance_id": server_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "os_family": "linux",
            "os_distribution": "Ubuntu",
            "os_version": "24.04.3 LTS",
            "kernel_version": "6.8.0-138-generic",
            "architecture": "x86_64",
            "cpu_model": None,
            "cpu_physical_count": None,
            "cpu_logical_count": None,
            "physical_ram_bytes": 811121803264,
            "execution_memory_limit_bytes": None,
            "filesystem_type": "overlayfs",
            "root_or_workspace_total_bytes": None,
            "root_or_workspace_available_bytes": None,
            "python_version": "3.12.3",
            "container_context": "isolated venv on overlayfs /tmp",
            "image_identity": None,
            "notes": "~30G on /; exact root bytes not recorded.",
        },
    )
    insert_or_ignore(
        connection,
        "accelerator_device",
        {
            "accelerator_device_id": device_id,
            "host_snapshot_id": host_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "vendor": "nvidia",
            "tool_index": 0,
            "provider_identity": NVIDIA_UUID,
            "uuid": NVIDIA_UUID,
            "model": NVIDIA_MODEL,
            "device_type": "discrete_gpu",
            "memory_topology": "discrete",
            "reported_memory_value": str(MEMORY_MIB),
            "reported_memory_unit": "MiB",
            "canonical_memory_bytes": MEMORY_BYTES,
            "driver_version": "580.178.04",
            "vendor_cli_name": "nvidia-smi",
            "vendor_cli_version": None,
            "visibility_scope": "visible_to_nvidia_smi",
            "evidence_artifact_id": evid_id,
            "notes": "/usr/bin/nvidia-smi CSV; Persistence-M On; MIG Disabled.",
        },
    )
    insert_or_ignore(
        connection,
        "software_snapshot",
        {
            "software_snapshot_id": stable_id("sw", server_id),
            "server_instance_id": server_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "python_version": "3.12.3",
            "pip_version": None,
            "machi_version": "0.1.0",
            "machi_build_id": BUILD_ID,
            "candidate_sha256": WHEEL_SHA256,
            "nvidia_smi_version": None,
            "nvidia_driver_version": "580.178.04",
            "amd_smi_version": None,
            "rocm_version": None,
            "image_identity": None,
            "runtime_context": "wheel-only venv; PYTHONPATH empty; kultrun absent",
            "additional_relevant_json": {
                "freeze": ["machi"],
                "cuda_installed_by_harness": False,
            },
        },
    )
    insert_or_ignore(
        connection,
        "experiment_run",
        {
            "experiment_run_id": run_id,
            "campaign_id": campaign_id,
            "candidate_id": candidate_id,
            "server_instance_id": server_id,
            "provider_target": "nvidia",
            "scenario_name": "nvidia-physical-discover",
            "phase": "physical",
            "retry_number": 0,
            "started_at_utc": format_utc(PHYSICAL_AT),
            "ended_at_utc": format_utc(PHYSICAL_AT),
            "duration_ms": None,
            "status": "pass",
            "operator_kind": "historical_import",
            "historical_import": 1,
            "notes": "NVIDIA physical PASS; Apple physical not executed.",
        },
    )
    insert_or_ignore(
        connection,
        "probe_run",
        {
            "probe_run_id": probe_smi,
            "experiment_run_id": run_id,
            "probe_name": "nvidia-smi query",
            "sanitized_argv_json": [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            "execution_context": "host",
            "started_at_utc": format_utc(PHYSICAL_AT),
            "ended_at_utc": format_utc(PHYSICAL_AT),
            "duration_ms": None,
            "exit_code": 0,
            "timed_out": 0,
            "result_classification": "observed",
            "notes": (f"0, {NVIDIA_UUID}, {NVIDIA_MODEL}, {MEMORY_MIB}"),
        },
    )
    insert_or_ignore(
        connection,
        "probe_run",
        {
            "probe_run_id": probe_machi,
            "experiment_run_id": run_id,
            "probe_name": "machi discover accelerator",
            "sanitized_argv_json": ["machi", "discover", "accelerator"],
            "execution_context": "isolated_venv",
            "started_at_utc": format_utc(PHYSICAL_AT),
            "ended_at_utc": format_utc(PHYSICAL_AT),
            "duration_ms": None,
            "exit_code": 0,
            "timed_out": 0,
            "result_classification": "observed",
            "notes": "Generic observer; NVIDIA observed; Apple not_applicable.",
        },
    )
    observation = {
        "status": "normalized",
        "observer": "native",
        "device_count": 1,
        "providers": [
            {"provider": "nvidia", "status": "observed", "device_count": 1},
            {"provider": "apple", "status": "not_applicable"},
        ],
        "device": {
            "vendor": "nvidia",
            "model": NVIDIA_MODEL,
            "identity": NVIDIA_UUID,
            "device_type": "discrete_gpu",
            "memory_topology": "discrete",
            "memory_total_bytes": MEMORY_BYTES,
            "ordinal": 0,
        },
    }
    insert_or_ignore(
        connection,
        "machi_observation",
        {
            "machi_observation_id": obs_id,
            "experiment_run_id": run_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "event_id": "evt_6c18a141e1dffb33",
            "event_occurred_at_utc": None,
            "observation_status": "normalized",
            "observer": "native",
            "provider_reports_json": observation["providers"],
            "device_count": 1,
            "observation_json": observation,
            "accelerator_schema_version": "accelerator_observation@1",
            "event_schema_version": "discover.accelerator.observed@1",
            "install_id": "inst_53e8843314ffb19a",
            "install_run_id": "irun_e5a76470dcd294e7",
            "host_id_state": "unresolved",
            "evidence_artifact_id": evid_id,
        },
    )
    comparisons = (
        ("device_count", 1, 1, "count", None),
        ("model", NVIDIA_MODEL, NVIDIA_MODEL, "exact", None),
        ("identity", NVIDIA_UUID, NVIDIA_UUID, "exact", None),
        ("memory_bytes", MEMORY_BYTES, MEMORY_BYTES, "exact_integer", "bytes"),
        ("topology", "discrete", "discrete", "exact", None),
        ("nvidia_provider_status", "observed", "observed", "exact", None),
        ("apple_provider_status", "not_applicable", "not_applicable", "exact", None),
    )
    for dimension, expected, actual, rule, unit in comparisons:
        insert_or_ignore(
            connection,
            "comparison",
            {
                "comparison_id": stable_id("cmp", run_id, dimension),
                "experiment_run_id": run_id,
                "machi_observation_id": obs_id,
                "accelerator_device_id": device_id,
                "dimension": dimension,
                "expected_value_json": expected,
                "actual_value_json": actual,
                "unit": unit,
                "comparison_rule": rule,
                "matched": 1,
            },
        )
    insert_or_ignore(
        connection,
        "test_result",
        {
            "test_result_id": stable_id("tres", run_id, "nvidia-physical"),
            "experiment_run_id": run_id,
            "test_name": "nvidia-physical-pass",
            "gate_name": "M2.3 NVIDIA physical",
            "started_at_utc": format_utc(PHYSICAL_AT),
            "ended_at_utc": format_utc(PHYSICAL_AT),
            "status": "pass",
            "assertion_count": len(comparisons),
            "failure_count": 0,
            "evidence_artifact_id": evid_id,
            "notes": "Apple physical PENDING; Checkpoint A not created.",
        },
    )
    insert_or_ignore(
        connection,
        "cost_record",
        {
            "cost_record_id": stable_id("cost", campaign_id, "unavailable"),
            "campaign_id": campaign_id,
            "candidate_id": candidate_id,
            "server_instance_id": server_id,
            "captured_at_utc": format_utc(PHYSICAL_AT),
            "hourly_price_usd": None,
            "runtime_seconds": None,
            "estimated_cost_usd": None,
            "actual_cost_usd": None,
            "account_balance_usd": None,
            "value_source": "unavailable",
            "currency": "USD",
            "notes": "Historical host cost was not recorded in repository evidence.",
        },
    )
    insert_or_ignore(
        connection,
        "checkpoint",
        {
            "checkpoint_id": chk_id,
            "campaign_id": campaign_id,
            "candidate_id": candidate_id,
            "checkpoint_name": "historical-nvidia-physical-pass",
            "checkpoint_type": "physical_provider",
            "semantic_meaning": (
                "The exact 351cee81 NVIDIA+Apple candidate physically observed "
                "one discrete NVIDIA GPU as integer bytes. This is not Checkpoint A "
                "and does not qualify a later NVIDIA+AMD candidate."
            ),
            "required_provider_set_json": ["nvidia"],
            "qualification_state": "nvidia_physical_pass_apple_pending",
            "git_tag": None,
            "git_commit": EVIDENCE_COMMIT,
            "created_at_utc": format_utc(PHYSICAL_AT),
            "historical_import": 1,
            "notes": "Checkpoint A was not created (2026-09-15).",
        },
    )
    connection.commit()
    return {
        "campaign_id": campaign_id,
        "candidate_id": candidate_id,
        "experiment_run_id": run_id,
    }
