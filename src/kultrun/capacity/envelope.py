"""Reported → effective → safe.

Stage 1.1 answered *what does the host report?* This answers *what can
Kultrun safely use?* The gap between those two questions is where the
previous attempt lost most of its time, so the three layers are kept
distinct all the way down to the leaf and only one of them may authorize
anything.

| Layer | Means | Authorizes |
|---|---|---|
| reported | what a provider, the OS or a filesystem says | never |
| effective | what is genuinely available to *this* deployment | no |
| safe | effective minus protected headroom | yes, and only this |

**Policy only.** No probing, no calibration, no evidence providers. That is
the roadmap's central sequencing insight: safe admission needs honest
conservatism, not empirical characterization. Empirical storage evidence is
Stage 2.2, and `docs/design/EMPIRICAL-STORAGE-CHARACTERIZATION.md` records
what it must and must not repeat.

**Derived, never stored.** An envelope is a view over host facts and a
policy. A persisted envelope invites a stale number authorizing a present
decision, and the host it described may no longer be the host running.
"""

from __future__ import annotations

from typing import Final

from kultrun.capacity.contracts import (
    AcceleratorCapacity,
    CapacityEnvelope,
    EvidenceRequirement,
    HeadroomPolicy,
    PoolCapacity,
)
from kultrun.capacity.policy import VOLATILE_FAMILIES, default_policy
from kultrun.evidence.contracts import Confidence, LayeredBytes, Provenance
from kultrun.host.contracts import Accelerator, HostCapabilities, MountFacts
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import (
    NOT_MEASURED,
    NOT_PROVIDED,
    Maybe,
    is_resolved,
)

PRODUCER: Final = Name("capacity")


