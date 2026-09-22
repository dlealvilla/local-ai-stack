"""Foundation events. Operational metadata only."""

from __future__ import annotations

from dataclasses import dataclass

from machi.foundation.contracts import FoundationSet
from machi.kernel.clock import Clock, FixedClock
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe, is_resolved

FOUNDATION_BLOCK = "5"
FOUNDATION_COMPONENT = "5"
INSPECTED_TYPE = "foundation.inspected"
SELECTED_TYPE = "foundation.selected"


@contract(kind="foundation.inspected", version=1)
@dataclass(frozen=True, slots=True)
class FoundationInspectedPayload(Contract):
    """Support outcome. No environment dumps."""

    support: str = meaning("support state")
    failure: str = meaning("typed failure or none")
    backend: str = meaning("cuda, rocm, or unresolved")


@contract(kind="foundation.selected", version=1)
@dataclass(frozen=True, slots=True)
class FoundationSelectedPayload(Contract):
    """Macropath decision identity. Not a model and not a server."""

    selection_id: str = meaning("selection identity")
    engine: str = meaning("vllm")
    executor: str = meaning("native_process")


def foundation_events(
    result: FoundationSet,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> tuple[EventRecord, ...]:
    moment = clock or FixedClock(result.observed_at)
    backend = result.selection.backend
    backend_text = backend.value if is_resolved(backend) else "unresolved"

    def emit(event_type: str, payload: Contract) -> EventRecord:
        return EventRecord.create(
            event_type=event_type,
            block_id=FOUNDATION_BLOCK,
            component_id=FOUNDATION_COMPONENT,
            outcome=EventOutcome.PASS,
            privacy=PrivacyClass.OPERATIONAL,
            payload=payload,
            install_id=install_id,
            install_run_id=install_run_id,
            clock=moment,
        )

    return (
        emit(
            INSPECTED_TYPE,
            FoundationInspectedPayload(
                support=result.selection.support.value,
                failure=result.selection.failure.value,
                backend=backend_text,
            ),
        ),
        emit(
            SELECTED_TYPE,
            FoundationSelectedPayload(
                selection_id=result.selection.selection_id,
                engine=result.selection.engine.value,
                executor=result.selection.executor.value,
            ),
        ),
    )
