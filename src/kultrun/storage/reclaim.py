"""Plan and execute pre-provision reclaim. Not Step 0 disposable cleanup.

Step 0 still removes DISPOSABLE roots. This path deletes inactive
RETAIN runtimes/models only when occupancy classified them reclaimable
and dual ownership still agrees at execute time.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kultrun.storage.contracts import (
    ManagedOccupancyClass,
    ManagedOccupancyItem,
    OwnershipRecord,
    ReclaimAction,
    StorageReclaimPlan,
    StorageReclaimResult,
)
from kultrun.storage.inventory import unique_occupancy
from kultrun.storage.ownership import OwnershipService, tree_bytes


def plan_reclaim(
    items: Sequence[ManagedOccupancyItem],
    *,
    mount_point: str,
    capacity_required: bool = False,
) -> StorageReclaimPlan:
    """Collect reclaimable roots on one mount. Does not delete."""
    actions = tuple(
        ReclaimAction(
            ownership_id=item.ownership_id,
            resource_type=item.resource_type,
            expected_bytes=item.occupied_bytes,
            mount_point=mount_point,
            reason=item.reason,
        )
        for item in unique_occupancy(items)
        if item.occupancy_class is ManagedOccupancyClass.RECLAIMABLE
        and item.mount_point == mount_point
        and item.occupied_bytes > 0
    )
    expected = sum(item.expected_bytes for item in actions)
    return StorageReclaimPlan(
        mount_point=mount_point,
        expected_bytes=expected,
        actions=actions,
        cleanup_required_by_lifecycle=expected > 0,
        cleanup_required_for_capacity=capacity_required and expected > 0,
    )


def execute_reclaim(
    plan: StorageReclaimPlan,
    records: Sequence[OwnershipRecord],
    ownership: OwnershipService,
    *,
    allowed_roots: Sequence[Path],
) -> StorageReclaimResult:
    """Delete planned roots after a last-moment ownership check."""
    by_id = {item.ownership_id: item for item in records}
    actual = 0
    removed = 0
    blocked: list[str] = []
    for action in plan.actions:
        record = by_id.get(action.ownership_id)
        if record is None:
            blocked.append(action.ownership_id.value)
            continue
        root = Path(record.managed_root)
        if not ownership.is_allowed(root, allowed_roots):
            blocked.append(str(root))
            continue
        before = tree_bytes(root)
        if not ownership.delete_owned_root(root, record):
            blocked.append(str(root))
            continue
        ownership.forget(action.ownership_id)
        actual += before
        removed += 1
    return StorageReclaimResult(
        mount_point=plan.mount_point,
        expected_bytes=plan.expected_bytes,
        actual_bytes=actual,
        removed=removed,
        blocked=tuple(blocked),
        rediscovery_required=True,
    )
