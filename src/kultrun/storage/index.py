"""Persisted storage observation vs authorizing characterization.

A cheap ``kultrun host`` may refresh the latest observation. It must not
erase a still-valid authorizing characterization merely because empirical
probing was not run.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.persistence import Store
from kultrun.storage.contracts import (
    AdministratorCapacityBound,
    EmpiricalProbeEvidence,
    StorageCapacityEvidence,
)
from kultrun.storage.topology import pools_from_host


def observation_key(host_id: HostId, mount_point: str) -> str:
    digest = hashlib.sha256(f"{host_id.value}:{mount_point}".encode()).hexdigest()[:24]
    return f"sco_{digest}"


def evidence_key(host_id: HostId, mount_point: str) -> str:
    digest = hashlib.sha256(f"{host_id.value}:{mount_point}".encode()).hexdigest()[:24]
    return f"sce_{digest}"


def empirical_key(host_id: HostId, mount_point: str) -> str:
    digest = hashlib.sha256(f"{host_id.value}:{mount_point}".encode()).hexdigest()[:24]
    return f"see_{digest}"


def administrator_key(host_id: HostId, mount_point: str) -> str:
    digest = hashlib.sha256(f"{host_id.value}:{mount_point}".encode()).hexdigest()[:24]
    return f"sca_{digest}"


def same_storage_identity(
    held: StorageCapacityEvidence, current: StorageCapacityEvidence
) -> bool:
    """True when the stored characterization still describes this pool."""
    if held.host_id != current.host_id:
        return False
    if held.mount_point != current.mount_point:
        return False
    if held.pool_fingerprint != current.pool_fingerprint:
        return False
    return held.quota_identity == current.quota_identity


class StorageEvidenceIndex:
    """Latest observation, latest authorizing characterization, empirical runs."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def put(self, evidence: StorageCapacityEvidence) -> None:
        """Write the authorizing slot. Used after contradiction or expensive runs."""
        self._store.put(evidence_key(evidence.host_id, evidence.mount_point), evidence)

    def put_many(self, items: dict[str, StorageCapacityEvidence]) -> None:
        """Expensive persist: observation + authorizing characterization."""
        self.record_expensive(items)

    def record_observation(self, items: Mapping[str, StorageCapacityEvidence]) -> None:
        """Cheap persist. Never overwrites authorizing evidence of the same identity."""
        for item in items.values():
            self._store.put(observation_key(item.host_id, item.mount_point), item)
            held = self._store.get(
                StorageCapacityEvidence, evidence_key(item.host_id, item.mount_point)
            )
            if held is not None and not same_storage_identity(held, item):
                self._invalidate_authorizing(item.host_id, item.mount_point)

    def record_expensive(
        self,
        items: Mapping[str, StorageCapacityEvidence],
        empirical: Mapping[str, EmpiricalProbeEvidence] | None = None,
    ) -> None:
        """Mutation-path persist. May replace authorizing, including UNRESOLVED."""
        for item in items.values():
            self._store.put(observation_key(item.host_id, item.mount_point), item)
            self.put(item)
        if empirical:
            for probe in empirical.values():
                self.put_empirical(probe)

    def put_empirical(self, evidence: EmpiricalProbeEvidence) -> None:
        self._store.put(empirical_key(evidence.host_id, evidence.mount_point), evidence)

    def put_administrator_bound(self, bound: AdministratorCapacityBound) -> None:
        self._store.put(administrator_key(bound.host_id, bound.mount_point), bound)

    def get_administrator_bound(
        self, host_id: HostId, mount_point: str
    ) -> AdministratorCapacityBound | None:
        return self._store.get(
            AdministratorCapacityBound, administrator_key(host_id, mount_point)
        )

    def delete_administrator_bound(self, host_id: HostId, mount_point: str) -> None:
        self._store.delete(
            AdministratorCapacityBound, administrator_key(host_id, mount_point)
        )

    def matching_administrator_bytes(self, host: HostCapabilities) -> dict[str, int]:
        """Identity-matched last-resort bytes. Fingerprint/quota mismatch is omitted."""
        pools = {pool.mount_point: pool for pool in pools_from_host(host)}
        found: dict[str, int] = {}
        for bound in self._store.records(AdministratorCapacityBound):
            if bound.host_id != host.host_id:
                continue
            pool = pools.get(bound.mount_point)
            if pool is None:
                continue
            if pool.fingerprint != bound.pool_fingerprint:
                continue
            if pool.quota_identity != bound.quota_identity:
                continue
            found[bound.mount_point] = bound.available_bytes
        return found

    def for_host(self, host: HostCapabilities) -> dict[str, StorageCapacityEvidence]:
        """Planning view: authorizing when identity still matches, else observation."""
        observations, authorizing = self._split(host.host_id)
        if not observations:
            return authorizing
        merged: dict[str, StorageCapacityEvidence] = {}
        for mount, observation in observations.items():
            held = authorizing.get(mount)
            if held is not None and same_storage_identity(held, observation):
                merged[mount] = held
            else:
                merged[mount] = observation
        return merged

    def empirical_for_host(
        self, host: HostCapabilities
    ) -> dict[str, EmpiricalProbeEvidence]:
        found: dict[str, EmpiricalProbeEvidence] = {}
        for item in self._store.records(EmpiricalProbeEvidence):
            if item.host_id == host.host_id:
                found[item.mount_point] = item
        return found

    def invalidate(
        self,
        host_id: HostId | None = None,
        mount_point: str | None = None,
    ) -> None:
        """Drop authorizing + empirical so the next mutation must rediscover.

        Observations remain. A later cheap GET still cannot invent capacity.
        """
        seen: set[tuple[str, str]] = set()
        for item in self._store.records(StorageCapacityEvidence):
            if host_id is not None and item.host_id != host_id:
                continue
            if mount_point is not None and item.mount_point != mount_point:
                continue
            pair = (item.host_id.value, item.mount_point)
            if pair in seen:
                continue
            seen.add(pair)
            self._invalidate_authorizing(item.host_id, item.mount_point)

    def _invalidate_authorizing(self, host_id: HostId, mount_point: str) -> None:
        self._store.delete(StorageCapacityEvidence, evidence_key(host_id, mount_point))
        self._store.delete(EmpiricalProbeEvidence, empirical_key(host_id, mount_point))

    def _split(
        self, host_id: HostId
    ) -> tuple[dict[str, StorageCapacityEvidence], dict[str, StorageCapacityEvidence]]:
        observations: dict[str, StorageCapacityEvidence] = {}
        authorizing: dict[str, StorageCapacityEvidence] = {}
        for key in self._store.keys(StorageCapacityEvidence):
            item = self._store.get(StorageCapacityEvidence, key)
            if item is None or item.host_id != host_id:
                continue
            if key.startswith("sco_"):
                observations[item.mount_point] = item
            else:
                authorizing[item.mount_point] = item
        return observations, authorizing
