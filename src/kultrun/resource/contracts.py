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
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import ArtifactId, MemoryPlacement, ModelId


class WorkloadId(EntityId):
    """Identifies one unit of work competing for host resources."""

    prefix = "wl"


class ReservationId(EntityId):
    """Identifies one admitted claim on host resources."""

    prefix = "resv"


class RequestId(EntityId):
    """Identifies one admission request. Not an artifact or reservation."""

    prefix = "rreq"


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
    RUNTIME_PROVISIONING = "runtime_provisioning"
    MODEL_ACQUISITION = "model_acquisition"


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


class AdmissionVerdict(StrEnum):
    """Whether the workload may consume resources now."""

    ADMITTED = "admitted"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class LedgerHealth(StrEnum):
    """Current capacity versus ACTIVE reservations. Not a reservation state."""

    WITHIN_CAPACITY = "within_capacity"
    OVERCOMMITTED = "overcommitted"
    UNRESOLVED = "unresolved"


class AdmissionReason(StrEnum):
    """Typed explanation for a non-admitted (or reused) decision."""

    ADMITTED = "admitted"
    REUSED = "reused"
    INSUFFICIENT_SAFE_RAM = "insufficient_safe_ram"
    INSUFFICIENT_SAFE_ACCELERATOR = "insufficient_safe_accelerator"
    INSUFFICIENT_SAFE_UNIFIED = "insufficient_safe_unified"
    SELECTED_ACCELERATOR_UNKNOWN = "incompatible_placement"
    ARTIFACT_NOT_STORED = "artifact_not_stored"
    LEDGER_OVERCOMMITTED = "ledger_overcommitted"
    UNRESOLVED_SAFE_CAPACITY = "unresolved_safe_capacity"
    UNRESOLVED_REQUIREMENT = "unresolved_requirement"
    PLACEMENT_UNDETERMINED = "placement_undetermined"
    INSUFFICIENT_SAFE_STORAGE = "insufficient_safe_storage"


POLICY_VERSION = "1.5A.0"


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
    request_id: RequestId | None = meaning(
        "the admission request that produced this grant", default=None
    )
    artifact_id: ArtifactId | None = meaning(
        "the stored model these resources are committed for", default=None
    )
    plan_fingerprint: Maybe[str] = meaning(
        "identity of the plan assumptions at admission", default=NOT_PROVIDED
    )
    admitted_unified_bytes: Maybe[int] = meaning(
        "unified memory granted; never a VRAM alias", default=NOT_PROVIDED
    )
    admitted_cpu: Maybe[int] = meaning(
        "CPU commitment; unresolved and non-load-bearing in v0",
        default=NOT_PROVIDED,
    )
    host_fingerprint: Maybe[str] = meaning(
        "capacity envelope identity at admission", default=NOT_PROVIDED
    )
    capacity_policy_version: Maybe[str] = meaning(
        "headroom policy in force when admitted", default=NOT_PROVIDED
    )
    admission_policy_version: Maybe[str] = meaning(
        "admission arithmetic version", default=NOT_PROVIDED
    )
    safe_ram_at_admission: Maybe[int] = meaning(
        "SAFE RAM observed when admitted", default=NOT_PROVIDED
    )
    safe_accelerator_at_admission: Maybe[int] = meaning(
        "SAFE device memory on the selected accelerator when admitted",
        default=NOT_PROVIDED,
    )
    reserved_ram_before: Maybe[int] = meaning(
        "ACTIVE RAM already reserved before this grant", default=NOT_PROVIDED
    )
    reserved_accelerator_before: Maybe[int] = meaning(
        "ACTIVE device memory already reserved on the selected accelerator",
        default=NOT_PROVIDED,
    )
    available_ram_after: Maybe[int] = meaning(
        "RAM remaining for new work after this grant; never negative",
        default=NOT_PROVIDED,
    )
    available_accelerator_after: Maybe[int] = meaning(
        "device memory remaining for new work after this grant; never negative",
        default=NOT_PROVIDED,
    )
    release_reason: Maybe[str] = meaning(
        "why the grant ended, when it has", default=NOT_PROVIDED
    )
    estimator_provider: Maybe[str] = meaning(
        "estimator that produced the requirement", default=NOT_PROVIDED
    )
    logical_name: Maybe[str] = meaning(
        "catalog name of the stored candidate", default=NOT_PROVIDED
    )
    quantization: Maybe[str] = meaning("variant reserved against", default=NOT_PROVIDED)
    model_revision: Maybe[str] = meaning(
        "artifact revision reserved against", default=NOT_PROVIDED
    )
    storage_pool_mount: Maybe[str] = meaning(
        "destination StoragePool mount for storage grants", default=NOT_PROVIDED
    )
    storage_quota_identity: Maybe[str] = meaning(
        "quota domain this storage grant spends from", default=NOT_PROVIDED
    )


