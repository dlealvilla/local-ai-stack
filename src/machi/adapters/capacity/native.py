"""Native Capacity evaluator. Domain code decides; this module only supplies facts."""

from __future__ import annotations

from machi.adapters.capacity.execution import read_execution_limit
from machi.capacity.compose import compose_envelope
from machi.capacity.contracts import (
    AdministratorBound,
    CapacityEnvelope,
    CapacitySettings,
    SonarEvidence,
    SonarWritePolicy,
    SpecialistBound,
)
from machi.capacity.derive import domain_needs_sonar
from machi.capacity.policy import default_capacity_settings, production_schedule
from machi.capacity.sonar import SonarMedia, run_sonar
from machi.discover.contracts import AcceleratorObservation, MemoryObservation
from machi.discover.mount_contracts import MountObservation
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.unresolved import Maybe
from machi.steward.contracts import OccupancyMap

NATIVE_CAPACITY = "native"


class NativeCapacity:
    """Compose an envelope from observations the caller already holds."""

    provider_id = NATIVE_CAPACITY

    def __init__(
        self,
        *,
        memory: MemoryObservation | None,
        accelerators: AcceleratorObservation | None,
        mounts: MountObservation | None,
        occupancy: OccupancyMap | None = None,
        execution_limit_bytes: Maybe[int] | None = None,
        specialists: tuple[SpecialistBound, ...] = (),
        admins: tuple[AdministratorBound, ...] = (),
        settings: CapacitySettings | None = None,
        sonar_media: dict[str, SonarMedia] | None = None,
        evidence_id: str = "cap_local",
        input_parts: tuple[str, ...] = (),
        clock: Clock | None = None,
    ) -> None:
        self._memory = memory
        self._accelerators = accelerators
        self._mounts = mounts
        self._occupancy = occupancy
        if execution_limit_bytes is None:
            self._execution = read_execution_limit()
        else:
            self._execution = execution_limit_bytes
        self._specialists = specialists
        self._admins = admins
        self._settings = settings or default_capacity_settings()
        self._sonar_media = sonar_media or {}
        self._evidence_id = evidence_id
        self._input_parts = input_parts
        self._clock = clock or SystemClock()

    def evaluate(self) -> CapacityEnvelope:
        """Derive SAFE ceilings. Sonar writes only when explicitly bounded."""
        sonar = self._maybe_sonar()
        return compose_envelope(
            evidence_id=self._evidence_id,
            memory=self._memory,
            execution_limit_bytes=self._execution,
            accelerators=self._accelerators,
            mounts=self._mounts,
            occupancy=self._occupancy,
            specialists=self._specialists,
            admins=self._admins,
            sonar_by_domain=sonar,
            settings=self._settings,
            observed_at=self._clock.now(),
            provider=self.provider_id,
            input_parts=self._input_parts or (self._evidence_id,),
        )

    def _maybe_sonar(self) -> dict[str, SonarEvidence]:
        if self._settings.sonar_writes is not SonarWritePolicy.BOUNDED:
            return {}
        if self._mounts is None:
            return {}
        upward, refine, downward = production_schedule()
        found: dict[str, SonarEvidence] = {}
        for domain_id, media in self._sonar_media.items():
            if not domain_needs_sonar(self._mounts, domain_id):
                continue
            reported = _reported(self._mounts, domain_id)
            found[domain_id] = run_sonar(
                media,
                upward=upward,
                refine=refine,
                downward=downward,
                reported_available_bytes=reported,
                reserve_bytes=self._settings.storage_reserve_bytes,
                max_tier_bytes=self._settings.sonar_max_tier_bytes,
            )
        return found


def _reported(mounts: MountObservation, domain_id: str) -> Maybe[int]:
    from machi.kernel.unresolved import NOT_MEASURED, is_resolved

    values: list[int] = []
    for entry in mounts.entries:
        identity = (
            str(entry.backing_store_id)
            if is_resolved(entry.backing_store_id)
            else entry.mount_id
        )
        if identity != domain_id:
            continue
        if is_resolved(entry.reported_capacity.available_bytes):
            values.append(int(entry.reported_capacity.available_bytes))
    if not values:
        return NOT_MEASURED
    return min(values)
