"""Deterministic sanitized Markdown and JSON reports."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from tools.acceptance_lab.jsonutil import canonical_json
from tools.acceptance_lab.paths import repository_root
from tools.acceptance_lab.store import fetch_all, fetch_one

_EVIDENCE_SQL = """
SELECT * FROM evidence_artifact
WHERE evidence_artifact_id IN (
    SELECT raw_evidence_artifact_id FROM control_plane_snapshot
    WHERE campaign_id = ? AND raw_evidence_artifact_id IS NOT NULL
    UNION
    SELECT evidence_artifact_id FROM machi_observation
    WHERE evidence_artifact_id IS NOT NULL
      AND experiment_run_id IN (
          SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?
      )
    UNION
    SELECT evidence_artifact_id FROM test_result
    WHERE evidence_artifact_id IS NOT NULL
      AND experiment_run_id IN (
          SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?
      )
    UNION
    SELECT evidence_artifact_id FROM failure
    WHERE campaign_id = ? AND evidence_artifact_id IS NOT NULL
    UNION
    SELECT stdout_evidence_artifact_id FROM probe_run
    WHERE stdout_evidence_artifact_id IS NOT NULL
      AND experiment_run_id IN (
          SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?
      )
    UNION
    SELECT stderr_evidence_artifact_id FROM probe_run
    WHERE stderr_evidence_artifact_id IS NOT NULL
      AND experiment_run_id IN (
          SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?
      )
    UNION
    SELECT adev.evidence_artifact_id FROM accelerator_device AS adev
    JOIN host_snapshot AS hs ON hs.host_snapshot_id = adev.host_snapshot_id
    JOIN server_instance AS srv ON srv.server_instance_id = hs.server_instance_id
    WHERE srv.campaign_id = ? AND adev.evidence_artifact_id IS NOT NULL
    UNION
    SELECT evidence_artifact_id FROM evidence_artifact
    WHERE source_experiment_run_id IN (
        SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?
    )
)
ORDER BY evidence_artifact_id
"""


def _sanitize(value: str, *, repo: Path) -> str:
    home = str(Path.home())
    text = value.replace(home, "~")
    return text.replace(str(repo), "<repo>")


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def campaign_report(
    connection: sqlite3.Connection,
    campaign_id: str,
    *,
    repo: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = repo or repository_root()
    campaign = fetch_one(
        connection, "SELECT * FROM campaign WHERE campaign_id = ?", (campaign_id,)
    )
    if campaign is None:
        raise KeyError(f"unknown campaign {campaign_id}")
    policy = fetch_one(
        connection,
        "SELECT * FROM policy_snapshot WHERE campaign_id = ? "
        "ORDER BY created_at_utc LIMIT 1",
        (campaign_id,),
    )
    summary = fetch_one(
        connection,
        "SELECT * FROM v_campaign_summary WHERE campaign_id = ?",
        (campaign_id,),
    )
    payload: dict[str, Any] = {
        "generated_at_utc": generated_at,
        "campaign": _row_dict(campaign),
        "summary": _row_dict(summary) if summary is not None else {},
        "policy": _row_dict(policy) if policy is not None else {},
        "candidates": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT DISTINCT cand.* FROM candidate AS cand "
                "JOIN experiment_run AS er ON er.candidate_id = cand.candidate_id "
                "WHERE er.campaign_id = ? ORDER BY cand.candidate_id",
                (campaign_id,),
            )
        ],
        "git_snapshots": [
            _sanitize_row(_row_dict(row), root)
            for row in fetch_all(
                connection,
                "SELECT DISTINCT g.* FROM git_snapshot AS g "
                "JOIN candidate AS cand ON cand.git_snapshot_id = g.git_snapshot_id "
                "JOIN experiment_run AS er ON er.candidate_id = cand.candidate_id "
                "WHERE er.campaign_id = ? ORDER BY g.git_snapshot_id",
                (campaign_id,),
            )
        ],
        "control_plane": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM control_plane_snapshot WHERE campaign_id = ? "
                "ORDER BY captured_at_utc, control_plane_snapshot_id",
                (campaign_id,),
            )
        ],
        "gpu_inventory": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT g.* FROM gpu_inventory_observation AS g "
                "JOIN control_plane_snapshot AS c "
                "ON c.control_plane_snapshot_id = g.control_plane_snapshot_id "
                "WHERE c.campaign_id = ? ORDER BY g.gpu_type, g.cloud_type",
                (campaign_id,),
            )
        ],
        "server_matrix": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM v_server_matrix WHERE campaign_id = ? "
                "ORDER BY server_instance_id",
                (campaign_id,),
            )
        ],
        "experiments": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM experiment_run WHERE campaign_id = ? "
                "ORDER BY experiment_run_id",
                (campaign_id,),
            )
        ],
        "probes": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT p.* FROM probe_run AS p "
                "JOIN experiment_run AS er "
                "ON er.experiment_run_id = p.experiment_run_id "
                "WHERE er.campaign_id = ? ORDER BY p.probe_run_id",
                (campaign_id,),
            )
        ],
        "vendor_truth": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT adev.* FROM accelerator_device AS adev "
                "JOIN host_snapshot AS hs "
                "ON hs.host_snapshot_id = adev.host_snapshot_id "
                "JOIN server_instance AS srv "
                "ON srv.server_instance_id = hs.server_instance_id "
                "WHERE srv.campaign_id = ? ORDER BY adev.accelerator_device_id",
                (campaign_id,),
            )
        ],
        "machi_observations": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT m.* FROM machi_observation AS m "
                "JOIN experiment_run AS er "
                "ON er.experiment_run_id = m.experiment_run_id "
                "WHERE er.campaign_id = ? ORDER BY m.machi_observation_id",
                (campaign_id,),
            )
        ],
        "comparisons": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM v_candidate_comparisons WHERE experiment_run_id IN "
                "(SELECT experiment_run_id FROM experiment_run WHERE campaign_id = ?) "
                "ORDER BY candidate_id, dimension",
                (campaign_id,),
            )
        ],
        "failures": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM v_failure_history WHERE campaign_id = ? "
                "ORDER BY failure_id",
                (campaign_id,),
            )
        ],
        "fix_lineage": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT v.* FROM v_fix_lineage AS v "
                "JOIN failure AS f ON f.failure_id = v.failure_id "
                "WHERE f.campaign_id = ? ORDER BY v.fix_iteration_id",
                (campaign_id,),
            )
        ],
        "costs": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM v_cost_summary WHERE campaign_id = ? "
                "ORDER BY provider, artifact_sha256, value_source",
                (campaign_id,),
            )
        ],
        "checkpoints": [
            _row_dict(row)
            for row in fetch_all(
                connection,
                "SELECT * FROM checkpoint WHERE campaign_id = ? ORDER BY checkpoint_id",
                (campaign_id,),
            )
        ],
        "evidence": [
            _sanitize_row(_row_dict(row), root)
            for row in fetch_all(
                connection,
                _EVIDENCE_SQL,
                (campaign_id,) * 8,
            )
        ],
    }
    return payload


def _sanitize_row(row: dict[str, Any], repo: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, str) and (
            key.endswith("path") or key in {"repository_root", "path"}
        ):
            out[key] = _sanitize(value, repo=repo)
        else:
            out[key] = value
    return out


def render_markdown(payload: dict[str, Any]) -> str:
    campaign = payload["campaign"]
    summary = payload["summary"]
    lines = [
        f"# Acceptance lab report — {campaign.get('name', '')}",
        "",
        f"- campaign_id: `{campaign.get('campaign_id')}`",
        f"- status: `{campaign.get('status')}`",
        f"- historical_import: `{campaign.get('historical_import')}`",
        f"- purpose: {campaign.get('purpose')}",
        f"- candidate_count: {summary.get('candidate_count')}",
        f"- physical_run_count: {summary.get('physical_run_count')}",
        f"- pass_count: {summary.get('pass_count')}",
        f"- failure_count: {summary.get('failure_count')}",
        f"- estimated_spend_usd: {summary.get('estimated_spend_usd')}",
        f"- actual_spend_usd: {summary.get('actual_spend_usd')}",
        "",
        "## Policy",
        "",
        f"- policy_sha256: `{payload.get('policy', {}).get('policy_sha256')}`",
        f"- active_provider_set: "
        f"{payload.get('policy', {}).get('active_provider_set')}",
        f"- first_amd_target: {payload.get('policy', {}).get('first_amd_target')}",
        "",
        "## Candidates",
        "",
    ]
    for candidate in payload["candidates"]:
        lines.append(
            f"- `{candidate.get('artifact_sha256')}` "
            f"({candidate.get('qualification_state')}) "
            f"impl `{candidate.get('implementation_commit')}`"
        )
    lines.extend(["", "## Servers", ""])
    for server in payload["server_matrix"]:
        lines.append(
            f"- requested `{server.get('requested_gpu_type')}` / "
            f"assigned `{server.get('assigned_gpu_type')}` / "
            f"observed `{server.get('observed_gpu_model')}`"
        )
    lines.extend(["", "## Comparisons", ""])
    for item in payload["comparisons"]:
        mark = "match" if item.get("matched") else "mismatch"
        lines.append(
            f"- {item.get('dimension')}: {mark} "
            f"expected {item.get('expected_value_json')} "
            f"actual {item.get('actual_value_json')}"
        )
    lines.extend(["", "## Failures", ""])
    if not payload["failures"]:
        lines.append("- none")
    for failure in payload["failures"]:
        lines.append(
            f"- `{failure.get('classification')}` {failure.get('summary')} "
            f"(candidate `{failure.get('artifact_sha256')}`)"
        )
    lines.extend(["", "## Checkpoints", ""])
    for checkpoint in payload["checkpoints"]:
        lines.append(
            f"- `{checkpoint.get('checkpoint_name')}`: "
            f"{checkpoint.get('semantic_meaning')}"
        )
    lines.extend(["", "## Evidence SHA", ""])
    for evidence in payload["evidence"]:
        lines.append(
            f"- `{evidence.get('sha256')}` {evidence.get('artifact_type')} "
            f"{evidence.get('path')}"
        )
    lines.append("")
    return "\n".join(lines)


def render_json(payload: dict[str, Any]) -> str:
    return canonical_json(payload) + "\n"


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