@contract(kind="resource.request", version=2)
@dataclass(frozen=True, slots=True)
class ResourceRequest(Contract):
    """One future workload's resource commitment. Not a ranking, not a launch.

    Amounts are derived server-side from a stored artifact and a plan.
    Unknown never becomes zero. Stored artifact disk is not requested again.
    """

    request_id: RequestId = meaning("idempotency identity of this admission")
    host_id: HostId = meaning("the host whose SAFE capacity is considered")
    plan_fingerprint: str = meaning("assumptions that produced these amounts")
    placement: MemoryPlacement = meaning("device strategy the plan selected")
    ram_bytes: Maybe[int] = meaning("host memory requested; unknown is not zero")
    accelerator_bytes: Maybe[int] = meaning(
        "device memory on the selected accelerator; never a GPU sum"
    )
    unified_bytes: Maybe[int] = meaning(
        "unified memory when that is the placement; never fake VRAM"
    )
    artifact_id: ArtifactId | None = meaning(
        "the STORED artifact this would serve; absent for storage-only work",
        default=None,
    )
    model_id: ModelId | None = meaning(
        "canonical model identity when this work serves one", default=None
    )
    logical_name: Maybe[str] = meaning("catalog name", default=NOT_PROVIDED)
    runtime: Maybe[str] = meaning(
        "proposed runtime, for provenance", default=NOT_PROVIDED
    )
    accelerator_index: int | None = meaning(
        "assigned device for discrete GPU; none for CPU-only", default=None
    )
    cpu: Maybe[int] = meaning(
        "CPU requirement; unresolved and non-load-bearing in v0",
        default=NOT_PROVIDED,
    )
    incremental_storage_bytes: Maybe[int] = meaning(
        "bytes this work would consume on the named pool",
        default=NOT_PROVIDED,
    )
    storage_pool_mount: Maybe[str] = meaning(
        "destination StoragePool; required when storage is load-bearing",
        default=NOT_PROVIDED,
    )
    storage_quota_identity: Maybe[str] = meaning(
        "quota domain of the destination pool", default=NOT_PROVIDED
    )
    port_count: Maybe[int] = meaning(
        "future endpoint/port seam; unused in v0", default=NOT_PROVIDED
    )
    estimator_provider: Maybe[str] = meaning(
        "estimator that produced the requirement", default=NOT_PROVIDED
    )
    plan_version: Maybe[str] = meaning(
        "selection/plan policy version", default=NOT_PROVIDED
    )
    model_revision: Maybe[str] = meaning("artifact revision", default=NOT_PROVIDED)
    quantization: Maybe[str] = meaning("variant", default=NOT_PROVIDED)
    context_tokens: Maybe[int] = meaning(
        "context the estimate assumed", default=NOT_PROVIDED
    )
    capacity_policy_version: Maybe[str] = meaning(
        "headroom policy of the envelope", default=NOT_PROVIDED
    )
    host_fingerprint: Maybe[str] = meaning(
        "envelope identity at request time", default=NOT_PROVIDED
    )
    workload_type: WorkloadType = meaning(
        "generic job type; inference is the v0 case", default=WorkloadType.INFERENCE
    )


@contract(kind="resource.admission_decision", version=1)
@dataclass(frozen=True, slots=True)
class AdmissionDecision(Contract):
    """Explainable admit / reject / unresolved. Not a boolean."""

    verdict: AdmissionVerdict = meaning("whether the request may consume resources now")
    request_id: RequestId = meaning("the request this decides")
    host_id: HostId = meaning("the host the decision is for")
    ledger_health: LedgerHealth = meaning("ACTIVE reservations versus current SAFE")
    reasons: tuple[str, ...] = meaning("human-readable explanation")
    reason_code: Maybe[str] = meaning("typed reason", default=NOT_PROVIDED)
    reservation: ResourceReservation | None = meaning(
        "the grant, when admitted", default=None
    )
    reused: bool = meaning(
        "true when an existing ACTIVE grant was returned", default=False
    )
    serving: bool = meaning(
        "always false in 1.5A; a reservation is not a running instance",
        default=False,
    )


