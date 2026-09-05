"""The single startup and reconciliation path.

One path, ordered phases, one report. Every later stage registers a phase
here rather than adding a startup of its own — which is what makes Stage
6.3 "one reconciliation path across models, components, runtimes,
workloads, reservations, ports and endpoints" a completion rather than an
invention.

**Startup does not stop because a subsystem found something wrong.** A
phase reports defects; the path records them and continues. Refusing to
start over an unreadable record would make the platform impossible to
diagnose through its own API, which is the surface an administrator has.
That is a deliberate policy for Milestone 0 and it is recorded as debt: once
a record can authorize something, at Milestone 2, an unreadable one must
fail closed instead.

A phase that *cannot complete* is different from one that found a defect,
and that distinction is why `PhaseReport` carries both.
"""

from __future__ import annotations

from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_MEASURED, Maybe
from kultrun.platform.contracts import PhaseReport, StartupReport
from kultrun.platform.ports import ReconcilePhase
from kultrun.platform.state import PlatformStateStore


class StoreReconcilePhase:
    """Startup phase: sweep interrupted writes, surface unreadable records.

    Always the first phase. Every other phase reads persisted state, so the
    store's own recovery has to have happened before any of them run.
    """

    phase = Name("record-store")

    def __init__(self, store: Store) -> None:
        self._store = store

    def reconcile(self) -> PhaseReport:
        report = self._store.reconcile()
        detail = (
            f"{report.records_verified} records verified, "
            f"{report.swept_temporaries} interrupted writes swept"
        )
        return PhaseReport(
            phase=self.phase,
            succeeded=True,
            detail=detail,
            defects=tuple(
                f"{defect.location}: {defect.problem}" for defect in report.defects
            ),
        )


class Startup:
    """Runs the platform's phases in order and records what happened."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._phases: list[ReconcilePhase] = []
        self._last: StartupReport | None = None

    def register(self, phase: ReconcilePhase) -> None:
        """Add a phase. Order of registration is order of execution."""
        self._phases.append(phase)

    @property
    def last_report(self) -> StartupReport | None:
        """What the most recent start did, or None before the first."""
        return self._last

    def run(self, *, state: PlatformStateStore | None = None) -> StartupReport:
        """Run every phase, in order, recording each.

        Continues past a failed phase so that the report describes the whole
        state of the platform rather than stopping at the first problem. An
        administrator diagnosing a broken installation needs all of it.
        """
        started_at = self._clock.now()
        reports: list[PhaseReport] = []
        for phase in self._phases:
            reports.append(phase.reconcile())

        first_run: Maybe[bool] = NOT_MEASURED
        if state is not None and state.is_loaded:
            first_run = _created_this_run(reports)

        report = StartupReport(
            started_at=started_at,
            completed=all(entry.succeeded for entry in reports),
            first_run=first_run,
            phases=tuple(reports),
        )
        self._last = report
        return report


def _created_this_run(reports: list[PhaseReport]) -> bool:
    return any(
        entry.detail == "initialized a new installation" for entry in reports
    )
