"""Typed operational observations. Metadata only; never customer content.

These records copy facts the control plane already produced. They do not
recalculate capacity, re-discover hardware, or authorize a deployment.
Numeric memory is integer bytes. Unknown stays null; it is never zero.

Value provenance is in the column names, not a collapsed single number:

``factual_`` / ``estimated_`` / ``measured_`` / ``derived_`` / ``calibrated_``.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class ObservationId(EntityId):
    """Identity of one telemetry observation row."""

    prefix = "tobs"


class TelemetryRunId(EntityId):
    """Identity of one deployment or probe run recorded for analysis."""

    prefix = "trun"


class TelemetryEventId(EntityId):
    """Identity of one lifecycle timing event."""

    prefix = "tevt"


class ValueProvenance(StrEnum):
    """How a numeric memory value was obtained. Columns stay distinct."""

    FACTUAL = "factual"
    ESTIMATED = "estimated"
    MEASURED = "measured"
    DERIVED = "derived"
    CALIBRATED = "calibrated"


class DeploymentRunKind(StrEnum):
    """A serving deployment is not a runtime-memory probe."""

    DEPLOYMENT = "deployment"
    RUNTIME_MEMORY_PROBE = "runtime_memory_probe"


class DeploymentEventType(StrEnum):
    """Major lifecycle milestones. Not a generic event bus."""

    HOST_DISCOVERY_COMPLETED = "HOST_DISCOVERY_COMPLETED"
    FOUNDATION_SELECTED = "FOUNDATION_SELECTED"
    RUNTIME_PROVISIONED = "RUNTIME_PROVISIONED"
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"
    MODEL_DISCOVERY_COMPLETED = "MODEL_DISCOVERY_COMPLETED"
    MODEL_SIZING_COMPLETED = "MODEL_SIZING_COMPLETED"
    RUNTIME_MEMORY_PROBE_STARTED = "RUNTIME_MEMORY_PROBE_STARTED"
    RUNTIME_MEMORY_PROBE_COMPLETED = "RUNTIME_MEMORY_PROBE_COMPLETED"
    RUNTIME_MEMORY_PROBE_FAILED = "RUNTIME_MEMORY_PROBE_FAILED"
    AVAILABLE_MODELS_COMPUTED = "AVAILABLE_MODELS_COMPUTED"
    MODEL_SELECTED = "MODEL_SELECTED"
    ARTIFACT_ACQUISITION_STARTED = "ARTIFACT_ACQUISITION_STARTED"
    ARTIFACT_ACQUISITION_COMPLETED = "ARTIFACT_ACQUISITION_COMPLETED"
    RESOURCE_ADMITTED = "RESOURCE_ADMITTED"
    RUNTIME_LAUNCH_STARTED = "RUNTIME_LAUNCH_STARTED"
    RUNTIME_READY = "RUNTIME_READY"
    RUNTIME_FAILED = "RUNTIME_FAILED"
    INFERENCE_INSTANCE_STOPPED = "INFERENCE_INSTANCE_STOPPED"
    RESERVATION_RELEASED = "RESERVATION_RELEASED"


@contract(kind="config.telemetry", version=1)
@dataclass(frozen=True, slots=True)
class TelemetrySettings(Contract):
    """Local operational telemetry. Path defaults to the state root."""

    enabled: bool = meaning(
        "whether this installation writes local operational telemetry",
        default=True,
    )
    database_path: Maybe[str] = meaning(
        "explicit sqlite path; unresolved means "
        "<state_root>/telemetry/kultrun-telemetry.sqlite3",
        default=NOT_PROVIDED,
    )


@contract(kind="telemetry.status", version=1)
@dataclass(frozen=True, slots=True)
class TelemetryStatus(Contract):
    """What the local telemetry store reports about itself."""

    enabled: bool = meaning("whether local telemetry is configured on")
    available: bool = meaning("whether the store is open and usable")
    database_path: str | None = meaning(
        "resolved sqlite path, when one was chosen", default=None
    )
    applied_version: int | None = meaning(
        "highest applied migration version, when the database opened",
        default=None,
    )
    last_error: str | None = meaning(
        "most recent persistence failure; absent means none recorded",
        default=None,
    )
    host_observations: int = meaning("rows in host_observation", default=0)
    runtime_observations: int = meaning("rows in runtime_observation", default=0)
    capacity_snapshots: int = meaning("rows in capacity_snapshot", default=0)
    model_sizing_observations: int = meaning(
        "rows in model_sizing_observation", default=0
    )
    runtime_memory_profiles: int = meaning("rows in runtime_memory_profile", default=0)
    deployment_runs: int = meaning("rows in deployment_run", default=0)
    deployment_events: int = meaning("rows in deployment_event", default=0)


@contract(kind="telemetry.host_observation", version=1)
@dataclass(frozen=True, slots=True)
class HostObservation(Contract):
    """A copy of Host Discovery facts. Does not re-probe hardware."""

    observation_id: ObservationId = meaning("identity of this observation")
    observed_at: dt.datetime = meaning("when discovery facts were recorded, UTC")
    host_id: HostId = meaning("host these facts describe")
    host_fingerprint: str | None = meaning(
        "host fingerprint at observation", default=None
    )
    duration_ms: int | None = meaning(
        "host-discovery duration when the boundary was timed", default=None
    )
    os_name: str | None = meaning("operating system family", default=None)
    os_version: str | None = meaning("operating system version", default=None)
    architecture: str | None = meaning("processor architecture", default=None)
    cpu_vendor: str | None = meaning("processor vendor as reported", default=None)
    cpu_model: str | None = meaning("processor model as reported", default=None)
    cpu_physical_cores: int | None = meaning("physical core count", default=None)
    cpu_logical_cores: int | None = meaning("logical processor count", default=None)
    ram_total_bytes: int | None = meaning(
        "factual installed system memory", default=None
    )
    ram_available_bytes: int | None = meaning(
        "factual free system memory at detection", default=None
    )
    ram_limit_bytes: int | None = meaning(
        "execution-context memory ceiling when reported", default=None
    )
    storage_mount_point: str | None = meaning(
        "primary reported mount; not a StoragePool", default=None
    )
    storage_total_bytes: int | None = meaning(
        "factual filesystem size of that mount", default=None
    )
    storage_free_bytes: int | None = meaning(
        "factual free space of that mount; never authorizes a write", default=None
    )
    accelerator_count: int | None = meaning(
        "how many accelerators Host Discovery reported", default=None
    )
    gpu_index: int | None = meaning("primary accelerator ordinal", default=None)
    gpu_vendor: str | None = meaning("primary accelerator family", default=None)
    gpu_model: str | None = meaning("primary accelerator model", default=None)
    gpu_architecture: str | None = meaning(
        "primary accelerator architecture when known", default=None
    )
    gpu_total_bytes: int | None = meaning(
        "factual installed device memory", default=None
    )
    driver_version: str | None = meaning("primary accelerator driver", default=None)
    producer_build_version: str | None = meaning(
        "Kultrun build that recorded this observation", default=None
    )


@contract(kind="telemetry.runtime_observation", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeObservation(Contract):
    """A copy of foundation / verification facts. Not a capability profile."""

    observation_id: ObservationId = meaning("identity of this observation")
    observed_at: dt.datetime = meaning("when these runtime facts were recorded, UTC")
    host_id: HostId | None = meaning("host the stack was observed on", default=None)
    host_fingerprint: str | None = meaning(
        "host fingerprint at observation", default=None
    )
    duration_ms: int | None = meaning(
        "foundation/verification duration when timed", default=None
    )
    foundation_id: str | None = meaning(
        "FoundationSelection identity when one exists", default=None
    )
    selection_mode: str | None = meaning("AUTO or MANUAL", default=None)
    runtime: str | None = meaning("runtime family", default=None)
    runtime_version: str | None = meaning("exact runtime version", default=None)
    executor: str | None = meaning("executor identity", default=None)
    installation_id: str | None = meaning("RuntimeInstallation identity", default=None)
    capability_profile_id: str | None = meaning(
        "RuntimeCapabilityProfile identity", default=None
    )
    verification_status: str | None = meaning(
        "effective verification status", default=None
    )
    foundation_role: str | None = meaning(
        "how this stack is being used, e.g. selected_foundation", default=None
    )


@contract(kind="telemetry.capacity_snapshot", version=1)
@dataclass(frozen=True, slots=True)
class CapacitySnapshotObservation(Contract):
    """A copy of a planning CurrentCapacitySnapshot. Does not recalculate."""

    snapshot_id: ObservationId = meaning("identity of this copied snapshot")
    observed_at: dt.datetime = meaning("when the snapshot was copied, UTC")
    host_id: HostId | None = meaning("host the snapshot describes", default=None)
    host_fingerprint: str | None = meaning(
        "envelope / host identity on the snapshot", default=None
    )
    safe_vram_bytes: int | None = meaning(
        "SAFE device memory from the authoritative snapshot", default=None
    )
    committed_vram_bytes: int | None = meaning(
        "ACTIVE reserved device memory from the snapshot", default=None
    )
    available_vram_bytes: int | None = meaning(
        "available device memory from the snapshot", default=None
    )
    safe_ram_bytes: int | None = meaning(
        "SAFE system memory from the snapshot", default=None
    )
    committed_ram_bytes: int | None = meaning(
        "ACTIVE reserved system memory from the snapshot", default=None
    )
    available_ram_bytes: int | None = meaning(
        "available system memory from the snapshot", default=None
    )
    available_storage_bytes: int | None = meaning(
        "available incremental storage from the snapshot", default=None
    )
    active_reservation_count: int | None = meaning(
        "ACTIVE reservation count on the snapshot", default=None
    )
    basis_fingerprint: str | None = meaning(
        "snapshot_basis from the authoritative snapshot", default=None
    )
    accelerator_index: int | None = meaning(
        "device the VRAM figures refer to", default=None
    )


@contract(kind="telemetry.model_sizing_observation", version=1)
@dataclass(frozen=True, slots=True)
class ModelSizingObservation(Contract):
    """One candidate's sizing evidence. Estimator and factual weight stay apart."""

    observation_id: ObservationId = meaning("identity of this observation")
    observed_at: dt.datetime = meaning("when sizing was recorded, UTC")
    model_id: str = meaning("candidate model identity")
    duration_ms: int | None = meaning(
        "sizing duration when the boundary was timed", default=None
    )
    source_model_ref: str | None = meaning("upstream source reference", default=None)
    revision: str | None = meaning("source revision", default=None)
    architecture: str | None = meaning("model architecture family", default=None)
    quantization: str | None = meaning("quantization family", default=None)
    runtime: str | None = meaning("assumed runtime", default=None)
    runtime_version: str | None = meaning("assumed runtime version", default=None)
    requested_context: int | None = meaning("assumed context tokens", default=None)
    concurrency: int | None = meaning("assumed concurrency", default=None)
    factual_weight_bytes: int | None = meaning(
        "factual Safetensors / stored-weight lower bound", default=None
    )
    estimator_mode: str | None = meaning("configured estimator mode", default=None)
    estimator_provider: str | None = meaning(
        "which estimator produced the estimate", default=None
    )
    estimator_version: str | None = meaning("estimator version", default=None)
    estimated_minimum_vram_bytes: int | None = meaning(
        "raw estimator minimum VRAM, when reported", default=None
    )
    estimated_recommended_vram_bytes: int | None = meaning(
        "raw estimator recommended VRAM, when reported", default=None
    )
    estimated_kv_bytes: int | None = meaning(
        "estimated KV cache bytes for the assumed context", default=None
    )
    estimated_runtime_overhead_bytes: int | None = meaning(
        "static estimated runtime overhead", default=None
    )
    estimated_final_requirement_bytes: int | None = meaning(
        "static estimated final VRAM requirement", default=None
    )
    required_ram_bytes: int | None = meaning("required system memory", default=None)
    required_storage_bytes: int | None = meaning(
        "required incremental storage", default=None
    )
    confidence: str | None = meaning("requirement confidence", default=None)
    cheap_filter_result: str | None = meaning(
        "cheap weight-gate outcome when one was produced", default=None
    )
    deep_feasibility_result: str | None = meaning(
        "deep capacity verdict when one was produced", default=None
    )
    capacity_basis: str | None = meaning(
        "capacity snapshot basis used for the comparison", default=None
    )


