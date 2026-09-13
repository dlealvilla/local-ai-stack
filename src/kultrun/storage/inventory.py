"""Classify dual-owned Kultrun roots as occupancy. Does not delete.

Platform supplies activity and reuse tags. This module never infers
ownership from a directory name and never adds unknown bytes to capacity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    ManagedOccupancyClass,
    ManagedOccupancyItem,
    ManagedResourceType,
    OwnershipRecord,
    PoolOccupancy,
    StoragePool,
)
from kultrun.storage.ownership import tree_bytes
from kultrun.storage.topology import bind_path

_RECLAIMABLE_TYPES = frozenset(
    {
        ManagedResourceType.RUNTIME_FINAL,
        ManagedResourceType.RUNTIME_STAGING,
        ManagedResourceType.MODEL_ARTIFACT,
        ManagedResourceType.MODEL_STAGING,
        ManagedResourceType.INSTALL_CACHE,
        ManagedResourceType.TEMP,
        ManagedResourceType.DOWNLOAD_CACHE,
        ManagedResourceType.SONAR_PROBE,
    }
)


def classify_occupancy(
    records: Sequence[OwnershipRecord],
    pools: Sequence[StoragePool],
    *,
    current_state_root: Path,
    live_roots: Sequence[Path] = (),
    reusable_roots: Sequence[Path] = (),
) -> tuple[ManagedOccupancyItem, ...]:
    """Assign occupancy classes. Unknown and protected never increase potential."""
    current = Path(current_state_root).resolve()
    live = _resolved(live_roots)
    reusable = _resolved(reusable_roots)
    items: list[ManagedOccupancyItem] = []
    seen: set[str] = set()
    for record in records:
        key = record.ownership_id.value
        if key in seen:
            continue
        seen.add(key)
        path = Path(record.managed_root)
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        pool = bind_path(resolved, pools)
        occupancy, reason = _class_for(
            record,
            resolved,
            current=current,
            live=live,
            reusable=reusable,
        )
        items.append(
            ManagedOccupancyItem(
                ownership_id=record.ownership_id,
                resource_type=record.resource_type,
                occupancy_class=occupancy,
                managed_root=str(resolved),
                occupied_bytes=tree_bytes(resolved),
                mount_point=pool.mount_point if pool is not None else NOT_PROVIDED,
                quota_identity=(
                    pool.quota_identity
                    if pool is not None and is_resolved(pool.quota_identity)
                    else record.quota_identity
                ),
                pool_fingerprint=(
                    pool.fingerprint if pool is not None else NOT_PROVIDED
                ),
                reason=reason,
            )
        )
    return tuple(items)


_CLASS_PRIORITY = {
    ManagedOccupancyClass.ACTIVE: 4,
    ManagedOccupancyClass.REUSABLE: 3,
    ManagedOccupancyClass.PROTECTED: 2,
    ManagedOccupancyClass.RECLAIMABLE: 1,
    ManagedOccupancyClass.UNKNOWN: 0,
}


def unique_occupancy(
    items: Sequence[ManagedOccupancyItem],
) -> tuple[ManagedOccupancyItem, ...]:
    """One class per path. Nested trees do not add the same bytes twice.

    A weaker ancestor must not hide a stronger descendant. An UNKNOWN
    sibling ``state`` root would otherwise swallow cleanup-eligible
    ``models`` / ``runtimes`` and block product reclaim.
    """
    by_path: dict[str, ManagedOccupancyItem] = {}
    for item in items:
        existing = by_path.get(item.managed_root)
        if (
            existing is None
            or _CLASS_PRIORITY[item.occupancy_class]
            > _CLASS_PRIORITY[existing.occupancy_class]
        ):
            by_path[item.managed_root] = item
    candidates = tuple(by_path.values())
    hidden_parents = {
        item.managed_root
        for item in candidates
        if any(
            _under(Path(other.managed_root), Path(item.managed_root))
            and _CLASS_PRIORITY[other.occupancy_class]
            > _CLASS_PRIORITY[item.occupancy_class]
            for other in candidates
        )
    }
    remaining = tuple(
        item for item in candidates if item.managed_root not in hidden_parents
    )
    kept: list[ManagedOccupancyItem] = []
    for item in remaining:
        path = Path(item.managed_root)
        prio = _CLASS_PRIORITY[item.occupancy_class]
        if any(
            _under(path, Path(other.managed_root))
            and _CLASS_PRIORITY[other.occupancy_class] >= prio
            for other in remaining
            if other.managed_root != item.managed_root
        ):
            continue
        kept.append(item)
    return tuple(sorted(kept, key=lambda row: row.managed_root))


def totals_by_pool(
    items: Sequence[ManagedOccupancyItem],
) -> Mapping[str, PoolOccupancy]:
    """Sum occupancy per mount. Missing mounts are omitted, not zero."""
    grouped: dict[str, dict[str, int]] = {}
    meta: dict[str, tuple[Maybe[str], Maybe[str]]] = {}
    for item in unique_occupancy(items):
        if not isinstance(item.mount_point, str):
            continue
        bucket = grouped.setdefault(
            item.mount_point,
            {
                "active": 0,
                "reusable": 0,
                "reclaimable": 0,
                "protected": 0,
                "unknown": 0,
            },
        )
        key = item.occupancy_class.value
        if key in bucket:
            bucket[key] += item.occupied_bytes
        meta[item.mount_point] = (item.quota_identity, item.pool_fingerprint)
    return {
        mount: PoolOccupancy(
            mount_point=mount,
            quota_identity=meta[mount][0],
            pool_fingerprint=meta[mount][1],
            active_bytes=values["active"],
            reusable_bytes=values["reusable"],
            reclaimable_bytes=values["reclaimable"],
            protected_bytes=values["protected"],
            unknown_bytes=values["unknown"],
        )
        for mount, values in grouped.items()
    }


def same_quota_domain(
    mount: str,
    quota: object,
    fingerprint: object,
    pool: StoragePool,
) -> bool:
    """Reclaimable bytes only count on the destination pool's identity."""
    if pool.mount_point != mount:
        return False
    if is_resolved(fingerprint) and fingerprint != pool.fingerprint:
        return False
    if is_resolved(quota) and is_resolved(pool.quota_identity):
        return quota == pool.quota_identity
    return True


