"""Capacity events. Operational metadata only. No paths and no file content."""

from __future__ import annotations

from dataclasses import dataclass

from machi.capacity.contracts import CapacityEnvelope, EvidenceStrength, SonarStatus
from machi.kernel.clock import Clock, FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, is_resolved

CAPACITY_BLOCK = "4"
CAPACITY_COMPONENT = "4"
OBSERVED_TYPE = "capacity.observed"
ENVELOPE_TYPE = "capacity.safe_envelope.derived"
SONAR_TYPE = "capacity.storage_sonar.completed"


@contract(kind="capacity.observed", version=1)
@dataclass(frozen=True, slots=True)
class CapacityObservedPayload(Contract):
    """Counts only. Resource paths stay off the event."""

    accelerator_count: int = meaning("per-device rows in the envelope")
    storage_domain_count: int = meaning(
        "backing domains, not a sum of mount free space"
    )
    unresolved_safe_count: int = meaning("rows whose safe_bytes stayed Unresolved")
    evidence_id: str = meaning("snapshot identity")


@contract(kind="capacity.safe_envelope.derived", version=1)
@dataclass(frozen=True, slots=True)
class SafeEnvelopePayload(Contract):
    """Whether SAFE values were derived. Not the byte values of customer trees."""

    memory_resolved: bool = meaning("system RAM safe ceiling is known")
    storage_resolved_count: int = meaning("storage domains with a known safe ceiling")
    input_token: str = meaning("inputs this snapshot was based on")


@contract(kind="capacity.storage_sonar.completed", version=1)
@dataclass(frozen=True, slots=True)
class SonarCompletedPayload(Contract):
    """Sonar outcome counts. Not a benchmark and not a path."""

    corroborated_count: int = meaning(
        "domains where a write signed off the reported ceiling"
    )
    contradicted_count: int = meaning(
        "domains where a hard failure downgraded the report"
    )
    not_attempted_count: int = meaning("domains that were not written")


def capacity_events(
    envelope: CapacityEnvelope,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> tuple[EventRecord, ...]:
    """Mint Capacity events. Does not persist them."""
    moment = clock or FixedClock(envelope.observed_at)
    unresolved = 0
    if envelope.memory.strength is EvidenceStrength.UNRESOLVED:
        unresolved += 1
    unresolved += sum(
        1
        for item in envelope.accelerators
        if item.strength is EvidenceStrength.UNRESOLVED
    )
    unresolved += sum(
        1 for item in envelope.storage_domains if not is_resolved(item.safe_bytes)
    )
    storage_resolved = sum(
        1 for item in envelope.storage_domains if is_resolved(item.safe_bytes)
    )
    corroborated = sum(
        1
        for item in envelope.storage_domains
        if item.sonar.status is SonarStatus.CORROBORATED
    )
    contradicted = sum(
        1
        for item in envelope.storage_domains
        if item.sonar.status is SonarStatus.CONTRADICTED
    )
    skipped = sum(
        1
        for item in envelope.storage_domains
        if item.sonar.status is SonarStatus.NOT_ATTEMPTED
    )

    def emit(event_type: str, payload: Contract) -> EventRecord:
        event = EventRecord.create(
            event_type=event_type,
            block_id=CAPACITY_BLOCK,
            component_id=CAPACITY_COMPONENT,
            outcome=EventOutcome.PASS,
            privacy=PrivacyClass.OPERATIONAL,
            payload=payload,
            install_id=install_id,
            install_run_id=install_run_id,
            clock=moment,
        )
        if event.privacy is not PrivacyClass.OPERATIONAL:
            raise ValidationError("capacity events must be operational")
        return event

    return (
        emit(
            OBSERVED_TYPE,
            CapacityObservedPayload(
                accelerator_count=len(envelope.accelerators),
                storage_domain_count=len(envelope.storage_domains),
                unresolved_safe_count=unresolved,
                evidence_id=envelope.evidence_id,
            ),
        ),
        emit(
            ENVELOPE_TYPE,
            SafeEnvelopePayload(
                memory_resolved=is_resolved(envelope.memory.safe_bytes),
                storage_resolved_count=storage_resolved,
                input_token=envelope.input_token,
            ),
        ),
        emit(
            SONAR_TYPE,
            SonarCompletedPayload(
                corroborated_count=corroborated,
                contradicted_count=contradicted,
                not_attempted_count=skipped,
            ),
        ),
    )
