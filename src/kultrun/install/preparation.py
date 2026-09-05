"""Detect, reuse, provision once, verify, record.

The exoskeleton version of plug-and-play: an administrator should not have
to install a discovery tool by hand because Kultrun chose that tool
internally. `docs/PRODUCT_VISION.md` §5.10.

Deliberately not a package manager abstraction and deliberately not a
downloader. Downloading is one provisioning mechanism among an existing
binary, a system package manager, a managed environment, a verified release,
an image, a mirror and an offline bundle, so the port is *provision this
requirement* and the mechanism is an adapter. `docs/ARCHITECTURE.md` Part IX.

**Reuse before provision is the property that matters.** A repeat run that
provisions again has failed, because it means the platform cannot tell what
it already has — and on a metered host it would also be paying to reinstall
the same package on every start.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from kultrun.components.contracts import (
    ComponentNecessity,
    ComponentRequirement,
    ComponentResolution,
    ResolutionOutcome,
)
from kultrun.components.inspect import ComponentInspector, Presence
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.platform.contracts import ComponentHealth, HealthStatus, PhaseReport


@runtime_checkable
class ComponentProvisioner(Protocol):
    """A mechanism that can make a component present.

    One implementation exists — the reference environment's package manager.
    The port is what allows a verified release artifact, an image or an
    offline bundle to be added later without this module changing.
    """

    @property
    def mechanism(self) -> Name:
        """How this provisioner obtains a component, for the record."""
        ...

    def supports(self, requirement: ComponentRequirement) -> bool:
        """Whether this mechanism can be used on this host for this component."""
        ...

    def provision(self, requirement: ComponentRequirement) -> tuple[bool, str]:
        """Attempt provisioning. Returns success and a human-readable detail."""
        ...


@dataclass(frozen=True, slots=True)
class PreparationOutcome:
    """What preparation did about every requirement."""

    resolutions: tuple[ComponentResolution, ...]

    @property
    def satisfied(self) -> bool:
        """Whether every *required* component is now available."""
        return all(
            resolution.outcome
            in (ResolutionOutcome.ALREADY_PRESENT, ResolutionOutcome.PROVISIONED)
            for resolution in self.resolutions
            if resolution.detail != "optional"
        )

    @property
    def reused(self) -> tuple[str, ...]:
        return tuple(
            resolution.component.value
            for resolution in self.resolutions
            if resolution.outcome is ResolutionOutcome.ALREADY_PRESENT
        )

    @property
    def provisioned(self) -> tuple[str, ...]:
        return tuple(
            resolution.component.value
            for resolution in self.resolutions
            if resolution.outcome is ResolutionOutcome.PROVISIONED
        )


class Preparation:
    """Ensures required components are present before discovery runs."""

    phase = Name("component-preparation")
    component = Name("component-preparation")

    def __init__(
        self,
        requirements: Sequence[ComponentRequirement],
        provisioners: Sequence[ComponentProvisioner] = (),
        *,
        inspector: ComponentInspector | None = None,
        clock: Clock | None = None,
        may_provision: bool = True,
    ) -> None:
        self._requirements = tuple(requirements)
        self._provisioners = tuple(provisioners)
        self._clock = clock or SystemClock()
        self._inspector = inspector or ComponentInspector(self._clock)
        self._may_provision = may_provision
        self._last: PreparationOutcome | None = None

    @property
    def last_outcome(self) -> PreparationOutcome | None:
        return self._last

    def prepare(self) -> PreparationOutcome:
        """Detect, reuse, provision once if needed, verify, record."""
        resolutions = [self._prepare_one(req) for req in self._requirements]
        self._last = PreparationOutcome(tuple(resolutions))
        return self._last

    def _prepare_one(
        self, requirement: ComponentRequirement
    ) -> ComponentResolution:
        found = self._inspector.inspect(requirement)
        if self._inspector.satisfied(requirement, found):
            return self._inspector.resolution(
                requirement,
                found,
                outcome=ResolutionOutcome.ALREADY_PRESENT,
                source=found.path or "PATH",
                detail=None,
            )

        optional = requirement.necessity is ComponentNecessity.OPTIONAL
        if not self._may_provision:
            return self._unavailable(
                requirement, found, "administrator policy forbids provisioning",
                optional=optional,
            )

        provisioner = next(
            (p for p in self._provisioners if p.supports(requirement)), None
        )
        if provisioner is None:
            return self._unavailable(
                requirement,
                found,
                "no provisioning mechanism supports this host",
                optional=optional,
            )

        succeeded, detail = provisioner.provision(requirement)
        after = self._inspector.inspect(requirement)
        if not succeeded or not self._inspector.satisfied(requirement, after):
            return self._inspector.resolution(
                requirement,
                after,
                outcome=ResolutionOutcome.FAILED,
                source=provisioner.mechanism.value,
                detail=detail,
            )
        # Verified after provisioning, not assumed: installing is not working.
        return self._inspector.resolution(
            requirement,
            after,
            outcome=ResolutionOutcome.PROVISIONED,
            source=provisioner.mechanism.value,
            detail=detail,
        )

    def _unavailable(
        self,
        requirement: ComponentRequirement,
        found: Presence,
        why: str,
        *,
        optional: bool,
    ) -> ComponentResolution:
        return self._inspector.resolution(
            requirement,
            found,
            outcome=ResolutionOutcome.UNAVAILABLE,
            detail="optional" if optional else why,
        )

    def reconcile(self) -> PhaseReport:
        """Startup phase: run before host discovery, never after."""
        outcome = self.prepare()
        defects = [
            f"{r.component}: {r.detail or r.outcome.value}"
            for r in outcome.resolutions
            if r.outcome in (ResolutionOutcome.UNAVAILABLE, ResolutionOutcome.FAILED)
        ]
        reused = ", ".join(outcome.reused) or "none"
        provisioned = ", ".join(outcome.provisioned) or "none"
        # The phase succeeded if it *ran*. An unmet requirement is a defect,
        # not a failed startup: `docs/ARCHITECTURE.md` is explicit that
        # fail-closed governs mutations rather than existence, and a platform
        # that refuses to boot on an unprepared host cannot tell its
        # administrator why. Health reports degraded instead.
        return PhaseReport(
            phase=self.phase,
            succeeded=True,
            detail=f"reused: {reused}; provisioned: {provisioned}",
            defects=tuple(defects),
        )

    def check_health(self) -> ComponentHealth:
        if self._last is None:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.UNKNOWN,
                detail="preparation has not run",
            )
        if not self._last.satisfied:
            return ComponentHealth(
                component=self.component,
                status=HealthStatus.DEGRADED,
                detail="a required component is unavailable",
            )
        return ComponentHealth(component=self.component, status=HealthStatus.HEALTHY)
