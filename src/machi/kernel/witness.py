"""Kernel 0.6.1 DeploymentWitness.

A read-time projection of identities the caller already persisted.
It does not discover, plan, admit, start, stop, or infer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import Clock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning

WITNESS_COMPONENT = "0.6.1"
WITNESS_COMPOSED_TYPE = "kernel.witness.composed"
NOT_RECORDED = "not_recorded"
_TOKEN_MAX = 128
_REASON_MAX = 240

_WAREHOUSE = "warehouse_artifact"
_PROVIDER = "provider_digest"
_IDENTITY_KINDS = frozenset({_WAREHOUSE, _PROVIDER, NOT_RECORDED})
_RESERVATION_STATES = frozenset({"reserved", "released", NOT_RECORDED})
_PROOF_OUTCOMES = frozenset({"proven", "failed", NOT_RECORDED})


class WitnessVerdict(StrEnum):
    """Journey reading. Not a boolean and not an admission."""

    SUPPORTED = "supported"
    INCOMPLETE = "incomplete"
    CONTRADICTORY = "contradictory"
    FAILED = "failed"


@contract(kind="kernel.deployment_witness", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentWitness(Contract):
    """Projected deployment journey. Identities only; no customer content."""

    witness_id: str = meaning("deterministic identity of these cited facts")
    install_id: str = meaning("install correlation, or not_recorded")
    capacity_evidence_id: str = meaning("cited capacity evidence, or not_recorded")
    foundation_selection_id: str = meaning("cited foundation selection")
    foundation_generation_id: str = meaning("cited foundation generation")
    model_identity: str = meaning(
        "warehouse artifact id or provider digest; catalogs stay separate"
    )
    model_identity_kind: str = meaning(
        "warehouse_artifact, provider_digest, or not_recorded"
    )
    qualification_id: str = meaning("cited qualification evidence, or not_recorded")
    plan_id: str = meaning("cited plan")
    reservation_id: str = meaning("cited reservation")
    reservation_state: str = meaning("reserved, released, or not_recorded")
    instance_id: str = meaning("cited serving instance")
    instance_state: str = meaning("observed instance state, or not_recorded")
    inference_proof_id: str = meaning("cited inference proof, or not_recorded")
    inference_outcome: str = meaning("proven, failed, or not_recorded")
    release_id: str = meaning("cited release, or not_recorded")
    verdict: str = meaning(
        "supported, incomplete, contradictory, or failed; never a boolean"
    )
    reason: str = meaning("why the verdict was reached; no paths or content")
    observed_at: str = meaning("caller-supplied observation time")

    def __post_init__(self) -> None:
        for label, value in (
            ("witness", self.witness_id),
            ("verdict", self.verdict),
            ("reason", self.reason),
            ("observed", self.observed_at),
        ):
            _token(label, value, required=True)
        if self.verdict not in {
            WitnessVerdict.SUPPORTED,
            WitnessVerdict.INCOMPLETE,
            WitnessVerdict.CONTRADICTORY,
            WitnessVerdict.FAILED,
        }:
            raise ValidationError("witness verdict is not a known reading")
        if self.model_identity_kind not in _IDENTITY_KINDS:
            raise ValidationError("witness model identity kind is unknown")
        if self.reservation_state not in _RESERVATION_STATES:
            raise ValidationError("witness reservation state is unknown")
        if self.inference_outcome not in _PROOF_OUTCOMES:
            raise ValidationError("witness inference outcome is unknown")


@contract(kind="kernel.witness.composed", version=1)
@dataclass(frozen=True, slots=True)
class WitnessComposedPayload(Contract):
    """Safe operational body. No prompt, response, path, or address."""

    witness_id: str = meaning("identity of the projection")
    verdict: str = meaning("supported, incomplete, contradictory, or failed")
    plan_id: str = meaning("cited plan identity, or not_recorded")


@dataclass(frozen=True, slots=True)
class WitnessFacts:
    """Citations already stored. The composer does not load them."""

    install_id: str = NOT_RECORDED
    capacity_evidence_id: str = NOT_RECORDED
    foundation_selection_id: str = NOT_RECORDED
    foundation_generation_id: str = NOT_RECORDED
    model_identity: str = NOT_RECORDED
    model_identity_kind: str = NOT_RECORDED
    qualification_id: str = NOT_RECORDED
    plan_id: str = NOT_RECORDED
    plan_generation_id: str = NOT_RECORDED
    reservation_id: str = NOT_RECORDED
    reservation_plan_id: str = NOT_RECORDED
    reservation_state: str = NOT_RECORDED
    instance_id: str = NOT_RECORDED
    instance_plan_id: str = NOT_RECORDED
    instance_reservation_id: str = NOT_RECORDED
    instance_generation_id: str = NOT_RECORDED
    instance_state: str = NOT_RECORDED
    proof_id: str = NOT_RECORDED
    proof_outcome: str = NOT_RECORDED
    proof_plan_id: str = NOT_RECORDED
    proof_reservation_id: str = NOT_RECORDED
    release_id: str = NOT_RECORDED
    observed_at: str = NOT_RECORDED


def compose_witness(facts: WitnessFacts) -> DeploymentWitness:
    """Project one journey. Missing evidence stays incomplete."""
    if facts.model_identity_kind not in _IDENTITY_KINDS:
        raise ValidationError("witness model identity kind is unknown")
    if facts.reservation_state not in _RESERVATION_STATES:
        raise ValidationError("witness reservation state is unknown")
    if facts.proof_outcome not in _PROOF_OUTCOMES:
        raise ValidationError("witness inference outcome is unknown")
    _token("observed", facts.observed_at, required=True)
    verdict, reason = _read(facts)
    witness_id = "wit_" + hashlib.sha256(_material(facts).encode()).hexdigest()[:16]
    return DeploymentWitness(
        witness_id=witness_id,
        install_id=_cite(facts.install_id),
        capacity_evidence_id=_cite(facts.capacity_evidence_id),
        foundation_selection_id=_cite(facts.foundation_selection_id),
        foundation_generation_id=_cite(facts.foundation_generation_id),
        model_identity=_cite(facts.model_identity),
        model_identity_kind=facts.model_identity_kind,
        qualification_id=_cite(facts.qualification_id),
        plan_id=_cite(facts.plan_id),
        reservation_id=_cite(facts.reservation_id),
        reservation_state=facts.reservation_state,
        instance_id=_cite(facts.instance_id),
        instance_state=_cite(facts.instance_state),
        inference_proof_id=_cite(facts.proof_id),
        inference_outcome=facts.proof_outcome,
        release_id=_cite(facts.release_id),
        verdict=verdict,
        reason=reason,
        observed_at=facts.observed_at,
    )


def witness_composed(
    witness: DeploymentWitness, *, clock: Clock | None = None
) -> EventRecord:
    """Mint the projection event. Does not persist it and does not admit."""
    if witness.verdict == WitnessVerdict.SUPPORTED:
        outcome = EventOutcome.PASS
    elif witness.verdict == WitnessVerdict.INCOMPLETE:
        outcome = EventOutcome.UNRESOLVED
    else:
        outcome = EventOutcome.FAIL
    return EventRecord.create(
        event_type=WITNESS_COMPOSED_TYPE,
        block_id="0",
        component_id=WITNESS_COMPONENT,
        outcome=outcome,
        privacy=PrivacyClass.RESTRICTED,
        payload=WitnessComposedPayload(
            witness_id=witness.witness_id,
            verdict=witness.verdict,
            plan_id=witness.plan_id,
        ),
        clock=clock,
    )


def _read(facts: WitnessFacts) -> tuple[str, str]:
    clashes = _clashes(facts)
    if clashes:
        return WitnessVerdict.CONTRADICTORY, clashes[0]
    if facts.proof_outcome == "failed":
        return WitnessVerdict.FAILED, "inference proof records failure"
    missing = _missing(facts)
    if missing:
        return WitnessVerdict.INCOMPLETE, missing[0]
    if facts.instance_state != "stopped":
        return WitnessVerdict.INCOMPLETE, "stop is not recorded"
    if facts.reservation_state == "released" and facts.release_id in ("", NOT_RECORDED):
        return WitnessVerdict.INCOMPLETE, "release id is not recorded"
    if facts.reservation_state == "released":
        return (
            WitnessVerdict.SUPPORTED,
            "inference proved; stopped; reservation released",
        )
    return (
        WitnessVerdict.SUPPORTED,
        "inference proved; stopped; reservation still held",
    )


def _clashes(facts: WitnessFacts) -> list[str]:
    found: list[str] = []
    pairs = (
        (
            facts.plan_generation_id,
            facts.foundation_generation_id,
            "plan generation does not match foundation",
        ),
        (
            facts.reservation_plan_id,
            facts.plan_id,
            "reservation cites a different plan",
        ),
        (
            facts.instance_plan_id,
            facts.plan_id,
            "instance cites a different plan",
        ),
        (
            facts.instance_reservation_id,
            facts.reservation_id,
            "instance cites a different reservation",
        ),
        (
            facts.instance_generation_id,
            facts.foundation_generation_id,
            "instance generation does not match foundation",
        ),
    )
    for left, right, reason in pairs:
        if _both(left, right) and left != right:
            found.append(reason)
        proof_present = facts.proof_outcome != NOT_RECORDED and facts.proof_id not in (
            "",
            NOT_RECORDED,
        )
        if proof_present:
            plan_clash = (
                _both(facts.proof_plan_id, facts.plan_id)
                and facts.proof_plan_id != facts.plan_id
            )
            if plan_clash:
                found.append("inference proof cites a different plan")
        if (
            _both(facts.proof_reservation_id, facts.reservation_id)
            and facts.proof_reservation_id != facts.reservation_id
        ):
            found.append("inference proof cites a different reservation")
    if (
        facts.reservation_state == "released"
        and facts.instance_state == "ready"
    ):
        found.append("instance is ready after the reservation was released")
    return found


def _missing(facts: WitnessFacts) -> list[str]:
    required = (
        (facts.install_id, "install id is not recorded"),
        (facts.capacity_evidence_id, "capacity evidence is not recorded"),
        (facts.foundation_selection_id, "foundation selection is not recorded"),
        (facts.foundation_generation_id, "foundation generation is not recorded"),
        (facts.model_identity, "model identity is not recorded"),
        (facts.model_identity_kind, "model identity kind is not recorded"),
        (facts.qualification_id, "qualification is not recorded"),
        (facts.plan_id, "plan id is not recorded"),
        (facts.plan_generation_id, "plan generation is not recorded"),
        (facts.reservation_id, "reservation id is not recorded"),
        (facts.reservation_state, "reservation state is not recorded"),
        (facts.instance_id, "instance id is not recorded"),
        (facts.instance_state, "instance state is not recorded"),
        (facts.proof_id, "inference proof is not recorded"),
        (facts.proof_outcome, "inference outcome is not recorded"),
    )
    return [reason for value, reason in required if value in ("", NOT_RECORDED)]


def _both(left: str, right: str) -> bool:
    return left not in ("", NOT_RECORDED) and right not in ("", NOT_RECORDED)


def _cite(value: str) -> str:
    text = value.strip() if value else NOT_RECORDED
    if not text:
        return NOT_RECORDED
    _token("citation", text, required=True)
    return text


def _token(label: str, value: str, *, required: bool) -> None:
    if not value:
        if required:
            raise ValidationError(f"witness {label} is empty")
        return
    if len(value) > _TOKEN_MAX and label != "reason":
        raise ValidationError(f"witness {label} is too long")
    if label == "reason" and len(value) > _REASON_MAX:
        raise ValidationError("witness reason is too long")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValidationError(f"witness {label} must not contain control characters")


def _material(facts: WitnessFacts) -> str:
    fields = (
        facts.install_id,
        facts.capacity_evidence_id,
        facts.foundation_selection_id,
        facts.foundation_generation_id,
        facts.model_identity,
        facts.model_identity_kind,
        facts.qualification_id,
        facts.plan_id,
        facts.plan_generation_id,
        facts.reservation_id,
        facts.reservation_plan_id,
        facts.reservation_state,
        facts.instance_id,
        facts.instance_plan_id,
        facts.instance_reservation_id,
        facts.instance_generation_id,
        facts.instance_state,
        facts.proof_id,
        facts.proof_outcome,
        facts.proof_plan_id,
        facts.proof_reservation_id,
        facts.release_id,
        facts.observed_at,
    )
    return "\n".join(fields)