def _class_for(
    record: OwnershipRecord,
    resolved: Path,
    *,
    current: Path,
    live: set[Path],
    reusable: set[Path],
) -> tuple[ManagedOccupancyClass, str]:
    if record.rollback_protected or record.evidence_retained:
        return ManagedOccupancyClass.PROTECTED, "rollback or evidence retained"
    if _covers(resolved, live):
        return ManagedOccupancyClass.ACTIVE, "referenced by a live workload"
    if _covers(resolved, reusable):
        return ManagedOccupancyClass.REUSABLE, "satisfies the next deployment"
    if _is_current_protected(record, resolved, current):
        return ManagedOccupancyClass.PROTECTED, "current installation retained root"
    if record.resource_type in _RECLAIMABLE_TYPES and not _under(resolved, current):
        return (
            ManagedOccupancyClass.RECLAIMABLE,
            "inactive owned Kultrun state on this quota domain",
        )
    if record.resource_type in _RECLAIMABLE_TYPES and _under(resolved, current):
        return ManagedOccupancyClass.PROTECTED, "current managed tree not reusable"
    return ManagedOccupancyClass.UNKNOWN, "ownership or activity not proven safe"


def _is_current_protected(
    record: OwnershipRecord, resolved: Path, current: Path
) -> bool:
    if not _under(resolved, current) and resolved != current:
        return False
    return record.resource_type not in _RECLAIMABLE_TYPES or record.protected


def _covers(path: Path, roots: set[Path]) -> bool:
    for root in roots:
        if path == root or _under(path, root) or _under(root, path):
            return True
    return False


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return path != root
    except ValueError:
        return False


def _resolved(paths: Sequence[Path]) -> set[Path]:
    found: set[Path] = set()
    for item in paths:
        try:
            found.add(Path(item).resolve())
        except OSError:
            continue
    return found
