"""Control-plane state: what this installation is, and how it started.

`PlatformState` is deliberately small. `docs/ARCHITECTURE.md` Part IV says
this module must not own state a domain should own, and a control-plane
state object is the first place that rule erodes: every subsystem has
something it would be convenient to keep here. Installation identity,
version, and who administers it are the whole of it.

`HealthReport` has three states rather than two. A source that has not
reported since startup is not healthy and is not failing, and Part II §6
requires unknown to stay unknown rather than resolve to a pass.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.identity.contracts import SubjectId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe


class InstallationId(EntityId):
    """Identifies one installation of Kultrun, for its whole life."""

    prefix = "inst"


class ApprovalId(EntityId):
    """Identifies one administrator decision."""

    prefix = "appr"


class HealthStatus(StrEnum):
    """How a component is doing.

    ``UNKNOWN`` is a real answer. A component that has not been asked since
    startup has not passed, and reporting it as healthy is the kind of
    optimistic default that makes a health endpoint worthless.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    UNKNOWN = "unknown"


class ApprovalDecision(StrEnum):
    """What an administrator decided."""

    GRANTED = "granted"
    REFUSED = "refused"


@contract(kind="platform.state", version=1)
@dataclass(frozen=True, slots=True)
class PlatformState(Contract):
    """What this installation is.

    Written once on first run and read on every start. The installation
    identity is never regenerated: records elsewhere reference it, and
    minting a new one would silently orphan them.
    """

    installation_id: InstallationId = meaning(
        "identity of this installation, stable for its whole life"
    )
    platform_version: str = meaning("the Kultrun version that wrote this record")
    initialized_at: dt.datetime = meaning("when the installation was first started")
    administrator_id: SubjectId = meaning(
        "the local administrator, by identifier; the subject record is stored "
        "in its own right, because a subject is an entity and not a property "
        "of the installation"
    )


@contract(kind="platform.approval", version=1)
@dataclass(frozen=True, slots=True)
class Approval(Contract):
    """One administrator decision about one proposed action.

    A record, not a workflow. Risk classification and the request-approve
    cycle are Stage 6.2. What must exist now is the record, because Stage
    1.5 is the first mutating workflow and a mutation whose approval was
    never written down cannot be audited afterwards.
    """

    approval_id: ApprovalId = meaning("identity of this decision")
    action: Name = meaning("what was proposed, as a stable dotted name")
    target_kind: Name = meaning("what sort of thing it concerns")
    target_id: str = meaning("which one, by identifier")
    requested_by: SubjectId = meaning("who proposed it")
    requested_at: dt.datetime = meaning("when it was proposed")
    decision: ApprovalDecision = meaning("what the administrator decided")
    decided_by: SubjectId = meaning("who decided")
    decided_at: dt.datetime = meaning("when they decided")
    reason: str | None = meaning(
        "why, which is the part a later reader actually needs", default=None
    )
    expires_at: dt.datetime | None = meaning(
        "when the decision stops standing; absent means it does not expire",
        default=None,
    )


@contract(kind="platform.component_health", version=1)
@dataclass(frozen=True, slots=True)
class ComponentHealth(Contract):
    """One component's answer about itself."""

    component: Name = meaning("which component is reporting")
    status: HealthStatus = meaning("how it is doing")
    detail: str | None = meaning(
        "what is wrong, when something is", default=None
    )


@contract(kind="platform.health_report", version=1)
@dataclass(frozen=True, slots=True)
class HealthReport(Contract):
    """The platform's aggregate answer.

    The aggregate is the worst component status, not an average. A platform
    with one failing subsystem is not three-quarters healthy.
    """

    status: HealthStatus = meaning("the worst status among the components")
    observed_at: dt.datetime = meaning("when health was last aggregated")
    components: tuple[ComponentHealth, ...] = meaning(
        "each component's own answer", default=()
    )


@contract(kind="platform.startup_phase", version=1)
@dataclass(frozen=True, slots=True)
class PhaseReport(Contract):
    """What one startup phase did."""

    phase: Name = meaning("which phase ran")
    succeeded: bool = meaning("whether it completed")
    detail: str | None = meaning(
        "what it found or why it failed", default=None
    )
    defects: tuple[str, ...] = meaning(
        "problems it surfaced but did not resolve", default=()
    )


