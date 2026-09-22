"""Build an OccupancyMap from classifications. No host I/O."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from machi.discover.mount_contracts import MountObservation
from machi.kernel.unresolved import (
    NOT_MEASURED,
    NOT_PROVIDED,
    Maybe,
    Unresolved,
    is_resolved,
)
from machi.steward.classify import Classification
from machi.steward.contracts import (
    BackingOccupancy,
    GenerationHint,
    LifecycleStatus,
    OccupancyMap,
    OccupancyTotals,
    OwnershipStatus,
    ProtectionStatus,
    Reclaimability,
    StewardResource,
    StewardSettings,
)

_PROTECTED = frozenset(
    {
        ProtectionStatus.ACTIVE_PROTECTED,
        ProtectionStatus.ROLLBACK_PROTECTED,
        ProtectionStatus.EVIDENCE_RETAINED,
        ProtectionStatus.POLICY_RETAINED,
    }
)


def associate_mount(
    path: str, observation: MountObservation | None
) -> tuple[Maybe[str], Maybe[str], Maybe[str]]:
    """Longest supplied mount point that contains this root. Does not rediscover."""
    if observation is None:
        return NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED
    best = None
    best_len = -1
    for entry in observation.entries:
        point = entry.mount_point.rstrip("/") or "/"
        if (path == point or path.startswith(point + "/")) and len(point) > best_len:
            best = entry
            best_len = len(point)
    if best is None:
        missing = Unresolved(
            NOT_PROVIDED.reason, "no supplied mount contains this root"
        )
        return missing, missing, missing
    storage = best.storage_class.value
    return best.mount_id, best.backing_store_id, storage


def resource_from_classification(
    *,
    resource_id: str,
    path: str,
    classification: Classification,
    generation: GenerationHint,
    install_id: Maybe[str],
    size_bytes: Maybe[int],
    mount_id: Maybe[str],
    backing_store_id: Maybe[str],
    storage_class: Maybe[str],
) -> StewardResource:
    """One classified root. Measured bytes are refused unless ownership is verified."""
    measured: Maybe[int]
    if classification.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED:
        measured = size_bytes
    else:
        measured = NOT_MEASURED
    return StewardResource(
        resource_id=resource_id,
        path=path,
        ownership=classification.ownership,
        lifecycle=classification.lifecycle,
        protection=classification.protection,
        reclaimability=classification.reclaimability,
        category=classification.category,
        generation=generation,
        install_id=install_id,
        size_bytes=measured,
        mount_id=mount_id,
        backing_store_id=backing_store_id,
        storage_class=storage_class,
        provenance=classification.provenance,
        reason=classification.reason,
        destructive_authorization=False,
    )


def occupancy_map(
    resources: tuple[StewardResource, ...],
    *,
    settings: StewardSettings,
    observed_at: dt.datetime,
    provider: str,
) -> OccupancyMap:
    """Aggregate without counting the same resource id twice."""
    unique: list[StewardResource] = []
    seen: set[str] = set()
    for resource in resources:
        if resource.resource_id in seen:
            continue
        seen.add(resource.resource_id)
        unique.append(resource)
    rows = tuple(unique)
    return OccupancyMap(
        resources=rows,
        totals=_totals(rows),
        backing=_backing(rows),
        settings=settings,
        destructive_authorization=False,
        observed_at=observed_at,
        provider=provider,
    )


def _totals(resources: tuple[StewardResource, ...]) -> OccupancyTotals:
    return OccupancyTotals(
        active_bytes=_sum(
            resources,
            lambda item: (
                item.lifecycle in {LifecycleStatus.ACTIVE, LifecycleStatus.STANDBY}
            ),
        ),
        protected_bytes=_sum(
            resources,
            lambda item: item.protection in _PROTECTED,
        ),
        reclaimable_bytes=_sum(
            resources,
            lambda item: item.reclaimability is Reclaimability.RECLAIMABLE,
        ),
        unknown_bytes=_unknown(resources),
    )


def _unknown(resources: tuple[StewardResource, ...]) -> Maybe[int]:
    unclassified = [
        item
        for item in resources
        if item.ownership is not OwnershipStatus.VERIFIED_MACHI_OWNED
    ]
    if not unclassified:
        return 0
    return Unresolved(
        NOT_MEASURED.reason,
        "unverified roots were not measured",
    )


def _sum(
    resources: tuple[StewardResource, ...],
    include: Callable[[StewardResource], bool],
) -> Maybe[int]:
    chosen = [item for item in resources if include(item)]
    if not chosen:
        return 0
    total = 0
    for item in chosen:
        size = item.size_bytes
        if not is_resolved(size):
            return Unresolved(NOT_MEASURED.reason, "a selected root was not measured")
        total += size
    return total


def _backing(resources: tuple[StewardResource, ...]) -> tuple[BackingOccupancy, ...]:
    groups: dict[str, list[StewardResource]] = {}
    for resource in resources:
        if is_resolved(resource.backing_store_id):
            key = str(resource.backing_store_id)
        else:
            key = ""
        groups.setdefault(key, []).append(resource)
    rows: list[BackingOccupancy] = []
    for key, members in groups.items():
        identity: Maybe[str]
        if key:
            identity = key
        else:
            identity = NOT_PROVIDED
        rows.append(
            BackingOccupancy(
                backing_store_id=identity,
                resource_count=len(members),
                size_bytes=_sum(tuple(members), lambda _item: True),
            )
        )
    return tuple(rows)
