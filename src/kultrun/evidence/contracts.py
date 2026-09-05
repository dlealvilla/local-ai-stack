"""How a claim is qualified: basis, confidence, provenance, and the layers.

`docs/ROADMAP.md` Part II §6 is this module's specification. Three rules
from it are given types here rather than left as prose:

- **Three layers, one authority.** Reported is what a source claims,
  effective corrects it for real usability, safe subtracts protected
  headroom. Only the safe layer may authorize an allocation or a mutation.
- **Facts are immutable; policy reinterprets them.** Provenance records the
  policy version a value was derived under, so a stored fact stays true
  when the objective changes.
- **Unknown is not zero.** Every layer is `Maybe[...]`, because an
  unmeasured capacity is not a capacity of nothing.

This module owns how a claim is qualified. It never owns the claim.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


class Basis(StrEnum):
    """Where a value came from, which determines what it may be used for."""

    REPORTED = "reported"
    EFFECTIVE = "effective"
    SAFE = "safe"
    THEORETICAL = "theoretical"
    OBSERVED = "observed"
    POLICY = "policy"


class Confidence(StrEnum):
    """How much weight a recommendation may place on a value.

    ``UNKNOWN`` is a first-class member rather than an absence, so that a
    provider that cannot judge its own confidence says so instead of
    defaulting to low — which would be a claim it has not earned.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@contract(kind="evidence.provenance", version=1)
@dataclass(frozen=True, slots=True)
class Provenance(Contract):
    """Who produced a value, when, and under which policy.

    A value object: it has no identity of its own and is embedded in the
    claim it qualifies rather than referenced by identifier.
    """

    producer: Name = meaning("the module or provider that produced the value")
    producer_version: Maybe[str] = meaning(
        "the producer's version, so a value can be reproduced or distrusted"
    )
    observed_at: dt.datetime = meaning("when the value was produced, UTC")
    policy_version: Maybe[str] = meaning(
        "the policy version the value was derived under; a fact outlives it"
    )


@contract(kind="evidence.layered_bytes", version=1)
@dataclass(frozen=True, slots=True)
class LayeredBytes(Contract):
    """A byte quantity at all three layers of credibility.

    The same shape serves RAM, VRAM and storage. Keeping the layers in one
    value rather than three loose fields is what makes the authorization
    rule attach to the type instead of to each use of it.
    """

    reported_bytes: Maybe[int] = meaning(
        "what the source claims; may be displayed, never authorizes"
    )
    effective_bytes: Maybe[int] = meaning(
        "reported corrected for real usability; still never authorizes"
    )
    safe_bytes: Maybe[int] = meaning(
        "effective minus protected headroom; the only layer that may authorize"
    )
    confidence: Confidence = meaning("how much weight this quantity carries")
    provenance: Provenance = meaning("who produced it, when, under which policy")

    @property
    def authorizing_bytes(self) -> Maybe[int]:
        """The only layer permitted to authorize an allocation or a mutation.

        Named as a property so that a caller reaching for a number to admit
        against has one obvious choice, and so that reaching for
        ``reported_bytes`` instead is visible in review.
        """
        return self.safe_bytes
