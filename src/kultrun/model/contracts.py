"""What can be served: metadata, artifact, requirement and inventory.

Four contracts that are routinely conflated and must not be. Metadata
describes a model as the world describes it. An artifact is the bytes on a
pool. A requirement is what serving it would cost. An inventory record is
what this host currently has and what state it is in.

**A requirement is host-independent.** What a model needs is a property of
the model; where a need meets a machine is feasibility, which belongs to
`planning` at Stage 1.4B. A host reference here would invert the
dependency the tier order exists to protect.

**Missing metadata stays missing.** The previous attempt's catalogue
routinely carried `context_length: null` and `download_bytes: null`, and
its own guidance was that an unmeasured value must surface rather than be
filled in. Both fields are `Maybe[...]` here for exactly that reason.

**Peak additional bytes is separate from installed size.** An acquisition
needs room for staging, conversion and the final artifact at once, so
admission is against the peak, not the result. Conflating them is how a
download fills a disk that had "enough space".
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.storage.contracts import StoragePoolId


class ModelId(EntityId):
    """Identifies one model within the platform."""

    prefix = "model"


class ArtifactId(EntityId):
    """Identifies one set of stored bytes for a model."""

    prefix = "artifact"


class InventoryState(StrEnum):
    """Where a model is in its lifecycle on this host.

    ``LOADED`` / ``RUNNING`` / ``STOPPED`` belong to InferenceInstance
    later. Stage 1.4C never writes them onto an artifact.
    """

    DISCOVERED = "discovered"
    REMOTE = "remote"
    ACQUIRING = "acquiring"
    STORED = "stored"
    VALIDATING = "validating"
    INVALID = "invalid"
    DELETED = "deleted"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    UPDATING = "updating"
    DEPRECATED = "deprecated"
    INCOMPATIBLE = "incompatible"
    DERIVED = "derived"


class ArtifactState(StrEnum):
    """Storage lifecycle of one ModelArtifact. Not a serving state."""

    REMOTE = "remote"
    ACQUIRING = "acquiring"
    STORED = "stored"
    INVALID = "invalid"
    DELETED = "deleted"


class VerificationState(StrEnum):
    """Whether stored bytes were checked before promotion."""

    NOT_VERIFIED = "not_verified"
    PASSED = "passed"
    FAILED = "failed"


class AcquisitionFailureReason(StrEnum):
    """Why acquisition did not produce a STORED artifact."""

    INSUFFICIENT_SAFE_STORAGE = "insufficient_safe_storage"
    UNRESOLVED_STORAGE_REQUIREMENT = "unresolved_storage_requirement"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_EXECUTION_ERROR = "provider_execution_error"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ACCESS_DENIED = "access_denied"
    REVISION_NOT_FOUND = "revision_not_found"
    MODEL_NOT_FOUND = "model_not_found"
    NETWORK_FAILURE = "network_failure"
    VERIFICATION_FAILED = "verification_failed"
    INTERRUPTED = "interrupted"
    INVALID_TARGET = "invalid_target"
    VARIANT_MISMATCH = "variant_mismatch"
    CONCURRENT_ACQUISITION = "concurrent_acquisition"


class AcquisitionId(EntityId):
    """Identifies one acquisition request."""

    prefix = "acq"


class DerivationType(StrEnum):
    """How a model was produced from a parent, when it was."""

    LORA = "lora"
    PEFT = "peft"
    SUPERVISED_FINE_TUNE = "supervised_fine_tune"
    PREFERENCE = "preference"
    MERGE = "merge"
    DISTILL = "distill"
    FULL_FINE_TUNE = "full_fine_tune"


@contract(kind="model.metadata", version=1)
@dataclass(frozen=True, slots=True)
class ModelMetadata(Contract):
    """A model as the world describes it, normalized into platform terms.

    ``source_ref`` keeps the upstream reference verbatim — ``Qwen/Qwen3-8B-AWQ``
    — while ``logical_name`` is the normalized platform name. Both are kept
    because the normalization is deliberately lossy and the original is what
    a source adapter must send back upstream.
    """

    model_id: ModelId = meaning("platform-minted identity of this model")
    logical_name: Name = meaning(
        "normalized platform name, distinct from the minted identity and "
        "from the upstream reference"
    )
    source: Name = meaning("which source adapter this came from")
    source_ref: str = meaning("the upstream reference, kept verbatim")
    source_revision: Maybe[str] = meaning(
        "immutable revision; an acquisition without one is not reproducible"
    )
    family: Maybe[str] = meaning("model family, where the source states one")
    parameter_count: Maybe[int] = meaning("parameter count, where stated")
    context_length_tokens: Maybe[int] = meaning(
        "maximum context the model supports; frequently absent upstream"
    )
    quantization: Maybe[str] = meaning("quantization scheme, where applicable")
    license_id: Maybe[str] = meaning("licence identifier as stated by the source")
    commercial_use_restricted: Maybe[bool] = meaning(
        "whether the licence restricts commercial use; unknown is not permission"
    )
    architecture: Maybe[str] = meaning(
        "model architecture family as stated by the source",
        default=NOT_PROVIDED,
    )
    display_name: Maybe[str] = meaning(
        "human-readable label for consoles; not an identifier",
        default=NOT_PROVIDED,
    )
    supported_runtimes: tuple[str, ...] = meaning(
        "runtime names this variant is known to support; empty means unstated",
        default=(),
    )
    is_moe: Maybe[bool] = meaning(
        "whether this variant is mixture-of-experts; unknown is not dense",
        default=NOT_PROVIDED,
    )


@contract(kind="model.artifact", version=1)
@dataclass(frozen=True, slots=True)
class ModelArtifact(Contract):
    """The stored bytes of one model revision."""

    artifact_id: ArtifactId = meaning("platform-minted identity of these bytes")
    model_id: ModelId = meaning("the model these bytes are for")
    revision: Maybe[str] = meaning("the immutable revision these bytes came from")
    pool_id: StoragePoolId | None = meaning(
        "the pool holding them; absent while the artifact is still remote",
        default=None,
    )
    download_bytes: Maybe[int] = meaning(
        "transfer size as stated upstream; frequently absent",
        default=NOT_PROVIDED,
    )
    installed_bytes: Maybe[int] = meaning(
        "size once written to a pool, which is not the transfer size",
        default=NOT_PROVIDED,
    )
    checksum: Maybe[str] = meaning(
        "integrity digest; absence means the bytes are unverified, not sound",
        default=NOT_PROVIDED,
    )
    logical_name: Maybe[str] = meaning(
        "catalog name of the candidate these bytes came from",
        default=NOT_PROVIDED,
    )
    source: Maybe[str] = meaning(
        "source adapter that identified the candidate", default=NOT_PROVIDED
    )
    source_ref: Maybe[str] = meaning(
        "upstream reference that was acquired", default=NOT_PROVIDED
    )
    requested_revision: Maybe[str] = meaning(
        "revision or tag the caller asked for, before resolution",
        default=NOT_PROVIDED,
    )
    artifact_format: Maybe[str] = meaning(
        "weight format of these bytes", default=NOT_PROVIDED
    )
    quantization: Maybe[str] = meaning(
        "quantization/variant of these bytes", default=NOT_PROVIDED
    )
    state: ArtifactState = meaning(
        "storage lifecycle; never a serving state", default=ArtifactState.REMOTE
    )
    created_at: dt.datetime | None = meaning(
        "when this record was first written, UTC", default=None
    )
    acquired_at: dt.datetime | None = meaning(
        "when promotion to STORED succeeded, UTC", default=None
    )
    updated_at: dt.datetime | None = meaning(
        "when this record last changed, UTC", default=None
    )
    location: Maybe[str] = meaning(
        "Kultrun-owned path relative to the model store; never a caller path",
        default=NOT_PROVIDED,
    )
    file_count: Maybe[int] = meaning(
        "number of regular files in the stored tree", default=NOT_PROVIDED
    )
    manifest_digest: Maybe[str] = meaning(
        "digest of the Kultrun artifact manifest", default=NOT_PROVIDED
    )
    acquisition_provider: Maybe[str] = meaning(
        "which ModelAcquisitionProvider fetched the bytes",
        default=NOT_PROVIDED,
    )
    acquisition_provider_version: Maybe[str] = meaning(
        "that provider's version", default=NOT_PROVIDED
    )
    license_id: Maybe[str] = meaning(
        "licence identifier retained from metadata", default=NOT_PROVIDED
    )
    verification_state: VerificationState = meaning(
        "whether verification passed before STORED",
        default=VerificationState.NOT_VERIFIED,
    )
    verification_method: Maybe[str] = meaning(
        "how the bytes were checked", default=NOT_PROVIDED
    )
    integrity_evidence: tuple[str, ...] = meaning(
        "checksums, ETags, or structural notes; never credentials",
        default=(),
    )
    failure_reason: Maybe[str] = meaning(
        "typed reason when state is invalid or deleted after failure",
        default=NOT_PROVIDED,
    )
    storage_mount: Maybe[str] = meaning(
        "mount point of the Kultrun-managed pool used for the SAFE check",
        default=NOT_PROVIDED,
    )


@contract(kind="model.requirement", version=1)
@dataclass(frozen=True, slots=True)
class ModelRequirement(Contract):
    """What serving a model would cost, independent of any host.

    Represents gaps rather than filling them. The previous attempt had no
    RAM estimator anywhere in its source and one provisional VRAM figure,
    and both correctly appeared as unresolved. Carrying that honesty is the
    point; Stage 3.1 retires the gaps.
    """

    model_id: ModelId = meaning("the model this requirement describes")
    confidence: Confidence = meaning("how much weight this requirement carries")
    storage_bytes: Maybe[int] = meaning("steady-state size once installed")
    peak_additional_bytes: Maybe[int] = meaning(
        "most additional storage needed at any moment during acquisition, "
        "including staging and conversion; admission is against this"
    )
    vram_weights_bytes: Maybe[int] = meaning("accelerator memory held by weights")
    vram_kv_bytes_per_token: Maybe[int] = meaning(
        "accelerator memory per token of context"
    )
    vram_overhead_bytes: Maybe[int] = meaning("accelerator memory held by the runtime")
    ram_bytes: Maybe[int] = meaning("system memory needed to load and serve")
    required_compute_features: tuple[str, ...] = meaning(
        "compute capabilities the model needs, such as a quantization kernel",
        default=(),
    )
    unified_memory_bytes: Maybe[int] = meaning(
        "shared CPU/GPU memory where that is the deployment memory model; "
        "not a VRAM alias. Unstated on discrete-GPU candidates",
        default=NOT_PROVIDED,
    )
    activation_bytes: Maybe[int] = meaning(
        "accelerator memory held by activations under the assumed context",
        default=NOT_PROVIDED,
    )
    estimated_vram_bytes: Maybe[int] = meaning(
        "deployed accelerator-memory estimate under the assumed runtime, "
        "quantization and context; not parameter count and not artifact size",
        default=NOT_PROVIDED,
    )
    assumed_context_tokens: Maybe[int] = meaning(
        "context length the memory estimates assume; distinct from the "
        "model's maximum advertised context",
        default=NOT_PROVIDED,
    )
    supported_runtimes: tuple[str, ...] = meaning(
        "runtimes these estimates assume; empty means unstated",
        default=(),
    )
    estimation_method: Maybe[str] = meaning(
        "how these figures were produced, so a reader can judge them",
        default=NOT_PROVIDED,
    )
    estimator_provider: Maybe[str] = meaning(
        "which ModelRequirementEstimator produced this; one provider per "
        "product evaluation",
        default=NOT_PROVIDED,
    )
    estimator_version: Maybe[str] = meaning(
        "the provider's version, so an estimate can be reproduced",
        default=NOT_PROVIDED,
    )
    assumptions: tuple[str, ...] = meaning(
        "what the estimator assumed; substitution of quant, context, "
        "model or offload is forbidden",
        default=(),
    )
    measured: bool = meaning(
        "true only when the figures were measured on this configuration, "
        "never when they are an estimate",
        default=False,
    )
    estimator_mode: Maybe[str] = meaning(
        "configured mode: auto, llmfit, or kultrun",
        default=NOT_PROVIDED,
    )
    requested_primary: Maybe[str] = meaning(
        "first provider the router asked; llmfit in auto mode",
        default=NOT_PROVIDED,
    )
    fallback_used: bool = meaning(
        "true only when the primary provider failed to estimate",
        default=False,
    )
    fallback_reason: Maybe[str] = meaning(
        "typed reason the primary failed; never a stack trace",
        default=NOT_PROVIDED,
    )
    estimator_failure: Maybe[str] = meaning(
        "typed provider failure when this result is not usable evidence",
        default=NOT_PROVIDED,
    )
    assumed_runtime: Maybe[str] = meaning(
        "runtime identity these figures assume; selected verified foundation, "
        "never catalog supported_runtimes[0]",
        default=NOT_PROVIDED,
    )
    assumed_runtime_version: Maybe[str] = meaning(
        "runtime version these figures assume, when known",
        default=NOT_PROVIDED,
    )
    requirement_basis: Maybe[str] = meaning(
        "fingerprint of eligibility view, profile, model, and estimator",
        default=NOT_PROVIDED,
    )


@contract(kind="model.inventory_record", version=1)
@dataclass(frozen=True, slots=True)
class ModelInventoryRecord(Contract):
    """What this host has, and what state it is in.

    ``managed_bytes`` is what `storage` sums through the
    `ManagedUsageSource` port. It is `Maybe[...]` deliberately: the previous
    attempt crashed during integration on a record whose management section
    was explicitly null, and the fix is for the unknown to be representable
    rather than for the crash to be caught.
    """

    model_id: ModelId = meaning("the model this record concerns")
    host_id: HostId = meaning("the host this record describes")
    state: InventoryState = meaning("where the model is in its lifecycle here")
    artifact_id: ArtifactId | None = meaning(
        "the stored bytes, once there are any", default=None
    )
    pool_id: StoragePoolId | None = meaning(
        "the pool holding them, once there is one", default=None
    )
    managed_bytes: Maybe[int] = meaning(
        "storage this model occupies under platform management; unknown "
        "must never be summed as zero",
        default=NOT_PROVIDED,
    )
    parent_model_id: ModelId | None = meaning(
        "the model this was derived from, for a derived artifact", default=None
    )
    derivation: DerivationType | None = meaning(
        "how it was derived from that parent", default=None
    )
    last_used_at: dt.datetime | None = meaning(
        "when it last served a request, for portfolio decisions later",
        default=None,
    )


@contract(kind="model.catalog_entry", version=1)
@dataclass(frozen=True, slots=True)
class ModelCatalogEntry(Contract):
    """One curated candidate: metadata plus host-independent requirement.

    This is not a recommendation and not an inventory record. Stage 1.4A
    lists candidates. Stage 1.4B decides fit. Stage 1.4C stores bytes.
    """

    metadata: ModelMetadata = meaning("normalized description of this variant")
    requirement: ModelRequirement = meaning(
        "what serving this variant would cost, independent of any host"
    )


class MemoryPlacement(StrEnum):
    """Where the estimate assumes the model will run."""

    DISCRETE_GPU = "discrete_gpu"
    CPU_ONLY = "cpu_only"
    UNIFIED_MEMORY = "unified_memory"


class EstimatorFailureReason(StrEnum):
    """Why an estimator did not produce usable evidence.

    Fallback policy matches these values, never exception text.
    """

    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_EXECUTION_ERROR = "provider_execution_error"
    INCOMPATIBLE_PROVIDER_VERSION = "incompatible_provider_version"
    INVALID_PROVIDER_OUTPUT = "invalid_provider_output"
    UNSUPPORTED_MODEL = "unsupported_model"
    UNSUPPORTED_CONFIGURATION = "unsupported_configuration"
    ASSUMPTION_MISMATCH = "assumption_mismatch"
    MISSING_LOAD_BEARING_REQUIREMENT = "missing_load_bearing_requirement"
    UNRESOLVED_ESTIMATE = "unresolved_estimate"


@contract(kind="model.estimation_request", version=1)
@dataclass(frozen=True, slots=True)
class ModelEstimationRequest(Contract):
    """The configuration an estimator must evaluate. No silent substitution.

    If the estimator cannot honour quant, context, model, placement or
    offload as stated, it returns unsupported or unresolved — it does not
    change the request.
    """

    model_id: ModelId = meaning("platform identity of the candidate")
    source_ref: str = meaning("upstream identity the provider must look up")
    source_revision: Maybe[str] = meaning(
        "immutable revision; absence means the estimate is not pinned"
    )
    artifact_format: Maybe[str] = meaning(
        "weight format where it changes the estimate, e.g. safetensors"
    )
    quantization: Maybe[str] = meaning("quantization the estimate must assume")
    context_tokens: Maybe[int] = meaning("context length the estimate must assume")
    runtime: Maybe[str] = meaning("runtime the estimate must assume")
    placement: MemoryPlacement = meaning("device memory model for this estimate")
    offload_allowed: bool = meaning(
        "whether CPU offload may be assumed; default forbids hidden offload",
        default=False,
    )
    tensor_parallel: int = meaning(
        "device-span assumption; v0 is 1 and anything else is unsupported",
        default=1,
    )
    batch_size: int = meaning(
        "concurrency assumption; v0 is 1",
        default=1,
    )
    runtime_version: Maybe[str] = meaning(
        "exact runtime version the estimate must assume, when known",
        default=NOT_PROVIDED,
    )


@contract(kind="model.acquisition_request", version=1)
@dataclass(frozen=True, slots=True)
class ModelAcquisitionRequest(Contract):
    """What to acquire. Destination paths are never accepted from callers."""

    request_id: AcquisitionId = meaning("correlation identity for this mutation")
    model_id: ModelId = meaning("canonical candidate identity")
    logical_name: Name = meaning("catalog name of the variant")
    source: Name = meaning("source adapter that identified the candidate")
    source_ref: str = meaning("upstream repository or identity")
    requested_revision: Maybe[str] = meaning(
        "tag or commit the caller asked for; latest is not durable identity",
        default=NOT_PROVIDED,
    )
    artifact_format: Maybe[str] = meaning(
        "weight format to obtain", default=NOT_PROVIDED
    )
    quantization: Maybe[str] = meaning(
        "quantization/variant to obtain; silent substitution is forbidden",
        default=NOT_PROVIDED,
    )
    expected_storage_bytes: Maybe[int] = meaning(
        "steady-state size used in the SAFE preflight", default=NOT_PROVIDED
    )
    expected_peak_bytes: Maybe[int] = meaning(
        "peak staging size used in the SAFE preflight", default=NOT_PROVIDED
    )
    pool_id: StoragePoolId | None = meaning(
        "Kultrun-managed pool; None means the default first SAFE pool",
        default=None,
    )
    file_intent: tuple[str, ...] = meaning(
        "optional allow-patterns; empty means conservative provider defaults",
        default=(),
    )
    credential_ref: Maybe[str] = meaning(
        "name of an environment secret, never the secret itself",
        default=NOT_PROVIDED,
    )
    license_id: Maybe[str] = meaning(
        "licence identifier retained from metadata", default=NOT_PROVIDED
    )


@contract(kind="model.acquisition_receipt", version=1)
@dataclass(frozen=True, slots=True)
class AcquisitionReceipt(Contract):
    """Outcome of one acquire attempt. STORED only after verification."""

    request_id: AcquisitionId = meaning("the request this answers")
    artifact_id: ArtifactId = meaning("the artifact that was created or reused")
    outcome: str = meaning("stored, reused, or failed")
    state: ArtifactState = meaning("lifecycle after the attempt")
    verification_state: VerificationState = meaning("verification result")
    reused: bool = meaning(
        "true when an exact STORED artifact was returned without fetching"
    )
    acquired_at: dt.datetime = meaning("when this receipt was issued, UTC")
    resolved_revision: Maybe[str] = meaning(
        "immutable revision actually obtained", default=NOT_PROVIDED
    )
    stored_bytes: Maybe[int] = meaning(
        "bytes on the pool after promotion", default=NOT_PROVIDED
    )
    file_count: Maybe[int] = meaning(
        "regular files after promotion", default=NOT_PROVIDED
    )
    failure_reason: Maybe[str] = meaning(
        "typed failure; never a stack trace or token", default=NOT_PROVIDED
    )
    serving: bool = meaning(
        "always false in Stage 1.4C; stored is not running", default=False
    )


@contract(kind="model.artifact_manifest", version=1)
@dataclass(frozen=True, slots=True)
class ArtifactManifest(Contract):
    """Kultrun-owned lifecycle evidence. Not Hugging Face cache metadata."""

    artifact_id: ArtifactId = meaning("the artifact this describes")
    model_id: ModelId = meaning("canonical candidate")
    logical_name: Name = meaning("catalog name")
    source: Name = meaning("source adapter")
    source_ref: str = meaning("upstream identity")
    resolved_revision: str = meaning("immutable revision that was stored")
    acquisition_provider: str = meaning("provider that fetched the bytes")
    acquisition_provider_version: str = meaning("that provider's version")
    files: tuple[str, ...] = meaning("relative file paths inside the artifact")
    sizes_bytes: tuple[int, ...] = meaning("size of each file, same order")
    total_bytes: int = meaning("sum of regular file sizes")
    integrity_evidence: tuple[str, ...] = meaning(
        "checksums or provider notes; never credentials"
    )
    verification_state: VerificationState = meaning("verification result")
    verification_method: str = meaning("how verification was performed")
    acquired_at: dt.datetime = meaning("when promotion succeeded, UTC")
    manifest_version: str = meaning("manifest format version", default="1")
    requested_revision: Maybe[str] = meaning("what was asked for", default=NOT_PROVIDED)
    artifact_format: Maybe[str] = meaning("weight format", default=NOT_PROVIDED)
    quantization: Maybe[str] = meaning("variant", default=NOT_PROVIDED)
    license_id: Maybe[str] = meaning(
        "retained licence identifier", default=NOT_PROVIDED
    )
