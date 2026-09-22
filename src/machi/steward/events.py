"""Steward events. Operational metadata only. Paths stay off the payload."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.clock import Clock, FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe
from machi.steward.contracts import OccupancyMap, OwnershipStatus, Reclaimability

STEWARD_BLOCK = "3"
STEWARD_COMPONENT = "3"
CLASSIFIED_TYPE = "steward.resource.classified"
CONFLICT_TYPE = "steward.ownership.conflict"
OCCUPANCY_TYPE = "steward.occupancy.observed"
RECLAIM_TYPE = "steward.reclaimability.assessed"


@contract(kind="steward.resource.classified", version=1)
@dataclass(frozen=True, slots=True)
class ResourceClassifiedPayload(Contract):
    """Counts by ownership. Resource paths stay on the in-process map."""

    resource_count: int = meaning("how many roots were classified")
    verified_count: int = meaning("roots with agreeing marker and registry")
    conflict_count: int = meaning("roots whose evidence disagreed")
    unknown_count: int = meaning("roots with incomplete proof")
    legacy_count: int = meaning("roots with legacy evidence only")
    not_machi_count: int = meaning("roots with no Machi marker")


@contract(kind="steward.ownership.conflict", version=1)
@dataclass(frozen=True, slots=True)
class OwnershipConflictPayload(Contract):
    """Conflict was classified and preserved. No path is included."""

    conflict_count: int = meaning("how many roots were conflicted")


@contract(kind="steward.occupancy.observed", version=1)
@dataclass(frozen=True, slots=True)
class OccupancyObservedPayload(Contract):
    """Whether occupancy bytes were measured. Not SAFE capacity."""

    measured_count: int = meaning("verified roots with a measured size")
    unresolved_size_count: int = meaning("roots whose size stayed Unresolved")
    destructive_authorization: bool = meaning("always false")


@contract(kind="steward.reclaimability.assessed", version=1)
@dataclass(frozen=True, slots=True)
class ReclaimabilityAssessedPayload(Contract):
    """Candidate count. A candidate is not a deletion."""

    reclaimable_count: int = meaning("verified obsolete unprotected candidates")
    not_reclaimable_count: int = meaning("roots that must be kept")
    destructive_authorization: bool = meaning("always false")


def steward_events(
    occupancy: OccupancyMap,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> tuple[EventRecord, ...]:
    """Mint the Tier-2 Steward events. Does not persist them."""
    moment = clock or FixedClock(occupancy.observed_at)
    verified = _count(occupancy, OwnershipStatus.VERIFIED_MACHI_OWNED)
    conflict = _count(occupancy, OwnershipStatus.CONFLICTED)
    unknown = _count(occupancy, OwnershipStatus.UNKNOWN)
    legacy = _count(occupancy, OwnershipStatus.LEGACY_UNVERIFIED)
    other = _count(occupancy, OwnershipStatus.NOT_MACHI_OWNED)
    measured = sum(1 for item in occupancy.resources if _measured(item.size_bytes))
    unresolved = len(occupancy.resources) - measured
    reclaimable = sum(
        1
        for item in occupancy.resources
        if item.reclaimability is Reclaimability.RECLAIMABLE
    )
    kept = len(occupancy.resources) - reclaimable

    def emit(event_type: str, outcome: EventOutcome, payload: Contract) -> EventRecord:
        return _event(
            event_type,
            outcome,
            payload,
            install_id=install_id,
            install_run_id=install_run_id,
            clock=moment,
        )

    events = (
        emit(
            CLASSIFIED_TYPE,
            EventOutcome.PASS,
            ResourceClassifiedPayload(
                resource_count=len(occupancy.resources),
                verified_count=verified,
                conflict_count=conflict,
                unknown_count=unknown,
                legacy_count=legacy,
                not_machi_count=other,
            ),
        ),
        emit(
            CONFLICT_TYPE,
            EventOutcome.FAIL if conflict else EventOutcome.PASS,
            OwnershipConflictPayload(conflict_count=conflict),
        ),
        emit(
            OCCUPANCY_TYPE,
            EventOutcome.PASS,
            OccupancyObservedPayload(
                measured_count=measured,
                unresolved_size_count=unresolved,
                destructive_authorization=False,
            ),
        ),
        emit(
            RECLAIM_TYPE,
            EventOutcome.PASS,
            ReclaimabilityAssessedPayload(
                reclaimable_count=reclaimable,
                not_reclaimable_count=kept,
                destructive_authorization=False,
            ),
        ),
    )
    for event in events:
        if event.privacy is not PrivacyClass.OPERATIONAL:
            raise ValidationError(
                "Steward events must be operational",
                privacy=event.privacy.value,
            )
    return events


def resource_classified(
    occupancy: OccupancyMap,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """The classification summary. Present for callers that want one event."""
    return steward_events(
        occupancy,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )[0]


def ownership_conflict(
    occupancy: OccupancyMap,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """The conflict summary."""
    return steward_events(
        occupancy,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )[1]


def occupancy_observed(
    occupancy: OccupancyMap,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """The occupancy summary. Does not include SAFE storage."""
    return steward_events(
        occupancy,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )[2]


def reclaimability_assessed(
    occupancy: OccupancyMap,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """The reclaimability summary. Does not delete."""
    return steward_events(
        occupancy,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )[3]


def _event(
    event_type: str,
    outcome: EventOutcome,
    payload: Contract,
    *,
    install_id: Maybe[InstallId] | None,
    install_run_id: Maybe[InstallRunId] | None,
    clock: Clock,
) -> EventRecord:
    return EventRecord.create(
        event_type=event_type,
        block_id=STEWARD_BLOCK,
        component_id=STEWARD_COMPONENT,
        outcome=outcome,
        privacy=PrivacyClass.OPERATIONAL,
        payload=payload,
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock,
    )


def _count(occupancy: OccupancyMap, status: OwnershipStatus) -> int:
    return sum(1 for item in occupancy.resources if item.ownership is status)


def _measured(value: object) -> bool:
    return isinstance(value, int)
