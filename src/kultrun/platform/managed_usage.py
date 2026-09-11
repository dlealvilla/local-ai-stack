"""Platform-managed bytes per pool. Speaks only mounts and byte counts.

Storage consumes this through ``ManagedUsageSource``. It must not learn
model identities or runtime names.
"""

from __future__ import annotations

from pathlib import Path

from kultrun.host.contracts import HostId
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.contracts import ArtifactState
from kultrun.model.inventory import ModelInventory
from kultrun.runtime.contracts import (
    InstallationStatus,
    RuntimeInstallation,
    RuntimeProvisioningPlan,
)


class PlatformManagedUsage:
    """Sums stored artifacts and installed runtimes per mount."""

    def __init__(
        self,
        store: Store,
        inventory: ModelInventory,
        state_root: Path | None = None,
    ) -> None:
        self._store = store
        self._inventory = inventory
        self._state_root = Path(state_root) if state_root is not None else None

    def bytes_by_mount(self, host_id: HostId) -> dict[str, int]:
        totals: dict[str, int] = {}
        for artifact in self._inventory.artifacts():
            record = self._inventory.record(artifact.artifact_id)
            if record is None or record.host_id != host_id:
                continue
            if artifact.state is not ArtifactState.STORED:
                continue
            mount = artifact.storage_mount
            size = artifact.installed_bytes
            if not is_resolved(mount) or not is_resolved(size):
                continue
            totals[mount] = totals.get(mount, 0) + size
        for installation in self._store.records(RuntimeInstallation):
            if installation.host_id != host_id:
                continue
            if installation.status is not InstallationStatus.INSTALLED:
                continue
            runtime_mount = self._runtime_mount(installation)
            runtime_size = self._runtime_bytes(installation)
            if runtime_mount is None or runtime_size is None:
                continue
            totals[runtime_mount] = totals.get(runtime_mount, 0) + runtime_size
        return totals

    def _runtime_mount(self, installation: RuntimeInstallation) -> str | None:
        plan = self._store.get(RuntimeProvisioningPlan, installation.plan_id.value)
        if plan is None or not is_resolved(plan.storage_mount):
            return None
        return plan.storage_mount

    def _runtime_bytes(self, installation: RuntimeInstallation) -> int | None:
        if is_resolved(installation.installed_bytes):
            return installation.installed_bytes
        plan = self._store.get(RuntimeProvisioningPlan, installation.plan_id.value)
        if plan is None or not is_resolved(plan.persistent_bytes):
            return None
        return plan.persistent_bytes