@contract(kind="resource.device_summary", version=1)
@dataclass(frozen=True, slots=True)
class DeviceResourceSummary(Contract):
    """SAFE / RESERVED / AVAILABLE for one accelerator. Never a GPU sum."""

    index: int = meaning("which assigned accelerator")
    safe_bytes: Maybe[int] = meaning("current SAFE device memory")
    reserved_bytes: int = meaning("sum of ACTIVE grants on this device")
    available_bytes: Maybe[int] = meaning(
        "SAFE minus reserved, or 0 when overcommitted; never negative"
    )
    vendor: Maybe[str] = meaning(
        "accelerator family from host facts, when known", default=NOT_PROVIDED
    )
    device_identity: Maybe[str] = meaning(
        "reported device model, when known", default=NOT_PROVIDED
    )


@contract(kind="resource.pool_summary", version=1)
@dataclass(frozen=True, slots=True)
class PoolResourceSummary(Contract):
    """SAFE / RESERVED / AVAILABLE for one storage pool."""

    mount_point: str = meaning("pool mount")
    reserved_bytes: int = meaning("ACTIVE grants on this pool")
    quota_identity: Maybe[str] = meaning("quota domain", default=NOT_PROVIDED)
    safe_bytes: Maybe[int] = meaning(
        "current SAFE storage on this pool", default=NOT_PROVIDED
    )
    available_bytes: Maybe[int] = meaning(
        "SAFE minus reserved; never negative", default=NOT_PROVIDED
    )


@contract(kind="resource.summary", version=1)
@dataclass(frozen=True, slots=True)
class ResourceSummary(Contract):
    """Current ledger. Available is recomputed; it is never stored as truth."""

    host_id: HostId = meaning("which host this describes")
    host_fingerprint: str = meaning("current envelope identity")
    health: LedgerHealth = meaning("whether ACTIVE grants fit current SAFE")
    policy_version: str = meaning("admission arithmetic version")
    capacity_policy_version: str = meaning("headroom policy of the envelope")
    safe_ram_bytes: Maybe[int] = meaning("current SAFE system memory")
    reserved_ram_bytes: int = meaning("sum of ACTIVE RAM grants")
    available_ram_bytes: Maybe[int] = meaning(
        "SAFE RAM minus reserved, or 0 when overcommitted; never negative"
    )
    accelerators: tuple[DeviceResourceSummary, ...] = meaning(
        "per-device accelerator ledger", default=()
    )
    safe_unified_bytes: Maybe[int] = meaning(
        "current SAFE unified memory", default=NOT_PROVIDED
    )
    reserved_unified_bytes: int = meaning("sum of ACTIVE unified grants", default=0)
    available_unified_bytes: Maybe[int] = meaning(
        "SAFE unified minus reserved, or 0 when overcommitted", default=NOT_PROVIDED
    )
    reserved_incremental_storage_bytes: int = meaning(
        "ACTIVE incremental storage only; not stored artifact bytes", default=0
    )
    active_count: int = meaning("ACTIVE reservations", default=0)
    serving: bool = meaning("always false; reserved is not running", default=False)
    running_instances: int = meaning("always 0 in 1.5A", default=0)
    snapshot_basis: str = meaning(
        "fingerprint of SAFE envelope plus ACTIVE commitments at read time",
        default="",
    )
    active_reservation_ids: tuple[str, ...] = meaning(
        "ACTIVE reservation identities included in this view", default=()
    )
    excluded_reservation_id: Maybe[str] = meaning(
        "own reservation omitted so revalidation does not double-subtract",
        default=NOT_PROVIDED,
    )
    observed_at: dt.datetime | None = meaning(
        "when this derived current-capacity view was observed, UTC", default=None
    )
    safe_storage_bytes: Maybe[int] = meaning(
        "SAFE free space from the current storage authority", default=NOT_PROVIDED
    )
    available_storage_bytes: Maybe[int] = meaning(
        "SAFE storage minus ACTIVE incremental reservations; not stored "
        "artifact bytes already reflected in free space",
        default=NOT_PROVIDED,
    )
    storage_source: Maybe[str] = meaning(
        "pool identity that supplied storage availability", default=NOT_PROVIDED
    )
    snapshot_version: str = meaning(
        "arithmetic version of this derived current-capacity view", default=""
    )
    pools: tuple[PoolResourceSummary, ...] = meaning(
        "per-pool storage ledger; never a host-wide scalar", default=()
    )