@contract(kind="platform.startup_report", version=1)
@dataclass(frozen=True, slots=True)
class StartupReport(Contract):
    """What the last start did, in order.

    One report for the whole platform. Every later stage registers a phase
    rather than adding a startup path of its own, which is what makes Stage
    6.3 a completion rather than an invention.
    """

    started_at: dt.datetime = meaning("when this start began")
    completed: bool = meaning("whether every phase completed")
    first_run: Maybe[bool] = meaning(
        "whether this start created the installation; unknown before state loads"
    )
    phases: tuple[PhaseReport, ...] = meaning(
        "each phase in the order it ran", default=()
    )

    @property
    def defects(self) -> tuple[str, ...]:
        """Every problem surfaced across phases, for the health view."""
        return tuple(
            defect for phase in self.phases for defect in phase.defects
        )


@contract(kind="config.platform", version=1)
@dataclass(frozen=True, slots=True)
class PlatformSettings(Contract):
    """The platform's own configuration section.

    A configuration section is a contract, so these fields are versioned and
    fingerprinted like any other. That is what makes "no existing config
    field may be reinterpreted" enforced by the same mechanism as "field
    meaning must never change silently", rather than by a second convention
    that could drift from the first.
    """

    state_root: str = meaning(
        "directory the platform owns for its records", default="./.state"
    )
    api_address: str = meaning(
        "address the Platform API binds to; loopback while there is no "
        "authentication",
        default="127.0.0.1",
    )
    api_port: int = meaning("port the Platform API binds to", default=8420)
    may_provision_components: bool = meaning(
        "whether Kultrun may install a missing platform component; an "
        "administrator may forbid it, and preparation then reports the "
        "component unavailable rather than acting",
        default=True,
    )
    model_requirement_estimator: str = meaning(
        "estimator mode: auto (llmfit then Kultrun fallback), or a "
        "strict provider id (llmfit, kultrun). Not a reconciler",
        default="auto",
    )
    model_acquisition_provider: str = meaning(
        "acquisition adapter: huggingface (product default) or fixture",
        default="huggingface",
    )
    model_source_mode: str = meaning(
        "offline uses the packaged catalog only; live may call optional "
        "Hugging Face listing/metadata and Accelerate structural extras",
        default="offline",
    )
    foundation_comfortable_storage_bytes: int = meaning(
        "SAFE storage ranking band used only when both vLLM and llama.cpp "
        "are already feasible. Prefers vLLM at or above this figure, "
        "llama.cpp below it. Not feasibility, not admission, and not "
        "the 32 GiB Sonar tier",
        default=64 * 1024**3,
    )


class OperationalFactId(EntityId):
    """Identifies one persisted operational fact."""

    prefix = "opf"


class OperationalStage(StrEnum):
    """Progress column. Stable labels for CLI/API, not a workflow engine."""

    RUN = "run"
    HOST = "host"
    STORAGE = "storage"
    PROBE = "probe"
    SONAR = "sonar"
    RUNTIME = "runtime"
    MODEL = "model"
    PLAN = "plan"
    ADMISSION = "admission"
    INSTANCE = "instance"
    INFERENCE = "inference"
    DEPLOYMENT = "deployment"


class OperationalOutcome(StrEnum):
    """How the fact ended. Unknown stays unresolved, never a pass."""

    PASS = "pass"
    FAIL = "fail"
    UNRESOLVED = "unresolved"
    INFO = "info"
    BLOCKED = "blocked"


@contract(kind="platform.operational_fact", version=1)
@dataclass(frozen=True, slots=True)
class OperationalFact(Contract):
    """One control-plane observation. Metadata only; never customer content."""

    fact_id: OperationalFactId = meaning("platform-minted identity of this fact")
    host_id: HostId = meaning("host this observation was made on")
    occurred_at: dt.datetime = meaning("when it happened, UTC")
    stage: OperationalStage = meaning("which deployment column this belongs to")
    event_type: Name = meaning(
        "stable dotted name such as storage.sonar_tier_passed"
    )
    outcome: OperationalOutcome = meaning("pass, fail, unresolved, info, or blocked")
    summary: str = meaning(
        "short operator line; never a prompt, response, or document"
    )
    reason_code: Maybe[str] = meaning(
        "typed product reason when one exists", default=NOT_PROVIDED
    )
    attributes: tuple[str, ...] = meaning(
        "key=value metadata; never file contents or generated text",
        default=(),
    )
    correlation_id: Maybe[str] = meaning(
        "ties this fact to the operation that caused it", default=NOT_PROVIDED
    )


