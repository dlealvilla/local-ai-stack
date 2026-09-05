"""What a deployment is entitled to.

Generic claims, not products. `docs/PRODUCT_VISION.md` §55 requires that
the architecture permit per-host, per-GPU, per-user, per-model, tiered and
usage-based commercial models without any of them being hard-coded, so a
claim is a name and an optional limit and nothing more. A marketing tier is
a bundle of claims assembled outside core logic.

Verification is local. `docs/PRODUCT_VISION.md` §53 requires air-gapped
operation to keep working, and that is only true if checking an entitlement
never needs the network. Renewal transport belongs to `vendor`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


class EntitlementKind(StrEnum):
    """Whether a claim unlocks a capability or bounds a quantity."""

    FEATURE = "feature"
    CAPACITY = "capacity"


@contract(kind="entitlement.claim", version=1)
@dataclass(frozen=True, slots=True)
class Entitlement(Contract):
    """One thing a deployment is permitted to do, or to have."""

    claim: Name = meaning(
        "what is claimed, as a generic name such as 'advanced_routing' or 'hosts'"
    )
    entitlement_kind: EntitlementKind = meaning(
        "whether this unlocks a capability or bounds a quantity"
    )
    limit: Maybe[int] | None = meaning(
        "the bound for a capacity claim; absent for a feature claim, "
        "unresolved when the grant is unreadable rather than unlimited",
        default=None,
    )
    granted_until: dt.datetime | None = meaning(
        "when the grant lapses; absent means perpetual", default=None
    )
    grace_until: dt.datetime | None = meaning(
        "how long the claim still holds after lapsing, so that a lost "
        "connection never interrupts production",
        default=None,
    )
