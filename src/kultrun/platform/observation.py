"""Control-plane operational journal. Not usage, not audit, not vendor export.

Domains keep their own records. This journal is the composition-level
trace of what Kultrun discovered, decided, and executed — the facts a
deployment report, Admin diagnostic, and future telemetry exporter share.

It never stores prompts, responses, documents, credentials, or named
personal content. A dropped observer callback is counted as a fact of
loss, not retried onto the mutating path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from typing import Protocol, runtime_checkable

from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.platform.contracts import (
    OperationalFact,
    OperationalFactId,
    OperationalOutcome,
    OperationalStage,
)
from kultrun.storage.contracts import EmpiricalProbeEvidence, StorageFailureCode
from kultrun.storage.limits import SONAR_UNIT_BYTES

__all__ = [
    "ConsoleProgress",
    "DeferredSonarProgress",
    "FanoutObserver",
    "NullObserver",
    "OperationalFact",
    "OperationalFactId",
    "OperationalJournal",
    "OperationalObserver",
    "OperationalOutcome",
    "OperationalStage",
    "SonarProgressAdapter",
    "attr",
    "attr_value",
    "chronological_facts",
    "format_progress",
    "storage_event_handler",
]


@runtime_checkable
class OperationalObserver(Protocol):
    """Non-blocking listener. Failure must not affect the mutating path."""

    def observe(self, fact: OperationalFact) -> None:
        """Receive one fact. Must not raise into the journal."""
        ...


class NullObserver:
    """Default observer. Silence is valid; it is not a dropped event."""

    def observe(self, fact: OperationalFact) -> None:
        del fact


class ConsoleProgress:
    """Live acceptance lines from persisted facts. Not a log parser."""

    def __init__(self, write: Callable[[str], object] | None = None) -> None:
        self._write = write

    def observe(self, fact: OperationalFact) -> None:
        line = format_progress(fact)
        if not line:
            return
        sink = self._write
        if sink is None:
            print(line, flush=True)
            return
        sink(line)


class FanoutObserver:
    """Deliver one fact to several observers. Each failure is isolated."""

    def __init__(self, observers: Sequence[OperationalObserver] = ()) -> None:
        self._observers = tuple(observers)

    def observe(self, fact: OperationalFact) -> None:
        for observer in self._observers:
            try:
                observer.observe(fact)
            except Exception:
                continue


_QUIET_PROGRESS = frozenset(
    {
        "model.blocked",
        "model.available",
        "runtime.candidate_evaluated",
        "deployment.started",
    }
)


def format_progress(fact: OperationalFact) -> str:
    """One live progress line. Derived from the fact, never invented."""
    if fact.event_type.value in _QUIET_PROGRESS:
        return ""
    if fact.event_type.value == "model.funnel_completed":
        return f"[MODELS] {fact.summary}"
    if fact.event_type.value == "runtime.selected":
        return f"[FOUNDATION] {fact.summary}"
    label = {
        OperationalStage.RUN: "RUN",
        OperationalStage.HOST: "HOST",
        OperationalStage.STORAGE: "STORAGE",
        OperationalStage.PROBE: "PROBE",
        OperationalStage.SONAR: "SONAR",
        OperationalStage.RUNTIME: "RUNTIME",
        OperationalStage.MODEL: "MODEL",
        OperationalStage.PLAN: "PLAN",
        OperationalStage.ADMISSION: "ADMISSION",
        OperationalStage.INSTANCE: "INSTANCE",
        OperationalStage.INFERENCE: "INFERENCE",
        OperationalStage.DEPLOYMENT: "DEPLOYMENT",
        OperationalStage.FEASIBILITY: "FEASIBILITY",
    }.get(fact.stage, fact.stage.value.upper())
    return f"[{label}] {fact.summary}"


def chronological_facts(
    facts: Sequence[OperationalFact],
) -> tuple[OperationalFact, ...]:
    """Stable occurred_at order. Same-instant ties keep input order."""
    return tuple(sorted(facts, key=lambda item: item.occurred_at))


def attr(key: str, value: object) -> str:
    """One allowlisted attribute. Values are stringified; never nested."""
    token = str(value).replace("\n", " ").strip()
    return f"{key}={token}"


def attr_value(fact: OperationalFact, key: str) -> str | None:
    """Exact attribute value. Prefix matching is not identity."""
    prefix = f"{key}="
    for item in fact.attributes:
        if item.startswith(prefix):
            return item[len(prefix) :]
    return None


class OperationalJournal:
    """Persist operational facts and fan out to a non-blocking observer."""

    def __init__(
        self,
        store: Store,
        clock: Clock | None = None,
        observer: OperationalObserver | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or SystemClock()
        self._observer: OperationalObserver = observer or NullObserver()
        self._correlation: str | None = None

    def set_observer(self, observer: OperationalObserver | None) -> None:
        self._observer = observer or NullObserver()

    def bind_correlation(self, correlation_id: str) -> None:
        """Stamp subsequent facts with this DeploymentRun identity."""
        token = correlation_id.strip()
        self._correlation = token or None

    def emit(
        self,
        *,
        host_id: HostId,
        stage: OperationalStage,
        event_type: str,
        summary: str,
        outcome: OperationalOutcome = OperationalOutcome.INFO,
        reason_code: str | None = None,
        attributes: Sequence[str] = (),
        correlation_id: str | None = None,
    ) -> OperationalFact:
        resolved = correlation_id or self._correlation
        fact = OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=host_id,
            occurred_at=self._clock.now(),
            stage=stage,
            event_type=Name(event_type),
            outcome=outcome,
            summary=summary[:240],
            reason_code=reason_code if reason_code else NOT_PROVIDED,
            attributes=tuple(attributes),
            correlation_id=resolved if resolved else NOT_PROVIDED,
        )
        self._store.put(fact.fact_id.value, fact)
        with suppress(Exception):
            self._observer.observe(fact)
        return fact

    def facts(self, host_id: HostId | None = None) -> tuple[OperationalFact, ...]:
        records = self._store.records(OperationalFact)
        if host_id is not None:
            records = tuple(item for item in records if item.host_id == host_id)
        return chronological_facts(records)


class SonarProgressAdapter:
    """Turn EmpiricalProbeEvidence into per-tier operational facts."""

    def __init__(self, journal: OperationalJournal, host_id: HostId) -> None:
        self._journal = journal
        self._host_id = host_id
        self._completed: dict[str, frozenset[int]] = {}
        self._failed: dict[str, str] = {}

    def __call__(self, evidence: EmpiricalProbeEvidence) -> None:
        mount = evidence.mount_point
        seen = self._completed.get(mount, frozenset())
        completed = frozenset(evidence.completed_tier_units)
        for tier in sorted(completed - seen):
            self._journal.emit(
                host_id=self._host_id,
                stage=OperationalStage.SONAR,
                event_type="storage.sonar_tier_passed",
                outcome=OperationalOutcome.PASS,
                summary=f"{tier} GiB PASS",
                attributes=(
                    attr("mount", mount),
                    attr("tier_units", tier),
                    attr("unit_bytes", SONAR_UNIT_BYTES),
                ),
            )
        self._completed[mount] = completed
        code = (
            evidence.failure_code if is_resolved(evidence.failure_code) else None
        )
        if not isinstance(code, str) or not code:
            return
        previous = self._failed.get(mount)
        if previous == code:
            return
        self._failed[mount] = code
        attempted = evidence.attempted_tier_units
        failed_at = attempted[-1] if attempted else None
        label = _capacity_failure_label(code)
        size = f"{failed_at} GiB " if failed_at is not None else ""
        self._journal.emit(
            host_id=self._host_id,
            stage=OperationalStage.SONAR,
            event_type="storage.sonar_capacity_failure",
            outcome=OperationalOutcome.FAIL,
            summary=f"{size}{label}".strip(),
            reason_code=code,
            attributes=(
                attr("mount", mount),
                *(() if failed_at is None else (attr("tier_units", failed_at),)),
            ),
        )


class DeferredSonarProgress:
    """Bind Sonar progress after host identity exists. One adapter per run."""

    def __init__(
        self, journal: OperationalJournal, host_id: Callable[[], HostId]
    ) -> None:
        self._journal = journal
        self._host_id = host_id
        self._inner: SonarProgressAdapter | None = None

    def __call__(self, evidence: EmpiricalProbeEvidence) -> None:
        if self._inner is None:
            self._inner = SonarProgressAdapter(self._journal, self._host_id())
        self._inner(evidence)


def _capacity_failure_label(code: str) -> str:
    if code == StorageFailureCode.STORAGE_QUOTA_EXCEEDED.value:
        return "EDQUOT"
    if code == StorageFailureCode.STORAGE_SPACE_EXHAUSTED.value:
        return "ENOSPC"
    return code


def storage_event_handler(
    journal: OperationalJournal, host_id: HostId | Callable[[], HostId]
) -> Callable[[str, Mapping[str, str]], None]:
    """Adapt storage's untyped on_event callback to the journal."""

    def on_event(event_type: str, fields: Mapping[str, str]) -> None:
        resolved = host_id() if callable(host_id) else host_id
        stage = _stage_for(event_type)
        outcome = _outcome_for(fields.get("outcome", "info"))
        summary = fields.get("summary") or event_type
        reason = fields.get("reason") or None
        skip = {"summary", "outcome", "reason"}
        attributes = tuple(
            attr(key, value) for key, value in fields.items() if key not in skip
        )
        journal.emit(
            host_id=resolved,
            stage=stage,
            event_type=event_type,
            summary=summary,
            outcome=outcome,
            reason_code=reason,
            attributes=attributes,
        )

    return on_event


def fanout_empirical(
    *callbacks: Callable[[EmpiricalProbeEvidence], None],
) -> Callable[[EmpiricalProbeEvidence], None]:
    """Persist Sonar evidence and emit progress without dropping either."""

    def on_progress(evidence: EmpiricalProbeEvidence) -> None:
        for callback in callbacks:
            callback(evidence)

    return on_progress


def _stage_for(event_type: str) -> OperationalStage:
    if event_type.startswith("storage.sonar"):
        return OperationalStage.SONAR
    if event_type.startswith("storage.probe"):
        return OperationalStage.PROBE
    prefix = event_type.split(".", 1)[0]
    try:
        return OperationalStage(prefix)
    except ValueError:
        if event_type.startswith("storage."):
            return OperationalStage.STORAGE
        return OperationalStage.DEPLOYMENT


def _outcome_for(token: str) -> OperationalOutcome:
    try:
        return OperationalOutcome(token)
    except ValueError:
        return OperationalOutcome.INFO