class DeploymentRunId(EntityId):
    """Identifies one end-to-end deployment journey across CLI processes."""

    prefix = "drun"


class DeploymentRunStatus(StrEnum):
    """Whether this correlation context is still the current journey."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@contract(kind="platform.deployment_run", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentRun(Contract):
    """One deployment journey for this state root. Not a workflow engine.

    Independent CLI processes reconstruct the same journey by reading this
    record and stamping OperationalFact.correlation_id with run_id.
    """

    run_id: DeploymentRunId = meaning("durable correlation identity of this journey")
    host_id: HostId = meaning("host this journey was recorded against")
    started_at: dt.datetime = meaning("when this run identity was minted, UTC")
    status: DeploymentRunStatus = meaning("open, completed, or failed")
    kultrun_build: str = meaning("build that minted the run")


class DeploymentReportId(EntityId):
    """Identifies one composed deployment report."""

    prefix = "drpt"


class DeploymentVerdict(StrEnum):
    """Overall vertical standing. Incomplete is not a pass."""

    PASS = "pass"
    FAIL = "fail"
    INCOMPLETE = "incomplete"


@contract(kind="platform.report_storage_pool", version=1)
@dataclass(frozen=True, slots=True)
class StoragePoolReport(Contract):
    """One pool as the deployment report presents it. Not authorizing."""

    mount_point: str = meaning("pool mount")
    filesystem_type: Maybe[str] = meaning("filesystem family")
    reported_free_bytes: Maybe[int] = meaning("generic reported free space")
    reported_trusted: bool = meaning("whether reported free space may be believed")
    specialist_probe: Maybe[str] = meaning("compatible specialist identity")
    specialist_result: Maybe[str] = meaning("specialist outcome summary")
    sonar_tiers: tuple[str, ...] = meaning("official tier results, in order")
    authorizing_bytes: Maybe[int] = meaning("authorizing remaining at report time")
    safe_bytes: Maybe[int] = meaning("SAFE remaining; never reported")
    managed_bytes: Maybe[int] = meaning("platform-managed bytes on this pool")
    remaining_bytes: Maybe[int] = meaning("authorizing remaining after managed usage")
    selected_reason: str = meaning("why the operational figure was chosen", default="")
    quota_identity: Maybe[str] = meaning(
        "quota domain of this pool, when known", default=NOT_PROVIDED
    )
    pool_fingerprint: Maybe[str] = meaning(
        "pool identity; invalid when the mount changes", default=NOT_PROVIDED
    )


@contract(kind="platform.report_runtime_candidate", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeCandidateReport(Contract):
    """One runtime path as evaluated. Not a selection."""

    candidate_id: str = meaning("RuntimeCandidate identity")
    runtime: str = meaning("runtime family")
    version: Maybe[str] = meaning("version pin when known")
    executor: str = meaning("executor identity")
    support_tier: str = meaning("PRODUCT, FUTURE, or other declared tier")
    compatibility: str = meaning("compatibility class")
    reason_codes: tuple[str, ...] = meaning("normalized reason codes")
    recommended: bool = meaning("true when this is the current recommendation")
    selected: bool = meaning("true when this is the selected foundation")


@contract(kind="platform.report_runtime_install", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeInstallReport(Contract):
    """One runtime installation as installed. Not verification."""

    installation_id: str = meaning("installation identity")
    runtime: str = meaning("runtime family")
    version: str = meaning("requested version")
    storage_pool_mount: Maybe[str] = meaning("destination pool")
    installed_bytes: Maybe[int] = meaning("measured persistent bytes")
    status: str = meaning("installing, installed, or failed")
    verification: Maybe[str] = meaning("verification status when known")
    duration_seconds: Maybe[float] = meaning("install attempt wall time")


@contract(kind="platform.report_model_candidate", version=1)
@dataclass(frozen=True, slots=True)
class ModelCandidateReport(Contract):
    """One model as the funnel last evaluated it."""

    model_id: str = meaning("catalog identity")
    logical_name: str = meaning("catalog name")
    revision: Maybe[str] = meaning("source revision")
    quantization: Maybe[str] = meaning("variant")
    available: bool = meaning("true when in the current Available Models set")
    blocked_reason: Maybe[str] = meaning("exclusion reason when not available")
    required_vram_bytes: Maybe[int] = meaning("evaluated VRAM demand")
    required_ram_bytes: Maybe[int] = meaning("evaluated RAM demand")
    required_storage_bytes: Maybe[int] = meaning("evaluated storage demand")
    context_tokens: Maybe[int] = meaning("context assumption")


@contract(kind="platform.report_instance", version=1)
@dataclass(frozen=True, slots=True)
class InstanceReport(Contract):
    """One serving instance as observed. Prompt text is never included."""

    instance_id: str = meaning("instance identity")
    endpoint: Maybe[str] = meaning("loopback URL when bound")
    ready: Maybe[bool] = meaning("readiness, distinct from reachable")
    ownership: Maybe[str] = meaning("process ownership class when known")
    lifecycle: str = meaning("intended/observed lifecycle")
    health: str = meaning("API health")
    execution_id: Maybe[str] = meaning(
        "current execution identity, when one exists", default=NOT_PROVIDED
    )
    pid: Maybe[int] = meaning("observed PID when owned", default=NOT_PROVIDED)
    observed_state: Maybe[str] = meaning(
        "observed instance state", default=NOT_PROVIDED
    )


@contract(kind="platform.report_layer", version=1)
@dataclass(frozen=True, slots=True)
class ReportLayer(Contract):
    """One stack layer as the report explains it. Projection, not new truth."""

    identity: str = meaning("stable layer key such as host or storage")
    title: str = meaning("human layer title")
    purpose: str = meaning("what this layer is for")
    status: str = meaning("pass, fail, incomplete, or info")
    kultrun: tuple[str, ...] = meaning(
        "conceptual module names, not a Python call stack", default=()
    )
    inputs: tuple[str, ...] = meaning("what this layer received", default=())
    process: tuple[str, ...] = meaning("what Kultrun did", default=())
    decision: tuple[str, ...] = meaning("what was measured or chosen", default=())
    outputs: tuple[str, ...] = meaning("structured output of this layer", default=())
    consumed_by: tuple[str, ...] = meaning("what consumes that output", default=())


@contract(kind="platform.decision_snapshot", version=1)
@dataclass(frozen=True, slots=True)
class DecisionSnapshot(Contract):
    """One automatic decision, projected from facts and domain state.

    Not a DecisionStore. Reconstructable from OperationalFact plus the
    owning domain records.
    """

    decision: str = meaning(
        "FOUNDATION_SELECTION, MODEL_SELECTION, RESOURCE_ADMISSION, or REPLAN"
    )
    inputs: tuple[str, ...] = meaning("what Kultrun knew", default=())
    options: tuple[str, ...] = meaning("what options existed", default=())
    selected: Maybe[str] = meaning("what was selected", default=NOT_PROVIDED)
    reason: Maybe[str] = meaning("why", default=NOT_PROVIDED)
    outcome: Maybe[str] = meaning("what happened afterward", default=NOT_PROVIDED)


@contract(kind="platform.inference_observation", version=1)
@dataclass(frozen=True, slots=True)
class InferenceObservation(Contract):
    """One inference as the report presents it. Never prompt or response text."""

    occurred_at: dt.datetime = meaning("when the inference completed, UTC")
    outcome: str = meaning("pass or fail")
    latency_ms: Maybe[int] = meaning("wall latency when recorded", default=NOT_PROVIDED)
    input_tokens: Maybe[int] = meaning(
        "local token count; not vendor telemetry by default", default=NOT_PROVIDED
    )
    output_tokens: Maybe[int] = meaning(
        "local token count; not vendor telemetry by default", default=NOT_PROVIDED
    )
    finish_reason: Maybe[str] = meaning(
        "runtime finish class when recorded", default=NOT_PROVIDED
    )


@contract(kind="platform.deployment_report", version=1)
@dataclass(frozen=True, slots=True)
class DeploymentReport(Contract):
    """Composed deployment picture. Nested rows are projections, not new truth."""

    report_id: DeploymentReportId = meaning("identity of this composed report")
    host_id: HostId = meaning("host the report describes")
    composed_at: dt.datetime = meaning("when this projection was built, UTC")
    kultrun_build: str = meaning("build id or origin string")
    os_name: str = meaning("operating system family")
    os_version: Maybe[str] = meaning("OS version")
    architecture: str = meaning("CPU architecture")
    cpu: Maybe[str] = meaning("CPU model")
    ram_total_bytes: Maybe[int] = meaning("reported RAM total")
    ram_safe_bytes: Maybe[int] = meaning("SAFE RAM")
    accelerators: tuple[str, ...] = meaning("one line per assigned GPU")
    storage_pools: tuple[StoragePoolReport, ...] = meaning("each known pool")
    runtime_candidates: tuple[RuntimeCandidateReport, ...] = meaning(
        "evaluated runtime paths"
    )
    recommended_runtime: Maybe[str] = meaning("recommended candidate id")
    selected_runtime: Maybe[str] = meaning("selected candidate id")
    runtime_installs: tuple[RuntimeInstallReport, ...] = meaning("install receipts")
    model_candidates: tuple[ModelCandidateReport, ...] = meaning(
        "evaluated model paths"
    )
    available_models: tuple[str, ...] = meaning("current Available Models names")
    recommended_model: Maybe[str] = meaning("recommended catalog name")
    selected_model: Maybe[str] = meaning("selected catalog name")
    selection_mode: Maybe[str] = meaning("AUTO or MANUAL")
    deployment_plan_id: Maybe[str] = meaning("authoritative plan identity")
    plan_storage_pool: Maybe[str] = meaning("plan destination pool")
    plan_ram_bytes: Maybe[int] = meaning("plan RAM requirement")
    plan_vram_bytes: Maybe[int] = meaning("plan VRAM requirement")
    plan_storage_bytes: Maybe[int] = meaning("plan storage requirement")
    instances: tuple[InstanceReport, ...] = meaning("serving instances")
    latest_inference_latency_ms: Maybe[int] = meaning(
        "last recorded inference latency from operational facts"
    )
    latest_inference_outcome: Maybe[str] = meaning("last inference operational outcome")
    verdict: DeploymentVerdict = meaning("overall standing of this vertical")
    failed_at: Maybe[str] = meaning("stage that blocked, when failed")
    reason: Maybe[str] = meaning("why the verdict is what it is")
    next_action: Maybe[str] = meaning("what the operator should do next")
    plan_runtime_candidate: Maybe[str] = meaning(
        "runtime candidate bound on the current plan", default=NOT_PROVIDED
    )
    lifecycle: tuple[str, ...] = meaning(
        "ordered start/stop/restart/infer summaries from operational facts",
        default=(),
    )
    run_id: Maybe[str] = meaning(
        "DeploymentRun identity correlating this journey", default=NOT_PROVIDED
    )
    run_started_at: Maybe[dt.datetime] = meaning(
        "when the current DeploymentRun was minted", default=NOT_PROVIDED
    )
    layers: tuple[ReportLayer, ...] = meaning(
        "guided stack layers for Admin UI and the human report", default=()
    )
    decisions: tuple[DecisionSnapshot, ...] = meaning(
        "automatic decision snapshots projected at compose time", default=()
    )
    inferences: tuple[InferenceObservation, ...] = meaning(
        "inference observations in occurred_at order; no prompt text", default=()
    )
    selected_stack: Maybe[str] = meaning(
        "one-line selected host → storage → foundation → model → executor",
        default=NOT_PROVIDED,
    )
    manual_intervention: Maybe[str] = meaning(
        "NONE, or a short operator-reclaim note that is not a product failure",
        default=NOT_PROVIDED,
    )
    reservation_id: Maybe[str] = meaning(
        "current or last admission reservation", default=NOT_PROVIDED
    )
    admission_verdict: Maybe[str] = meaning(
        "latest resource admission outcome", default=NOT_PROVIDED
    )
    catalog_count: Maybe[int] = meaning(
        "catalog/discovery count feeding model feasibility", default=NOT_PROVIDED
    )
    compatible_count: Maybe[int] = meaning(
        "runtime-compatible count before capacity filtering", default=NOT_PROVIDED
    )
    available_count: Maybe[int] = meaning(
        "Available Models count after capacity filtering", default=NOT_PROVIDED
    )
