"""Native Steward (MACHI 3).

Classifies caller-supplied roots. Does not crawl mounts, does not delete,
and does not compute SAFE storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from machi.adapters.steward.measure import measure_owned_tree
from machi.adapters.steward.read import read_ownership
from machi.discover.mount_contracts import MountObservation
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.store import Store
from machi.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe
from machi.steward.classify import classify_ownership
from machi.steward.contracts import (
    GenerationHint,
    OccupancyMap,
    OwnershipStatus,
    ProtectionHint,
    StewardResource,
    StewardSettings,
)
from machi.steward.policy import default_steward_settings
from machi.steward.project import (
    associate_mount,
    occupancy_map,
    resource_from_classification,
)

NATIVE_STEWARD = "native"


@dataclass(frozen=True, slots=True)
class RootClaim:
    """One root the caller already knows. Not a discovered path."""

    path: str
    generation: GenerationHint = GenerationHint.CURRENT
    protection: ProtectionHint = ProtectionHint.DEFAULT


class NativeSteward:
    """Assess known roots against Install evidence and an optional mount map."""

    observer_id = NATIVE_STEWARD

    def __init__(
        self,
        claims: tuple[RootClaim, ...] | list[RootClaim],
        *,
        store: Store | None = None,
        mounts: MountObservation | None = None,
        settings: StewardSettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._claims = tuple(claims)
        self._store = store
        self._mounts = mounts
        self._settings = settings or default_steward_settings()
        self._clock = clock or SystemClock()

    def assess(self) -> OccupancyMap:
        """Classify and, for verified roots only, measure occupancy."""
        when = self._clock.now()
        resources: list[StewardResource] = []
        seen: set[str] = set()
        for claim in self._claims:
            root = Path(claim.path)
            facts, fingerprint = read_ownership(root, self._store)
            classification = classify_ownership(
                facts,
                generation=claim.generation,
                protection=claim.protection,
                settings=self._settings,
            )
            resource_id = facts.marker_id or f"fp:{fingerprint}"
            if resource_id in seen:
                continue
            seen.add(resource_id)
            resolved = str(root.expanduser().resolve())
            mount_id, backing, storage = associate_mount(resolved, self._mounts)
            size: Maybe[int] = NOT_MEASURED
            if classification.ownership is OwnershipStatus.VERIFIED_MACHI_OWNED:
                size = measure_owned_tree(root.expanduser().resolve()).size_bytes
            install_id: Maybe[str]
            if facts.install_id is None:
                install_id = NOT_PROVIDED
            else:
                install_id = facts.install_id
            resources.append(
                resource_from_classification(
                    resource_id=resource_id,
                    path=resolved,
                    classification=classification,
                    generation=claim.generation,
                    install_id=install_id,
                    size_bytes=size,
                    mount_id=mount_id,
                    backing_store_id=backing,
                    storage_class=storage,
                )
            )
        return occupancy_map(
            tuple(resources),
            settings=self._settings,
            observed_at=when,
            provider=self.observer_id,
        )