@contract(kind="telemetry.runtime_memory_profile", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeMemoryObservation(Contract):
    """Append-only copy of a RuntimeMemoryProfile plus calibrated demand.

    The operational profile remains authoritative for planning. This row
    never feeds RuntimeMemoryCalibrationService.
    """

    observation_id: ObservationId = meaning("identity of this analytical copy")
    measured_at: dt.datetime = meaning("when the profile facts were captured, UTC")
    profile_id: str | None = meaning(
        "operational RuntimeMemoryProfile identity", default=None
    )
    model_id: str | None = meaning("sentinel or member model", default=None)
    revision: str | None = meaning("artifact revision probed", default=None)
    architecture: str | None = meaning("model architecture family", default=None)
    quantization: str | None = meaning("quantization family", default=None)
    host_id: HostId | None = meaning("host the probe ran on", default=None)
    host_fingerprint: str | None = meaning(
        "host fingerprint at measurement", default=None
    )
    gpu_model: str | None = meaning("accelerator model at measurement", default=None)
    gpu_architecture: str | None = meaning(
        "accelerator architecture at measurement", default=None
    )
    runtime: str | None = meaning("runtime family", default=None)
    runtime_version: str | None = meaning("exact runtime version", default=None)
    capability_profile_id: str | None = meaning(
        "RuntimeCapabilityProfile bound to the probe", default=None
    )
    context_tokens: int | None = meaning("context the probe assumed", default=None)
    concurrency: int | None = meaning("concurrency the probe assumed", default=None)
    probe_budget_bytes: int | None = meaning(
        "admitted SAFE VRAM budget B", default=None
    )
    factual_weight_bytes: int | None = meaning(
        "factual stored-weight component when known", default=None
    )
    estimated_static_requirement_bytes: int | None = meaning(
        "static estimated-feasible total at probe time", default=None
    )
    estimated_kv_bytes: int | None = meaning(
        "static estimated KV component at probe time", default=None
    )
    measured_model_load_bytes: int | None = meaning(
        "runtime-reported model-load memory", default=None
    )
    measured_available_kv_bytes: int | None = meaning(
        "runtime-reported available KV cache K; may be negative", default=None
    )
    measured_peak_gpu_bytes: int | None = meaning(
        "observed peak device memory when captured", default=None
    )
    derived_non_kv_bytes: int | None = meaning("derived B minus K", default=None)
    derived_runtime_extra_bytes: int | None = meaning(
        "derived non-KV minus model-load when valid", default=None
    )
    calibrated_required_vram_bytes: int | None = meaning(
        "raise-only calibrated serving demand", default=None
    )
    profile_status: str | None = meaning(
        "measured, failed, or unresolved", default=None
    )
    confidence: str | None = meaning("profile confidence", default=None)
    measurement_quality: str | None = meaning(
        "short quality token when one exists", default=None
    )
    failure_reason: str | None = meaning(
        "why the probe produced no usable serving profile", default=None
    )
    class_key: str | None = meaning("runtime-memory validation class", default=None)
    basis_fingerprint: str | None = meaning(
        "execution basis the operational profile is valid for", default=None
    )


@contract(kind="telemetry.deployment_run", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentRunObservation(Contract):
    """One deployment attempt or one runtime-memory probe attempt."""

    deployment_run_id: TelemetryRunId = meaning("identity of this run")
    started_at: dt.datetime = meaning("when the attempt began, UTC")
    run_kind: DeploymentRunKind = meaning(
        "deployment versus runtime-memory probe",
        default=DeploymentRunKind.DEPLOYMENT,
    )
    ended_at: dt.datetime | None = meaning("when the attempt ended, UTC", default=None)
    duration_ms: int | None = meaning("wall time of the attempt", default=None)
    host_id: HostId | None = meaning("host the attempt ran on", default=None)
    selected_model: str | None = meaning("selected model identity", default=None)
    selected_revision: str | None = meaning("selected artifact revision", default=None)
    runtime: str | None = meaning("runtime family", default=None)
    runtime_version: str | None = meaning("runtime version", default=None)
    executor: str | None = meaning("executor identity", default=None)
    plan_id: str | None = meaning("DeploymentPlan identity", default=None)
    artifact_id: str | None = meaning("artifact identity", default=None)
    reservation_id: str | None = meaning("reservation identity", default=None)
    instance_id: str | None = meaning("InferenceInstance identity", default=None)
    state: str | None = meaning("run state, e.g. started or failed", default=None)
    failure_reason_code: str | None = meaning(
        "typed failure when the attempt failed", default=None
    )


@contract(kind="telemetry.deployment_event", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentEventObservation(Contract):
    """One major lifecycle milestone. Not a log line and not a request body."""

    event_id: TelemetryEventId = meaning("identity of this event")
    occurred_at: dt.datetime = meaning("when it happened, UTC")
    event_type: DeploymentEventType = meaning("which milestone")
    correlation_id: str | None = meaning(
        "deployment or probe run this belongs to", default=None
    )
    status: str | None = meaning("succeeded, failed, or a domain state", default=None)
    duration_ms: int | None = meaning(
        "duration of this milestone when timed", default=None
    )
