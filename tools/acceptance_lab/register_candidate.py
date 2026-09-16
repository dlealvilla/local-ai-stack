"""Register a local acceptance candidate without Pod mutation."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.paths import repository_root
from tools.acceptance_lab.store import fetch_one, insert_or_ignore, insert_row
from tools.acceptance_lab.timeutil import UTC, format_utc

NVIDIA_AMD_SETTINGS: tuple[tuple[str, str, Any, str], ...] = (
    ("observer", "provider_order", ["nvidia", "amd", "apple"], "native_accelerator.py"),
    (
        "observer",
        "implemented_providers",
        ["nvidia", "amd", "apple"],
        "native_accelerator.py",
    ),
    (
        "observer",
        "accepted_provider_target",
        ["nvidia", "amd"],
        "product_policy",
    ),
    ("nvidia", "source", "nvidia-smi-csv", "nvidia_accelerator.py"),
    ("nvidia", "timeout_seconds", 8.0, "nvidia_accelerator.py"),
    ("amd", "source", "amd-smi-json", "amd_accelerator.py"),
    ("amd", "list_argv", ["amd-smi", "list", "--json"], "amd_accelerator.py"),
    (
        "amd",
        "static_argv",
        ["amd-smi", "static", "--asic", "--vram", "--bus", "--json"],
        "amd_accelerator.py",
    ),
    ("amd", "timeout_seconds", 20.0, "amd_accelerator.py"),
    (
        "amd",
        "memory_unit_rule",
        "amd-smi-mb-mib-as-2-20-bytes-v1",
        "amd_accelerator.py",
    ),
    (
        "amd",
        "topology_rule",
        "mi300a-or-apu-unified-hbm-discrete-v1",
        "amd_accelerator.py",
    ),
    ("amd", "applicability", "linux", "amd_accelerator.py"),
    (
        "apple",
        "source",
        "system_profiler-SPDisplaysDataType-json",
        "apple_accelerator.py",
    ),
    ("apple", "timeout_seconds", 45.0, "apple_accelerator.py"),
    ("apple", "accepted", False, "product_policy"),
    ("accelerator", "max_devices", 64, "discover/contracts.py"),
    ("accelerator", "schema_version", 1, "discover/contracts.py"),
    ("schema", "discover.accelerator.observed", 1, "discover/events.py"),
    ("runtime", "requires_python", ">=3.11", "pyproject.machi.toml"),
    ("composition", "intel_implemented", False, "native_accelerator.py"),
    (
        "policy",
        "accepted_provider_policy",
        "nvidia_amd_active_apple_retained_intel_out",
        "product_policy",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(repository_root()))
    except ValueError:
        return path.name


def _git(root: Path, *arguments: str) -> str:
    finished = subprocess.run(
        ["git", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if finished.returncode != 0:
        return ""
    return finished.stdout.strip()


def capture_git_snapshot(
    connection: sqlite3.Connection,
    *,
    when: dt.datetime,
    notes: str = "",
    historical_import: bool = False,
) -> str:
    root = repository_root()
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(root, "rev-parse", "HEAD")
    if not head:
        raise RuntimeError("cannot capture git snapshot without HEAD")
    origin_ref = _git(root, "rev-parse", "--abbrev-ref", "@{u}")
    origin_commit = _git(root, "rev-parse", "@{u}") if origin_ref else ""
    porcelain = _git(root, "status", "--porcelain")
    tags = [
        item for item in _git(root, "tag", "--points-at", "HEAD").splitlines() if item
    ]
    snapshot_id = stable_id("git", head, branch, format_utc(when), notes)
    insert_or_ignore(
        connection,
        "git_snapshot",
        {
            "git_snapshot_id": snapshot_id,
            "captured_at_utc": format_utc(when),
            "repository_root": None,
            "branch": branch,
            "head_commit": head,
            "origin_ref": origin_ref or None,
            "origin_commit": origin_commit or None,
            "local_remote_equal": (
                int(head == origin_commit) if origin_commit else None
            ),
            "working_tree_clean": int(porcelain == ""),
            "tags_json": tags,
            "notes": notes,
            "historical_import": int(historical_import),
        },
    )
    return snapshot_id


def register_candidate(
    connection: sqlite3.Connection,
    *,
    wheel: Path,
    implementation_commit: str,
    branch: str,
    package_version: str,
    build_id: str,
    qualification_state: str,
    provider_set: Sequence[str],
    accepted_provider_target: Sequence[str],
    notes: str,
    settings: Sequence[tuple[str, str, Any, str]] = NVIDIA_AMD_SETTINGS,
    evidence_commit: str | None = None,
    git_snapshot_id: str | None = None,
    built_at: dt.datetime | None = None,
    when: dt.datetime | None = None,
    artifact_path: str | None = None,
) -> str:
    """Insert one exact wheel as a new candidate. Does not supersede history."""
    moment = when or dt.datetime.now(UTC)
    built = built_at or moment
    resolved = wheel.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"no wheel at {resolved}")
    digest = sha256_file(resolved)
    existing = fetch_one(
        connection,
        "SELECT candidate_id FROM candidate WHERE artifact_sha256 = ?",
        (digest,),
    )
    if existing is not None:
        return str(existing["candidate_id"])
    snapshot = git_snapshot_id or capture_git_snapshot(
        connection,
        when=moment,
        notes="candidate registration snapshot",
    )
    candidate_id = stable_id("cand", digest)
    insert_row(
        connection,
        "candidate",
        {
            "candidate_id": candidate_id,
            "created_at_utc": format_utc(moment),
            "git_snapshot_id": snapshot,
            "implementation_commit": implementation_commit,
            "evidence_commit": evidence_commit,
            "branch": branch,
            "package_version": package_version,
            "build_id": build_id,
            "artifact_filename": resolved.name,
            "artifact_sha256": digest,
            "artifact_size_bytes": resolved.stat().st_size,
            "artifact_path": artifact_path or _artifact_path(resolved),
            "built_at_utc": format_utc(built),
            "provider_set_json": list(provider_set),
            "accepted_provider_target_json": list(accepted_provider_target),
            "qualification_state": qualification_state,
            "historical_import": 0,
            "notes": notes,
        },
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
                "recorded_at_utc": format_utc(moment),
            },
        )
    return candidate_id


def record_local_gate_run(
    connection: sqlite3.Connection,
    *,
    campaign_id: str,
    candidate_id: str,
    scenario_name: str,
    status: str,
    gates: Sequence[Mapping[str, Any]],
    notes: str = "",
    when: dt.datetime | None = None,
) -> str:
    """Record local quality-gate results. No server_instance is created."""
    moment = when or dt.datetime.now(UTC)
    run_id = stable_id(
        "erun", campaign_id, candidate_id, scenario_name, format_utc(moment)
    )
    insert_row(
        connection,
        "experiment_run",
        {
            "experiment_run_id": run_id,
            "campaign_id": campaign_id,
            "candidate_id": candidate_id,
            "server_instance_id": None,
            "provider_target": "local",
            "scenario_name": scenario_name,
            "phase": "local_candidate_freeze",
            "retry_number": 0,
            "started_at_utc": format_utc(moment),
            "ended_at_utc": format_utc(moment),
            "status": status,
            "operator_kind": "cursor",
            "historical_import": 0,
            "notes": notes,
        },
    )
    for gate in gates:
        name = str(gate["name"])
        insert_row(
            connection,
            "test_result",
            {
                "test_result_id": stable_id("tres", run_id, name),
                "experiment_run_id": run_id,
                "test_name": name,
                "gate_name": str(gate.get("gate_name") or name),
                "started_at_utc": format_utc(moment),
                "ended_at_utc": format_utc(moment),
                "status": str(gate["status"]),
                "assertion_count": gate.get("assertion_count"),
                "failure_count": gate.get("failure_count", 0),
                "notes": str(gate.get("notes") or ""),
            },
        )
    return run_id


def record_checkpoint(
    connection: sqlite3.Connection,
    *,
    campaign_id: str,
    candidate_id: str,
    name: str,
    git_tag: str,
    git_commit: str,
    semantic_meaning: str,
    when: dt.datetime | None = None,
    notes: str = "",
) -> str:
    moment = when or dt.datetime.now(UTC)
    checkpoint_id = stable_id("chk", candidate_id, name, git_commit)
    insert_or_ignore(
        connection,
        "checkpoint",
        {
            "checkpoint_id": checkpoint_id,
            "campaign_id": campaign_id,
            "candidate_id": candidate_id,
            "checkpoint_name": name,
            "checkpoint_type": "local_candidate_ready",
            "semantic_meaning": semantic_meaning,
            "required_provider_set_json": ["nvidia", "amd"],
            "qualification_state": "local_candidate_ready",
            "git_tag": git_tag,
            "git_commit": git_commit,
            "created_at_utc": format_utc(moment),
            "historical_import": 0,
            "notes": notes,
        },
    )
    return checkpoint_id


def load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON document must be an object")
    return payload
