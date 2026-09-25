"""DeploymentWitness projects persisted identities. It does not execute."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

from machi.kernel.clock import FixedClock
from machi.kernel.events import EventOutcome
from machi.kernel.privacy import FORBIDDEN_PUBLIC_OPS_KEYS
from machi.kernel.schema import from_dict, to_dict
from machi.kernel.witness import (
    NOT_RECORDED,
    WitnessFacts,
    WitnessVerdict,
    compose_witness,
    witness_composed,
)

OBSERVED = "2026-09-25T00:00:00+00:00"
_SOURCE = Path("src/machi/kernel/witness.py")


def _native(**overrides: str) -> WitnessFacts:
    facts = WitnessFacts(
        install_id="inst_native",
        capacity_evidence_id="cap_l40s",
        foundation_selection_id="fsel_native",
        foundation_generation_id="fgen_071b23a5b1db1192",
        model_identity="mart_7ff1b147d6c56cd6",
        model_identity_kind="warehouse_artifact",
        qualification_id="qual_smollm2_135",
        plan_id="plan_native",
        plan_generation_id="fgen_071b23a5b1db1192",
        reservation_id="rsv_native",
        reservation_plan_id="plan_native",
        reservation_state="released",
        instance_id="srv_native",
        instance_plan_id="plan_native",
        instance_reservation_id="rsv_native",
        instance_generation_id="fgen_071b23a5b1db1192",
        instance_state="stopped",
        proof_id="inf_native",
        proof_outcome="proven",
        proof_plan_id="plan_native",
        proof_reservation_id="rsv_native",
        release_id="rel_native",
        observed_at=OBSERVED,
    )
    return replace(facts, **overrides) if overrides else facts


def _provider(**overrides: str) -> WitnessFacts:
    facts = WitnessFacts(
        install_id="inst_provider",
        capacity_evidence_id="cap_a40",
        foundation_selection_id="fsel_66a0af2ac4ba618c",
        foundation_generation_id="fgen_66a0af2ac4ba618c",
        model_identity="2d470404841a51320639b2c2418c7ad8643cccbbcb88c2a242b211ae83bf46a9",
        model_identity_kind="provider_digest",
        qualification_id="oq_smollm2_135",
        plan_id="plan_d24362279180c37c",
        plan_generation_id="fgen_66a0af2ac4ba618c",
        reservation_id="rsv_35c15204781dc933",
        reservation_plan_id="plan_d24362279180c37c",
        reservation_state="released",
        instance_id="srv_provider",
        instance_plan_id="plan_d24362279180c37c",
        instance_reservation_id="rsv_35c15204781dc933",
        instance_generation_id="fgen_66a0af2ac4ba618c",
        instance_state="stopped",
        proof_id="inf_provider",
        proof_outcome="proven",
        proof_plan_id="plan_d24362279180c37c",
        proof_reservation_id="rsv_35c15204781dc933",
        release_id="rel_provider",
        observed_at=OBSERVED,
    )
    return replace(facts, **overrides) if overrides else facts


def test_native_chain_is_supported_and_deterministic() -> None:
    first = compose_witness(_native())
    second = compose_witness(_native())
    assert first.verdict is WitnessVerdict.SUPPORTED
    assert first.witness_id == second.witness_id
    assert first.model_identity_kind == "warehouse_artifact"
    assert "reservation released" in first.reason


def test_provider_chain_keeps_digest_identity() -> None:
    witness = compose_witness(_provider())
    assert witness.verdict is WitnessVerdict.SUPPORTED
    assert witness.model_identity_kind == "provider_digest"
    assert witness.model_identity != compose_witness(_native()).model_identity
    assert witness.plan_id == "plan_d24362279180c37c"


def test_missing_qualification_is_incomplete() -> None:
    witness = compose_witness(_native(qualification_id=NOT_RECORDED))
    assert witness.verdict is WitnessVerdict.INCOMPLETE
    assert "qualification" in witness.reason


def test_mismatched_foundation_generation_is_contradictory() -> None:
    witness = compose_witness(_native(plan_generation_id="fgen_other"))
    assert witness.verdict is WitnessVerdict.CONTRADICTORY
    assert "foundation" in witness.reason


def test_wrong_plan_on_the_instance_is_contradictory() -> None:
    witness = compose_witness(_provider(instance_plan_id="plan_stale"))
    assert witness.verdict is WitnessVerdict.CONTRADICTORY
    assert "plan" in witness.reason


def test_released_reservation_with_ready_instance_is_contradictory() -> None:
    witness = compose_witness(
        _native(instance_state="ready", reservation_state="released")
    )
    assert witness.verdict is WitnessVerdict.CONTRADICTORY
    assert "released" in witness.reason


def test_missing_inference_proof_is_incomplete() -> None:
    witness = compose_witness(
        _native(proof_id=NOT_RECORDED, proof_outcome=NOT_RECORDED)
    )
    assert witness.verdict is WitnessVerdict.INCOMPLETE
    assert "inference" in witness.reason


def test_failed_inference_is_not_supported() -> None:
    witness = compose_witness(_native(proof_outcome="failed"))
    assert witness.verdict is WitnessVerdict.FAILED


def test_stop_and_release_are_distinct() -> None:
    held = compose_witness(
        _native(reservation_state="reserved", release_id=NOT_RECORDED)
    )
    assert held.verdict is WitnessVerdict.SUPPORTED
    assert "still held" in held.reason
    running = compose_witness(
        _native(
            instance_state="ready",
            reservation_state="reserved",
            release_id=NOT_RECORDED,
        )
    )
    assert running.verdict is WitnessVerdict.INCOMPLETE
    assert "stop" in running.reason
    released_without_id = compose_witness(_native(release_id=NOT_RECORDED))
    assert released_without_id.verdict is WitnessVerdict.INCOMPLETE
    assert "release" in released_without_id.reason


def test_historical_unresolved_fields_are_not_strengthened() -> None:
    witness = compose_witness(
        _provider(
            qualification_id=NOT_RECORDED,
            capacity_evidence_id=NOT_RECORDED,
        )
    )
    assert witness.verdict is WitnessVerdict.INCOMPLETE
    assert witness.qualification_id == NOT_RECORDED


def test_projection_round_trips_without_customer_content() -> None:
    witness = compose_witness(_native())
    encoded = to_dict(witness)
    restored = from_dict(encoded)
    assert restored == witness
    blob = str(encoded)
    for forbidden in ("prompt", "response", "secret", "api_key"):
        assert forbidden not in blob
    for key in FORBIDDEN_PUBLIC_OPS_KEYS:
        assert key not in encoded
    event = witness_composed(
        witness, clock=FixedClock(dt.datetime.fromisoformat(OBSERVED))
    )
    assert event.outcome is EventOutcome.PASS
    assert event.payload is not None
    body = to_dict(event.payload)
    assert body["verdict"] == "supported"
    assert "prompt" not in str(body)
    incomplete = witness_composed(
        compose_witness(_native(proof_id=NOT_RECORDED, proof_outcome=NOT_RECORDED)),
        clock=FixedClock(dt.datetime.fromisoformat(OBSERVED)),
    )
    assert incomplete.outcome is EventOutcome.UNRESOLVED


def test_composer_does_not_invoke_live_resolvers() -> None:
    text = _SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "from machi.adapters",
        "from machi.serve",
        "from machi.admit",
        "from machi.plan",
        "ResourceManager",
        "subprocess",
        "http",
    ):
        assert forbidden not in text
