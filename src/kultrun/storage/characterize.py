"""Capacity-first storage characterization. Runs before runtime/model selection.

Cheap GET / ``kultrun host`` may call this with ``run_empirical=False``.
That pass must never launch Sonar. The composition root invokes an expensive
pass before a mutation.

On that expensive path a credible specialist is the capacity value; Sonar
corroborates or contradicts it. With no usable specialist bytes, Sonar
runs the full V2 tree. Each pool is characterized independently: a probe
writes inside the pool it claims, and an already-authoritative overlay
does not inherit a sibling FUSE pool's need for Sonar.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from kultrun.host.contracts import HostCapabilities, MountFacts
from kultrun.kernel.clock import Clock
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.cleanup import step0_cleanup
from kultrun.storage.contracts import (
    CleanupReport,
    EmpiricalProbeEvidence,
    LowSpaceGuidance,
    StorageCapacityEvidence,
    StorageEvidenceStatus,
    StoragePool,
)
from kultrun.storage.evidence import arbitrate, needs_empirical_fallback
from kultrun.storage.index import StorageEvidenceIndex, same_storage_identity
from kultrun.storage.limits import (
    DEFAULT_BELIEF_BOUND_BYTES,
    LOW_SPACE_THRESHOLD_BYTES,
)
from kultrun.storage.native import native_available_bytes
from kultrun.storage.ownership import OwnershipService
from kultrun.storage.ports import StorageEnvironment
from kultrun.storage.probe_target import probe_parent_for, probe_roots_for
from kultrun.storage.probes import ProbeRegistry
from kultrun.storage.sonar import RUN_RUNNING, EmpiricalStorageProbe
from kultrun.storage.topology import family_of, is_credible_family, pools_from_host


@dataclass(frozen=True, slots=True)
class Characterization:
    """One complete storage-truth pass. Not an admission."""

    pools: tuple[StoragePool, ...]
    evidence: dict[str, StorageCapacityEvidence]
    cleanup: CleanupReport | None
    low_space: tuple[LowSpaceGuidance, ...]
    empirical_ran: tuple[str, ...]
    empirical_evidence: dict[str, EmpiricalProbeEvidence] = field(default_factory=dict)


class StorageCharacterizationService:
    """Native → compatible specialists → Sonar corroboration or full tree."""

    def __init__(
        self,
        clock: Clock,
        registry: ProbeRegistry,
        ownership: OwnershipService | None = None,
        empirical: EmpiricalStorageProbe | None = None,
        index: StorageEvidenceIndex | None = None,
        *,
        low_space_bytes: int = LOW_SPACE_THRESHOLD_BYTES,
        belief_bound_bytes: int = DEFAULT_BELIEF_BOUND_BYTES,
        use_live_native: bool = True,
        on_event: Callable[[str, Mapping[str, str]], None] | None = None,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._ownership = ownership
        self._empirical = empirical
        self._index = index
        self._low_space = low_space_bytes
        self._belief = belief_bound_bytes
        self._use_live_native = use_live_native
        self._on_event = on_event

    def characterize(
        self,
        host: HostCapabilities,
        *,
        run_cleanup: bool = True,
        run_empirical: bool = True,
        active_roots: Sequence[Path] = (),
        administrator_bounds: Mapping[str, int] | None = None,
        probe_workspace: Path | None = None,
    ) -> Characterization:
        pools = pools_from_host(host)
        probe_roots = probe_roots_for(pools)
        cleanup = None
        if run_cleanup and self._ownership is not None:
            allowed = (self._ownership.state_root, *probe_roots)
            cleanup = step0_cleanup(
                self._ownership,
                host.host_id,
                active_roots=active_roots,
                allowed_roots=allowed,
                extra_roots=probe_roots,
            )
        mounts = {item.mount_point: item for item in host.mounts}
        evidence: dict[str, StorageCapacityEvidence] = {}
        empirical_ran: list[str] = []
        empirical_evidence: dict[str, EmpiricalProbeEvidence] = {}
        if administrator_bounds is None:
            bounds: Mapping[str, int] = (
                self._index.matching_administrator_bytes(host)
                if run_empirical and self._index is not None
                else {}
            )
        else:
            bounds = administrator_bounds
        for pool in pools:
            mount = mounts.get(pool.mount_point)
            if mount is None:
                continue
            if run_empirical:
                self._notify(
                    "storage.pool_evaluated",
                    mount=pool.mount_point,
                    filesystem=str(mount.filesystem_type)
                    if is_resolved(mount.filesystem_type)
                    else "unknown",
                    summary=f"evaluating {pool.mount_point}",
                    outcome="info",
                )
            item = self._one(
                host,
                pool,
                mount,
                pools,
                run_empirical=run_empirical,
                administrator_bounds=bounds,
                probe_workspace=probe_workspace,
                empirical_ran=empirical_ran,
                empirical_evidence=empirical_evidence,
            )
            evidence[pool.mount_point] = item
            if run_empirical:
                auth = item.authorizing_available_bytes
                self._notify(
                    "storage.authority_established",
                    mount=pool.mount_point,
                    summary=(
                        f"authorizing {auth} bytes"
                        if isinstance(auth, int)
                        else "authorizing unresolved"
                    ),
                    outcome="pass" if isinstance(auth, int) else "unresolved",
                )
        low = tuple(
            _low_space(host, item, self._low_space, cleanup)
            for item in evidence.values()
            if _is_low(item, self._low_space)
            or _empirical_very_low(empirical_evidence.get(item.mount_point))
        )
        return Characterization(
            pools=pools,
            evidence=evidence,
            cleanup=cleanup,
            low_space=low,
            empirical_ran=tuple(empirical_ran),
            empirical_evidence=empirical_evidence,
        )

    def _one(
        self,
        host: HostCapabilities,
        pool: StoragePool,
        mount: MountFacts,
        pools: Sequence[StoragePool],
        *,
        run_empirical: bool,
        administrator_bounds: Mapping[str, int],
        probe_workspace: Path | None,
        empirical_ran: list[str],
        empirical_evidence: dict[str, EmpiricalProbeEvidence],
    ) -> StorageCapacityEvidence:
        environment = environment_for(host, mount)
        native, source = native_available_bytes(
            mount, environment, live=self._use_live_native
        )
        reports = self._registry.run(environment)
        probe_available, hard = self._registry.strongest_available(reports)
        compatible = any(item.compatible for item in reports)
        executed = any(item.executed for item in reports if item.compatible)
        family = family_of(mount.filesystem_type)
        credible = is_credible_family(family)
        belief = self._belief if not credible else NOT_PROVIDED
        probe_name: Maybe[str] = NOT_PROVIDED
        for report in reports:
            if report.compatible:
                probe_name = report.probe_name
                if report.executed and is_resolved(report.available_bytes):
                    break
        if run_empirical and (not compatible or probe_name == "none"):
            self._notify(
                "storage.probe_result",
                mount=pool.mount_point,
                summary=f"{family or 'unknown'} specialist unavailable",
                outcome="unresolved",
                reason="specialist_unavailable",
            )
        elif run_empirical and isinstance(probe_name, str):
            result = "ran" if executed else "compatible-not-run"
            self._notify(
                "storage.probe_result",
                mount=pool.mount_point,
                probe=probe_name,
                summary=f"{probe_name} {result}",
                outcome="info" if executed else "unresolved",
            )
        first = arbitrate(
            host_id=host.host_id,
            mount_point=pool.mount_point,
            quota_identity=pool.quota_identity,
            pool_fingerprint=pool.fingerprint,
            clock=self._clock,
            reported_available=mount.free_bytes,
            native_available=native,
            probe_available=probe_available,
            hard_maximum=hard,
            belief_bound=belief,
            native_source=source,
            probe_name=probe_name,
            probe_compatible=compatible,
            probe_executed=executed,
            administrator_bound=NOT_PROVIDED,
            native_trusted=credible,
        )
        admin = administrator_bounds.get(pool.mount_point, NOT_PROVIDED)
        bound = admin if isinstance(admin, int) else NOT_PROVIDED
        if run_empirical:
            stored = self._reuse_empirical(
                host, pool, first, native_trusted=credible
            )
            if stored is not None:
                return stored
        if not run_empirical or self._empirical is None:
            return (
                first
                if not run_empirical
                else arbitrate(
                    host_id=host.host_id,
                    mount_point=pool.mount_point,
                    quota_identity=pool.quota_identity,
                    pool_fingerprint=pool.fingerprint,
                    clock=self._clock,
                    reported_available=mount.free_bytes,
                    native_available=native,
                    probe_available=probe_available,
                    hard_maximum=hard,
                    belief_bound=belief,
                    native_source=source,
                    probe_name=probe_name,
                    probe_compatible=compatible,
                    probe_executed=executed,
                    administrator_bound=bound,
                    native_trusted=credible,
                )
            )
        if not needs_empirical_fallback(
            family=family,
            credible_family=credible,
            reports=reports,
            evidence=first,
        ):
            return arbitrate(
                host_id=host.host_id,
                mount_point=pool.mount_point,
                quota_identity=pool.quota_identity,
                pool_fingerprint=pool.fingerprint,
                clock=self._clock,
                reported_available=mount.free_bytes,
                native_available=native,
                probe_available=probe_available,
                hard_maximum=hard,
                belief_bound=belief,
                native_source=source,
                probe_name=probe_name,
                probe_compatible=compatible,
                probe_executed=executed,
                administrator_bound=bound,
                native_trusted=credible,
            )
        parent = probe_parent_for(pool, pools, probe_workspace)
        corroborate: int | None = None
        if is_resolved(probe_available) and probe_available > 0:
            corroborate = probe_available
            if is_resolved(hard):
                corroborate = min(corroborate, hard)
        empirical = self._empirical.probe(
            host.host_id,
            pool.mount_point,
            parent,
            quota_identity=pool.quota_identity,
            pool_fingerprint=pool.fingerprint,
            corroborate_bytes=corroborate,
            intended_pool=pool,
            pools=pools,
        )
        empirical_ran.append(pool.mount_point)
        empirical_evidence[pool.mount_point] = empirical
        native, source = native_available_bytes(
            mount, environment, live=self._use_live_native
        )
        usable: EmpiricalProbeEvidence | None = empirical
        if not _identity_matches(empirical, pool) or not _empirical_may_authorize(
            empirical
        ):
            usable = None
        return arbitrate(
            host_id=host.host_id,
            mount_point=pool.mount_point,
            quota_identity=pool.quota_identity,
            pool_fingerprint=pool.fingerprint,
            clock=self._clock,
            reported_available=mount.free_bytes,
            native_available=native,
            probe_available=probe_available,
            hard_maximum=hard,
            belief_bound=belief,
            native_source=source,
            probe_name=probe_name,
            probe_compatible=compatible,
            probe_executed=executed,
            administrator_bound=bound,
            empirical=usable,
            native_trusted=credible,
        )

    def _reuse_empirical(
        self,
        host: HostCapabilities,
        pool: StoragePool,
        cheap: StorageCapacityEvidence,
        *,
        native_trusted: bool,
    ) -> StorageCapacityEvidence | None:
        """Reuse identity-matched Sonar without rewriting tens of GiB."""
        if self._index is None:
            return None
        stored = self._index.empirical_for_host(host).get(pool.mount_point)
        held = self._index.authorizing_for(host.host_id, pool.mount_point)
        if stored is None or not _identity_matches(stored, pool):
            return None
        if not _empirical_may_authorize(stored):
            return None
        if held is not None:
            if not same_storage_identity(held, cheap):
                return None
            if is_resolved(held.authorizing_available_bytes):
                return held
        return arbitrate(
            host_id=host.host_id,
            mount_point=pool.mount_point,
            quota_identity=pool.quota_identity,
            pool_fingerprint=pool.fingerprint,
            clock=self._clock,
            reported_available=cheap.reported_available_bytes,
            native_available=cheap.declared_available_bytes,
            probe_available=cheap.probe_available_bytes,
            hard_maximum=cheap.hard_maximum_bytes,
            belief_bound=cheap.belief_bound_bytes,
            native_source=cheap.native_source,
            probe_name=cheap.probe_name,
            probe_compatible=cheap.probe_available,
            probe_executed=cheap.probe_executed,
            administrator_bound=cheap.administrator_bound_bytes,
            empirical=stored,
            native_trusted=native_trusted,
        )

    def _notify(self, event_type: str, **fields: str) -> None:
        if self._on_event is None:
            return
        self._on_event(event_type, fields)


def environment_for(host: HostCapabilities, mount: MountFacts) -> StorageEnvironment:
    os_name = host.operating_environment.os_name
    architecture = host.operating_environment.architecture.value
    return StorageEnvironment(
        os_name=os_name,
        architecture=architecture,
        mount_point=mount.mount_point,
        filesystem_type=mount.filesystem_type,
        device=mount.device,
    )


def _is_low(evidence: StorageCapacityEvidence, threshold: int) -> bool:
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return False
    value = evidence.operational_available_bytes
    return is_resolved(value) and value < threshold


def _empirical_very_low(empirical: EmpiricalProbeEvidence | None) -> bool:
    if empirical is None:
        return False
    state = empirical.run_state
    return is_resolved(state) and state == "very_low"


def _identity_matches(empirical: EmpiricalProbeEvidence, pool: StoragePool) -> bool:
    fingerprint = empirical.pool_fingerprint
    if is_resolved(fingerprint) and fingerprint != pool.fingerprint:
        return False
    quota = empirical.quota_identity
    return not (
        is_resolved(quota)
        and is_resolved(pool.quota_identity)
        and quota != pool.quota_identity
    )


def _empirical_may_authorize(empirical: EmpiricalProbeEvidence) -> bool:
    """Incomplete in-flight evidence must not become capacity."""
    state = empirical.run_state
    return not (is_resolved(state) and state == RUN_RUNNING)


def _low_space(
    host: HostCapabilities,
    evidence: StorageCapacityEvidence,
    threshold: int,
    cleanup: CleanupReport | None,
) -> LowSpaceGuidance:
    cleaned = cleanup.bytes_removed if cleanup is not None else 0
    available = evidence.operational_available_bytes
    shown = available if is_resolved(available) else "unknown"
    return LowSpaceGuidance(
        host_id=host.host_id,
        mount_point=evidence.mount_point,
        quota_identity=evidence.quota_identity,
        authorizing_available_bytes=available,
        threshold_bytes=threshold,
        cleaned_bytes=cleaned,
        message=(
            f"storage domain {evidence.mount_point} has {shown} bytes "
            f"Kultrun can currently establish (threshold {threshold}). "
            "Eligible owned disposable state has already been cleaned. "
            "Unrelated files will not be removed automatically. "
            "Clear space, then rediscover from the beginning."
        ),
        rediscovery_required=True,
    )
