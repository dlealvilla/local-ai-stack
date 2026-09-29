"""Model contracts (MACHI 6).

Stored artifacts are not loaded models and not running servers.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

_TOKEN_MAX = 80
_REASON_MAX = 240
_PATH_MAX = 240
_MAX_FILES = 512
_MAX_ENTRIES = 64
_MAX_SETTINGS = 24


class ModelSourceKind(StrEnum):
    """Where a model reference comes from. Not a cache layout."""

    HUB = "hub"
    LOCAL = "local"


class AcquisitionMode(StrEnum):
    """Inspection does not fetch weights. Acquire is explicit."""

    INSPECT_ONLY = "inspect_only"
    PLAN_ACQUISITION = "plan_acquisition"
    ACQUIRE = "acquire"


class CompatibilityState(StrEnum):
    """Technical fit, with policy and capacity kept visible."""

    COMPATIBLE = "compatible"
    CONDITIONALLY_COMPATIBLE = "conditionally_compatible"
    UNSUPPORTED = "unsupported"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    INSUFFICIENT_CAPACITY = "insufficient_capacity"
    UNRESOLVED = "unresolved"


class ArtifactLifecycle(StrEnum):
    """Warehouse state. Loaded and running belong to later blocks."""

    STAGING = "staging"
    STORED = "stored"
    VERIFICATION_FAILED = "verification_failed"
    CORRUPT = "corrupt"
    UNAVAILABLE = "unavailable"


class DerivationKind(StrEnum):
    """How this artifact relates to a parent. Metadata only."""

    ORIGINAL = "original"
    QUANTIZED = "quantized"
    MERGED = "merged"
    ADAPTER = "adapter"
    FINE_TUNED = "fine_tuned"
    DISTILLED = "distilled"
    UNKNOWN = "unknown"


class CommercialUse(StrEnum):
    """Source-declared commercial metadata. Not a legal opinion."""

    DECLARED_ALLOWED = "declared_allowed"
    DECLARED_RESTRICTED = "declared_restricted"
    REQUIRES_REVIEW = "requires_review"
    UNKNOWN = "unknown"


class WeightFormat(StrEnum):
    SAFETENSORS = "safetensors"
    PYTORCH_BIN = "pytorch_bin"
    UNKNOWN = "unknown"


class QuantizationKind(StrEnum):
    NONE = "none"
    AWQ = "awq"
    GPTQ = "gptq"
    FP8 = "fp8"
    OTHER = "other"
    UNKNOWN = "unknown"


class ProviderQualification(StrEnum):
    """Product-support evidence. Not an instance READY bit."""

    QUALIFIED = "qualified"
    DEFERRED = "deferred"
    UNKNOWN = "unknown"


class SelectionProvenance(StrEnum):
    ADMINISTRATOR_SELECTED = "administrator_selected"
    PRODUCT_DEFAULT = "product_default"
    CURATED_DEFAULT = "curated_default"
    POLICY_FORCED = "policy_forced"


class ModelFailure(StrEnum):
    NONE = "none"
    SOURCE_UNAVAILABLE = "source_unavailable"
    PACKAGING_INCOMPLETE = "packaging_incomplete"
    REPOSITORY_NOT_FOUND = "repository_not_found"
    REVISION_NOT_FOUND = "revision_not_found"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ACCESS_DENIED = "access_denied"
    GATED_ACCESS_REQUIRED = "gated_access_required"
    METADATA_INVALID = "metadata_invalid"
    MODEL_CONFIG_MISSING = "model_config_missing"
    UNSUPPORTED_ARCHITECTURE = "unsupported_architecture"
    UNSUPPORTED_WEIGHT_FORMAT = "unsupported_weight_format"
    UNSUPPORTED_QUANTIZATION = "unsupported_quantization"
    REMOTE_CODE_REQUIRED = "remote_code_required"
    LICENSE_POLICY_BLOCKED = "license_policy_blocked"
    INSUFFICIENT_STORAGE = "insufficient_storage"
    INSUFFICIENT_BASELINE_CAPACITY = "insufficient_baseline_capacity"
    DOWNLOAD_FAILED = "download_failed"
    INTEGRITY_FAILED = "integrity_failed"
    LOCAL_IMPORT_INVALID = "local_import_invalid"
    RUNTIME_CAPABILITY_UNRESOLVED = "runtime_capability_unresolved"
    ATTENTION_CONFIGURATION_UNSUPPORTED = "attention_configuration_unsupported"
    INTERRUPTED = "interrupted"


class SettingProvenance(StrEnum):
    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR = "administrator"


@contract(kind="model.setting", version=1)
@dataclass(frozen=True, slots=True)
class ModelSetting(Contract):
    name: str = meaning("dotted setting name")
    value: str = meaning("current value")
    provenance: SettingProvenance = meaning("who selected it")
    reason: str = meaning("why it is in force")
    invalidation: str = meaning("what must be recomputed")

    def __post_init__(self) -> None:
        _bounded(self.name, what="name", maximum=_TOKEN_MAX)
        _bounded(self.value, what="value", maximum=_REASON_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)
        _bounded(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="model.settings", version=1)
@dataclass(frozen=True, slots=True)
class ModelSettings(Contract):
    """Typed model policy. Weights are not fetched unless acquire is set."""

    acquisition_mode: AcquisitionMode = meaning("inspect, plan, or acquire")
    remote_code_policy: str = meaning("refuse is the only supported policy")
    warehouse_policy: str = meaning("artifacts live under the owned state root")
    copy_policy: str = meaning("local sources are copied, not linked")
    integrity_policy: str = meaning("sha256 after acquisition")
    revision_policy: str = meaning("persist an immutable revision")
    license_policy: str = meaning("surface metadata; do not invent permission")
    timeout_seconds: int = meaning("bound on one source operation")
    max_retries: int = meaning("bounded retries, not an infinite loop")
    settings: tuple[ModelSetting, ...] = meaning("inspectable records")

    def __post_init__(self) -> None:
        if self.remote_code_policy != "refuse":
            raise ValidationError("remote code policy must refuse")
        if self.warehouse_policy != "state_root_warehouse":
            raise ValidationError("warehouse policy is not supported")
        if self.copy_policy != "copy_into_warehouse":
            raise ValidationError("copy policy is not supported")
        if self.integrity_policy != "sha256":
            raise ValidationError("integrity policy is not supported")
        if self.revision_policy != "immutable_commit":
            raise ValidationError("revision policy is not supported")
        if self.license_policy != "surface_unknown":
            raise ValidationError("license policy is not supported")
        if self.timeout_seconds < 1 or self.timeout_seconds > 3600:
            raise ValidationError("timeout is outside 1..3600 seconds")
        if self.max_retries < 0 or self.max_retries > 3:
            raise ValidationError("retries are outside 0..3")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many model settings")


@contract(kind="model.definition", version=1)
@dataclass(frozen=True, slots=True)
class ModelDefinition(Contract):
    """Logical model. One definition can have many stored copies."""

    model_id: str = meaning("stable id of source plus repository")
    source_kind: ModelSourceKind = meaning("hub or local")
    repository: str = meaning("repository id or local label, no secrets")
    requested_revision: str = meaning("what the caller asked for")
    immutable_revision: str = meaning("exact commit or content digest")
    display_name: str = meaning("short name from metadata or the repository")
    architecture: Maybe[str] = meaning("config architecture when present")
    dtype: Maybe[str] = meaning("declared dtype")
    quantization: QuantizationKind = meaning("published quant method, or none")
    weight_format: WeightFormat = meaning("selected weight files")
    context_length: Maybe[int] = meaning("declared context, not a serving choice")
    parameter_count: Maybe[int] = meaning("only when metadata states it")
    license_id: Maybe[str] = meaning("source license identifier")
    commercial_use: CommercialUse = meaning("declared, review, or unknown")
    gated: bool = meaning("source says access is gated")
    requires_remote_code: bool = meaning("config asks to execute repository code")
    derivation: DerivationKind = meaning("lineage kind")
    base_model: Maybe[str] = meaning("declared base model id")

    def __post_init__(self) -> None:
        _bounded(self.model_id, what="model", maximum=_TOKEN_MAX)
        _bounded(self.repository, what="repository", maximum=_PATH_MAX)
        _bounded(self.requested_revision, what="requested revision", maximum=_TOKEN_MAX)
        _bounded(self.immutable_revision, what="revision", maximum=_TOKEN_MAX)
        _bounded(self.display_name, what="name", maximum=_PATH_MAX)
        if isinstance(self.context_length, int) and self.context_length < 1:
            raise ValidationError("context length must be positive")
        if isinstance(self.parameter_count, int) and self.parameter_count < 1:
            raise ValidationError("parameter count must be positive")


@contract(kind="model.requirement", version=1)
@dataclass(frozen=True, slots=True)
class ModelRequirement(Contract):
    """Bytes to store the artifact, plus a static weight baseline."""

    persistent_bytes: Maybe[int] = meaning("warehouse bytes; unresolved is not zero")
    transient_bytes: Maybe[int] = meaning("staging bytes during acquisition")
    static_weight_bytes: Maybe[int] = meaning("weight file bytes, not serving VRAM")

    def __post_init__(self) -> None:
        for name, value in (
            ("persistent_bytes", self.persistent_bytes),
            ("transient_bytes", self.transient_bytes),
            ("static_weight_bytes", self.static_weight_bytes),
        ):
            if isinstance(value, int) and value < 0:
                raise ValidationError(
                    "requirement bytes must not be negative",
                    field=name,
                )


@contract(kind="model.compatibility", version=1)
@dataclass(frozen=True, slots=True)
class ModelCompatibility(Contract):
    """Technical fit and policy, kept as separate dimensions."""

    state: CompatibilityState = meaning("normalized result")
    failure: ModelFailure = meaning("primary reason, or none")
    technical_state: CompatibilityState = meaning("runtime and capacity fit")
    policy_state: CompatibilityState = meaning("remote code and license policy")
    provider_qualification: ProviderQualification = meaning(
        "foundation provider evidence, not instance ready"
    )
    reason: str = meaning("why this assessment was made")

    def __post_init__(self) -> None:
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)


@contract(kind="model.file", version=1)
@dataclass(frozen=True, slots=True)
class ModelFileRecord(Contract):
    """One stored file. The hash is Machi's, not an external etag."""

    relative_path: str = meaning("path inside the artifact, not a host path")
    size_bytes: int = meaning("stored size")
    sha256: str = meaning("hex digest")

    def __post_init__(self) -> None:
        _bounded(self.relative_path, what="path", maximum=_PATH_MAX)
        if self.size_bytes < 0:
            raise ValidationError("file size must not be negative")
        if len(self.sha256) != 64:
            raise ValidationError("file digest must be sha256 hex")


