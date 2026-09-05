"""Storage as a set of pools.

A pool is the platform's interpretation of a mount as allocatable,
quota-bounded, fingerprinted capacity. That is a different concept from the
mount facts `host` reports, which is why they have different owners: one is
inspection, the other is the domain against which a mutation is admitted.

Pools are plural from v1 on a reference host that has one. The previous
attempt designed multi-pool storage and never exercised it, and
`docs/ARCHITECTURE.md` Part II §6 makes the general form of that mistake —
assuming one of something there will later be many of — the thing to avoid
at contract-writing time.

The evidence and probing that make a pool's capacity *credible* are Stages
2.2 to 2.4. What exists here is pool identity, which Stage 1.2 needs in
order to speak about storage at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from kultrun.host.contracts import HostId
from kultrun.kernel.ids import EntityId
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


class StoragePoolId(EntityId):
    """Identifies one storage pool."""

    prefix = "pool"


class ProviderClass(StrEnum):
    """What kind of storage backs a pool.

    This drives whether evidence gathered on one pool may be reused on
    another, and whether free-space reporting can be trusted at all —
    network and virtualized volumes reclaim space asynchronously, which is
    how the previous attempt saw a 42,990 MiB deletion return 1.1 GB to
    ``df``.
    """

    LOCAL_DISK = "local_disk"
    NETWORK = "network"
    VIRTUAL = "virtual"
    UNKNOWN = "unknown"


@contract(kind="storage.pool", version=1)
@dataclass(frozen=True, slots=True)
class StoragePool(Contract):
    """One region of storage a mutation can be admitted against."""

    pool_id: StoragePoolId = meaning("platform-minted identity of this pool")
    host_id: HostId = meaning("the host this pool belongs to")
    mount_point: str = meaning("path at which the pool's filesystem is mounted")
    provider_class: ProviderClass = meaning(
        "what backs the pool, which governs whether its evidence is reusable"
    )
    fingerprint: str = meaning(
        "digest of mount identity, filesystem type and quota identity; "
        "evidence is keyed on this and is invalid when it changes"
    )
    generation: int = meaning(
        "advances on every successful mutation, invalidating earlier evidence"
    )
    filesystem_type: Maybe[str] = meaning("filesystem type as reported")
    quota_identity: Maybe[str] = meaning(
        "the quota this pool is bounded by, where one applies; a quota "
        "failure bounds capacity differently from a disk-full failure"
    )
