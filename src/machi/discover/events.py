"""Discover events for OS/architecture observation (MACHI 2.1.1).

OS family and CPU architecture are non-identifying machine facts.
Privacy is ``public_ops``. Hostname, paths, and customer content stay out.
HostId stays unresolved. Composition supplies Install correlation.
"""

from __future__ import annotations

from dataclasses import dataclass

from machi.discover.contracts import (
    CpuArchitecture,
    ObservationStatus,
    OSArchitectureObservation,
    OSFamily,
)
from machi.kernel.clock import Clock, FixedClock
from machi.kernel.errors import ValidationError
from machi.kernel.events import EventOutcome, EventRecord
from machi.kernel.ids import InstallId, InstallRunId
from machi.kernel.privacy import PrivacyClass
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

DISCOVER_BLOCK = "2"
OS_ARCH_COMPONENT = "2.1.1"
OS_ARCH_OBSERVED_TYPE = "discover.os_arch.observed"


@contract(kind="discover.os_arch.observed", version=1)
@dataclass(frozen=True, slots=True)
class OSArchObservedPayload(Contract):
    """Safe public operational body for an OS/arch observation."""

    os_family: Maybe[OSFamily] = meaning(
        "normalized OS family; Unresolved when unobserved or unrecognized"
    )
    architecture: Maybe[CpuArchitecture] = meaning(
        "normalized CPU architecture; Unresolved when unobserved or unrecognized"
    )
    os_status: ObservationStatus = meaning("how the OS family was normalized")
    architecture_status: ObservationStatus = meaning(
        "how the CPU architecture was normalized"
    )
    raw_os: str = meaning("narrow raw OS string; not a hostname or path")
    raw_architecture: str = meaning("narrow raw architecture string")
    observer: str = meaning("adapter identifier, for example native")


def os_arch_observed(
    observation: OSArchitectureObservation,
    *,
    install_id: Maybe[InstallId] | None = None,
    install_run_id: Maybe[InstallRunId] | None = None,
    clock: Clock | None = None,
) -> EventRecord:
    """Mint the OS/arch event. Does not persist it. Does not mint HostId."""
    event = EventRecord.create(
        event_type=OS_ARCH_OBSERVED_TYPE,
        block_id=DISCOVER_BLOCK,
        component_id=OS_ARCH_COMPONENT,
        outcome=EventOutcome.PASS,
        privacy=PrivacyClass.PUBLIC_OPS,
        payload=OSArchObservedPayload(
            os_family=observation.os_family,
            architecture=observation.architecture,
            os_status=observation.os_status,
            architecture_status=observation.architecture_status,
            raw_os=observation.raw_os,
            raw_architecture=observation.raw_architecture,
            observer=observation.observer,
        ),
        install_id=install_id,
        install_run_id=install_run_id,
        clock=clock or FixedClock(observation.observed_at),
    )
    if event.privacy is not PrivacyClass.PUBLIC_OPS:
        raise ValidationError(
            "discover.os_arch.observed must be public_ops",
            privacy=event.privacy.value,
        )
    return event
