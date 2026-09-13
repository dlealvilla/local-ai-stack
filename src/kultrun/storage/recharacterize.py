"""When identity-matched Sonar may be reused, and when it must not.

A verified writable lower bound remains true after occupancy drops.
An EDQUOT/ENOSPC upper observation is conditional on occupancy at probe
time. It is not an immutable quota ceiling.
"""

from __future__ import annotations

from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.contracts import EmpiricalProbeEvidence, StorageCapacityEvidence


def should_recharacterize(
    empirical: EmpiricalProbeEvidence | None,
    held: StorageCapacityEvidence | None,
    *,
    managed_now: int | None,
    reclaimable_bytes: int,
    current_safe_blocks: bool,
    actual_reclaimed_bytes: int = 0,
) -> bool:
    """True when reused empirical authority would hide newly available quota.

    Unchanged occupancy keeps the last identity-matched characterization.
    Historical free-space observations never appear here. Reclaimable
    bytes still on disk are counted in potential capacity; Sonar waits
    until after product reclaim.

    Actual product reclaim is an occupancy drop even when the stored
    ``accounted_managed_bytes`` snapshot is missing (sibling leftovers are
    not current-install managed usage).
    """
    if not current_safe_blocks:
        return False
    if actual_reclaimed_bytes > 0:
        return True
    if empirical is None or held is None:
        return False
    accounted = (
        held.accounted_managed_bytes
        if is_resolved(held.accounted_managed_bytes)
        else None
    )
    occupancy_dropped = (
        isinstance(managed_now, int)
        and isinstance(accounted, int)
        and managed_now < accounted
    )
    del reclaimable_bytes
    return occupancy_dropped
