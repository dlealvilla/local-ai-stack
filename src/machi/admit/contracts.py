"""Admit contracts (MACHI 8).

A reservation is permission to use resources. It is not a running
process. Plan may request. Only Admit may reserve.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved

_TOKEN_MAX = 80
_REASON_MAX = 240


class AdmissionFailure(StrEnum):
    """Why admission or release did not proceed."""

    NONE = "none"
    PLAN_NOT_SUCCESSFUL = "plan_not_successful"
    PLAN_REQUEST_MISMATCH = "plan_request_mismatch"
    PLAN_CONFIGURATION_MISMATCH = "plan_configuration_mismatch"
    STALE_PLAN = "stale_plan"
    STALE_CAPACITY_INPUT = "stale_capacity_input"
    CAPACITY_UNRESOLVED = "capacity_unresolved"
    ACCELERATOR_NOT_PRESENT = "accelerator_not_present"
    INSUFFICIENT_ACCELERATOR_CAPACITY = "insufficient_accelerator_capacity"
    INSUFFICIENT_HOST_MEMORY = "insufficient_host_memory"
    INSUFFICIENT_PERSISTENT_STORAGE = "insufficient_persistent_storage"
    INSUFFICIENT_TRANSIENT_STORAGE = "insufficient_transient_storage"
    MULTI_ACCELERATOR_ADMISSION_NOT_IMPLEMENTED = (
        "multi_accelerator_admission_not_implemented"
    )
    RESERVATION_STATE_INVALID = "reservation_state_invalid"
    RESERVATION_CONFLICT = "reservation_conflict"
    CURRENT_CAPACITY_OVERCOMMITTED = "current_capacity_overcommitted"


class ReservationState(StrEnum):
    """Reserved means held. Released means freed. Running is later."""

    RESERVED = "reserved"
    RELEASED = "released"


class AdmissionOutcome(StrEnum):
    ADMITTED = "admitted"
    REFUSED = "refused"
    RELEASED = "released"


class ReconciliationStatus(StrEnum):
    CONSISTENT = "consistent"
    OVERCOMMITTED = "overcommitted"
    DEGRADED = "degraded"


@contract(kind="admit.reservation", version=1)
@dataclass(frozen=True, slots=True)
class ResourceReservation(Contract):
    """Held resources for one plan. The stored record is not rewritten."""

    reservation_id: str = meaning("identity of this hold")
    plan_id: str = meaning("plan this hold authorizes")
    fingerprint: str = meaning("plan fingerprint at admission")
    request_id: str = meaning("resource request this hold binds")
    capacity_evidence_id: str = meaning("capacity snapshot cited by the plan")
    accelerator_identity: str = meaning("exact device; not a substitute")
    accelerator_memory_bytes: int = meaning("SAFE accelerator bytes held")
    host_memory_bytes: int = meaning("SAFE host bytes held")
    persistent_bytes: int = meaning("persistent storage bytes held")
    transient_bytes: int = meaning("transient storage bytes held")
    cpu_count: int = meaning("requested process slots; Capacity has no CPU pool")
    policy_version: str = meaning("admission policy that created this hold")
    state: ReservationState = meaning("reserved until a release record exists")

    def __post_init__(self) -> None:
        for name, value in (
            ("reservation", self.reservation_id),
            ("plan", self.plan_id),
            ("fingerprint", self.fingerprint),
            ("request", self.request_id),
            ("capacity", self.capacity_evidence_id),
            ("accelerator", self.accelerator_identity),
            ("policy", self.policy_version),
        ):
            _bounded(value, what=name, maximum=_TOKEN_MAX)
        if self.accelerator_memory_bytes < 1 or self.host_memory_bytes < 1:
            raise ValidationError("reserved memory must be positive")
        if self.persistent_bytes < 0 or self.transient_bytes < 0:
            raise ValidationError("reserved storage must not be negative")
        if self.cpu_count < 1:
            raise ValidationError("cpu count must be positive")


@contract(kind="admit.release", version=1)
@dataclass(frozen=True, slots=True)
class ReservationRelease(Contract):
    """Frees a hold. The reservation record itself stays in the store."""

    release_id: str = meaning("identity of this release")
    reservation_id: str = meaning("hold being freed")
    plan_id: str = meaning("plan whose hold was freed")

    def __post_init__(self) -> None:
        _bounded(self.release_id, what="release", maximum=_TOKEN_MAX)
        _bounded(self.reservation_id, what="reservation", maximum=_TOKEN_MAX)
        _bounded(self.plan_id, what="plan", maximum=_TOKEN_MAX)


@contract(kind="admit.decision", version=1)
@dataclass(frozen=True, slots=True)
class AdmissionDecision(Contract):
    """Admitted with a reservation, or refused with none."""

    outcome: AdmissionOutcome = meaning("admitted, refused, or released")
    failure: AdmissionFailure = meaning("none when the outcome succeeded")
    reason: str = meaning("short explanation or underlying stale code")
    reservation: Maybe[ResourceReservation] = meaning(
        "hold when admitted or released; unresolved when refused"
    )

    def __post_init__(self) -> None:
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)
        present = is_resolved(self.reservation)
        if self.outcome is AdmissionOutcome.REFUSED:
            if self.failure is AdmissionFailure.NONE or present:
                raise ValidationError("a refusal has a reason and no reservation")
        elif not present or self.failure is not AdmissionFailure.NONE:
            raise ValidationError("a successful decision carries a reservation")


@contract(kind="admit.reconciliation", version=1)
@dataclass(frozen=True, slots=True)
class ReconciliationReport(Contract):
    """Discrepancy report. It does not rewrite reservations."""

    status: ReconciliationStatus = meaning("consistent, overcommitted, or degraded")
    active_count: int = meaning("unreleased holds")
    malformed_count: int = meaning("records that could not be read")
    missing_accelerators: tuple[str, ...] = meaning("held devices absent now")
    overcommitted: tuple[str, ...] = meaning("dimensions whose holds exceed SAFE")
    policy_version: str = meaning("policy used for this reading")

    def __post_init__(self) -> None:
        _bounded(self.policy_version, what="policy", maximum=_TOKEN_MAX)
        if self.active_count < 0 or self.malformed_count < 0:
            raise ValidationError("reconciliation counts must not be negative")
        if len(self.missing_accelerators) > 64 or len(self.overcommitted) > 8:
            raise ValidationError("reconciliation detail is unbounded")


def refused(failure: AdmissionFailure, reason: str) -> AdmissionDecision:
    return AdmissionDecision(
        outcome=AdmissionOutcome.REFUSED,
        failure=failure,
        reason=reason,
        reservation=NOT_PROVIDED,
    )


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
