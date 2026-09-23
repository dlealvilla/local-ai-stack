"""Serve events. Identifiers and reason codes only."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.serve.contracts import ServeDecision, ServeFailure, ServeOutcome

SERVE_BLOCK = "9"
SERVE_COMPONENT = "9"
STARTED_TYPE = "serve.started"
READY_TYPE = "serve.ready"
FAILED_TYPE = "serve.failed"
STOPPED_TYPE = "serve.stopped"
INFERENCE_COMPLETED_TYPE = "inference.completed"
INFERENCE_FAILED_TYPE = "inference.failed"


@contract(kind="serve.started", version=1)
@dataclass(frozen=True, slots=True)
class ServeStartedPayload(Contract):
    instance_id: str = meaning("instance identity")
    plan_id: str = meaning("plan")
    reservation_id: str = meaning("authorizing reservation")


@contract(kind="serve.ready", version=1)
@dataclass(frozen=True, slots=True)
class ServeReadyPayload(Contract):
    instance_id: str = meaning("instance identity")
    plan_id: str = meaning("plan")


@contract(kind="serve.failed", version=1)
@dataclass(frozen=True, slots=True)
class ServeFailedPayload(Contract):
    instance_id: str = meaning("instance identity, or none before launch")
    failure: str = meaning("typed failure")


@contract(kind="serve.stopped", version=1)
@dataclass(frozen=True, slots=True)
class ServeStoppedPayload(Contract):
    instance_id: str = meaning("instance that stopped")
    reservation_id: str = meaning("reservation still held until release")


@contract(kind="inference.completed", version=1)
@dataclass(frozen=True, slots=True)
class InferenceCompletedPayload(Contract):
    proof_id: str = meaning("proof identity")
    instance_id: str = meaning("instance")
    purpose: str = meaning("request")


@contract(kind="inference.failed", version=1)
@dataclass(frozen=True, slots=True)
class InferenceFailedPayload(Contract):
    instance_id: str = meaning("instance")
    failure: str = meaning("typed failure")


def serve_event(decision: ServeDecision, *, clock: Clock) -> EventRecord:
    """One operational event. No prompt, path, or address."""
    from machi.kernel.unresolved import is_resolved

    failure = decision.failure.value
    instance_id = "none"
    plan_id = "none"
    reservation_id = "none"
    if is_resolved(decision.instance):
        instance_id = decision.instance.instance_id
        plan_id = decision.instance.plan_id
        reservation_id = decision.instance.reservation_id
    if decision.outcome is ServeOutcome.READY:
        payload: Contract = ServeReadyPayload(instance_id=instance_id, plan_id=plan_id)
        event_type = READY_TYPE
        outcome = EventOutcome.PASS
    elif decision.outcome is ServeOutcome.STOPPED:
        payload = ServeStoppedPayload(
            instance_id=instance_id, reservation_id=reservation_id
        )
        event_type = STOPPED_TYPE
        outcome = EventOutcome.PASS
    elif decision.outcome is ServeOutcome.PROVEN:
        proof_id = "none"
        if is_resolved(decision.proof):
            proof_id = decision.proof.proof_id
        payload = InferenceCompletedPayload(
            proof_id=proof_id, instance_id=instance_id, purpose="request"
        )
        event_type = INFERENCE_COMPLETED_TYPE
        outcome = EventOutcome.PASS
    elif decision.failure is ServeFailure.INFERENCE_FAILED:
        payload = InferenceFailedPayload(instance_id=instance_id, failure=failure)
        event_type = INFERENCE_FAILED_TYPE
        outcome = EventOutcome.FAIL
    elif decision.outcome is ServeOutcome.FAILED:
        payload = ServeFailedPayload(instance_id=instance_id, failure=failure)
        event_type = FAILED_TYPE
        outcome = EventOutcome.FAIL
    elif decision.outcome is ServeOutcome.STARTED:
        payload = ServeStartedPayload(
            instance_id=instance_id,
            plan_id=plan_id,
            reservation_id=reservation_id,
        )
        event_type = STARTED_TYPE
        outcome = EventOutcome.PASS
    else:
        payload = ServeFailedPayload(instance_id=instance_id, failure=failure)
        event_type = FAILED_TYPE
        outcome = EventOutcome.FAIL
    return EventRecord.create(
        event_type=event_type,
        block_id=SERVE_BLOCK,
        component_id=SERVE_COMPONENT,
        outcome=outcome,
        privacy=PrivacyClass.OPERATIONAL,
        payload=payload,
        clock=clock,
    )
