"""Operational report. Transport evidence, not deployment authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from machi.kernel.analytics import AnalyticsEvent
from machi.kernel.cadence import PROFILES, interval_seconds, phase_limit
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, from_dict, meaning, to_dict
from machi.kernel.snapshot import SupportSnapshot, reject_customer_content
from machi.kernel.usage import _amount

REPORT_SCHEMA = "rukan.operational_report"
PRIVACY_POLICY = "rukan.telemetry.export.1"
MAX_REPORT_BYTES = 512_000
MAX_EVENTS = 64
MAX_ROLLUPS = 32
MAX_TRIGGERS = 16
MAX_FAILURES = 8
_TOKEN_MAX = 240


@contract(kind="kernel.usage_failure_count", version=1)
@dataclass(frozen=True, slots=True)
class UsageFailureCount(Contract):
    """How many requests shared one typed failure."""

    failure: str = meaning("typed failure class")
    count: int = meaning("requests in this class")

    def __post_init__(self) -> None:
        _token("failure", self.failure)
        if type(self.count) is not int or self.count < 1:
            raise ValidationError("usage failure count is invalid")


@contract(kind="kernel.usage_rollup", version=1)
@dataclass(frozen=True, slots=True)
class UsageRollup(Contract):
    """One group inside a report window. No request text."""

    model_identity: str = meaning("artifact id or provider digest")
    model_identity_kind: str = meaning("identity kind")
    macropath: str = meaning("runtime family")
    purpose: str = meaning("why the request was made")
    outcome: str = meaning("completed or failed")
    requests: int = meaning("requests in this group")
    input_tokens_total: str = meaning("sum of reported input tokens, or not_recorded")
    input_sample_count: int = meaning("requests that reported input tokens")
    output_tokens_total: str = meaning("sum of reported output tokens, or not_recorded")
    output_sample_count: int = meaning("requests that reported output tokens")
    latency_ms_sum: str = meaning("sum of boundary latency, or not_recorded")
    latency_sample_count: int = meaning("requests with boundary latency")
    latency_min_ms: str = meaning("minimum boundary latency, or not_recorded")
    latency_max_ms: str = meaning("maximum boundary latency, or not_recorded")
    failures: tuple[UsageFailureCount, ...] = meaning("failure classes in this group")

    def __post_init__(self) -> None:
        _nonneg("requests", self.requests)
        _nonneg("input samples", self.input_sample_count)
        _nonneg("output samples", self.output_sample_count)
        _nonneg("latency samples", self.latency_sample_count)
        _amount("input tokens", self.input_tokens_total)
        _amount("output tokens", self.output_tokens_total)
        _amount("latency sum", self.latency_ms_sum)
        _amount("latency min", self.latency_min_ms)
        _amount("latency max", self.latency_max_ms)
        if len(self.failures) > MAX_FAILURES:
            raise ValidationError("usage rollup has too many failure classes")


@contract(kind="kernel.usage_cumulative", version=1)
@dataclass(frozen=True, slots=True)
class UsageCumulative(Contract):
    """Lifetime counters. A missed window still moves these."""

    requests: int = meaning("usage records retained locally")
    succeeded: int = meaning("completed usage records")
    failed: int = meaning("failed usage records")
    input_tokens_total: str = meaning("lifetime reported input tokens, or not_recorded")
    input_sample_count: int = meaning("records that reported input tokens")
    output_tokens_total: str = meaning("lifetime reported output tokens, or not_recorded")  # noqa: E501
    output_sample_count: int = meaning("records that reported output tokens")
    latency_ms_sum: str = meaning("lifetime boundary latency sum, or not_recorded")
    latency_sample_count: int = meaning("records with boundary latency")

    def __post_init__(self) -> None:
        _nonneg("requests", self.requests)
        _nonneg("succeeded", self.succeeded)
        _nonneg("failed", self.failed)
        if self.succeeded + self.failed != self.requests:
            raise ValidationError("usage cumulative outcomes do not add up")
        _amount("input tokens", self.input_tokens_total)
        _amount("output tokens", self.output_tokens_total)
        _amount("latency sum", self.latency_ms_sum)
        _nonneg("input samples", self.input_sample_count)
        _nonneg("output samples", self.output_sample_count)
        _nonneg("latency samples", self.latency_sample_count)


@contract(kind="kernel.operational_report", version=1)
@dataclass(frozen=True, slots=True)
class OperationalReport(Contract):
    """One deployment report. Accepting it does not operate the host."""

    report_id: str = meaning("stable report identity")
    schema_name: str = meaning("rukan.operational_report")
    install_id: str = meaning("deployment install id")
    sequence: int = meaning("deployment report sequence, starting at 1")
    generated_at: str = meaning("UTC composition time")
    cadence_profile: str = meaning("development, production, or custom")
    cadence_seconds: int = meaning("periodic interval in seconds")
    cadence_phase_seconds: int = meaning("stable per-install phase inside the interval")
    trigger_reasons: tuple[str, ...] = meaning("why this report was composed")
    version: str = meaning("Rukan version")
    build_id: str = meaning("build id, or not_recorded")
    source_commit: str = meaning("source commit, or not_recorded")
    previous_report_id: str = meaning("previous report id, or not_recorded")
    telemetry_stream_id: str = meaning("local telemetry stream; reset starts a new one")
    stream_started_at: str = meaning("when this local stream was minted")
    usage_records_dropped: int = meaning("local usage rows that failed to persist")
    usage_accounting_status: str = meaning("complete or degraded")
    window_start: str = meaning("start of incremental facts")
    window_end: str = meaning("end of incremental facts")
    privacy_policy: str = meaning("telemetry allow-list version")
    snapshot: SupportSnapshot = meaning("latest safe deployment summary")
    events: tuple[AnalyticsEvent, ...] = meaning("incremental event envelopes")
    rollups: tuple[UsageRollup, ...] = meaning("incremental usage groups")
    cumulative: UsageCumulative = meaning("lifetime usage counters")
    event_count: int = meaning("event envelopes in this report")
    rollup_count: int = meaning("usage groups in this report")

    def __post_init__(self) -> None:
        if self.schema_name != REPORT_SCHEMA:
            raise ValidationError("operational report schema name is not Rukan's")
        if self.privacy_policy != PRIVACY_POLICY:
            raise ValidationError("operational report privacy policy is not v1")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise ValidationError("operational report sequence is invalid")
        if self.sequence < 1:
            raise ValidationError("operational report sequence starts at 1")
        if self.usage_accounting_status not in {"complete", "degraded"}:
            raise ValidationError("usage accounting status is unknown")
        dropped = self.usage_records_dropped
        if type(dropped) is not int or dropped < 0:
            raise ValidationError("usage dropped count is invalid")
        _token("stream", self.telemetry_stream_id)
        if not self.stream_started_at or len(self.stream_started_at) > 80:
            raise ValidationError("operational report stream start is missing")
        if self.cadence_profile not in PROFILES:
            raise ValidationError("operational report cadence profile is unknown")
        expected = interval_seconds(
            self.cadence_profile,
            self.cadence_seconds if self.cadence_profile == "custom" else None,
        )
        if self.cadence_seconds != expected:
            raise ValidationError("operational report cadence seconds do not match the profile")  # noqa: E501
        limit = phase_limit(self.cadence_profile, self.cadence_seconds)
        if type(self.cadence_phase_seconds) is not int or not 0 <= self.cadence_phase_seconds <= limit:  # noqa: E501
            raise ValidationError("operational report cadence phase is outside the profile")  # noqa: E501
        if not self.trigger_reasons or len(self.trigger_reasons) > MAX_TRIGGERS:
            raise ValidationError("operational report triggers are missing or too many")
        for reason in self.trigger_reasons:
            _token("trigger", reason)
        if len(self.events) > MAX_EVENTS or len(self.rollups) > MAX_ROLLUPS:
            raise ValidationError("operational report has too many rows")
        if self.event_count != len(self.events) or self.rollup_count != len(self.rollups):  # noqa: E501
            raise ValidationError("operational report counts do not match")
        if self.snapshot.install_id != self.install_id:
            raise ValidationError("operational report snapshot install id does not match")  # noqa: E501
        for event in self.events:
            if event.install_id != self.install_id:
                raise ValidationError("operational report event install id does not match")  # noqa: E501


def report_id_for(
    install_id: str, sequence: int, generated_at: str, triggers: tuple[str, ...]
) -> str:
    """Stable id. The clock is an input, not a hidden read."""
    material = "\n".join((install_id, str(sequence), generated_at, ",".join(triggers)))
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"rpt_{digest}"


def dump_report(report: OperationalReport) -> str:
    """Canonical JSON. Privacy is checked before bytes are returned."""
    document = to_dict(report)
    reject_customer_content(document)
    encoded = json.dumps(document, sort_keys=True)
    if len(encoded) > MAX_REPORT_BYTES:
        raise ValidationError("operational report is too large")
    return encoded


def load_report(text: str) -> OperationalReport:
    """Validate an untrusted report. A bad document fails closed."""
    if len(text) > MAX_REPORT_BYTES:
        raise ValidationError("operational report is too large")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError("operational report is not json") from exc
    if not isinstance(document, dict):
        raise ValidationError("operational report is not an object")
    reject_customer_content(document)
    loaded = from_dict(document)
    if not isinstance(loaded, OperationalReport):
        raise ValidationError("operational report kind is not recognised")
    return loaded


def _token(label: str, value: str) -> None:
    if not value or len(value) > _TOKEN_MAX:
        raise ValidationError(f"operational report {label} is empty or too long")
    if any(char in value for char in ("\x00", "\n", "\r")):
        raise ValidationError(f"operational report {label} must not contain controls")


def _nonneg(label: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValidationError(f"operational report {label} count is invalid")
