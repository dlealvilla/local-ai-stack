"""What a policy is, and how a decision records the one that produced it.

Deliberately tiny. This module exists so that every policy in the platform
— headroom, retention, routing, selection, access — is versioned the same
way, rather than five domains inventing five conventions.

The determinism rule it supports: identical inputs under an identical
policy version yield an identical decision. Stage 3.5 depends on that being
checkable, and it is only checkable if the decision carries the version.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from kultrun.kernel.ids import Name
from kultrun.kernel.schema import Contract, contract, meaning


@contract(kind="policy.reference", version=1)
@dataclass(frozen=True, slots=True)
class PolicyRef(Contract):
    """Identifies the policy a decision was made under.

    A value object embedded in decisions and evidence. The policy's own
    content belongs to the domain that owns it.
    """

    policy_id: Name = meaning(
        "which policy, as a stable dotted name such as 'capacity.headroom'"
    )
    version: int = meaning(
        "policy version; a decision is reproducible only against the same one"
    )
    effective_at: dt.datetime = meaning("when this version took effect, UTC")
