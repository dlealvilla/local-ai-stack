"""Record one empirical inference case. Development lab only."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from tools.acceptance_lab.jsonutil import canonical_json, sha256_bytes
from tools.acceptance_lab.paths import artifact_root

_FORBIDDEN = frozenset(
    {
        "api_key",
        "password",
        "private_key",
        "token",
        "oauth",
        "prompt",
        "response",
        "customer_content",
    }
)


class EmpiricalRecordError(ValueError):
    """The case or its raw artifact cannot be stored."""


def store_raw(root: Path, payload: bytes) -> str:
    """Write immutable bytes addressed by SHA-256. A mismatch is a refusal."""
    digest = sha256_bytes(payload)
    path = root / "sha256" / digest
    if path.is_file():
        if path.read_bytes() != payload:
            raise EmpiricalRecordError("raw artifact hash does not match its bytes")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if sha256_bytes(path.read_bytes()) != digest:
        raise EmpiricalRecordError("raw artifact was not stored intact")
    return digest


def verify_raw(root: Path, digest: str) -> bool:
    path = root / "sha256" / digest
    if not path.is_file():
        return False
    return sha256_bytes(path.read_bytes()) == digest


def record_case(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    *,
    raw: bytes | None = None,
    artifact_directory: Path | None = None,
) -> str:
    """Insert one case. Secret-shaped fields and prompt text are refused."""
    _refuse_secrets(case)
    stored = dict(case)
    if raw is not None:
        root = artifact_directory or artifact_root()
        stored["raw_artifact_sha256"] = store_raw(root, raw)
    required = (
        "empirical_case_id",
        "instruction_id",
        "step_id",
        "attempt",
        "branch",
        "implementation_sha",
        "evidence_sha",
        "build_id",
        "wheel_sha256",
        "created_at_utc",
    )
    missing = [name for name in required if not stored.get(name)]
    if missing:
        raise EmpiricalRecordError("missing " + ",".join(missing))
    columns = (
        "empirical_case_id",
        "instruction_id",
        "step_id",
        "campaign_id",
        "experiment_run_id",
        "attempt",
        "branch",
        "implementation_sha",
        "evidence_sha",
        "build_id",
        "wheel_sha256",
        "provider",
        "region",
        "hourly_usd",
        "duration_seconds",
        "gpu_vendor",
        "gpu_model",
        "gpu_count",
        "vram_bytes",
        "compute_capability",
        "execution_environment_fingerprint",
        "foundation_generation_id",
        "model_source",
        "model_revision",
        "model_license",
        "architecture",
        "dtype",
        "quantization",
        "context_length",
        "funnel_stage",
        "exclusion_reason",
        "estimated_vram_bytes",
        "measured_vram_bytes",
        "plan_id",
        "reservation_id",
        "serving_instance_id",
        "proof_id",
        "typed_failure",
        "readiness_seconds",
        "ttft_seconds",
        "tokens_per_second",
        "request_latency_seconds",
        "peak_ram_bytes",
        "peak_vram_bytes",
        "stop_evidence",
        "restart_evidence",
        "raw_artifact_sha256",
        "created_at_utc",
    )
    values = tuple(stored.get(name) for name in columns)
    connection.execute(
        "INSERT INTO empirical_case ("
        + ", ".join(columns)
        + ") VALUES ("
        + ", ".join("?" for _ in columns)
        + ")",
        values,
    )
    connection.commit()
    return str(stored["empirical_case_id"])


def cases_for_hardware(
    connection: sqlite3.Connection, gpu_model: str
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT * FROM empirical_case WHERE gpu_model = ? ORDER BY created_at_utc",
            (gpu_model,),
        )
    )


def failure_counts(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT COALESCE(typed_failure, 'none') AS typed_failure, COUNT(*) AS n "
            "FROM empirical_case GROUP BY typed_failure ORDER BY n DESC"
        )
    )


def estimate_gap(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT empirical_case_id, estimated_vram_bytes, measured_vram_bytes "
            "FROM empirical_case "
            "WHERE estimated_vram_bytes IS NOT NULL "
            "AND measured_vram_bytes IS NOT NULL"
        )
    )


def _refuse_secrets(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN:
                raise EmpiricalRecordError("refusing a secret or customer field")
            _refuse_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _refuse_secrets(item)
    elif isinstance(value, str) and "BEGIN OPENSSH PRIVATE KEY" in value:
        raise EmpiricalRecordError("refusing a secret or customer field")


def case_summary(case: dict[str, Any]) -> str:
    return canonical_json(
        {
            "id": case.get("empirical_case_id"),
            "model": case.get("model_revision"),
            "gpu": case.get("gpu_model"),
            "failure": case.get("typed_failure"),
        }
    )
