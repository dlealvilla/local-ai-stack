"""Admit events. Identifiers and reason codes only."""

from __future__ import annotations

from dataclasses import dataclass

from machi.admit.contracts import (
    AdmissionDecision,
    AdmissionOutcome,
    ReconciliationReport,
    ReconciliationStatus,
)
from machi.kernel.clock import Clock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import is_resolved

ADMIT_BLOCK = "8"
ADMIT_COMPONENT = "8"
COMPLETED_TYPE = "admit.completed"
REJECTED_TYPE = "admit.rejected"
RELEASED_TYPE = "admit.released"
RECONCILED_TYPE = "admit.reconciliation_detected"


@contract(kind="admit.completed", version=1)
@dataclass(frozen=True, slots=True)
class AdmitCompletedPayload(Contract):
    reservation_id: str = meaning("hold identity")
    plan_id: str = meaning("authorized plan")
    fingerprint: str = meaning("plan fingerprint")
    accelerator_count: int = meaning("accelerators held")


@contract(kind="admit.rejected", version=1)
@dataclass(frozen=True, slots=True)
class AdmitRejectedPayload(Contract):
    failure: str = meaning("typed refusal")
    plan_id: str = meaning("plan that was not reserved")


@contract(kind="admit.released", version=1)
@dataclass(frozen=True, slots=True)
class AdmitReleasedPayload(Contract):
    reservation_id: str = meaning("hold that was freed")
    plan_id: str = meaning("plan whose hold was freed")


@contract(kind="admit.reconciliation_detected", version=1)
@dataclass(frozen=True, slots=True)
class AdmitReconciledPayload(Contract):
    status: str = meaning("consistent, overcommitted, or degraded")
    active_count: int = meaning("unreleased holds")


def admission_event(
    decision: AdmissionDecision,
    *,
    plan_id: str,
    clock: Clock,
) -> EventRecord:
    if decision.outcome is AdmissionOutcome.ADMITTED and is_resolved(
        decision.reservation
    ):
        payload: Contract = AdmitCompletedPayload(
            reservation_id=decision.reservation.reservation_id,
            plan_id=decision.reservation.plan_id,
            fingerprint=decision.reservation.fingerprint,
            accelerator_count=1,
        )
        event_type = COMPLETED_TYPE
        outcome = EventOutcome.PASS
    elif decision.outcome is AdmissionOutcome.RELEASED and is_resolved(
        decision.reservation
    ):
        payload = AdmitReleasedPayload(
            reservation_id=decision.reservation.reservation_id,
            plan_id=decision.reservation.plan_id,
        )
        event_type = RELEASED_TYPE
        outcome = EventOutcome.PASS
    else:
        payload = AdmitRejectedPayload(failure=decision.failure.value, plan_id=plan_id)
        event_type = REJECTED_TYPE
        outcome = EventOutcome.FAIL
    return EventRecord.create(
        event_type=event_type,
        block_id=ADMIT_BLOCK,
        component_id=ADMIT_COMPONENT,
        outcome=outcome,
        privacy=PrivacyClass.OPERATIONAL,
        payload=payload,
        clock=clock,
    )


def reconciliation_event(report: ReconciliationReport, *, clock: Clock) -> EventRecord:
    return EventRecord.create(
        event_type=RECONCILED_TYPE,
        block_id=ADMIT_BLOCK,
        component_id=ADMIT_COMPONENT,
        outcome=(
            EventOutcome.PASS
            if report.status is ReconciliationStatus.CONSISTENT
            else EventOutcome.FAIL
        ),
        privacy=PrivacyClass.OPERATIONAL,
        payload=AdmitReconciledPayload(
            status=report.status.value,
            active_count=report.active_count,
        ),
        clock=clock,
    )
