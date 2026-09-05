"""What capacity Kultrun is willing to treat as effective and safe.

Two things live here and they point in opposite directions.
:class:`CapacityEvidence` is what a *provider claims a model would need*.
:class:`CapacityEnvelope` is what *this host can safely give*. Feasibility
compares them at Stage 3.3; neither authorizes on its own, and only the
envelope's safe layer ever authorizes anything.

The field set is transcribed from `docs/PRODUCT_VISION.md` §23. Every
quantity is `Maybe[...]` because §23 states plainly that providers may
populate only what they know — an estimator that cannot compute KV cache
growth must say so rather than return zero.

This contract exists at Stage 0.2 to fix the *shape of a provider's
answer*, not to be populated. The internal conservative estimator and the
external advisory providers arrive at Stage 3.2, and observed evidence at
Milestone 11. Fixing the shape now is what lets `llmfit` be demoted to
advisory later without changing anything that consumes it — which is
exactly what happened to `llmfit` in the previous attempt, after it was
found nondeterministic on the reference host.

Theoretical and observed evidence stay distinguishable. Evidence measured
from a real run of the exact configuration carries more weight than a
formula, and a consumer that cannot tell them apart cannot apply that.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved


class EvidenceType(StrEnum):
    """Whether a claim was derived or measured."""

    THEORETICAL = "theoretical"
    OBSERVED = "observed"


@contract(kind="capacity.evidence", version=1)
@dataclass(frozen=True, slots=True)
class CapacityEvidence(Contract):
    """One provider's answer about what a model would need.

    Advisory. `docs/ROADMAP.md` Part II §6: evidence providers inform and
    never authorize. The Resource Manager admits against the safe layer of
    a `CapacityEnvelope`, not against this.
    """

    evidence_type: EvidenceType = meaning("whether this was derived or measured")
    model_ref: str = meaning("which model this concerns, by identifier")
    host_fingerprint: str = meaning(
        "the host shape it applies to; evidence is not portable across shapes"
    )
    confidence: Confidence = meaning("how much weight this evidence carries")
    provenance: Provenance = meaning(
        "which provider produced it, when, at what version"
    )
    runtime: Maybe[Name] = meaning("the runtime the estimate assumes")
    runtime_version: Maybe[str] = meaning("the runtime version the estimate assumes")
    weights_bytes: Maybe[int] = meaning("accelerator memory held by model weights")
    kv_cache_bytes_per_token: Maybe[int] = meaning(
        "accelerator memory per token of context, which is what makes "
        "context length a capacity question rather than a setting"
    )
    activation_bytes: Maybe[int] = meaning("accelerator memory held by activations")
    runtime_overhead_bytes: Maybe[int] = meaning(
        "accelerator memory the runtime itself holds"
    )
    total_memory_bytes: Maybe[int] = meaning(
        "the provider's total, which may differ from the sum of its parts"
    )
    host_memory_bytes: Maybe[int] = meaning("system memory required to load and serve")
    max_context_tokens: Maybe[int] = meaning(
        "largest context the provider believes fits"
    )
    assumptions: tuple[str, ...] = meaning(
        "what the provider assumed, so a reader can judge whether it holds here",
        default=(),
    )


class EvidenceRequirement(StrEnum):
    """Whether a reported quantity can be believed without further evidence.

    The generic form of the problem the Stage 1.1 reference host presents:
    a network filesystem advertising 2.15 PB, and a container reporting the
    machine's 251.5 GiB of memory while permitted 57.7 GiB. In both cases
    the number is real and describes something other than what Kultrun may
    use.

    Deliberately about *classes of evidence*, never about a vendor or a
    product. Which filesystem families fall where is policy data, not code.
    """

    #: The source is credible for this purpose; reported may become effective.
    SUFFICIENT = "sufficient"
    #: The environment restricts what is usable, and the restriction is known.
    RESTRICTED = "restricted"
    #: Reported is not credible evidence of usable capacity. Effective is
    #: bounded by policy until empirical evidence exists — Stage 2.2.
    EMPIRICAL_EVIDENCE_NEEDED = "empirical_evidence_needed"
    #: Nothing is known about credibility, so nothing may be assumed.
    UNKNOWN = "unknown"


@contract(kind="capacity.headroom_policy", version=1)
@dataclass(frozen=True, slots=True)
class HeadroomPolicy(Contract):
    """How much Kultrun keeps back, and what it refuses to believe.

    Every value here is **chosen conservatively, not measured.** That is the
    honest state at Stage 1.2 and it is recorded as debt: a reserve derived
    from real workloads belongs to Milestone 3, and empirical storage bounds
    to Stage 2.2. A policy that is conservative and versioned can be
    tightened with evidence; one tuned to look generous cannot be loosened
    safely.

    A fraction **and** a floor, because a fraction alone protects nothing on
    a small resource and a floor alone protects nothing on a large one.
    """

    policy_version: str = meaning(
        "which policy produced a value, so an old decision stays explicable "
        "after the policy changes"
    )
    memory_reserve_fraction: float = meaning(
        "share of effective system memory kept back for the operating "
        "system and everything Kultrun does not manage"
    )
    memory_reserve_floor_bytes: int = meaning(
        "minimum system memory kept back regardless of size"
    )
    accelerator_reserve_fraction: float = meaning(
        "share of effective accelerator memory kept back for runtime "
        "overhead, fragmentation and allocator behaviour"
    )
    accelerator_reserve_floor_bytes: int = meaning(
        "minimum accelerator memory kept back regardless of device size"
    )
    storage_reserve_fraction: float = meaning(
        "share of effective pool space kept back so a full pool cannot be "
        "reached by a managed write"
    )
    storage_reserve_floor_bytes: int = meaning(
        "minimum pool space kept back regardless of pool size"
    )
    unverified_pool_ceiling_bytes: int = meaning(
        "the most Kultrun will treat as effective in a pool whose reported "
        "size is not credible evidence. Not a claim about the pool: a bound "
        "on how much may be believed without having verified anything"
    )
    families_requiring_evidence: tuple[str, ...] = meaning(
        "filesystem families whose reported size does not corroborate "
        "usable capacity — network and distributed filesystems, whose "
        "totals describe a backend rather than an entitlement"
    )
    families_with_credible_size: tuple[str, ...] = meaning(
        "filesystem families whose reported free space is credible evidence. "
        "An allow-list, so an unrecognised family is disbelieved rather than "
        "trusted: the alternative fails open, and any mount nobody had "
        "thought about would become a capacity claim"
    )


@contract(kind="capacity.accelerator", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorCapacity(Contract):
    """One accelerator's memory at all three layers.

    Referenced by the index Stage 1.1 assigned, not by a provider handle,
    and **only assigned devices appear here.** The reference host had four
    accelerators visible on the bus and one assigned; an envelope covering
    four would claim roughly 128 GiB that does not exist.
    """

    index: int = meaning("which accelerator, as host discovery numbered it")
    memory: LayeredBytes = meaning("device memory, reported through safe")
    requirement: EvidenceRequirement = meaning(
        "whether the reported figure could be believed for this purpose"
    )
    note: str | None = meaning(
        "why a layer is bounded or unresolved, when it is", default=None
    )


@contract(kind="capacity.pool", version=1)
@dataclass(frozen=True, slots=True)
class PoolCapacity(Contract):
    """One storage location's usable space at all three layers.

    Space, not size: the question capacity answers is how much may be
    written, so the layers describe free space. Total is carried beside
    them for explanation, never for authorization.
    """

    mount_point: str = meaning("where the pool is mounted, its identity here")
    space: LayeredBytes = meaning("free space, reported through safe")
    requirement: EvidenceRequirement = meaning(
        "whether the reported figure could be believed for this purpose"
    )
    filesystem_type: Maybe[str] = meaning(
        "the filesystem family, which decides credibility",
        default=NOT_PROVIDED,
    )
    reported_total_bytes: Maybe[int] = meaning(
        "the pool's reported size, for explanation only",
        default=NOT_PROVIDED,
    )
    note: str | None = meaning(
        "why a layer is bounded or unresolved, when it is", default=None
    )


@contract(kind="capacity.envelope", version=1)
@dataclass(frozen=True, slots=True)
class CapacityEnvelope(Contract):
    """What this host can safely give, right now, under this policy.

    Derived rather than stored: an envelope is a view over host facts and a
    policy, and a persisted view invites a stale number authorizing a
    present decision. Scoped to a host fingerprint because capacity is not
    portable — a different machine's envelope is not an approximation of
    this one's.

    Recommends only. `docs/ROADMAP.md` Part II §6: the Resource Manager
    admits, capacity never does.
    """

    host_id: HostId = meaning("which host this describes, by identifier")
    host_fingerprint: str = meaning(
        "the host shape it was computed for; an envelope from another shape "
        "is invalid rather than stale"
    )
    computed_at: dt.datetime = meaning("when it was computed, UTC")
    policy_version: str = meaning("the headroom policy in force")
    memory: LayeredBytes = meaning("system memory, reported through safe")
    memory_requirement: EvidenceRequirement = meaning(
        "whether reported system memory could be believed for this purpose"
    )
    accelerators: tuple[AcceleratorCapacity, ...] = meaning(
        "every **assigned** accelerator; plural on a host that has one",
        default=(),
    )
    pools: tuple[PoolCapacity, ...] = meaning(
        "every candidate storage location", default=()
    )
    defects: tuple[str, ...] = meaning(
        "what could not be assessed, and why. A resource whose safe layer is "
        "unresolved appears here so an administrator is told rather than "
        "left to infer it from a missing number",
        default=(),
    )
    memory_note: str | None = meaning(
        "why a memory layer is bounded or unresolved, when it is", default=None
    )

    @property
    def admits_anything(self) -> bool:
        """Whether any resource has a safe figure that could authorize.

        A platform whose every safe layer is unresolved can admit nothing,
        and that is the correct behaviour rather than a failure — but it is
        worth being able to ask directly.
        """
        if is_resolved(self.memory.safe_bytes):
            return True
        return any(
            is_resolved(accelerator.memory.safe_bytes)
            for accelerator in self.accelerators
        )
