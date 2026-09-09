"""Map ResourceSummary onto planning's DeploymentCapacity.

Planning cannot import resource. Platform copies current available
bytes from the snapshot onto the existing typed planning view.
"""

from __future__ import annotations

from dataclasses import replace

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import is_resolved
from kultrun.planning.contracts import (
    DeploymentCapacity,
    DeploymentPlan,
    ModelSelection,
)
from kultrun.planning.evaluate import deployment_capacity
from kultrun.resource.contracts import ResourceSummary
from kultrun.resource.manager import ResourceManager


def revalidation_plan_basis(
    plan: DeploymentPlan | None,
    selection: ModelSelection | None,
    *,
    pending_model: str | None = None,
) -> object:
    """Exclude this plan's grant only while selection is still that model."""
    if plan is None:
        return None
    plan_tokens = {plan.model_id.value, plan.logical_name.value}
    token = (pending_model or "").strip()
    if token and token not in plan_tokens:
        return None
    if token:
        return plan.plan_basis
    if selection is None:
        return plan.plan_basis
    selected = selection.selected_model_id
    if is_resolved(selected) and selected in plan_tokens:
        return plan.plan_basis
    name = selection.selected_logical_name
    if is_resolved(name) and name in plan_tokens:
        return plan.plan_basis
    return None


def planning_capacity(
    resources: ResourceManager,
    envelope: CapacityEnvelope,
    host: HostCapabilities,
    *,
    plan_basis: object = None,
) -> DeploymentCapacity:
    """Current available for planning. Omits this plan's own ACTIVE grant."""
    found = resources.active_reservation_for_plan(plan_basis)
    snapshot = resources.snapshot(
        envelope,
        host=host,
        exclude_reservation_id=(found.reservation_id if found is not None else None),
    )
    return bind_current_capacity(envelope, snapshot)


def bind_current_capacity(
    envelope: CapacityEnvelope, snapshot: ResourceSummary
) -> DeploymentCapacity:
    """SAFE from the envelope; available from the derived snapshot."""
    capacity = deployment_capacity(envelope)
    device = None
    if capacity.accelerator_index is not None:
        for item in snapshot.accelerators:
            if item.index == capacity.accelerator_index:
                device = item
                break
    return replace(
        capacity,
        available_ram_bytes=snapshot.available_ram_bytes,
        available_vram_bytes=(
            device.available_bytes
            if device is not None
            else capacity.available_vram_bytes
        ),
        available_storage_bytes=snapshot.available_storage_bytes,
        snapshot_basis=snapshot.snapshot_basis or capacity.snapshot_basis,
    )
