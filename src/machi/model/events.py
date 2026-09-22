"""Model events. Operational metadata only. No tokens or card text."""

from __future__ import annotations

from dataclasses import dataclass

from machi.kernel.clock import Clock, FixedClock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.model.contracts import (
    AvailableModels,
    ModelArtifact,
    ModelFailure,
    ModelSelection,
)

MODEL_BLOCK = "6"
MODEL_COMPONENT = "6"
INSPECTED_TYPE = "model.inspected"
SELECTED_TYPE = "model.selected"
ACQUIRED_TYPE = "model.acquisition.completed"
ACQUIRE_FAILED_TYPE = "model.acquisition.failed"
INTEGRITY_FAILED_TYPE = "model.artifact.integrity_failed"


@contract(kind="model.inspected", version=1)
@dataclass(frozen=True, slots=True)
class ModelInspectedPayload(Contract):
    """Counts and states. No repository secrets."""

    entry_count: int = meaning("candidates in this snapshot")
    compatible_count: int = meaning("entries whose technical state is compatible")
    input_token: str = meaning("snapshot input fingerprint")


@contract(kind="model.selected", version=1)
@dataclass(frozen=True, slots=True)
class ModelSelectedPayload(Contract):
    """Selection identity. Not a running server."""

    selection_id: str = meaning("selection identity")
    model_id: str = meaning("logical model")
    state: str = meaning("compatibility state")


@contract(kind="model.acquisition.completed", version=1)
@dataclass(frozen=True, slots=True)
class ModelAcquiredPayload(Contract):
    """Stored identity and size. No source credential and no host path."""

    artifact_id: str = meaning("warehouse artifact")
    total_bytes: int = meaning("stored bytes")
    lifecycle: str = meaning("stored")


@contract(kind="model.acquisition.failed", version=1)
@dataclass(frozen=True, slots=True)
class ModelAcquireFailedPayload(Contract):
    """Why acquisition stopped. No token and no path."""

    failure: str = meaning("typed failure code")


@contract(kind="model.artifact.integrity_failed", version=1)
@dataclass(frozen=True, slots=True)
class ModelIntegrityFailedPayload(Contract):
    """An existing manifest no longer matches. It was not rewritten."""

    artifact_id: str = meaning("artifact that failed verification")


def model_events(
    snapshot: AvailableModels,
    selection: ModelSelection | None = None,
    *,
    clock: Clock | None = None,
) -> tuple[EventRecord, ...]:
    moment = clock or FixedClock(snapshot.observed_at)
    compatible = sum(
        1
        for entry in snapshot.entries
        if entry.compatibility.technical_state.value == "compatible"
    )

    def emit(event_type: str, payload: Contract) -> EventRecord:
        return EventRecord.create(
            event_type=event_type,
            block_id=MODEL_BLOCK,
            component_id=MODEL_COMPONENT,
            outcome=EventOutcome.PASS,
            privacy=PrivacyClass.OPERATIONAL,
            payload=payload,
            clock=moment,
        )

    records = [
        emit(
            INSPECTED_TYPE,
            ModelInspectedPayload(
                entry_count=len(snapshot.entries),
                compatible_count=compatible,
                input_token=snapshot.input_token,
            ),
        )
    ]
    if selection is not None:
        records.append(
            emit(
                SELECTED_TYPE,
                ModelSelectedPayload(
                    selection_id=selection.selection_id,
                    model_id=selection.model_id,
                    state=selection.compatibility_state.value,
                ),
            )
        )
    return tuple(records)


def acquisition_events(
    *,
    artifact: ModelArtifact | None,
    failure: ModelFailure,
    artifact_id: str | None,
    clock: Clock,
) -> tuple[EventRecord, ...]:
    """Record acquire outcome without source secrets."""
    if failure is ModelFailure.INTEGRITY_FAILED and artifact_id:
        return (
            EventRecord.create(
                event_type=INTEGRITY_FAILED_TYPE,
                block_id=MODEL_BLOCK,
                component_id=MODEL_COMPONENT,
                outcome=EventOutcome.FAIL,
                privacy=PrivacyClass.OPERATIONAL,
                payload=ModelIntegrityFailedPayload(artifact_id=artifact_id),
                clock=clock,
            ),
        )
    if artifact is None or failure is not ModelFailure.NONE:
        return (
            EventRecord.create(
                event_type=ACQUIRE_FAILED_TYPE,
                block_id=MODEL_BLOCK,
                component_id=MODEL_COMPONENT,
                outcome=EventOutcome.FAIL,
                privacy=PrivacyClass.OPERATIONAL,
                payload=ModelAcquireFailedPayload(failure=failure.value),
                clock=clock,
            ),
        )
    return (
        EventRecord.create(
            event_type=ACQUIRED_TYPE,
            block_id=MODEL_BLOCK,
            component_id=MODEL_COMPONENT,
            outcome=EventOutcome.PASS,
            privacy=PrivacyClass.OPERATIONAL,
            payload=ModelAcquiredPayload(
                artifact_id=artifact.artifact_id,
                total_bytes=artifact.total_bytes,
                lifecycle=artifact.lifecycle.value,
            ),
            clock=clock,
        ),
    )