class CapacityService:
    """Computes what this host can safely give, under a headroom policy."""

    def __init__(
        self, policy: HeadroomPolicy | None = None, clock: Clock | None = None
    ) -> None:
        self._policy = policy or default_policy()
        self._clock = clock or SystemClock()

    @property
    def policy(self) -> HeadroomPolicy:
        return self._policy

    def compute(self, host: HostCapabilities) -> CapacityEnvelope:
        """Derive the envelope from host facts. Deterministic but for the clock."""
        defects: list[str] = []
        memory, memory_requirement, memory_note = self._memory(host, defects)
        accelerators = self._accelerators(host, defects)
        pools = self._pools(host, defects)

        return CapacityEnvelope(
            host_id=host.host_id,
            host_fingerprint=host.fingerprint,
            computed_at=self._clock.now(),
            policy_version=self._policy.policy_version,
            memory=memory,
            memory_requirement=memory_requirement,
            accelerators=accelerators,
            pools=pools,
            defects=tuple(defects),
            memory_note=memory_note,
        )

    # -- system memory -----------------------------------------------------

    def _memory(
        self, host: HostCapabilities, defects: list[str]
    ) -> tuple[LayeredBytes, EvidenceRequirement, str | None]:
        """Reported total, restricted by any environment ceiling, then reserved.

        The restriction is the point. The reference host reports 251.5 GiB
        of system memory while its container may use 57.7 GiB — admitting
        against the machine would get workloads OOM-killed. `MemTotal`
        describes the machine; `limit_bytes` describes what this deployment
        has. Effective takes the smaller.
        """
        reported = host.memory.total_bytes
        limit = host.memory.limit_bytes
        requirement = EvidenceRequirement.SUFFICIENT
        note: str | None = None

        if not is_resolved(reported):
            defects.append(
                "system memory total is unresolved, so no safe memory figure "
                "exists and nothing may be admitted against memory"
            )
            return (
                self._layered(NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED,
                              Confidence.UNKNOWN),
                EvidenceRequirement.UNKNOWN,
                "host discovery reported no memory total",
            )

        effective = reported
        if is_resolved(limit):
            requirement = EvidenceRequirement.RESTRICTED
            if limit < reported:
                effective = limit
                note = (
                    f"the environment restricts this deployment to "
                    f"{limit} bytes of the machine's {reported}"
                )
            else:
                note = "an environment limit exists and is not restrictive"

        safe = self._withhold(
            effective,
            self._policy.memory_reserve_fraction,
            self._policy.memory_reserve_floor_bytes,
        )
        if not is_resolved(safe):
            defects.append(
                "the memory reserve exceeds effective memory, so no safe "
                "memory remains"
            )
        return (
            self._layered(reported, effective, safe, Confidence.HIGH),
            requirement,
            note,
        )

    # -- accelerators ------------------------------------------------------

    def _accelerators(
        self, host: HostCapabilities, defects: list[str]
    ) -> tuple[AcceleratorCapacity, ...]:
        """Only the accelerators Stage 1.1 found **assigned**.

        Devices are not rediscovered here. Host discovery already reconciled
        four devices visible on the reference host's bus down to the one
        assigned to this container, and an envelope covering four would
        claim roughly 128 GiB of accelerator memory that does not exist.
        """
        if not host.accelerators:
            defects.append(
                "no accelerator is assigned to this deployment, so no "
                "accelerator capacity exists"
            )
            return ()
        return tuple(
            self._accelerator(accelerator, host, defects)
            for accelerator in host.accelerators
        )

    def _accelerator(
        self,
        accelerator: Accelerator,
        host: HostCapabilities,
        defects: list[str],
    ) -> AcceleratorCapacity:
        reported = accelerator.memory_total_bytes
        if not is_resolved(reported):
            defects.append(
                f"accelerator {accelerator.index} reports no memory total, so "
                f"nothing may be admitted to it"
            )
            return AcceleratorCapacity(
                index=accelerator.index,
                memory=self._layered(NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED,
                                     Confidence.UNKNOWN),
                requirement=EvidenceRequirement.UNKNOWN,
                note="the vendor interface reported no device memory",
            )

        # Unified memory must never be double-counted, and unknown fails
        # closed rather than assuming independence. On a unified host the
        # device figure is not additional to system memory, so treating it
        # as a separate budget would admit a workload that cannot fit.
        unified = _first_resolved(
            accelerator.unified_memory, host.memory.unified_with_accelerator
        )
        if not is_resolved(unified):
            defects.append(
                f"accelerator {accelerator.index}: whether its memory is "
                f"shared with system memory is unknown, so no safe figure is "
                f"asserted rather than assuming the two are independent"
            )
            return AcceleratorCapacity(
                index=accelerator.index,
                memory=self._layered(reported, NOT_PROVIDED, NOT_PROVIDED,
                                     Confidence.LOW),
                requirement=EvidenceRequirement.UNKNOWN,
                note="unified memory unresolved; failing closed",
            )
        if unified is True:
            defects.append(
                f"accelerator {accelerator.index} shares system memory, "
                f"which Stage 1.2 does not model; no separate accelerator "
                f"budget is asserted (DC-01)"
            )
            return AcceleratorCapacity(
                index=accelerator.index,
                memory=self._layered(reported, NOT_PROVIDED, NOT_PROVIDED,
                                     Confidence.LOW),
                requirement=EvidenceRequirement.EMPIRICAL_EVIDENCE_NEEDED,
                note=(
                    "unified with system memory; a shared budget is deferred "
                    "rather than double-counted"
                ),
            )

        safe = self._withhold(
            reported,
            self._policy.accelerator_reserve_fraction,
            self._policy.accelerator_reserve_floor_bytes,
        )
        if not is_resolved(safe):
            defects.append(
                f"accelerator {accelerator.index}: the reserve exceeds device "
                f"memory, so no safe accelerator memory remains"
            )
        return AcceleratorCapacity(
            index=accelerator.index,
            memory=self._layered(reported, reported, safe, Confidence.HIGH),
            requirement=EvidenceRequirement.SUFFICIENT,
        )

    # -- storage -----------------------------------------------------------

    def _pools(
        self, host: HostCapabilities, defects: list[str]
    ) -> tuple[PoolCapacity, ...]:
        return tuple(
            self._pool(mount, defects)
            for mount in host.mounts
            if not _is_volatile(mount)
        )

    def _pool(self, mount: MountFacts, defects: list[str]) -> PoolCapacity:
        """Free space, bounded when the filesystem's own figure proves nothing.

        The case this exists for: the reference host mounts a network
        filesystem advertising 2.15 PB with hundreds of terabytes free.
        Nothing about that number is evidence of what this deployment may
        write, so effective is bounded by policy until Stage 2.2 can verify
        a reservation. Reported is preserved intact — it is displayed, and
        it authorizes nothing.
        """
        reported = mount.free_bytes
        family = _family(mount.filesystem_type)

        if not is_resolved(reported):
            defects.append(
                f"pool {mount.mount_point} reports no free space, so nothing "
                f"may be written to it"
            )
            return PoolCapacity(
                mount_point=mount.mount_point,
                space=self._layered(NOT_PROVIDED, NOT_PROVIDED, NOT_PROVIDED,
                                    Confidence.UNKNOWN),
                requirement=EvidenceRequirement.UNKNOWN,
                filesystem_type=mount.filesystem_type,
                reported_total_bytes=mount.total_bytes,
                note="the filesystem reported no free space",
            )

        # Credibility is decided by an allow-list, so anything unrecognised
        # is bounded rather than trusted. A deny-list would fail open: the
        # one filesystem nobody had thought about would be believed.
        ceiling = self._policy.unverified_pool_ceiling_bytes
        if family in self._policy.families_with_credible_size:
            requirement = EvidenceRequirement.SUFFICIENT
            effective = reported
            note = None
        elif family in self._policy.families_requiring_evidence:
            requirement = EvidenceRequirement.EMPIRICAL_EVIDENCE_NEEDED
            effective = min(reported, ceiling)
            note = (
                f"a {family} filesystem's reported size describes a backend "
                f"rather than an entitlement, so it is not evidence of usable "
                f"capacity; effective bounded at {ceiling} bytes pending "
                f"empirical verification (Stage 2.2)"
            )
        else:
            requirement = EvidenceRequirement.UNKNOWN
            effective = min(reported, ceiling)
            described = family or "unreported"
            note = (
                f"a {described} filesystem is not a family Kultrun has "
                f"validated, so its reported size is not treated as evidence; "
                f"effective bounded at {ceiling} bytes"
            )

        if effective < reported:
            defects.append(
                f"pool {mount.mount_point} reports {reported} bytes free but "
                f"only {effective} is treated as effective: "
                f"{requirement.value}"
            )

        safe = self._withhold(
            effective,
            self._policy.storage_reserve_fraction,
            self._policy.storage_reserve_floor_bytes,
        )
        confidence = (
            Confidence.HIGH
            if requirement is EvidenceRequirement.SUFFICIENT
            else Confidence.LOW
        )
        return PoolCapacity(
            mount_point=mount.mount_point,
            space=self._layered(reported, effective, safe, confidence),
            requirement=requirement,
            filesystem_type=mount.filesystem_type,
            reported_total_bytes=mount.total_bytes,
            note=note,
        )

    # -- shared ------------------------------------------------------------

    def _withhold(
        self, effective: Maybe[int], fraction: float, floor: int
    ) -> Maybe[int]:
        """Effective minus the larger of a fraction and a floor.

        A fraction alone protects nothing on a small resource; a floor alone
        protects nothing on a large one. When the reserve would consume
        everything the answer is **unresolved, not zero** — zero reads as "a
        measured absence of capacity", and this is "too small to use safely",
        which is a different fact.
        """
        if not is_resolved(effective):
            return NOT_PROVIDED
        reserve = max(int(effective * fraction), floor)
        remaining = effective - reserve
        if remaining <= 0:
            return NOT_MEASURED
        return remaining

    def _layered(
        self,
        reported: Maybe[int],
        effective: Maybe[int],
        safe: Maybe[int],
        confidence: Confidence,
    ) -> LayeredBytes:
        return LayeredBytes(
            reported_bytes=reported,
            effective_bytes=effective,
            safe_bytes=safe,
            confidence=confidence,
            provenance=Provenance(
                producer=PRODUCER,
                producer_version=NOT_PROVIDED,
                observed_at=self._clock.now(),
                policy_version=self._policy.policy_version,
            ),
        )


def _first_resolved(*values: Maybe[bool]) -> Maybe[bool]:
    """The first value that is actually known, or unresolved."""
    for value in values:
        if is_resolved(value):
            return value
    return NOT_PROVIDED


def _family(filesystem_type: Maybe[str]) -> str | None:
    if isinstance(filesystem_type, str):
        return filesystem_type.strip().lower()
    return None


def _is_volatile(mount: MountFacts) -> bool:
    """Memory-backed storage is not a durable pool.

    Real space, but it is RAM: it does not survive a restart, and counting
    it as storage would count the same bytes twice.
    """
    return _family(mount.filesystem_type) in VOLATILE_FAMILIES

