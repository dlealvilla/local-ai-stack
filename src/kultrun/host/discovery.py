"""Collect, normalize, reconcile — the module that owns meaning.

Providers speak **paths and JSON-safe values**. This module owns the
vocabulary of paths and the contract they become, which is what keeps a
provider's schema out of the platform: a provider cannot introduce a concept
by reporting it, because an unrecognised path is recorded and ignored rather
than absorbed.

Three things happen here and they are worth naming separately.

*Collect* asks every available provider and keeps every report, including
the reports of providers that failed.

*Normalize* maps observed paths onto `HostCapabilities`. Anything no
provider reported stays unresolved; nothing is defaulted to zero.

*Reconcile* merges overlapping observations. This is **not** the restart
reconciliation every stateful domain performs — that lives in
`host/inventory.py`. Two operations, two modules, because a word that means
two things is how a concept starts to fragment.

There is no global provider precedence and there will not be one. A rule of
the form "vendor beats general" resolves every future conflict including the
ones where the general tool was right, and does so silently. Exactly one
field-specific rule exists, it is declared through a provider capability
rather than a provider name, and it exists because of a measurement.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from kultrun.evidence.contracts import Confidence, Derivation
from kultrun.host.contracts import (
    Accelerator,
    AcceleratorVendor,
    Architecture,
    CpuFacts,
    DeploymentProfile,
    ExecutionCapabilities,
    FieldProvenance,
    HostCapabilities,
    HostId,
    MemoryFacts,
    MountFacts,
    NetworkFacts,
    Observation,
    ObservationConflict,
    OperatingEnvironment,
    ProviderReport,
    ProviderStatus,
)
from kultrun.host.ports import HostDiscoveryProvider
from kultrun.host.profile import classify
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe, Unresolved

#: Paths for a single device or mount are namespaced by a stable key:
#: ``accelerator.<pci_bus_id>.<field>`` and ``mount.<mount_point>.<field>``.
#: The key is a host-scoped attribute, never a provider-local handle, which
#: is the invariant in `docs/ARCHITECTURE.md` Part II §6.
# The key is greedy to the last dot because a PCI address contains one
# (`0000:82:00.0`). Field names never do.
_ACCELERATOR_PATH = re.compile(r"^accelerator\.(?P<key>.+)\.(?P<field>[^.]+)$")
_MOUNT_PATH = re.compile(r"^mount\.(?P<key>.+?)\.(?P<field>[^.]+)$")

#: The reconciliation rule, named so it can appear in a conflict record.
_ASSIGNMENT_RULE = (
    "accelerator presence is taken from a provider that reports device "
    "assignment to this execution context; enumeration of the physical bus "
    "is retained as evidence"
)


@dataclass(frozen=True, slots=True)
class _Accepted:
    """One normalized value and where it came from."""

    value: Any
    provenance: FieldProvenance


class HostDiscoveryService:
    """Turns provider observations into Kultrun-owned `HostCapabilities`."""

    def __init__(
        self,
        providers: Sequence[HostDiscoveryProvider],
        *,
        clock: Clock | None = None,
    ) -> None:
        self._providers = tuple(providers)
        self._clock = clock or SystemClock()

    @property
    def providers(self) -> tuple[Name, ...]:
        """Which providers will be consulted, in order."""
        return tuple(provider.provider for provider in self._providers)

    def discover(
        self, *, host_id: HostId | None = None, profile: DeploymentProfile | None = None
    ) -> HostCapabilities:
        """Consult every provider and produce one normalized description."""
        reports = self._collect()
        capabilities = self.normalize(
            reports,
            host_id=host_id or HostId.generate(),
            profile=profile,
            assignment_aware=self._assignment_aware_providers(),
        )
        if profile is not None:
            return capabilities
        # Classify here so a description is never born with a profile nobody
        # chose. An explicit `profile` argument still wins, which is what
        # lets a stage record the tier its own acceptance earned.
        return replace(capabilities, profile=classify(capabilities))

    # -- collect -----------------------------------------------------------

    def _collect(self) -> tuple[ProviderReport, ...]:
        collected: list[ProviderReport] = []
        for provider in self._providers:
            try:
                collected.append(provider.observe())
            except Exception as error:  # a provider must not break discovery
                collected.append(
                    ProviderReport(
                        provider=provider.provider,
                        status=ProviderStatus.FAILED,
                        observed_at=self._clock.now(),
                        detail=f"provider raised: {error}",
                    )
                )
        return tuple(collected)

    def _assignment_aware_providers(self) -> frozenset[str]:
        return frozenset(
            provider.provider.value
            for provider in self._providers
            if provider.reports_accelerator_assignment
        )

    # -- normalize and reconcile -------------------------------------------

    def normalize(
        self,
        reports: Iterable[ProviderReport],
        *,
        host_id: HostId,
        profile: DeploymentProfile | None = None,
        assignment_aware: frozenset[str] = frozenset(),
    ) -> HostCapabilities:
        """Merge reports into one description, preserving unknowns.

        Separated from :meth:`discover` so that a committed fixture can be
        replayed through exactly the path a real host takes. A normalization
        regression is then catchable without hardware.
        """
        reports = tuple(reports)
        by_path = _group_by_path(reports)
        conflicts: list[ObservationConflict] = []
        accepted: dict[str, _Accepted] = {}

        for path, observations in by_path.items():
            resolution = self._reconcile(path, observations, conflicts)
            if resolution is not None:
                accepted[path] = resolution

        accelerators, accelerator_conflicts = self._normalize_accelerators(
            by_path, accepted, assignment_aware
        )
        conflicts.extend(accelerator_conflicts)

        return HostCapabilities(
            host_id=host_id,
            fingerprint="",  # assigned by host.fingerprint, which reads this
            detected_at=self._clock.now(),
            operating_environment=OperatingEnvironment(
                os_name=_text(accepted, "operating_environment.os_name", "unknown"),
                os_version=_text(
                    accepted, "operating_environment.os_version", "unknown"
                ),
                architecture=_enum(
                    accepted,
                    "operating_environment.architecture",
                    Architecture,
                    Architecture.UNKNOWN,
                ),
                kernel_version=_maybe(accepted, "operating_environment.kernel_version"),
                virtualized=_maybe(accepted, "operating_environment.virtualized"),
                distribution=_maybe(accepted, "operating_environment.distribution"),
            ),
            cpu=CpuFacts(
                vendor=_maybe(accepted, "cpu.vendor"),
                model_name=_maybe(accepted, "cpu.model_name"),
                physical_cores=_maybe(accepted, "cpu.physical_cores"),
                logical_cores=_maybe(accepted, "cpu.logical_cores"),
            ),
            memory=MemoryFacts(
                total_bytes=_maybe(accepted, "memory.total_bytes"),
                available_bytes=_maybe(accepted, "memory.available_bytes"),
                limit_bytes=_maybe(accepted, "memory.limit_bytes"),
                unified_with_accelerator=_maybe(
                    accepted, "memory.unified_with_accelerator"
                ),
            ),
            execution=ExecutionCapabilities(
                native_process=True,
                docker=_maybe(accepted, "execution.docker"),
                podman=_maybe(accepted, "execution.podman"),
            ),
            network=NetworkFacts(
                hostname=_maybe(accepted, "network.hostname"),
                loopback_address=_maybe(accepted, "network.loopback_address"),
                occupied_ports=tuple(
                    _sequence(accepted, "network.occupied_ports", int)
                ),
            ),
            accelerators=accelerators,
            mounts=self._normalize_mounts(by_path, accepted),
            profile=profile or DeploymentProfile.EXPERIMENTAL,
            provenance=tuple(
                entry.provenance for _, entry in sorted(accepted.items())
            ),
            conflicts=tuple(conflicts),
            provider_reports=reports,
        )

    def _reconcile(
        self,
        path: str,
        observations: Sequence[tuple[Name, Observation]],
        conflicts: list[ObservationConflict],
    ) -> _Accepted | None:
        """Accept one value for a path, or record a conflict and accept none.

        A later observation never blindly overwrites an earlier one. Agreement
        is recorded with every contributing provider named, so an operator can
        see that two independent sources concurred — which is itself evidence.
        """
        distinct = {_hashable(obs.value) for _, obs in observations}
        providers = tuple(provider for provider, _ in observations)
        if len(distinct) > 1:
            conflicts.append(
                ObservationConflict(
                    path=path,
                    observations=tuple(obs for _, obs in observations),
                )
            )
            return None
        first_provider, first = observations[0]
        return _Accepted(
            value=first.value,
            provenance=FieldProvenance(
                path=path,
                providers=providers,
                accepted_from=first_provider,
                derivation=first.derivation,
                confidence=first.confidence,
            ),
        )

    def _normalize_accelerators(
        self,
        by_path: Mapping[str, list[tuple[Name, Observation]]],
        accepted: Mapping[str, _Accepted],
        assignment_aware: frozenset[str],
    ) -> tuple[tuple[Accelerator, ...], list[ObservationConflict]]:
        """Build the accelerator collection, applying the one field rule.

        Plural on a host that has one, per `docs/ARCHITECTURE.md` Part II §6.
        Keys are PCI bus identifiers — host-scoped and stable — never a
        provider handle.
        """
        seen: dict[str, set[str]] = defaultdict(set)
        for path, observations in by_path.items():
            match = _ACCELERATOR_PATH.match(path)
            if match is None:
                continue
            for provider, _ in observations:
                seen[match.group("key")].add(provider.value)

        if not seen:
            return (), []

        assigned = {
            key
            for key, providers in seen.items()
            if providers & assignment_aware
        }
        conflicts: list[ObservationConflict] = []

        if assignment_aware and assigned != set(seen):
            unassigned = sorted(set(seen) - assigned)
            conflicts.append(
                ObservationConflict(
                    path="accelerators",
                    observations=tuple(
                        Observation(
                            path=f"accelerator.{key}.assigned",
                            value=False,
                            derivation=Derivation.DERIVED,
                            confidence=Confidence.HIGH,
                        )
                        for key in unassigned
                    ),
                    resolution=_ASSIGNMENT_RULE,
                )
            )
            keys = sorted(assigned)
        else:
            keys = sorted(seen)

        accelerators = tuple(
            Accelerator(
                index=index,
                vendor=_enum(
                    accepted,
                    f"accelerator.{key}.vendor",
                    AcceleratorVendor,
                    AcceleratorVendor.UNKNOWN,
                ),
                model_name=_maybe(accepted, f"accelerator.{key}.model_name"),
                memory_total_bytes=_maybe(
                    accepted, f"accelerator.{key}.memory_total_bytes"
                ),
                driver_version=_maybe(accepted, f"accelerator.{key}.driver_version"),
                unified_memory=_maybe(accepted, f"accelerator.{key}.unified_memory"),
            )
            for index, key in enumerate(keys)
        )
        return accelerators, conflicts

    def _normalize_mounts(
        self,
        by_path: Mapping[str, list[tuple[Name, Observation]]],
        accepted: Mapping[str, _Accepted],
    ) -> tuple[MountFacts, ...]:
        keys = sorted(
            {
                match.group("key")
                for path in by_path
                if (match := _MOUNT_PATH.match(path)) is not None
            }
        )
        return tuple(
            MountFacts(
                mount_point=_text(accepted, f"mount.{key}.mount_point", key),
                device=_maybe(accepted, f"mount.{key}.device"),
                filesystem_type=_maybe(accepted, f"mount.{key}.filesystem_type"),
                total_bytes=_maybe(accepted, f"mount.{key}.total_bytes"),
                free_bytes=_maybe(accepted, f"mount.{key}.free_bytes"),
            )
            for key in keys
        )


def _group_by_path(
    reports: Iterable[ProviderReport],
) -> dict[str, list[tuple[Name, Observation]]]:
    grouped: dict[str, list[tuple[Name, Observation]]] = defaultdict(list)
    for report in reports:
        for observation in report.observations:
            grouped[observation.path].append(
                (report.provider, _tidied(observation))
            )
    return dict(grouped)


def _tidied(observation: Observation) -> Observation:
    """Strip surrounding whitespace from a reported string.

    `docs/DEBT.md` K-21: a topology tool reports the CPU model padded to a
    fixed width, and `cpu.model_name` is a **host fingerprint input**. Left
    alone, a change in that padding between tool versions would change host
    identity and discard cached evidence for no real reason — the same class
    of latent instability as the container mount whose name carried a random
    UUID.

    Done here rather than in each provider so that two providers reporting
    the same value with different padding are recognised as agreeing, which
    is the other half of the bug.
    """
    if not isinstance(observation.value, str):
        return observation
    tidied = observation.value.strip()
    if tidied == observation.value:
        return observation
    return replace(observation, value=tidied)


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    return value


def _maybe(accepted: Mapping[str, _Accepted], path: str) -> Maybe[Any]:
    """The accepted value, or unresolved — never a default.

    A path no provider reported is not zero and not false. This single
    helper is why: normalization has no way to invent a value.
    """
    entry = accepted.get(path)
    if entry is None:
        return NOT_PROVIDED
    if entry.value is None:
        return NOT_MEASURED
    return entry.value


def _text(accepted: Mapping[str, _Accepted], path: str, fallback: str) -> str:
    entry = accepted.get(path)
    if entry is None or not isinstance(entry.value, str):
        return fallback
    return entry.value


def _enum(
    accepted: Mapping[str, _Accepted], path: str, enum_type: Any, fallback: Any
) -> Any:
    """Map a reported string onto a platform enumeration, failing to unknown.

    A vendor or architecture Kultrun has never seen becomes `UNKNOWN` rather
    than an error or a guess. That is what allows a host the platform does
    not recognise to still be described, and to profile as experimental
    rather than to crash discovery.
    """
    entry = accepted.get(path)
    if entry is None or not isinstance(entry.value, str):
        return fallback
    try:
        return enum_type(entry.value)
    except ValueError:
        return fallback


def _sequence(
    accepted: Mapping[str, _Accepted], path: str, item_type: type
) -> list[Any]:
    entry = accepted.get(path)
    if entry is None or not isinstance(entry.value, list):
        return []
    return [item for item in entry.value if isinstance(item, item_type)]


__all__ = ["HostDiscoveryService", "Unresolved"]
