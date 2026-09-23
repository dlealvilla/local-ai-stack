"""Synthetic empirical cases. No host and no customer content."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from tools.acceptance_lab.empirical import (
    EmpiricalRecordError,
    cases_for_hardware,
    estimate_gap,
    failure_counts,
    record_case,
    verify_raw,
)
from tools.acceptance_lab.jsonutil import sha256_bytes


def _case(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "empirical_case_id": "ecase_fixture",
        "instruction_id": "MACHI-INFERENCE-EXEC-005-001",
        "step_id": "MACHI-INF-02-EMPIRICAL-LAB",
        "attempt": 1,
        "branch": "automation/inference-program",
        "implementation_sha": "a" * 40,
        "evidence_sha": "b" * 40,
        "build_id": "0.1.0+fixture",
        "wheel_sha256": "c" * 64,
        "gpu_vendor": "nvidia",
        "gpu_model": "A40",
        "vram_bytes": 48 * 1024**3,
        "compute_capability": "8.6",
        "model_revision": "rev-fixture",
        "funnel_stage": "qualified",
        "estimated_vram_bytes": 1000,
        "measured_vram_bytes": 1200,
        "typed_failure": None,
        "created_at_utc": "2026-09-23T00:00:00Z",
    }
    body.update(overrides)
    return body


def test_case_round_trip_and_queries(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    raw = b'{"probe":"fixture"}'
    record_case(connection, _case(), raw=raw, artifact_directory=tmp_path)
    found = cases_for_hardware(connection, "A40")
    assert len(found) == 1
    assert found[0]["model_revision"] == "rev-fixture"
    digest = sha256_bytes(raw)
    assert found[0]["raw_artifact_sha256"] == digest
    assert verify_raw(tmp_path, digest) is True
    gaps = estimate_gap(connection)
    assert gaps[0]["measured_vram_bytes"] == 1200
    counts = failure_counts(connection)
    assert counts[0]["typed_failure"] == "none"


def test_tampered_raw_artifact_is_rejected(tmp_path: Path) -> None:
    from tools.acceptance_lab.empirical import store_raw

    digest = store_raw(tmp_path, b"intact")
    path = tmp_path / "sha256" / digest
    path.write_bytes(b"tampered")
    assert verify_raw(tmp_path, digest) is False


def test_secret_fields_are_refused(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    with pytest.raises(EmpiricalRecordError, match="secret"):
        record_case(
            connection,
            _case(prompt="hello"),
            raw=b"{}",
            artifact_directory=tmp_path,
        )
