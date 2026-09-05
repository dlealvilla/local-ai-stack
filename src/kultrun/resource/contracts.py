"""Workloads, and the reservations that make room for them.

`docs/PRODUCT_VISION.md` §30 requires four quantities to stay separate:
what a workload *requested*, what was *admitted*, what it is *actually
consuming*, and its *peak observed* consumption. They are different facts
with different uses — reservations provide scheduling safety, observation
provides learning — and collapsing them is how a scheduler starts lying.

Here, the request lives on the workload and the grant lives on the
reservation. Observation and peak arrive at Milestone 11, when there is
something running to observe.

**Workload types are generic from v1** even though only inference executes
before Milestone 4. `docs/PRODUCT_VISION.md` §31 asks for the job model to
allow extension, and adding training to an enum is free while retrofitting
a type parameter into a finished resource manager is not.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe
from kultrun.model.contracts import ModelId


class WorkloadId(EntityId):
    """Identifies one unit of work competing for host resources."""

    prefix = "wl"


class ReservationId(EntityId):
    """Identifies one admitted claim on host resources."""

    prefix = "resv"


class WorkloadType(StrEnum):
    """What sort of work this is. Only inference executes before Milestone 4."""

    INFERENCE = "inference"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
    INDEXING = "indexing"
    BENCHMARK = "benchmark"
    TRAINING = "training"
    EVALUATION = "evaluation"
    QUANTIZATION = "quantization"
    DISTILLATION = "distillation"
    AGENT_WORKER = "agent_worker"


class ReservationState(StrEnum):
    """Where a reservation is in its life.

    ``FAILED`` is distinct from ``RELEASED``: a reservation whose workload
    failed to start must be rolled back, and one that was cleanly released
    must not be confused with it during reconciliation.
    """

    REQUESTED = "requested"
    ADMITTED = "admitted"
    ACTIVE = "active"
    RELEASED = "released"
    FAILED = "failed"


@contract(kind="resource.workload", version=1)
@dataclass(frozen=True, slots=True)
class Workload(Contract):
    """One unit of work asking for room to run."""

    workload_id: WorkloadId = meaning("platform-minted identity of this work")
    host_id: HostId = meaning("the host it would run on")
    workload_type: WorkloadType = meaning("what sort of work it is")
    created_at: dt.datetime = meaning("when it was requested, UTC")
    model_id: ModelId | None = meaning(
        "the model it serves, for workload types that have one", default=None
    )
    priority: int = meaning(
        "relative importance; higher wins when capacity is contested", default=0
    )


@contract(kind="resource.workload_profile", version=1)
@dataclass(frozen=True, slots=True)
class WorkloadProfile(Contract):
    """How a workload is expected to be used.

    The same model on the same hardware has different safe settings for an
    interactive assistant, a batch extraction job and a high-throughput
    classifier. Nothing consumes this before Milestone 11; it exists now
    because capacity recommendations must be able to accept it without
    every signature changing.
    """

    average_input_tokens: Maybe[int] = meaning("typical prompt length")
    average_output_tokens: Maybe[int] = meaning("typical completion length")
    maximum_input_tokens: Maybe[int] = meaning("largest prompt to plan for")
    maximum_output_tokens: Maybe[int] = meaning("largest completion to plan for")
    requests_per_second: Maybe[float] = meaning("expected steady request rate")
    expected_concurrency: Maybe[int] = meaning("expected simultaneous requests")
    streaming: Maybe[bool] = meaning("whether responses are streamed")
    target_ttft_seconds: Maybe[float] = meaning("time-to-first-token objective")


@contract(kind="resource.reservation", version=1)
@dataclass(frozen=True, slots=True)
class ResourceReservation(Contract):
    """Resources granted to a workload, held until it releases them.

    These are *admitted* quantities, not requested and not observed. They
    exist independently of what the workload actually uses, which is what
    makes them safe to schedule against.

    Per-accelerator by index, never a total. Aggregating device memory is
    only valid where the interconnect permits it, and a reservation that
    does not say which device it is on cannot prevent oversubscription of
    that device.
    """

    reservation_id: ReservationId = meaning("platform-minted identity of this grant")
    workload_id: WorkloadId = meaning("the workload it was granted to")
    host_id: HostId = meaning("the host whose resources are held")
    state: ReservationState = meaning("where this reservation is in its life")
    created_at: dt.datetime = meaning("when it was admitted, UTC")
    admitted_vram_bytes: Maybe[int] = meaning(
        "accelerator memory granted, on the device named below"
    )
    admitted_ram_bytes: Maybe[int] = meaning("system memory granted")
    admitted_storage_bytes: Maybe[int] = meaning("pool storage granted")
    accelerator_index: int | None = meaning(
        "which device the accelerator memory is held on; absent for "
        "workloads that need none",
        default=None,
    )
    released_at: dt.datetime | None = meaning(
        "when the grant ended; absent while it is still held", default=None
    )