@contract(kind="model.artifact", version=1)
@dataclass(frozen=True, slots=True)
class ModelArtifact(Contract):
    """A verified warehouse copy. Not a loaded model."""

    artifact_id: str = meaning("id of this revision and variant")
    model_id: str = meaning("logical model")
    source_kind: ModelSourceKind = meaning("hub or local")
    repository: str = meaning("source identity without secrets")
    immutable_revision: str = meaning("exact revision that was stored")
    variant: str = meaning("dtype, quant, and format")
    lifecycle: ArtifactLifecycle = meaning("stored only when hashes match")
    total_bytes: int = meaning("sum of stored file sizes")
    files: tuple[ModelFileRecord, ...] = meaning("manifest entries")
    config_sha256: Maybe[str] = meaning("digest of config.json when present")
    derivation: DerivationKind = meaning("lineage kind copied from the definition")
    base_model: Maybe[str] = meaning("declared base model id")
    parent_artifact_id: Maybe[str] = meaning("parent artifact when this copy names one")
    acquired_at: dt.datetime = meaning("when promotion succeeded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "acquired_at", require_utc(self.acquired_at, what="acquired_at")
        )
        _bounded(self.artifact_id, what="artifact", maximum=_TOKEN_MAX)
        _bounded(self.model_id, what="model", maximum=_TOKEN_MAX)
        _bounded(self.repository, what="repository", maximum=_PATH_MAX)
        _bounded(self.immutable_revision, what="revision", maximum=_TOKEN_MAX)
        _bounded(self.variant, what="variant", maximum=_TOKEN_MAX)
        if self.total_bytes < 0:
            raise ValidationError("artifact size must not be negative")
        if len(self.files) > _MAX_FILES:
            raise ValidationError("too many artifact files")


