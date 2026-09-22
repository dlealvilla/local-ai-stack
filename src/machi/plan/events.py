"""Plan events. Identifiers and reason codes only."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import is_resolved
from machi.plan.contracts import PlanDecision, PlanFailure

PLAN_BLOCK = "7"
PLAN_COMPONENT = "7"
CREATED_TYPE = "plan.created"
REFUSED_TYPE = "plan.refused"
STALE_TYPE = "plan.stale"


@contract(kind="plan.created", version=1)
@dataclass(frozen=True, slots=True)
class PlanCreatedPayload(Contract):
    """A plan exists. No paths and no model bytes."""

    plan_id: str = meaning("plan identity")
    fingerprint: str = meaning("material input token")
    provider: str = meaning("runtime provider")
    accelerator_count: int = meaning("accelerators requested")


@contract(kind="plan.refused", version=1)
@dataclass(frozen=True, slots=True)
class PlanRefusedPayload(Contract):
    """Compose refused. The reason is a code."""

    fingerprint: str = meaning("material input token")
    failure: str = meaning("typed refusal")


@contract(kind="plan.stale", version=1)
@dataclass(frozen=True, slots=True)
class PlanStalePayload(Contract):
    """An existing plan no longer matches its inputs."""

    plan_id: str = meaning("plan that was compared")
    failure: str = meaning("why it is stale")


def plan_events(decision: PlanDecision, *, clock: Clock) -> tuple[EventRecord, ...]:
    """One operational event for a compose result."""
    configuration = decision.configuration
    if decision.failure is PlanFailure.NONE and is_resolved(configuration):
        payload: Contract = PlanCreatedPayload(
            plan_id=configuration.plan_id,
            fingerprint=decision.fingerprint,
            provider=configuration.provider,
            accelerator_count=configuration.accelerator_count,
        )
        event_type = CREATED_TYPE
        outcome = EventOutcome.PASS
    else:
        payload = PlanRefusedPayload(
            fingerprint=decision.fingerprint,
            failure=decision.failure.value,
        )
        event_type = REFUSED_TYPE
        outcome = EventOutcome.FAIL
    return (
        EventRecord.create(
            event_type=event_type,
            block_id=PLAN_BLOCK,
            component_id=PLAN_COMPONENT,
            outcome=outcome,
            privacy=PrivacyClass.OPERATIONAL,
            payload=payload,
            clock=clock,
        ),
    )


def stale_event(plan_id: str, failure: PlanFailure, *, clock: Clock) -> EventRecord:
    """Record that a stored plan was not reused."""
    return EventRecord.create(
        event_type=STALE_TYPE,
        block_id=PLAN_BLOCK,
        component_id=PLAN_COMPONENT,
        outcome=EventOutcome.FAIL,
        privacy=PrivacyClass.OPERATIONAL,
        payload=PlanStalePayload(plan_id=plan_id, failure=failure.value),
        clock=clock,
    )
