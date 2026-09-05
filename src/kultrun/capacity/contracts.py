"""What a provider claims a model would need.

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

from dataclasses import dataclass
from enum import StrEnum

from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


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
