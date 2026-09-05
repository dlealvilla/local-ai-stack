"""The two seams every domain plugs into.

Both exist from Stage 0.3 rather than from Milestone 6, because both are
*destinations*: a health console and an idempotent startup path are only
assemblies if every domain has been contributing to them all along. The
module-map review found that the destinations were planned and the sources
were not.

A domain implements `HealthSource` when it can be unwell, and
`ReconcilePhase` when it holds state. A domain that holds state and
registers no phase is incomplete under `docs/ROADMAP.md` Part II §4.4.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.platform.contracts import ComponentHealth, PhaseReport


@runtime_checkable
class HealthSource(Protocol):
    """Something that can report on its own condition."""

    @property
    def component(self) -> Name:
        """Which component this is, as it appears in the health report."""
        ...

    def check_health(self) -> ComponentHealth:
        """Answer honestly, including that the answer is not known."""
        ...


@runtime_checkable
class ReconcilePhase(Protocol):
    """A step in the single startup path.

    Phases run in registration order, which is the platform's dependency
    order: a phase may rely on every earlier phase having run.

    A phase **reports** what it found rather than deciding what it means.
    Whether an unreadable record should stop the platform is a policy
    question, and policy belongs to the startup path rather than to the
    subsystem that noticed.
    """

    @property
    def phase(self) -> Name:
        """Which phase this is, as it appears in the startup report."""
        ...

    def reconcile(self) -> PhaseReport:
        """Bring persisted state and reality back into agreement."""
        ...