@contract(kind="model.available_entry", version=1)
@dataclass(frozen=True, slots=True)
class AvailableModelEntry(Contract):
    """One candidate against one foundation and capacity snapshot."""

    definition: ModelDefinition = meaning("normalized model")
    compatibility: ModelCompatibility = meaning("assessment")
    requirement: ModelRequirement = meaning("storage and static weights")
    artifact_id: Maybe[str] = meaning("stored artifact when one exists")
    lifecycle: Maybe[str] = meaning("warehouse lifecycle when stored")


@contract(kind="model.available", version=1)
@dataclass(frozen=True, slots=True)
class AvailableModels(Contract):
    """Bounded candidate snapshot. Not a crawl of every public model."""

    snapshot_id: str = meaning("identity of this evaluation")
    input_token: str = meaning("fingerprint of foundation, capacity, and policy")
    foundation_id: str = meaning("foundation generation or selection cited")
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    entries: tuple[AvailableModelEntry, ...] = meaning("evaluated candidates")
    observed_at: dt.datetime = meaning("when this snapshot was made; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _bounded(self.snapshot_id, what="snapshot", maximum=_TOKEN_MAX)
        _bounded(self.input_token, what="token", maximum=_TOKEN_MAX)
        _bounded(self.foundation_id, what="foundation", maximum=_TOKEN_MAX)
        _bounded(self.capacity_evidence_id, what="capacity", maximum=_TOKEN_MAX)
        if len(self.entries) > _MAX_ENTRIES:
            raise ValidationError("too many available model entries")


@contract(kind="model.selection", version=1)
@dataclass(frozen=True, slots=True)
class ModelSelection(Contract):
    """Chosen model for a later plan. Not a reservation and not a server."""

    selection_id: str = meaning("identity of this choice")
    model_id: str = meaning("logical model")
    artifact_id: Maybe[str] = meaning("stored artifact when already acquired")
    immutable_revision: str = meaning("exact revision")
    provenance: SelectionProvenance = meaning("who chose it")
    compatibility_state: CompatibilityState = meaning("assessment at selection")
    foundation_id: str = meaning("foundation this choice cited")
    capacity_evidence_id: str = meaning("capacity snapshot cited")
    reason: str = meaning("why this model was selected")

    def __post_init__(self) -> None:
        _bounded(self.selection_id, what="selection", maximum=_TOKEN_MAX)
        _bounded(self.model_id, what="model", maximum=_TOKEN_MAX)
        _bounded(self.immutable_revision, what="revision", maximum=_TOKEN_MAX)
        _bounded(self.foundation_id, what="foundation", maximum=_TOKEN_MAX)
        _bounded(self.capacity_evidence_id, what="capacity", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="reason", maximum=_REASON_MAX)


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
