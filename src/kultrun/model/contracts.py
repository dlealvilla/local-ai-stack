"""What can be served: metadata, artifact, requirement and inventory.

Four contracts that are routinely conflated and must not be. Metadata
describes a model as the world describes it. An artifact is the bytes on a
pool. A requirement is what serving it would cost. An inventory record is
what this host currently has and what state it is in.

**A requirement is host-independent.** What a model needs is a property of
the model; where a need meets a machine is feasibility, which belongs to
`planning` at Milestone 3. A host reference here would invert the
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
    """Where a model is in its lifecycle on this host."""

    DISCOVERED = "discovered"
    REMOTE = "remote"
    ACQUIRING = "acquiring"
    STORED = "stored"
    VALIDATING = "validating"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    UPDATING = "updating"
    DEPRECATED = "deprecated"
    INCOMPATIBLE = "incompatible"
    DERIVED = "derived"


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
