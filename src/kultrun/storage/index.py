"""Persisted Storage Sonar evidence. A lookup, never a probe."""

from __future__ import annotations

import hashlib

from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.persistence import Store
from kultrun.storage.contracts import StorageCapacityEvidence


def evidence_key(host_id: HostId, mount_point: str) -> str:
    digest = hashlib.sha256(f"{host_id.value}:{mount_point}".encode()).hexdigest()[:24]
    return f"sce_{digest}"


class StorageEvidenceIndex:
    """Index of last characterization per pool. Rebuildable by characterizing."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def put(self, evidence: StorageCapacityEvidence) -> None:
        self._store.put(evidence_key(evidence.host_id, evidence.mount_point), evidence)

    def put_many(self, items: dict[str, StorageCapacityEvidence]) -> None:
        for item in items.values():
            self.put(item)

    def for_host(self, host: HostCapabilities) -> dict[str, StorageCapacityEvidence]:
        found: dict[str, StorageCapacityEvidence] = {}
        for item in self._store.records(StorageCapacityEvidence):
            if item.host_id == host.host_id:
                found[item.mount_point] = item
        return found

    def invalidate(
        self,
        host_id: HostId | None = None,
        mount_point: str | None = None,
    ) -> None:
        """Drop authorizing evidence so the next mutation must rediscover."""
        for item in self._store.records(StorageCapacityEvidence):
            if host_id is not None and item.host_id != host_id:
                continue
            if mount_point is not None and item.mount_point != mount_point:
                continue
            self._store.delete(
                StorageCapacityEvidence, evidence_key(item.host_id, item.mount_point)
            )
