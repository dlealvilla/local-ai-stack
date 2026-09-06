"""Control-plane state: what this installation is, and how it started.

`PlatformState` is deliberately small. `docs/ARCHITECTURE.md` Part IV says
this module must not own state a domain should own, and a control-plane
state object is the first place that rule erodes: every subsystem has
something it would be convenient to keep here. Installation identity,
version, and who administers it are the whole of it.

`HealthReport` has three states rather than two. A source that has not
reported since startup is not healthy and is not failing, and Part II §6
requires unknown to stay unknown rather than resolve to a pass.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from kultrun.identity.contracts import SubjectId
from kultrun.kernel.ids import EntityId, Name
from kultrun.kernel.schema import Contract, contract, meaning
from kultrun.kernel.unresolved import Maybe


class InstallationId(EntityId):
    """Identifies one installation of Kultrun, for its whole life."""

    prefix = "inst"


class ApprovalId(EntityId):
    """Identifies one administrator decision."""

    prefix = "appr"


class HealthStatus(StrEnum):
    """How a component is doing.

    ``UNKNOWN`` is a real answer. A component that has not been asked since
    startup has not passed, and reporting it as healthy is the kind of
    optimistic default that makes a health endpoint worthless.
    """

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILING = "failing"
    UNKNOWN = "unknown"


class ApprovalDecision(StrEnum):
    """What an administrator decided."""

    GRANTED = "granted"
    REFUSED = "refused"


@contract(kind="platform.state", version=1)
@dataclass(frozen=True, slots=True)
class PlatformState(Contract):
    """What this installation is.

    Written once on first run and read on every start. The installation
    identity is never regenerated: records elsewhere reference it, and
    minting a new one would silently orphan them.
    """

    installation_id: InstallationId = meaning(
        "identity of this installation, stable for its whole life"
    )
    platform_version: str = meaning("the Kultrun version that wrote this record")
    initialized_at: dt.datetime = meaning("when the installation was first started")
    administrator_id: SubjectId = meaning(
        "the local administrator, by identifier; the subject record is stored "
        "in its own right, because a subject is an entity and not a property "
        "of the installation"
    )


@contract(kind="platform.approval", version=1)
@dataclass(frozen=True, slots=True)
class Approval(Contract):
    """One administrator decision about one proposed action.

    A record, not a workflow. Risk classification and the request-approve
    cycle are Stage 6.2. What must exist now is the record, because Stage
    1.5 is the first mutating workflow and a mutation whose approval was
    never written down cannot be audited afterwards.
    """

    approval_id: ApprovalId = meaning("identity of this decision")
    action: Name = meaning("what was proposed, as a stable dotted name")
    target_kind: Name = meaning("what sort of thing it concerns")
    target_id: str = meaning("which one, by identifier")
    requested_by: SubjectId = meaning("who proposed it")
    requested_at: dt.datetime = meaning("when it was proposed")
    decision: ApprovalDecision = meaning("what the administrator decided")
    decided_by: SubjectId = meaning("who decided")
    decided_at: dt.datetime = meaning("when they decided")
    reason: str | None = meaning(
        "why, which is the part a later reader actually needs", default=None
    )
    expires_at: dt.datetime | None = meaning(
        "when the decision stops standing; absent means it does not expire",
        default=None,
    )


@contract(kind="platform.component_health", version=1)
@dataclass(frozen=True, slots=True)
class ComponentHealth(Contract):
    """One component's answer about itself."""

    component: Name = meaning("which component is reporting")
    status: HealthStatus = meaning("how it is doing")
    detail: str | None = meaning(
        "what is wrong, when something is", default=None
    )


@contract(kind="platform.health_report", version=1)
@dataclass(frozen=True, slots=True)
class HealthReport(Contract):
    """The platform's aggregate answer.

    The aggregate is the worst component status, not an average. A platform
    with one failing subsystem is not three-quarters healthy.
    """

    status: HealthStatus = meaning("the worst status among the components")
    observed_at: dt.datetime = meaning("when health was last aggregated")
    components: tuple[ComponentHealth, ...] = meaning(
        "each component's own answer", default=()
    )


@contract(kind="platform.startup_phase", version=1)
@dataclass(frozen=True, slots=True)
class PhaseReport(Contract):
    """What one startup phase did."""

    phase: Name = meaning("which phase ran")
    succeeded: bool = meaning("whether it completed")
    detail: str | None = meaning(
        "what it found or why it failed", default=None
    )
    defects: tuple[str, ...] = meaning(
        "problems it surfaced but did not resolve", default=()
    )


@contract(kind="platform.startup_report", version=1)
@dataclass(frozen=True, slots=True)
class StartupReport(Contract):
    """What the last start did, in order.

    One report for the whole platform. Every later stage registers a phase
    rather than adding a startup path of its own, which is what makes Stage
    6.3 a completion rather than an invention.
    """

    started_at: dt.datetime = meaning("when this start began")
    completed: bool = meaning("whether every phase completed")
    first_run: Maybe[bool] = meaning(
        "whether this start created the installation; unknown before state loads"
    )
    phases: tuple[PhaseReport, ...] = meaning(
        "each phase in the order it ran", default=()
    )

    @property
    def defects(self) -> tuple[str, ...]:
        """Every problem surfaced across phases, for the health view."""
        return tuple(
            defect for phase in self.phases for defect in phase.defects
        )


@contract(kind="config.platform", version=1)
@dataclass(frozen=True, slots=True)
class PlatformSettings(Contract):
    """The platform's own configuration section.

    A configuration section is a contract, so these fields are versioned and
    fingerprinted like any other. That is what makes "no existing config
    field may be reinterpreted" enforced by the same mechanism as "field
    meaning must never change silently", rather than by a second convention
    that could drift from the first.
    """

    state_root: str = meaning(
        "directory the platform owns for its records", default="./.state"
    )
    api_address: str = meaning(
        "address the Platform API binds to; loopback while there is no "
        "authentication",
        default="127.0.0.1",
    )
    api_port: int = meaning("port the Platform API binds to", default=8420)
    may_provision_components: bool = meaning(
        "whether Kultrun may install a missing platform component; an "
        "administrator may forbid it, and preparation then reports the "
        "component unavailable rather than acting",
        default=True,
    )
    model_requirement_estimator: str = meaning(
        "estimator mode: auto (llmfit then Kultrun fallback), or a "
        "strict provider id (llmfit, kultrun). Not a reconciler",
        default="auto",
    )
