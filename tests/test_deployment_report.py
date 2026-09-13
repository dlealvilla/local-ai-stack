"""Operational facts, deployment report projection, and disabled telemetry."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.telemetry.disabled import DisabledProductTelemetryExporter
from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import config_schema
from kultrun.platform.contracts import (
    DeploymentVerdict,
    OperationalFact,
    OperationalFactId,
    OperationalOutcome,
    OperationalStage,
)
from kultrun.platform.observation import (
    OperationalJournal,
    attr,
    format_progress,
    storage_event_handler,
)
from kultrun.platform.report import compose_deployment_report, format_deployment_report
from kultrun.vendor.contracts import TelemetrySettings
from kultrun.vendor.sanitize import ExportingObserver, sanitize_fact
from tests.test_capacity import GIB, INSTANT, host
from tests.test_control_plane import build_platform, call
from tests.test_storage_recompute import _layered


def test_journal_persists_and_reloads(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "records")
    clock = FixedClock(now_utc())
    journal = OperationalJournal(store, clock)
    host_id = HostId.generate()
    journal.emit(
        host_id=host_id,
        stage=OperationalStage.STORAGE,
        event_type="storage.authority_established",
        summary="authorizing 32 GiB",
        outcome=OperationalOutcome.PASS,
        attributes=(attr("mount", "/workspace"),),
    )
    reloaded = OperationalJournal(store, clock)
    facts = reloaded.facts(host_id)
    assert len(facts) == 1
    assert facts[0].summary == "authorizing 32 GiB"
    assert facts[0].event_type.value == "storage.authority_established"


def test_progress_line_is_derived_from_the_fact() -> None:
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.SONAR,
        event_type=Name("storage.sonar_tier_passed"),
        outcome=OperationalOutcome.PASS,
        summary="32 GiB PASS",
    )
    assert format_progress(fact) == "[SONAR] 32 GiB PASS"


def test_probe_progress_column_is_not_storage() -> None:
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.PROBE,
        event_type=Name("storage.probe_result"),
        outcome=OperationalOutcome.UNRESOLVED,
        summary="MooseFS specialist unavailable",
    )
    assert format_progress(fact) == "[PROBE] MooseFS specialist unavailable"


def test_storage_probe_event_maps_to_probe_stage(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "records")
    journal = OperationalJournal(store, FixedClock(now_utc()))
    host_id = HostId.generate()
    handler = storage_event_handler(journal, host_id)
    handler(
        "storage.probe_result",
        {
            "summary": "MooseFS specialist unavailable",
            "outcome": "unresolved",
            "reason": "specialist_unavailable",
        },
    )
    facts = journal.facts(host_id)
    assert len(facts) == 1
    assert facts[0].stage is OperationalStage.PROBE
    assert facts[0].event_type.value == "storage.probe_result"
    assert format_progress(facts[0]) == "[PROBE] MooseFS specialist unavailable"


def test_report_projection_from_stored_state() -> None:
    subject = host(memory_total=64 * GIB)
    envelope = CapacityEnvelope(
        host_id=subject.host_id,
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=(
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(27 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="fuse.moosefs",
            ),
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={"/workspace": 7 * GIB},
        candidates=(),
        recommended_candidate_id=None,
        selection=None,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=None,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=(),
    )
    assert report.verdict is DeploymentVerdict.INCOMPLETE
    assert report.host_id == subject.host_id
    text = format_deployment_report(report)
    assert "OVERALL: INCOMPLETE" in text
    assert "/workspace" in text
    assert "Managed usage" in text


def test_telemetry_disabled_by_default_and_never_required() -> None:
    settings = config_schema().load({}).section(TelemetrySettings)
    assert settings.enabled is False
    assert settings.export_operational_metadata is False
    captured: list[object] = []

    class Recording:
        def export(self, records: object) -> None:
            captured.append(records)

    observer = ExportingObserver(Recording(), enabled=False)
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.HOST,
        event_type=Name("host.discovered"),
        outcome=OperationalOutcome.INFO,
        summary="discovered linux x86_64",
        attributes=(attr("os", "linux"), attr("arch", "x86_64")),
    )
    observer.observe(fact)
    assert captured == []
    record = sanitize_fact(fact)
    assert record.os_name == "linux"
    assert is_resolved(record.kultrun_build)
    DisabledProductTelemetryExporter().export((record,))


def test_deployment_report_api(tmp_path: Path) -> None:
    platform = build_platform(tmp_path, FixedClock(now_utc()))
    payload = call(platform, "/deployment-report")
    assert payload["kind"] == "platform.deployment_report"
    assert "verdict" in payload


def test_enabled_exporter_failure_does_not_raise() -> None:
    class Boom:
        def export(self, records: object) -> None:
            raise RuntimeError("network")

    observer = ExportingObserver(Boom(), enabled=True)
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.RUNTIME,
        event_type=Name("runtime.selected"),
        outcome=OperationalOutcome.PASS,
        summary="selected vllm",
    )
    observer.observe(fact)
