"""Operational facts, deployment report projection, and disabled telemetry."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from kultrun.adapters.persistence.file_store import FileStore
from kultrun.adapters.telemetry.disabled import DisabledProductTelemetryExporter
from kultrun.capacity.contracts import (
    CapacityEnvelope,
    EvidenceRequirement,
    PoolCapacity,
)
from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.clock import FixedClock, now_utc
from kultrun.kernel.ids import Name
from kultrun.kernel.schema import to_dict
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.main import config_schema
from kultrun.platform.contracts import (
    DeploymentReport,
    DeploymentVerdict,
    OperationalFact,
    OperationalFactId,
    OperationalOutcome,
    OperationalStage,
    RuntimeCandidateReport,
)
from kultrun.platform.observation import (
    OperationalJournal,
    attr,
    format_progress,
    storage_event_handler,
)
from kultrun.platform.report import (
    _human_reason_codes,
    compose_deployment_report,
    format_deployment_report,
)
from kultrun.storage.contracts import StorageCapacityEvidence
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
    assert "Managed by Kultrun" in text
    assert "UNTRUSTED" in text
    assert "LAYER 3 — MINIMUM FEASIBILITY" in text


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


def _capacity_evidence(
    host_id: HostId, mount: str, fingerprint: str, quota: str
) -> StorageCapacityEvidence:
    from kultrun.evidence.contracts import Confidence, Provenance
    from kultrun.kernel.unresolved import NOT_PROVIDED
    from kultrun.storage.contracts import StorageEvidenceStatus

    return StorageCapacityEvidence(
        host_id=host_id,
        mount_point=mount,
        quota_identity=quota,
        pool_fingerprint=fingerprint,
        observed_at=INSTANT,
        status=StorageEvidenceStatus.PROBED,
        confidence=Confidence.MEDIUM,
        provenance=Provenance(
            producer=Name("test"),
            producer_version=NOT_PROVIDED,
            observed_at=INSTANT,
            policy_version="t",
        ),
        operational_available_bytes=32 * GIB,
        authorizing_available_bytes=32 * GIB,
        selected_reason="test",
    )


def test_attr_value_matches_exact_mount_identity() -> None:
    from kultrun.platform.observation import attr_value

    workspace = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=INSTANT,
        stage=OperationalStage.SONAR,
        event_type=Name("storage.sonar_tier_passed"),
        outcome=OperationalOutcome.PASS,
        summary="32 GiB PASS",
        attributes=(attr("mount", "/workspace"),),
    )
    assert attr_value(workspace, "mount") == "/workspace"
    assert attr_value(workspace, "mount") != "/"


def test_report_keeps_root_and_workspace_sonar_separate() -> None:
    from kultrun.model.contracts import MemoryPlacement, ModelId
    from kultrun.planning.contracts import DeploymentPlan
    from kultrun.runtime.contracts import (
        FoundationSelection,
        FoundationSelectionId,
        FoundationSelectionMode,
    )

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
                mount_point="/",
                space=_layered(8 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="overlay",
            ),
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(200 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="fuse.moosefs",
            ),
        ),
    )
    root_fail = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.SONAR,
        event_type=Name("storage.sonar_tier_failed"),
        outcome=OperationalOutcome.FAIL,
        summary="8 GiB EDQUOT",
        attributes=(attr("mount", "/"),),
    )
    workspace_pass = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.SONAR,
        event_type=Name("storage.sonar_tier_passed"),
        outcome=OperationalOutcome.PASS,
        summary="32 GiB PASS",
        attributes=(attr("mount", "/workspace"),),
    )
    selection = FoundationSelection(
        selection_id=FoundationSelectionId.parse("fsel_" + "a" * 16),
        host_id=subject.host_id,
        selection_mode=FoundationSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        recommended_candidate_id="cand_recommended",
        selected_candidate_id="cand_selected",
    )
    plan = DeploymentPlan(
        model_id=ModelId.generate(),
        logical_name=Name("probe"),
        source_ref="org/probe",
        quantization="awq",
        runtime="vllm",
        executor_kind="native-process",
        placement=MemoryPlacement.DISCRETE_GPU,
        expected_ram_bytes=GIB,
        expected_vram_bytes=8 * GIB,
        expected_unified_bytes=NOT_PROVIDED,
        expected_storage_bytes=GIB,
        expected_utilization=0.4,
        estimator_provider="test",
        policy_version="test",
        rationale=("fixture",),
        source_revision=NOT_PROVIDED,
        selected_candidate_id="cand_plan",
    )
    facts = (
        root_fail,
        workspace_pass,
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INSTANCE,
            event_type=Name("instance.started"),
            outcome=OperationalOutcome.PASS,
            summary="starting inst_first",
            attributes=(attr("instance", "inst_first"), attr("pid", "11")),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INFERENCE,
            event_type=Name("inference.completed"),
            outcome=OperationalOutcome.PASS,
            summary="inference pass",
            attributes=(attr("latency_ms", 12),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INSTANCE,
            event_type=Name("instance.stopped"),
            outcome=OperationalOutcome.INFO,
            summary="stopped inst_first",
            attributes=(attr("reservation", "held"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INSTANCE,
            event_type=Name("instance.restarted"),
            outcome=OperationalOutcome.PASS,
            summary="restarted inst_first",
            attributes=(attr("pid", "22"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INFERENCE,
            event_type=Name("inference.completed"),
            outcome=OperationalOutcome.PASS,
            summary="inference pass again",
            attributes=(attr("latency_ms", 9),),
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={
            "/": _capacity_evidence(subject.host_id, "/", "fp-root", "quota-root"),
            "/workspace": _capacity_evidence(
                subject.host_id, "/workspace", "fp-workspace", "quota-workspace"
            ),
        },
        empirical={},
        managed={"/": 1 * GIB, "/workspace": 7 * GIB},
        candidates=(),
        recommended_candidate_id="cand_recommended",
        selection=selection,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=None,
        deployment_plan=plan,
        instances=(),
        executions=(),
        facts=facts,
    )
    assert report.verdict is DeploymentVerdict.PASS
    by_mount = {pool.mount_point: pool for pool in report.storage_pools}
    assert "8 GiB EDQUOT" in by_mount["/"].sonar_tiers
    assert "32 GiB PASS" not in by_mount["/"].sonar_tiers
    assert "32 GiB PASS" in by_mount["/workspace"].sonar_tiers
    assert "8 GiB EDQUOT" not in by_mount["/workspace"].sonar_tiers
    assert by_mount["/"].quota_identity == "quota-root"
    assert by_mount["/"].pool_fingerprint == "fp-root"
    assert by_mount["/workspace"].quota_identity == "quota-workspace"
    assert by_mount["/workspace"].pool_fingerprint == "fp-workspace"
    assert report.recommended_runtime == "cand_recommended"
    assert report.selected_runtime == "cand_selected"
    assert report.plan_runtime_candidate == "cand_plan"
    text = format_deployment_report(report)
    storage_text = text.split("LAYER 5 — EXECUTION FOUNDATION", 1)[0]
    root_section, workspace_section = storage_text.split("  Pool  /workspace", 1)
    assert "8 GiB EDQUOT" in root_section
    assert "32 GiB PASS" not in root_section
    assert "32 GiB PASS" in workspace_section
    assert "LAYER 5 — EXECUTION FOUNDATION" in text
    assert "LAYER 11 — INSTANCE & INFERENCE" in text
    assert "INFERENCE 1" in text
    assert "INFERENCE 2" in text
    assert "Latency        9 ms" in text
    assert "instance.started" in text
    assert "instance.stopped" in text
    assert "instance.restarted" in text
    assert "inference.completed" not in text
    assert report.latest_inference_latency_ms == 9
    assert report.inferences[-1].latency_ms == 9
    debug = format_deployment_report(report, debug=True)
    assert "DEBUG EVIDENCE" in debug
    assert "quota-workspace" in debug
    assert "cand_selected" in debug


def test_sonar_edquot_does_not_fail_the_vertical() -> None:
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
                mount_point="/",
                space=_layered(8 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="overlay",
            ),
        ),
    )
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.SONAR,
        event_type=Name("storage.sonar_tier_failed"),
        outcome=OperationalOutcome.FAIL,
        summary="8 GiB EDQUOT",
        attributes=(attr("mount", "/"),),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(),
        recommended_candidate_id="cand_vllm",
        selection=None,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=None,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=(fact,),
    )
    assert report.verdict is DeploymentVerdict.INCOMPLETE
    assert report.recommended_runtime == "cand_vllm"
    assert not is_resolved(report.selected_runtime)
    text = format_deployment_report(report)
    assert "OVERALL: INCOMPLETE" in text
    assert "OVERALL: FAIL" not in text
    assert "  selected" not in text.split("LAYER 5 —", 1)[0]
    assert "- selected" not in text


def _base_envelope(
    subject: HostCapabilities, pools: tuple[PoolCapacity, ...]
) -> CapacityEnvelope:
    return CapacityEnvelope(
        host_id=subject.host_id,
        host_fingerprint="test",
        computed_at=INSTANT,
        policy_version="t",
        memory=_layered(48 * GIB),
        memory_requirement=EvidenceRequirement.SUFFICIENT,
        pools=pools,
    )


def _compose(
    subject: HostCapabilities,
    envelope: CapacityEnvelope,
    facts: tuple[OperationalFact, ...],
) -> DeploymentReport:
    return compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
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
        facts=facts,
        run_id="drun_test0000000001",
        run_started_at=INSTANT,
    )


def test_layers_are_ordered_and_linked() -> None:
    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(
        subject,
        (
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(32 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="fuse.moosefs",
            ),
        ),
    )
    report = _compose(subject, envelope, ())
    identities = tuple(item.identity for item in report.layers)
    assert identities == (
        "run",
        "host",
        "cleanup",
        "minimum",
        "storage",
        "foundation",
        "runtime",
        "model_feasibility",
        "model_selection",
        "plan",
        "admission",
        "instance",
        "outcome",
    )
    text = format_deployment_report(report)
    for heading in (
        "LAYER 0 — RUN",
        "LAYER 1 — HOST DISCOVERY",
        "LAYER 2 — MANAGED-STATE RECONCILIATION",
        "LAYER 3 — MINIMUM FEASIBILITY",
        "LAYER 4 — STORAGE & CAPACITY",
        "LAYER 5 — EXECUTION FOUNDATION",
        "LAYER 6 — RUNTIME ENVIRONMENT",
        "LAYER 7 — MODEL FEASIBILITY",
        "LAYER 8 — MODEL SELECTION",
        "LAYER 9 — DEPLOYMENT PLAN",
        "LAYER 10 — RESOURCE ADMISSION",
        "LAYER 11 — INSTANCE & INFERENCE",
        "LAYER 12 — FINAL OUTCOME",
    ):
        assert heading in text
    assert report.run_id == "drun_test0000000001"
    assert "MooseFS / FUSE" in text
    assert (
        "Purpose: Determine whether this host can support a minimum Kultrun deployment."
    ) in text
    for layer in report.layers:
        assert layer.inputs
        assert layer.process
        assert layer.outputs
        assert layer.consumed_by
    assert "Input            " in text
    assert "Process          " in text
    assert "Output           " in text
    assert "Next             " in text


def test_decision_snapshots_are_projected() -> None:
    from kultrun.planning.contracts import (
        ModelSelection,
        ModelSelectionId,
        ModelSelectionMode,
    )
    from kultrun.runtime.contracts import (
        FoundationSelection,
        FoundationSelectionId,
        FoundationSelectionMode,
    )

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    selection = FoundationSelection(
        selection_id=FoundationSelectionId.parse("fsel_" + "b" * 16),
        host_id=subject.host_id,
        selection_mode=FoundationSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        recommended_candidate_id="cand_vllm",
        selected_candidate_id="cand_vllm",
    )
    model_selection = ModelSelection(
        selection_id=ModelSelectionId.generate(),
        host_id=subject.host_id,
        selection_mode=ModelSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        selection_basis="sel",
        recommended_logical_name="qwen2.5-7b-instruct-awq",
        selected_logical_name="qwen2.5-7b-instruct-awq",
    )
    facts = (
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.ADMISSION,
            event_type=Name("resource.admission_completed"),
            outcome=OperationalOutcome.PASS,
            summary="admission ADMITTED",
            attributes=(attr("reservation", "resv_test000000001"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.STORAGE,
            event_type=Name("storage.replan_completed"),
            outcome=OperationalOutcome.INFO,
            summary="replan invoked",
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(),
        recommended_candidate_id="cand_vllm",
        selection=selection,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=None,
        model_selection=model_selection,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=facts,
    )
    kinds = tuple(item.decision for item in report.decisions)
    assert kinds == (
        "FOUNDATION_SELECTION",
        "MODEL_SELECTION",
        "RESOURCE_ADMISSION",
        "REPLAN",
    )
    assert report.selected_model == "qwen2.5-7b-instruct-awq"
    assert report.reservation_id == "resv_test000000001"
    assert report.admission_verdict == "ADMITTED"


def test_latest_inference_follows_occurred_at() -> None:
    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    later = INSTANT + dt.timedelta(seconds=10)
    first = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.INFERENCE,
        event_type=Name("inference.completed"),
        outcome=OperationalOutcome.PASS,
        summary="inference pass",
        attributes=(attr("latency_ms", 686),),
    )
    second = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=later,
        stage=OperationalStage.INFERENCE,
        event_type=Name("inference.completed"),
        outcome=OperationalOutcome.PASS,
        summary="inference pass again",
        attributes=(attr("latency_ms", 473), attr("input_tokens", 7)),
    )
    report = _compose(subject, envelope, (second, first))
    assert report.latest_inference_latency_ms == 473
    assert len(report.inferences) == 2
    assert report.inferences[0].latency_ms == 686
    assert report.inferences[1].latency_ms == 473
    text = format_deployment_report(report)
    assert "INFERENCE 2" in text
    assert "Latency        473 ms" in text


def test_failure_boundary_names_the_layer() -> None:
    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.MODEL,
        event_type=Name("deployment.failed"),
        outcome=OperationalOutcome.FAIL,
        summary="No feasible model survived capacity filtering",
        reason_code="infeasible_vram",
    )
    report = _compose(subject, envelope, (fact,))
    assert report.verdict is DeploymentVerdict.FAIL
    text = format_deployment_report(report)
    assert "OVERALL: FAIL" in text
    assert "FAILED LAYER:" in text
    assert "Model Feasibility" in text
    assert "VerifiedRuntimeCapabilityProfile" in text
    assert "infeasible_vram" in text
    assert "No feasible model survived capacity filtering" in text


def test_blocked_model_progress_is_quiet() -> None:
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.MODEL,
        event_type=Name("model.blocked"),
        outcome=OperationalOutcome.BLOCKED,
        summary="huge-model BLOCKED: infeasible_vram",
    )
    assert format_progress(fact) == ""
    funnel = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.MODEL,
        event_type=Name("model.funnel_completed"),
        outcome=OperationalOutcome.INFO,
        summary="5 catalog → 2 available",
    )
    assert format_progress(funnel) == "[MODELS] 5 catalog → 2 available"
    selected = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.RUNTIME,
        event_type=Name("runtime.selected"),
        outcome=OperationalOutcome.PASS,
        summary="vllm selected",
    )
    assert format_progress(selected) == "[FOUNDATION] vllm selected"


def test_verified_selected_hides_component_missing_in_human_view() -> None:
    item = RuntimeCandidateReport(
        candidate_id="rcand_verified",
        runtime="vllm",
        version="0.28.0",
        executor="native-process",
        support_tier="product",
        compatibility="compatible",
        reason_codes=("required_component_missing",),
        recommended=True,
        selected=True,
    )
    assert _human_reason_codes(item, True) == ()
    assert _human_reason_codes(item, False) == ("required_component_missing",)
    unselected = RuntimeCandidateReport(
        candidate_id="rcand_other",
        runtime="vllm",
        version="0.28.0",
        executor="native-process",
        support_tier="product",
        compatibility="compatible",
        reason_codes=("required_component_missing",),
        recommended=False,
        selected=False,
    )
    assert _human_reason_codes(unselected, True) == ()


def test_deployment_run_survives_second_cli(tmp_path: Path) -> None:
    clock = FixedClock(now_utc())
    first = build_platform(tmp_path, clock)
    run = first.runs.current()
    assert run is not None
    first.journal.emit(
        host_id=first.hosts.current.host_id,
        stage=OperationalStage.STORAGE,
        event_type="storage.authority_established",
        summary="authorizing 32 GiB",
        outcome=OperationalOutcome.PASS,
    )
    stored = first.journal.facts(first.hosts.current.host_id)
    assert any(
        is_resolved(item.correlation_id) and item.correlation_id == run.run_id.value
        for item in stored
    )
    second = build_platform(tmp_path, clock)
    again = second.runs.current()
    assert again is not None
    assert again.run_id == run.run_id
    started = [
        item
        for item in second.journal.facts()
        if item.event_type.value == "deployment.started"
    ]
    assert len(started) == 1
    payload = call(second, "/deployment-report")
    assert payload["run_id"] == run.run_id.value
    run_payload = call(second, "/deployment-run")
    assert run_payload["kind"] == "platform.deployment_run"
    assert run_payload["run_id"] == run.run_id.value


def test_sanitize_excludes_paths_tokens_and_hostname() -> None:
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.INFERENCE,
        event_type=Name("inference.completed"),
        outcome=OperationalOutcome.PASS,
        summary="inference PASS",
        correlation_id="drun_abc12300000000",
        attributes=(
            attr("mount", "/workspace/customer-a/secret-project/models"),
            attr("input_tokens", 7),
            attr("output_tokens", 10),
            attr("hostname", "gpu-host-1"),
            attr("pid", "4744"),
            attr("latency_ms", 686),
            attr("runtime", "vllm"),
            attr("os", "linux"),
        ),
    )
    record = sanitize_fact(fact)
    encoded = str(to_dict(record))
    assert "customer-a" not in encoded
    assert "secret-project" not in encoded
    assert record.latency_ms == 686
    assert record.runtime == "vllm"
    assert record.run_id == "drun_abc12300000000"
    assert "input_tokens" not in encoded
    assert record.os_name == "linux"


def test_guided_report_replays_physical_16l_shape() -> None:
    from kultrun.host.contracts import Accelerator, AcceleratorVendor

    subject = host(
        memory_total=64 * GIB,
        accelerators=(
            Accelerator(
                index=0,
                vendor=AcceleratorVendor.NVIDIA,
                model_name="NVIDIA RTX PRO 4500 Blackwell",
                memory_total_bytes=int(31.9 * GIB),
                driver_version="580.178.04",
                unified_memory=False,
            ),
        ),
    )
    envelope = _base_envelope(
        subject,
        (
            PoolCapacity(
                mount_point="/",
                space=_layered(8 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="overlay",
            ),
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(32 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="fuse.moosefs",
            ),
        ),
    )
    later = INSTANT + dt.timedelta(seconds=30)
    facts = (
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.SONAR,
            event_type=Name("storage.sonar_tier_passed"),
            outcome=OperationalOutcome.PASS,
            summary="16 GiB PASS",
            attributes=(attr("mount", "/workspace"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.SONAR,
            event_type=Name("storage.sonar_tier_passed"),
            outcome=OperationalOutcome.PASS,
            summary="24 GiB PASS",
            attributes=(attr("mount", "/workspace"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.SONAR,
            event_type=Name("storage.sonar_tier_passed"),
            outcome=OperationalOutcome.PASS,
            summary="32 GiB PASS",
            attributes=(attr("mount", "/workspace"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.SONAR,
            event_type=Name("storage.sonar_capacity_failure"),
            outcome=OperationalOutcome.FAIL,
            summary="48 GiB EDQUOT",
            attributes=(attr("mount", "/workspace"),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=INSTANT,
            stage=OperationalStage.INFERENCE,
            event_type=Name("inference.completed"),
            outcome=OperationalOutcome.PASS,
            summary="inference PASS",
            attributes=(attr("latency_ms", 686),),
        ),
        OperationalFact(
            fact_id=OperationalFactId.generate(),
            host_id=subject.host_id,
            occurred_at=later,
            stage=OperationalStage.INFERENCE,
            event_type=Name("inference.completed"),
            outcome=OperationalOutcome.PASS,
            summary="inference PASS",
            attributes=(attr("latency_ms", 473),),
        ),
    )
    report = _compose(subject, envelope, facts)
    assert report.verdict is DeploymentVerdict.PASS
    text = format_deployment_report(report)
    assert "NVIDIA RTX PRO 4500" in text
    assert "physical" in text
    assert "SAFE" in text
    assert "not selected" in text
    assert "MooseFS / FUSE" in text
    assert "16 GiB PASS" in text
    assert "32 GiB PASS" in text
    assert "48 GiB EDQUOT" in text
    assert "INFERENCE 2" in text
    assert "Latency        473 ms" in text
    assert "OVERALL: PASS" in text
    assert "Manual intervention  NONE" in text


def _runtime_candidate(
    subject: HostCapabilities,
    *,
    ident: str,
    runtime: str,
    executor: str,
    executor_type: str,
    tier: str,
    compatibility: str,
    reasons: tuple[str, ...] = (),
    version: str = "0.28.0",
):
    from kultrun.evidence.contracts import Confidence
    from kultrun.runtime.contracts import (
        CompatibilityClass,
        ResolutionReasonCode,
        RuntimeCandidate,
        RuntimeCandidateId,
        RuntimeResolverMode,
        RuntimeSupportTier,
    )

    codes = tuple(ResolutionReasonCode(item) for item in reasons)
    del ident
    return RuntimeCandidate(
        candidate_id=RuntimeCandidateId.generate(),
        runtime=Name(runtime),
        runtime_family=Name(runtime),
        runtime_provider=Name(runtime),
        executor=Name(executor),
        executor_type=Name(executor_type),
        host_id=subject.host_id,
        compatibility=CompatibilityClass(compatibility),
        support_tier=RuntimeSupportTier(tier),
        reason="fixture",
        version=version,
        reason_codes=codes,
        confidence=Confidence.MEDIUM,
        policy_mode=RuntimeResolverMode.AUTO,
    )


def test_runtime_funnel_distinguishes_executor_and_recommendation() -> None:
    from kultrun.runtime.contracts import (
        FoundationSelection,
        FoundationSelectionId,
        FoundationSelectionMode,
    )

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    native = _runtime_candidate(
        subject,
        ident="rcand_native0000001",
        runtime="vllm",
        executor="native-process",
        executor_type="process",
        tier="product",
        compatibility="compatible",
    )
    container = _runtime_candidate(
        subject,
        ident="rcand_docker0000001",
        runtime="vllm",
        executor="container",
        executor_type="container",
        tier="product",
        compatibility="unsupported",
        reasons=("executor_unavailable",),
    )
    llama = _runtime_candidate(
        subject,
        ident="rcand_llama00000001",
        runtime="llama.cpp",
        executor="native-process",
        executor_type="process",
        tier="future",
        compatibility="compatible",
    )
    selection = FoundationSelection(
        selection_id=FoundationSelectionId.parse("fsel_" + "c" * 16),
        host_id=subject.host_id,
        selection_mode=FoundationSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        recommended_candidate_id=native.candidate_id.value,
        selected_candidate_id=native.candidate_id.value,
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(native, container, llama),
        recommended_candidate_id=native.candidate_id.value,
        selection=selection,
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
    assert report.runtime_discovered == 3
    assert report.runtime_product_selectable == 2
    assert report.runtime_executor_compatible == 2
    assert report.runtime_capacity_feasible == 2
    text = format_deployment_report(report)
    assert "vllm/native-process" in text
    assert "vllm/container" in text
    assert "NOT SELECTABLE" in text
    assert "FILTERED" in text
    assert "FEASIBLE" in text
    assert "Recommended" in text
    assert "Selected" in text
    assert "- selected" not in text
    assert report.recommended_runtime == native.candidate_id.value
    assert report.selected_runtime == native.candidate_id.value


def test_conditional_selected_foundation_is_feasible_not_filtered() -> None:
    from kultrun.runtime.contracts import (
        FoundationSelection,
        FoundationSelectionId,
        FoundationSelectionMode,
    )

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    native = _runtime_candidate(
        subject,
        ident="rcand_native0000001",
        runtime="vllm",
        executor="native-process",
        executor_type="process",
        tier="product",
        compatibility="conditional",
        reasons=("required_component_missing",),
    )
    container = _runtime_candidate(
        subject,
        ident="rcand_docker0000001",
        runtime="vllm",
        executor="container",
        executor_type="container",
        tier="product",
        compatibility="unsupported",
        reasons=("executor_unavailable",),
    )
    selection = FoundationSelection(
        selection_id=FoundationSelectionId.parse("fsel_" + "c" * 16),
        host_id=subject.host_id,
        selection_mode=FoundationSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        recommended_candidate_id=native.candidate_id.value,
        selected_candidate_id=native.candidate_id.value,
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(native, container),
        recommended_candidate_id=native.candidate_id.value,
        selection=selection,
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
    assert report.runtime_discovered == 2
    assert report.runtime_product_selectable == 2
    assert report.runtime_executor_compatible == 1
    assert report.runtime_capacity_feasible == 1
    text = format_deployment_report(report)
    assert "vllm/native-process" in text
    assert "FEASIBLE" in text
    assert "FILTERED" in text
    assert "FILTERED  -  selected" not in text
    assert "- selected" not in text
    native_line = next(
        line
        for line in text.splitlines()
        if line.strip().startswith("vllm/native-process")
    )
    assert "selected" in native_line
    assert "FILTERED" not in native_line


def test_model_funnel_and_blocked_reasons() -> None:
    from kultrun.planning.contracts import (
        AvailableModelExclusion,
        AvailableModelMember,
        AvailableModelView,
        AvailableModelViewId,
        AvailableViewStatus,
        FunnelStage,
        ModelSelection,
        ModelSelectionId,
        ModelSelectionMode,
    )

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    member = AvailableModelMember(
        model_id="mdl_ok",
        logical_name="qwen2.5-7b-instruct-awq",
        source_ref="org/qwen",
        source_revision=NOT_PROVIDED,
        runtime="vllm",
        runtime_version="0.28.0",
        quantization="awq",
        requested_context_tokens=4096,
        required_vram_bytes=8 * GIB,
        available_vram_bytes=24 * GIB,
        required_ram_bytes=16 * GIB,
        available_ram_bytes=48 * GIB,
        incremental_storage_bytes=GIB,
        available_storage_bytes=32 * GIB,
        requirement_provider="test",
        requirement_confidence="low",
        requirement_basis="basis-ok",
    )
    blocked_storage = AvailableModelExclusion(
        model_id="mdl_big",
        logical_name="llama-8b-fp16",
        stage=FunnelStage.DEEP_CAPACITY,
        reason="infeasible_storage",
    )
    blocked_vram = AvailableModelExclusion(
        model_id="mdl_vram",
        logical_name="qwen-72b-awq",
        stage=FunnelStage.DEEP_CAPACITY,
        reason="infeasible_vram",
        required_vram_bytes=40 * GIB,
        available_vram_bytes=24 * GIB,
    )
    available = AvailableModelView(
        view_id=AvailableModelViewId.generate(),
        host_id=subject.host_id,
        status=AvailableViewStatus.CURRENT,
        evaluated_at=INSTANT,
        view_basis="view-test",
        snapshot_basis="snap",
        host_fingerprint="fp",
        eligible_view_id="emv_test",
        runtime="vllm",
        runtime_version="0.28.0",
        requested_context_tokens=4096,
        universe_count=4,
        discovered_count=4,
        compatibility_count=4,
        cheap_reject_count=0,
        deep_analyzed_count=3,
        available_count=1,
        excluded_count=2,
        estimator_invocations=3,
        members=(member,),
        exclusions=(blocked_storage, blocked_vram),
    )
    model_selection = ModelSelection(
        selection_id=ModelSelectionId.generate(),
        host_id=subject.host_id,
        selection_mode=ModelSelectionMode.AUTO,
        created_at=INSTANT,
        selected_at=INSTANT,
        selection_basis="sel",
        recommended_logical_name="qwen2.5-7b-instruct-awq",
        selected_logical_name="qwen2.5-7b-instruct-awq",
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
        candidates=(),
        recommended_candidate_id=None,
        selection=None,
        installations=(),
        provisioning_plans=(),
        profiles={},
        available=available,
        model_selection=model_selection,
        deployment_plan=None,
        instances=(),
        executions=(),
        facts=(),
    )
    assert report.catalog_count == 4
    assert report.available_count == 1
    assert report.model_storage_feasible == 2
    assert report.recommended_model == "qwen2.5-7b-instruct-awq"
    assert report.selected_model == "qwen2.5-7b-instruct-awq"
    text = format_deployment_report(report)
    assert "AVAILABLE" in text
    assert "infeasible_storage" in text
    assert "infeasible_vram" in text
    assert report.selection_mode == "auto"


def test_readiness_probe_is_not_counted_as_inference() -> None:
    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    ready = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.INSTANCE,
        event_type=Name("inference.completed"),
        outcome=OperationalOutcome.PASS,
        summary="readiness probe",
        attributes=(attr("latency_ms", 12), attr("purpose", "readiness")),
    )
    request = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT + dt.timedelta(seconds=1),
        stage=OperationalStage.INFERENCE,
        event_type=Name("inference.completed"),
        outcome=OperationalOutcome.PASS,
        summary="inference PASS",
        attributes=(attr("latency_ms", 125), attr("purpose", "request")),
    )
    report = _compose(subject, envelope, (ready, request))
    assert report.latest_inference_latency_ms == 125
    text = format_deployment_report(report)
    assert "INFERENCE 1" in text
    assert "INFERENCE 2" not in text
    assert "125" in text


def test_realize_minimum_is_not_overwritten_by_live_remaining() -> None:
    from kultrun.platform.contracts import MinimumFeasibilityVerdict
    from kultrun.platform.minimum import assess_minimum, destination_pool
    from kultrun.storage.topology import pools_from_host

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(
        subject,
        (
            PoolCapacity(
                mount_point="/workspace",
                space=_layered(4 * GIB),
                requirement=EvidenceRequirement.SUFFICIENT,
                filesystem_type="ext4",
            ),
        ),
    )
    dest = destination_pool(Path("/workspace/app/state"), pools_from_host(subject))
    live = assess_minimum(
        subject,
        destination=dest,
        evidence=None,
        items=(),
        descriptors=(),
        ram_safe_bytes=32 * GIB,
    )
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=subject.host_id,
        occurred_at=INSTANT,
        stage=OperationalStage.FEASIBILITY,
        event_type=Name("minimum.feasibility_completed"),
        outcome=OperationalOutcome.PASS,
        summary="MINIMUM FEASIBILITY PASS",
        attributes=(
            attr("verdict", "pass"),
            attr("potential_safe_bytes", 32 * GIB),
            attr("current_authorizing_bytes", 32 * GIB),
            attr("current_safe_bytes", 27 * GIB),
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
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
        facts=(fact,),
        minimum=live,
    )
    assert report.minimum_source == "realize"
    assert report.minimum is not None
    assert report.minimum.verdict is MinimumFeasibilityVerdict.PASS
    assert report.current_minimum is not None
    assert report.current_minimum.verdict is MinimumFeasibilityVerdict.FAIL
    text = format_deployment_report(report)
    assert "Deployment-time assessment  PASS" in text
    assert "post-install" in text
    assert "potential post-reclaim SAFE is below net new peak" not in text
    assert "minimum_storage" not in text
    assert report.minimum.potential_safe_bytes == 32 * GIB


def test_cleanup_and_funnel_progress_columns() -> None:
    host_id = HostId.generate()
    occupancy = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=host_id,
        occurred_at=now_utc(),
        stage=OperationalStage.STORAGE,
        event_type=Name("storage.occupancy_classified"),
        outcome=OperationalOutcome.INFO,
        summary="17.0 GiB obsolete Kultrun state identified",
    )
    reclaimed = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=host_id,
        occurred_at=now_utc(),
        stage=OperationalStage.STORAGE,
        event_type=Name("storage.reclaim_completed"),
        outcome=OperationalOutcome.PASS,
        summary="Cleanup PASS — 16.8 GiB reclaimed",
    )
    minimum = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=host_id,
        occurred_at=now_utc(),
        stage=OperationalStage.FEASIBILITY,
        event_type=Name("minimum.feasibility_completed"),
        outcome=OperationalOutcome.PASS,
        summary="MINIMUM FEASIBILITY PASS",
    )
    funnel = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=host_id,
        occurred_at=now_utc(),
        stage=OperationalStage.RUNTIME,
        event_type=Name("runtime.funnel_completed"),
        outcome=OperationalOutcome.INFO,
        summary="4 candidates → 1 feasible",
    )
    assert format_progress(occupancy).startswith("[CLEANUP]")
    assert format_progress(reclaimed) == ("[CLEANUP] Cleanup PASS — 16.8 GiB reclaimed")
    assert format_progress(minimum) == "[MINIMUM] MINIMUM FEASIBILITY PASS"
    assert format_progress(funnel) == "[FOUNDATION] 4 candidates → 1 feasible"


def test_sanitize_funnel_fields_and_drops_purpose() -> None:
    fact = OperationalFact(
        fact_id=OperationalFactId.generate(),
        host_id=HostId.generate(),
        occurred_at=now_utc(),
        stage=OperationalStage.RUNTIME,
        event_type=Name("runtime.funnel_completed"),
        outcome=OperationalOutcome.INFO,
        summary="4 candidates → 1 feasible",
        correlation_id="drun_funnel00000000",
        attributes=(
            attr("discovered", 4),
            attr("product_selectable", 2),
            attr("host_compatible", 2),
            attr("executor_compatible", 1),
            attr("capacity_feasible", 1),
            attr("cleanup_lifecycle", True),
            attr("cleanup_capacity", False),
            attr("purpose", "request"),
            attr("mount", "/workspace/customer/models"),
        ),
    )
    record = sanitize_fact(fact)
    encoded = str(to_dict(record))
    assert record.discovered == "4"
    assert record.product_selectable == "2"
    assert record.cleanup_lifecycle == "True"
    assert record.cleanup_capacity == "False"
    assert "customer" not in encoded
    assert "purpose" not in encoded
    assert "request" not in encoded


def test_occupancy_categories_are_mutually_exclusive() -> None:
    from kultrun.storage.contracts import (
        ManagedOccupancyClass,
        ManagedOccupancyItem,
        ManagedResourceType,
        OwnershipId,
    )

    subject = host(memory_total=64 * GIB)
    envelope = _base_envelope(subject, ())
    items = (
        ManagedOccupancyItem(
            ownership_id=OwnershipId.generate(),
            resource_type=ManagedResourceType.MODEL_ARTIFACT,
            occupancy_class=ManagedOccupancyClass.UNKNOWN,
            managed_root="/workspace/prior/models",
            occupied_bytes=5 * GIB,
            mount_point="/workspace",
            quota_identity=NOT_PROVIDED,
            pool_fingerprint=NOT_PROVIDED,
            reason="unproven",
        ),
        ManagedOccupancyItem(
            ownership_id=OwnershipId.generate(),
            resource_type=ManagedResourceType.MODEL_ARTIFACT,
            occupancy_class=ManagedOccupancyClass.RECLAIMABLE,
            managed_root="/workspace/prior/models",
            occupied_bytes=5 * GIB,
            mount_point="/workspace",
            quota_identity=NOT_PROVIDED,
            pool_fingerprint=NOT_PROVIDED,
            reason="inactive owned",
        ),
    )
    report = compose_deployment_report(
        host=subject,
        envelope=envelope,
        composed_at=INSTANT,
        kultrun_build="test-build",
        storage_evidence={},
        empirical={},
        managed={},
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
        occupancy_items=items,
    )
    reclaimable = [
        item for item in report.occupancy if item.occupancy_class == "reclaimable"
    ]
    unknown = [item for item in report.occupancy if item.occupancy_class == "unknown"]
    assert len(reclaimable) == 1
    assert unknown == []
