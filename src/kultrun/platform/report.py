"""Deployment report projection. Facts stay in their owning domains.

The report is not a second source of truth. It is composed from persisted
contracts and live HostCapabilities/CapacityEnvelope so Admin UI, local
analytics, and physical acceptance all read the same product state.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import replace

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.execution.contracts import ExecutorHandle
from kultrun.host.contracts import HostCapabilities
from kultrun.inference.contracts import InferenceInstance
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.planning.contracts import (
    AvailableModelView,
    DeploymentPlan,
    ModelSelection,
)
from kultrun.platform.contracts import (
    DecisionSnapshot,
    DeploymentReport,
    DeploymentReportId,
    DeploymentVerdict,
    InferenceObservation,
    InstanceReport,
    ModelCandidateReport,
    OperationalFact,
    OperationalOutcome,
    OperationalStage,
    ReportLayer,
    RuntimeCandidateReport,
    RuntimeInstallReport,
    StoragePoolReport,
)
from kultrun.platform.observation import attr_value, chronological_facts
from kultrun.resource.contracts import ReservationState, ResourceReservation
from kultrun.runtime.contracts import (
    FoundationSelection,
    FoundationSelectionMode,
    RuntimeCandidate,
    RuntimeInstallation,
    RuntimeProvisioningPlan,
)
from kultrun.storage.contracts import EmpiricalProbeEvidence, StorageCapacityEvidence
from kultrun.storage.remaining import remaining_after_usage


def compose_deployment_report(
    *,
    host: HostCapabilities,
    envelope: CapacityEnvelope,
    composed_at: dt.datetime,
    kultrun_build: str,
    storage_evidence: Mapping[str, StorageCapacityEvidence],
    empirical: Mapping[str, EmpiricalProbeEvidence],
    managed: Mapping[str, int],
    candidates: Sequence[RuntimeCandidate],
    recommended_candidate_id: str | None,
    selection: FoundationSelection | None,
    installations: Sequence[RuntimeInstallation],
    provisioning_plans: Sequence[RuntimeProvisioningPlan],
    profiles: Mapping[str, str],
    available: AvailableModelView | None,
    model_selection: ModelSelection | None,
    deployment_plan: DeploymentPlan | None,
    instances: Sequence[InferenceInstance],
    executions: Sequence[ExecutorHandle],
    facts: Sequence[OperationalFact],
    run_id: str | None = None,
    run_started_at: dt.datetime | None = None,
    reservations: Sequence[ResourceReservation] = (),
) -> DeploymentReport:
    """Project current product state. Does not mutate anything."""
    ordered = chronological_facts(facts)
    env = host.operating_environment
    pools = tuple(
        _pool_row(
            mount=item.mount_point,
            filesystem=(
                item.filesystem_type if is_resolved(item.filesystem_type) else None
            ),
            reported=(
                item.space.reported_bytes
                if is_resolved(item.space.reported_bytes)
                else None
            ),
            trusted=item.requirement.value != "empirical_evidence_needed",
            safe=(
                item.space.safe_bytes if is_resolved(item.space.safe_bytes) else None
            ),
            evidence=storage_evidence.get(item.mount_point),
            empirical_row=empirical.get(item.mount_point),
            managed_bytes=managed.get(item.mount_point),
            facts=ordered,
        )
        for item in envelope.pools
    )
    selected_id = (
        selection.selected_candidate_id
        if selection is not None and is_resolved(selection.selected_candidate_id)
        else None
    )
    if (
        not isinstance(selected_id, str)
        and isinstance(recommended_candidate_id, str)
        and (
            selection is None
            or selection.selection_mode is FoundationSelectionMode.AUTO
        )
    ):
        selected_id = recommended_candidate_id
    runtime_rows = tuple(
        RuntimeCandidateReport(
            candidate_id=item.candidate_id.value,
            runtime=item.runtime.value,
            version=item.version if is_resolved(item.version) else NOT_PROVIDED,
            executor=item.executor.value,
            support_tier=item.support_tier.value,
            compatibility=item.compatibility.value,
            reason_codes=tuple(code.value for code in item.reason_codes),
            recommended=item.candidate_id.value == recommended_candidate_id,
            selected=item.candidate_id.value == selected_id,
        )
        for item in candidates
    )
    plan_by_id = {item.plan_id.value: item for item in provisioning_plans}
    install_rows = tuple(
        _install_row(item, plan_by_id.get(item.plan_id.value), profiles)
        for item in installations
    )
    model_rows, available_names = _model_rows(available)
    inferences = _inference_observations(ordered)
    latest_latency, latest_infer = _latest_inference(ordered)
    verdict, failed_at, reason, next_action = _verdict(
        pools,
        install_rows,
        available_names,
        deployment_plan,
        instances,
        ordered,
    )
    ownership = {
        handle.execution_id.value: handle.ownership.value for handle in executions
    }
    reservation_id, admission_verdict = _admission_view(ordered, reservations)
    catalog_count = (
        available.discovered_count if available is not None else None
    )
    compatible_count = (
        available.compatibility_count if available is not None else None
    )
    available_count = (
        available.available_count if available is not None else None
    )
    report = DeploymentReport(
        report_id=DeploymentReportId.generate(),
        host_id=host.host_id,
        composed_at=composed_at,
        kultrun_build=kultrun_build,
        os_name=env.os_name,
        os_version=env.os_version if is_resolved(env.os_version) else NOT_PROVIDED,
        architecture=env.architecture.value,
        cpu=host.cpu.model_name if is_resolved(host.cpu.model_name) else NOT_PROVIDED,
        ram_total_bytes=(
            host.memory.total_bytes
            if is_resolved(host.memory.total_bytes)
            else NOT_PROVIDED
        ),
        ram_safe_bytes=(
            envelope.memory.safe_bytes
            if is_resolved(envelope.memory.safe_bytes)
            else NOT_PROVIDED
        ),
        accelerators=_accelerator_lines(host, envelope),
        storage_pools=pools,
        runtime_candidates=runtime_rows,
        recommended_runtime=recommended_candidate_id or NOT_PROVIDED,
        selected_runtime=selected_id if isinstance(selected_id, str) else NOT_PROVIDED,
        runtime_installs=install_rows,
        model_candidates=model_rows,
        available_models=available_names,
        recommended_model=_maybe_name(
            model_selection.recommended_logical_name if model_selection else None
        ),
        selected_model=_maybe_name(
            model_selection.selected_logical_name if model_selection else None
        ),
        selection_mode=(
            model_selection.selection_mode.value
            if model_selection is not None
            else NOT_PROVIDED
        ),
        deployment_plan_id=_maybe_name(
            deployment_plan.plan_id if deployment_plan is not None else None
        ),
        plan_storage_pool=_maybe_name(
            deployment_plan.storage_pool_mount if deployment_plan is not None else None
        ),
        plan_ram_bytes=_maybe_int(
            deployment_plan.expected_ram_bytes if deployment_plan is not None else None
        ),
        plan_vram_bytes=_maybe_int(
            deployment_plan.expected_vram_bytes if deployment_plan is not None else None
        ),
        plan_storage_bytes=_maybe_int(
            deployment_plan.expected_storage_bytes
            if deployment_plan is not None
            else None
        ),
        plan_runtime_candidate=_maybe_name(
            deployment_plan.selected_candidate_id
            if deployment_plan is not None
            else None
        ),
        instances=tuple(_instance_row(item, ownership) for item in instances),
        latest_inference_latency_ms=(
            latest_latency if latest_latency is not None else NOT_PROVIDED
        ),
        latest_inference_outcome=(
            latest_infer if latest_infer is not None else NOT_PROVIDED
        ),
        lifecycle=_lifecycle_lines(ordered),
        verdict=verdict,
        failed_at=failed_at if failed_at else NOT_PROVIDED,
        reason=reason if reason else NOT_PROVIDED,
        next_action=next_action if next_action else NOT_PROVIDED,
        run_id=run_id if run_id else NOT_PROVIDED,
        run_started_at=run_started_at if run_started_at else NOT_PROVIDED,
        inferences=inferences,
        reservation_id=reservation_id if reservation_id else NOT_PROVIDED,
        admission_verdict=(
            admission_verdict if admission_verdict else NOT_PROVIDED
        ),
        catalog_count=catalog_count if catalog_count is not None else NOT_PROVIDED,
        compatible_count=(
            compatible_count if compatible_count is not None else NOT_PROVIDED
        ),
        available_count=(
            available_count if available_count is not None else NOT_PROVIDED
        ),
        manual_intervention=_manual_intervention(ordered),
    )
    return replace(
        report,
        layers=_build_layers(report, ordered),
        decisions=_decision_snapshots(report, ordered),
        selected_stack=_selected_stack(report),
    )


def format_deployment_report(
    report: DeploymentReport, *, debug: bool = False
) -> str:
    """Guided human report. One consumer of the structured projection."""
    lines: list[str] = []
    lines.extend(_layer_run(report))
    lines.extend(_layer_host(report))
    lines.extend(_layer_storage(report))
    lines.extend(_layer_foundation(report))
    lines.extend(_layer_runtime(report))
    lines.extend(_layer_models(report))
    lines.extend(_layer_selection(report))
    lines.extend(_layer_plan(report))
    lines.extend(_layer_admission(report))
    lines.extend(_layer_instance(report))
    lines.extend(_layer_outcome(report))
    if debug:
        lines.extend(_debug_appendix(report))
    return "\n".join(lines) + "\n"


def _layer_run(report: DeploymentReport) -> list[str]:
    return [
        "LAYER 0 — RUN",
        "Purpose: identify the deployment journey.",
        *_flow(_layer_named(report, "run")),
        f"  Kultrun          {report.kultrun_build}",
        f"  Deployment Run   {_show(report.run_id)}",
        f"  Started          {_show(report.run_started_at)}",
        f"  Status           {report.verdict.value.upper()}",
        f"  Host             {report.host_id.value}",
        "",
    ]


def _layer_host(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 1 — HOST DISCOVERY",
        "Question: What machine is Kultrun running on?",
        *_flow(_layer_named(report, "host")),
        f"  OS               {report.os_name} {_show(report.os_version)} "
        f"{report.architecture}",
        f"  CPU              {_show(report.cpu)}",
        f"  RAM              total {_bytes(report.ram_total_bytes)}  "
        f"SAFE {_bytes(report.ram_safe_bytes)}",
    ]
    if report.accelerators:
        for line in report.accelerators:
            lines.append(f"  GPU              {line}")
    else:
        lines.append("  GPU              none")
    lines.append(
        "  Host profile is the normalized hardware truth used by "
        "capacity and runtime feasibility."
    )
    lines.append("")
    return lines


def _layer_storage(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 2 — STORAGE & CAPACITY",
        "Question: What storage can Kultrun safely consume?",
        *_flow(_layer_named(report, "storage")),
    ]
    for pool in report.storage_pools:
        lines.extend(_format_pool(pool, debug=False))
    dest = _show(report.plan_storage_pool)
    if dest != "-":
        lines.append(f"  Selected destination  {dest}")
    lines.append("")
    return lines


def _layer_foundation(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 3 — EXECUTION FOUNDATION",
        "Question: Which AI execution foundation can this host support?",
        *_flow(_layer_named(report, "foundation")),
        "  Runtime           Product status    Feasibility    Reason",
    ]
    verified = _foundation_verified(report)
    for item in report.runtime_candidates:
        codes = _human_reason_codes(item, verified)
        reason = ",".join(codes) if codes else "-"
        version = _show(item.version)
        name = item.runtime if version == "-" else f"{item.runtime} {version}"
        mark = ""
        if item.selected:
            mark = "  selected"
        elif item.recommended:
            mark = "  recommended"
        lines.append(
            f"  {name:<18} {item.support_tier.upper():<16} "
            f"{item.compatibility.upper():<14} {reason}{mark}"
        )
    if not report.runtime_candidates:
        lines.append("  none")
    lines.append(f"  Recommended      {_foundation_label(report, recommended=True)}")
    lines.append(f"  Selected        {_foundation_label(report)}")
    mode = _show(report.selection_mode)
    lines.append(f"  Selection mode  {mode.upper() if mode != '-' else '-'}")
    lines.append("")
    return lines


def _layer_runtime(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 4 — RUNTIME ENVIRONMENT",
        "Question: Can the selected runtime actually be installed and verified?",
        *_flow(_layer_named(report, "runtime")),
    ]
    if not report.runtime_installs:
        lines.append("  none")
        lines.append("")
        return lines
    for install in report.runtime_installs:
        lines.append(f"  Runtime          {install.runtime}")
        lines.append(f"  Version          {install.version}")
        lines.append(f"  Destination      {_show(install.storage_pool_mount)}")
        lines.append(f"  Installed        {_bytes(install.installed_bytes)}")
        lines.append(f"  Status          {install.status}")
        lines.append(f"  Verification    {_show(install.verification).upper()}")
        dest = _show(install.storage_pool_mount)
        pool = next(
            (item for item in report.storage_pools if item.mount_point == dest),
            None,
        )
        if (
            pool is not None
            and is_resolved(install.installed_bytes)
            and is_resolved(pool.remaining_bytes)
        ):
            before = pool.remaining_bytes + install.installed_bytes
            lines.append(f"  Before install   {_bytes(before)}")
            lines.append(f"  After install    {_bytes(pool.remaining_bytes)}")
            lines.append(f"  Remaining        {_bytes(pool.remaining_bytes)}")
    lines.append("")
    return lines


def _layer_models(report: DeploymentReport) -> list[str]:
    catalog = _show(report.catalog_count)
    compatible = _show(report.compatible_count)
    available = _show(report.available_count)
    if catalog == "-":
        catalog = str(len(report.model_candidates) or "-")
    if available == "-":
        available = str(len(report.available_models) or 0)
    lines = [
        "LAYER 5 — MODEL FEASIBILITY",
        "Question: Which catalog models can actually run on this foundation and host?",
        *_flow(_layer_named(report, "model_feasibility")),
        f"  Catalog candidates      {catalog}",
        f"  Runtime-compatible      {compatible}",
        f"  Available Models        {available}",
    ]
    for model in report.model_candidates:
        if model.available:
            result = "AVAILABLE"
        else:
            result = f"BLOCKED {_show(model.blocked_reason)}"
        lines.append(
            f"  {model.logical_name} {_show(model.quantization)}  {result}  "
            f"vram {_bytes(model.required_vram_bytes)}  "
            f"storage {_bytes(model.required_storage_bytes)}"
        )
    if not report.model_candidates:
        lines.append("  none")
    lines.append("")
    return lines


def _layer_selection(report: DeploymentReport) -> list[str]:
    mode = _show(report.selection_mode)
    lines = [
        "LAYER 6 — MODEL SELECTION",
        "Question: Which feasible model did Kultrun choose and why?",
        *_flow(_layer_named(report, "model_selection")),
        f"  Mode             {mode.upper() if mode != '-' else '-'}",
        f"  Recommended       {_show(report.recommended_model)}",
        f"  Selected         {_show(report.selected_model)}",
    ]
    for snap in report.decisions:
        if snap.decision == "MODEL_SELECTION" and is_resolved(snap.reason):
            lines.append(f"  Reason           {_show(snap.reason)}")
    lines.append("")
    return lines


def _layer_plan(report: DeploymentReport) -> list[str]:
    return [
        "LAYER 7 — DEPLOYMENT PLAN",
        "Question: Exactly what will Kultrun attempt to run?",
        *_flow(_layer_named(report, "plan")),
        f"  Foundation       {_foundation_label(report)}",
        f"  Model            {_show(report.selected_model)}",
        f"  Storage pool     {_show(report.plan_storage_pool)}",
        f"  RAM              {_bytes(report.plan_ram_bytes)}",
        f"  VRAM             {_bytes(report.plan_vram_bytes)}",
        f"  Storage          {_bytes(report.plan_storage_bytes)}",
        f"  Plan             {_show(report.deployment_plan_id)}",
        "",
    ]


def _layer_admission(report: DeploymentReport) -> list[str]:
    return [
        "LAYER 8 — RESOURCE ADMISSION",
        "Question: Can the machine safely run this configuration right now?",
        *_flow(_layer_named(report, "admission")),
        f"  RAM requested     {_bytes(report.plan_ram_bytes)}",
        f"  VRAM requested    {_bytes(report.plan_vram_bytes)}",
        f"  Storage requested {_show(report.plan_storage_pool)} "
        f"{_bytes(report.plan_storage_bytes)}",
        f"  Decision          {_show(report.admission_verdict).upper()}",
        f"  Reservation       {_show(report.reservation_id)}",
        "",
    ]


def _layer_instance(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 9 — INSTANCE & INFERENCE",
        "Question: Did the planned service actually run?",
        *_flow(_layer_named(report, "instance")),
    ]
    for instance in report.instances:
        lines.append(
            f"  Instance         {instance.lifecycle}/{instance.health}  "
            f"ready {_show(instance.ready)}  own {_show(instance.ownership)}"
        )
    if not report.instances:
        lines.append("  none")
    for index, item in enumerate(report.inferences, start=1):
        lines.append(
            f"  Inference {index}     {_show(item.outcome).upper()}  "
            f"{_show(item.latency_ms)} ms"
        )
        if is_resolved(item.input_tokens) or is_resolved(item.output_tokens):
            lines.append(
                f"                   in {_show(item.input_tokens)}  "
                f"out {_show(item.output_tokens)}"
            )
    if report.lifecycle:
        lines.append("  Lifecycle")
        for event in report.lifecycle:
            lines.append(f"    {event}")
    lines.append(
        "  Physical GPU released after stop and logical reservation "
        "held/released are separate facts."
    )
    lines.append("")
    return lines


def _layer_outcome(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 10 — FINAL OUTCOME",
        "Question: What stack did Kultrun ultimately build, and did it work?",
        *_flow(_layer_named(report, "outcome")),
        "  SELECTED STACK",
        f"  {_show(report.selected_stack)}",
        "",
        f"OVERALL: {report.verdict.value.upper()}",
        f"  Manual intervention  {_show(report.manual_intervention)}",
    ]
    if report.verdict is DeploymentVerdict.FAIL:
        lines.extend(_failure_block(report))
    elif is_resolved(report.next_action) and report.next_action not in {"none", "-"}:
        lines.append(f"  NEXT ACTION          {_show(report.next_action)}")
    return lines


def _failure_block(report: DeploymentReport) -> list[str]:
    layer = _failed_layer_title(report)
    failure, code = _failure_parts(report)
    return [
        "",
        "FAILED LAYER:",
        f"  {layer}",
        "INPUT:",
        f"  {_show(_failure_input(report))}",
        "FAILURE:",
        f"  {failure}",
        "REASON:",
        f"  {code}",
        "LAST VALID OUTPUT:",
        f"  {_last_valid_output(report)}",
        "NEXT REQUIRED ACTION:",
        f"  {_show(report.next_action)}",
    ]


def _failure_parts(report: DeploymentReport) -> tuple[str, str]:
    detail = _show(report.reason)
    if ": " in detail:
        code, _, rest = detail.partition(": ")
        if rest:
            return rest, code
    return detail, _show(report.failed_at)


def _debug_appendix(report: DeploymentReport) -> list[str]:
    lines = ["", "DEBUG EVIDENCE"]
    lines.append(f"  report            {report.report_id.value}")
    lines.append(f"  host             {report.host_id.value}")
    lines.append(f"  recommended id   {_show(report.recommended_runtime)}")
    lines.append(f"  selected id      {_show(report.selected_runtime)}")
    lines.append(f"  plan runtime id  {_show(report.plan_runtime_candidate)}")
    for pool in report.storage_pools:
        lines.append(
            f"  pool {pool.mount_point}  quota {_show(pool.quota_identity)}  "
            f"fingerprint {_show(pool.pool_fingerprint)}"
        )
    for item in report.runtime_candidates:
        codes = ",".join(item.reason_codes) if item.reason_codes else "-"
        lines.append(f"  candidate {item.candidate_id}  {codes}")
    for instance in report.instances:
        lines.append(
            f"  instance {instance.instance_id}  exec {_show(instance.execution_id)}  "
            f"pid {_show(instance.pid)}"
        )
    for snap in report.decisions:
        lines.append(f"  decision {snap.decision}  {_show(snap.selected)}")
    return lines


def _format_pool(pool: StoragePoolReport, *, debug: bool = False) -> list[str]:
    trusted = "trusted" if pool.reported_trusted else "UNTRUSTED"
    lines = [
        f"  Pool  {pool.mount_point}",
        f"    Technology          {_technology(pool.filesystem_type)}",
        f"    Reported free       {_bytes(pool.reported_free_bytes)} [{trusted}]",
        f"    Specialist probe    {_show(pool.specialist_probe)} "
        f"{_show(pool.specialist_result)}",
        "    Sonar:",
    ]
    if pool.sonar_tiers:
        for tier in pool.sonar_tiers:
            lines.append(f"      {tier}")
    else:
        lines.append("      (not run)")
    lines.append(f"    Characterized       {_bytes(pool.authorizing_bytes)}")
    lines.append(f"    SAFE                {_bytes(pool.safe_bytes)}")
    lines.append(f"    Managed by Kultrun  {_bytes(pool.managed_bytes)}")
    lines.append(f"    Remaining           {_bytes(pool.remaining_bytes)}")
    if debug and (
        is_resolved(pool.quota_identity) or is_resolved(pool.pool_fingerprint)
    ):
        lines.append(
            f"    Identity            quota {_show(pool.quota_identity)}  "
            f"fingerprint {_show(pool.pool_fingerprint)}"
        )
    if pool.selected_reason:
        lines.append(f"    Reason             {pool.selected_reason}")
    return lines


def _flow(layer: ReportLayer | None) -> list[str]:
    if layer is None:
        return []
    lines = [f"  Kultrun          {', '.join(layer.kultrun) or '-'}"]
    if layer.inputs:
        lines.append(f"  Input            {'; '.join(layer.inputs)}")
    if layer.process:
        lines.append(f"  Process          {'; '.join(layer.process)}")
    if layer.decision:
        lines.append(f"  Decision         {'; '.join(layer.decision)}")
    if layer.outputs:
        lines.append(f"  Output           {'; '.join(layer.outputs)}")
    if layer.consumed_by:
        lines.append(f"  Next             {'; '.join(layer.consumed_by)}")
    return lines


def _layer_named(report: DeploymentReport, identity: str) -> ReportLayer | None:
    return next((item for item in report.layers if item.identity == identity), None)


def _technology(value: object) -> str:
    token = _show(value)
    if token == "fuse.moosefs":
        return "MooseFS / FUSE"
    if token == "overlay":
        return "overlay"
    return token


def _foundation_verified(report: DeploymentReport) -> bool:
    return any(
        is_resolved(item.verification) and str(item.verification) == "verified"
        for item in report.runtime_installs
    )


def _human_reason_codes(
    item: RuntimeCandidateReport, verified: bool
) -> tuple[str, ...]:
    if item.selected and verified:
        return tuple(
            code
            for code in item.reason_codes
            if code != "required_component_missing"
        )
    return item.reason_codes


def _foundation_label(
    report: DeploymentReport, *, recommended: bool = False
) -> str:
    wanted = (
        _show(report.recommended_runtime)
        if recommended
        else _show(report.selected_runtime)
    )
    for item in report.runtime_candidates:
        matched = (
            item.recommended
            if recommended
            else item.selected or item.candidate_id == wanted
        )
        if not matched:
            continue
        version = _show(item.version)
        if version != "-":
            return f"{item.runtime} {version}"
        return item.runtime
    if not recommended:
        for install in report.runtime_installs:
            return f"{install.runtime} {install.version}"
    return wanted


def _executor_label(report: DeploymentReport) -> str:
    for item in report.runtime_candidates:
        if item.selected:
            if item.executor in {"native-process", "process"}:
                return "Native Process Executor"
            return item.executor
    return "Native Process Executor"


def _gpu_summary(report: DeploymentReport) -> str:
    if not report.accelerators:
        return f"{report.os_name} / {report.architecture}"
    line = report.accelerators[0]
    # "[0] nvidia RTX PRO 4500 31.9 GiB  driver ..."
    body = line.split("] ", 1)[-1]
    model = body.split("  driver", 1)[0].strip()
    return f"{report.os_name} / {model}"


def _selected_stack(report: DeploymentReport) -> str:
    dest = _show(report.plan_storage_pool)
    if dest == "-":
        dest = next((pool.mount_point for pool in report.storage_pools), "-")
    pool = next(
        (item for item in report.storage_pools if item.mount_point == dest),
        None,
    )
    tech = _technology(pool.filesystem_type) if pool is not None else ""
    storage = f"{dest} {tech}".strip() if dest != "-" else "-"
    foundation = _foundation_label(report)
    model = _show(report.selected_model)
    ready = (
        "inference ready"
        if report.verdict is DeploymentVerdict.PASS
        else report.verdict.value
    )
    return (
        f"{_gpu_summary(report)} → {storage} → {foundation} → {model} → "
        f"{_executor_label(report)} → {ready}"
    )


def _admission_view(
    facts: Sequence[OperationalFact],
    reservations: Sequence[ResourceReservation],
) -> tuple[str | None, str | None]:
    held = [
        item
        for item in reservations
        if item.state in {ReservationState.ADMITTED, ReservationState.ACTIVE}
    ]
    reservation_id = held[-1].reservation_id.value if held else None
    verdict = None
    for fact in facts:
        if fact.event_type.value == "resource.admission_completed":
            verdict = fact.summary.replace("admission ", "")
            token = attr_value(fact, "reservation")
            if token:
                reservation_id = token
    if verdict is None and reservation_id is not None:
        verdict = "ADMITTED"
    return reservation_id, verdict


def _manual_intervention(facts: Sequence[OperationalFact]) -> Maybe[str]:
    for fact in facts:
        if "operator reclaim" in fact.summary.lower():
            return fact.summary
    return "NONE"


def _int_attr(fact: OperationalFact, key: str) -> Maybe[int]:
    raw = attr_value(fact, key)
    if raw is None or not raw.isdigit():
        return NOT_PROVIDED
    return int(raw)


def _inference_observations(
    facts: Sequence[OperationalFact],
) -> tuple[InferenceObservation, ...]:
    rows: list[InferenceObservation] = []
    for fact in facts:
        if fact.event_type.value != "inference.completed":
            continue
        finish = attr_value(fact, "finish_reason")
        rows.append(
            InferenceObservation(
                occurred_at=fact.occurred_at,
                outcome=fact.outcome.value,
                latency_ms=_int_attr(fact, "latency_ms"),
                input_tokens=_int_attr(fact, "input_tokens"),
                output_tokens=_int_attr(fact, "output_tokens"),
                finish_reason=finish if finish else NOT_PROVIDED,
            )
        )
    return tuple(rows)


def _decision_snapshots(
    report: DeploymentReport, facts: Sequence[OperationalFact]
) -> tuple[DecisionSnapshot, ...]:
    snaps: list[DecisionSnapshot] = []
    foundation_options = tuple(
        _foundation_option(item) for item in report.runtime_candidates
    )
    if report.runtime_candidates or is_resolved(report.selected_runtime):
        snaps.append(
            DecisionSnapshot(
                decision="FOUNDATION_SELECTION",
                inputs=(f"{len(report.runtime_candidates)} runtime candidates",),
                options=foundation_options,
                selected=_foundation_label(report),
                reason="highest-ranked feasible PRODUCT foundation"
                if is_resolved(report.selected_runtime)
                else NOT_PROVIDED,
                outcome=(
                    "deployment PASS"
                    if report.verdict is DeploymentVerdict.PASS
                    else report.verdict.value
                ),
            )
        )
    if report.model_candidates or is_resolved(report.selected_model):
        options = tuple(
            item.logical_name for item in report.model_candidates if item.available
        )
        snaps.append(
            DecisionSnapshot(
                decision="MODEL_SELECTION",
                inputs=(
                    f"{_show(report.catalog_count)} catalog models",
                    f"{len(report.available_models)} Available Models",
                ),
                options=options,
                selected=_show(report.selected_model)
                if is_resolved(report.selected_model)
                else NOT_PROVIDED,
                reason="highest-ranked model in the current Available Models set"
                if is_resolved(report.selected_model)
                else NOT_PROVIDED,
                outcome=(
                    "inference PASS"
                    if report.verdict is DeploymentVerdict.PASS
                    else report.verdict.value
                ),
            )
        )
    if is_resolved(report.admission_verdict) or is_resolved(report.reservation_id):
        snaps.append(
            DecisionSnapshot(
                decision="RESOURCE_ADMISSION",
                inputs=(
                    f"RAM {_bytes(report.plan_ram_bytes)}",
                    f"VRAM {_bytes(report.plan_vram_bytes)}",
                ),
                options=("admit", "reject"),
                selected=_show(report.reservation_id),
                reason=_show(report.admission_verdict),
                outcome=_show(report.admission_verdict),
            )
        )
    for fact in facts:
        if "replan" in fact.event_type.value:
            snaps.append(
                DecisionSnapshot(
                    decision="REPLAN",
                    inputs=(fact.summary,),
                    options=(),
                    selected=NOT_PROVIDED,
                    reason=fact.reason_code
                    if is_resolved(fact.reason_code)
                    else NOT_PROVIDED,
                    outcome=fact.outcome.value,
                )
            )
    return tuple(snaps)


def _foundation_option(item: RuntimeCandidateReport) -> str:
    version = _show(item.version)
    label = item.runtime if version == "-" else f"{item.runtime} {version}"
    return f"{label} ({item.support_tier}/{item.compatibility})"


def _build_layers(
    report: DeploymentReport, facts: Sequence[OperationalFact]
) -> tuple[ReportLayer, ...]:
    del facts
    host_ready = bool(report.os_name)
    storage_ready = any(
        is_resolved(pool.authorizing_bytes) for pool in report.storage_pools
    )
    foundation_ready = is_resolved(report.selected_runtime)
    runtime_ready = any(item.status == "installed" for item in report.runtime_installs)
    models_ready = bool(report.available_models)
    selected_ready = is_resolved(report.selected_model)
    plan_ready = is_resolved(report.deployment_plan_id)
    admitted = _show(report.admission_verdict).upper() == "ADMITTED"
    inferred = bool(report.inferences)
    return (
        ReportLayer(
            identity="run",
            title="Run",
            purpose="Identify the deployment journey.",
            status=report.verdict.value,
            kultrun=("DeploymentRun", "OperationalFact"),
            inputs=("Kultrun build", "state root"),
            process=("mint or reuse DeploymentRunId",),
            outputs=("DeploymentRunId",),
            consumed_by=("every OperationalFact.correlation_id",),
        ),
        ReportLayer(
            identity="host",
            title="Host Discovery",
            purpose="Normalize what machine Kultrun is running on.",
            status="pass" if host_ready else "incomplete",
            kultrun=("Host Discovery", "HostCapabilities"),
            inputs=("OS, CPU, RAM, accelerators, mounts",),
            process=("discover and normalize",),
            outputs=("HostCapabilityProfile",),
            consumed_by=("capacity", "runtime feasibility"),
        ),
        ReportLayer(
            identity="storage",
            title="Storage & Capacity",
            purpose="Establish authorizing storage, never reported FUSE free space.",
            status="pass" if storage_ready else "incomplete",
            kultrun=("StoragePool", "Storage Sonar", "CapacityEnvelope"),
            inputs=("host mounts",),
            process=("specialist probe", "Sonar", "SAFE remaining"),
            outputs=("StoragePool", "CapacityEnvelope"),
            consumed_by=("foundation selection", "runtime provision"),
        ),
        ReportLayer(
            identity="foundation",
            title="Execution Foundation",
            purpose="Choose which AI execution foundation this host can support.",
            status="pass" if foundation_ready else "incomplete",
            kultrun=("RuntimeResolver", "RuntimeCatalogue", "FoundationSelection"),
            inputs=("HostCapabilityProfile", "CapacityEnvelope"),
            process=("evaluate candidates", "AUTO or MANUAL selection"),
            outputs=("FoundationSelection",),
            consumed_by=("runtime provision",),
        ),
        ReportLayer(
            identity="runtime",
            title="Runtime Environment",
            purpose="Install and verify the selected foundation.",
            status="pass" if runtime_ready else "incomplete",
            kultrun=("RuntimeProvisioningPlan", "RuntimeVerifier"),
            inputs=("FoundationSelection", "StoragePool"),
            process=("provision", "verify"),
            outputs=("VerifiedRuntimeCapabilityProfile",),
            consumed_by=("model feasibility",),
        ),
        ReportLayer(
            identity="model_feasibility",
            title="Model Feasibility",
            purpose="Which catalog models can run on this foundation and host.",
            status="pass" if models_ready else "incomplete",
            kultrun=("ModelCatalog", "ModelEligibility", "Available Models"),
            inputs=("VerifiedRuntimeCapabilityProfile", "current capacity"),
            process=("compatibility then capacity funnel",),
            outputs=("AvailableModels",),
            consumed_by=("model selection",),
        ),
        ReportLayer(
            identity="model_selection",
            title="Model Selection",
            purpose="Choose among only the feasible models.",
            status="pass" if selected_ready else "incomplete",
            kultrun=("ModelSelector", "ModelSelection"),
            inputs=("Available Models",),
            process=("AUTO or MANUAL policy",),
            outputs=("ModelSelection",),
            consumed_by=("deployment plan",),
        ),
        ReportLayer(
            identity="plan",
            title="Deployment Plan",
            purpose="Build the executable configuration.",
            status="pass" if plan_ready else "incomplete",
            kultrun=("DeploymentPlan", "ResourceRequest"),
            inputs=("ModelSelection", "verified runtime"),
            process=("compose authoritative plan",),
            outputs=("DeploymentPlan", "ResourceRequest"),
            consumed_by=("resource admission",),
        ),
        ReportLayer(
            identity="admission",
            title="Resource Admission",
            purpose="Decide whether the machine can run this configuration now.",
            status="pass" if admitted else "incomplete",
            kultrun=("ResourceManager", "ResourceReservation"),
            inputs=("ResourceRequest", "CurrentCapacitySnapshot"),
            process=("admit or reject",),
            outputs=("ResourceReservation",),
            consumed_by=("instance launch",),
        ),
        ReportLayer(
            identity="instance",
            title="Instance & Inference",
            purpose="Run the planned service and prove a request.",
            status="pass" if inferred else "incomplete",
            kultrun=("InferenceInstance", "Executor", "InferenceRuntime"),
            inputs=("DeploymentPlan", "ResourceReservation"),
            process=("start", "infer", "stop", "restart"),
            outputs=("InferenceObservation",),
            consumed_by=("final outcome",),
        ),
        ReportLayer(
            identity="outcome",
            title="Final Outcome",
            purpose="Summarize the stack that was built and whether it worked.",
            status=report.verdict.value,
            kultrun=("DeploymentReport",),
            inputs=("all prior layers",),
            process=("project overall verdict",),
            outputs=("DeploymentVerdict",),
            consumed_by=("Admin UI", "acceptance", "support evidence"),
        ),
    )


def _failed_layer_title(report: DeploymentReport) -> str:
    mapping = {
        "host": "Host Discovery",
        "storage": "Storage & Capacity",
        "probe": "Storage & Capacity",
        "sonar": "Storage & Capacity",
        "runtime": "Execution Foundation",
        "model": "Model Feasibility",
        "plan": "Deployment Plan",
        "admission": "Resource Admission",
        "instance": "Instance & Inference",
        "inference": "Instance & Inference",
        "deployment": "Final Outcome",
    }
    token = _show(report.failed_at)
    return mapping.get(token, token)


def _failure_input(report: DeploymentReport) -> str:
    token = _show(report.failed_at)
    if token == "model":
        return "Verified runtime + current capacity"
    if token in {"runtime", "plan"}:
        return "FoundationSelection + CapacityEnvelope"
    if token == "admission":
        return "DeploymentPlan + CurrentCapacitySnapshot"
    return "previous layer output"


def _last_valid_output(report: DeploymentReport) -> str:
    token = _show(report.failed_at)
    if token == "model":
        return "VerifiedRuntimeCapabilityProfile"
    if token == "admission":
        return "DeploymentPlan"
    if token in {"instance", "inference"}:
        return "ResourceReservation"
    if token == "runtime":
        return "FoundationSelection"
    return "previous successful layer"


def _pool_row(
    *,
    mount: str,
    filesystem: str | None,
    reported: int | None,
    trusted: bool,
    safe: int | None,
    evidence: StorageCapacityEvidence | None,
    empirical_row: EmpiricalProbeEvidence | None,
    managed_bytes: int | None,
    facts: Sequence[OperationalFact],
) -> StoragePoolReport:
    specialist = None
    specialist_result = None
    authorizing = None
    reason = ""
    if evidence is not None:
        specialist = (
            evidence.probe_name if is_resolved(evidence.probe_name) else None
        )
        if evidence.probe_available and not evidence.probe_executed:
            specialist_result = "unavailable"
        elif evidence.probe_executed and is_resolved(evidence.probe_available_bytes):
            specialist_result = "bytes"
        elif evidence.probe_name == "none":
            specialist_result = "unavailable"
        authorizing = (
            evidence.authorizing_available_bytes
            if is_resolved(evidence.authorizing_available_bytes)
            else None
        )
        reason = evidence.selected_reason
    remaining = authorizing
    managed_val = managed_bytes if managed_bytes is not None else None
    if evidence is not None:
        reduced = remaining_after_usage(
            evidence,
            managed_bytes if managed_bytes is not None else NOT_PROVIDED,
        )
        if is_resolved(reduced.authorizing_available_bytes):
            remaining = reduced.authorizing_available_bytes
    return StoragePoolReport(
        mount_point=mount,
        filesystem_type=filesystem if filesystem else NOT_PROVIDED,
        reported_free_bytes=reported if reported is not None else NOT_PROVIDED,
        reported_trusted=trusted,
        specialist_probe=specialist if specialist else NOT_PROVIDED,
        specialist_result=specialist_result if specialist_result else NOT_PROVIDED,
        sonar_tiers=_sonar_lines(mount, empirical_row, facts),
        authorizing_bytes=authorizing if authorizing is not None else NOT_PROVIDED,
        safe_bytes=safe if safe is not None else NOT_PROVIDED,
        managed_bytes=managed_val if managed_val is not None else NOT_PROVIDED,
        remaining_bytes=remaining if remaining is not None else NOT_PROVIDED,
        selected_reason=reason,
        quota_identity=(
            evidence.quota_identity
            if evidence is not None and is_resolved(evidence.quota_identity)
            else NOT_PROVIDED
        ),
        pool_fingerprint=(
            evidence.pool_fingerprint
            if evidence is not None and is_resolved(evidence.pool_fingerprint)
            else NOT_PROVIDED
        ),
    )


def _sonar_lines(
    mount: str,
    empirical: EmpiricalProbeEvidence | None,
    facts: Sequence[OperationalFact],
) -> tuple[str, ...]:
    from_facts = tuple(
        fact.summary
        for fact in facts
        if fact.event_type.value.startswith("storage.sonar")
        and attr_value(fact, "mount") == mount
    )
    if from_facts:
        return from_facts
    if empirical is None:
        return ()
    lines = [f"{tier} GiB PASS" for tier in empirical.completed_tier_units]
    if is_resolved(empirical.failure_code) and empirical.attempted_tier_units:
        failed = empirical.attempted_tier_units[-1]
        if failed not in empirical.completed_tier_units:
            code = str(empirical.failure_code)
            label = "EDQUOT" if "quota" in code else (
                "ENOSPC" if "space" in code else code
            )
            lines.append(f"{failed} GiB {label}")
    return tuple(lines)


def _install_row(
    installation: RuntimeInstallation,
    plan: RuntimeProvisioningPlan | None,
    profiles: Mapping[str, str],
) -> RuntimeInstallReport:
    duration: Maybe[float] = NOT_PROVIDED
    if installation.started_at is not None and installation.completed_at is not None:
        duration = (
            installation.completed_at - installation.started_at
        ).total_seconds()
    mount = plan.storage_mount if plan is not None else NOT_PROVIDED
    return RuntimeInstallReport(
        installation_id=installation.installation_id.value,
        runtime=installation.runtime.value,
        version=installation.runtime_version,
        storage_pool_mount=mount if is_resolved(mount) else NOT_PROVIDED,
        installed_bytes=installation.installed_bytes,
        status=installation.status.value,
        verification=profiles.get(installation.installation_id.value, NOT_PROVIDED),
        duration_seconds=duration,
    )


def _model_rows(
    available: AvailableModelView | None,
) -> tuple[tuple[ModelCandidateReport, ...], tuple[str, ...]]:
    if available is None:
        return (), ()
    members = tuple(
        ModelCandidateReport(
            model_id=item.model_id,
            logical_name=item.logical_name,
            revision=item.source_revision,
            quantization=item.quantization,
            available=True,
            blocked_reason=NOT_PROVIDED,
            required_vram_bytes=item.required_vram_bytes,
            required_ram_bytes=item.required_ram_bytes,
            required_storage_bytes=item.incremental_storage_bytes,
            context_tokens=item.requested_context_tokens,
        )
        for item in available.members
    )
    blocked = tuple(
        ModelCandidateReport(
            model_id=item.model_id,
            logical_name=item.logical_name,
            revision=NOT_PROVIDED,
            quantization=NOT_PROVIDED,
            available=False,
            blocked_reason=item.reason,
            required_vram_bytes=NOT_PROVIDED,
            required_ram_bytes=NOT_PROVIDED,
            required_storage_bytes=NOT_PROVIDED,
            context_tokens=NOT_PROVIDED,
        )
        for item in available.exclusions
    )
    names = tuple(item.logical_name for item in available.members)
    return members + blocked, names


def _instance_row(
    instance: InferenceInstance, ownership: Mapping[str, str]
) -> InstanceReport:
    endpoint: Maybe[str]
    if instance.endpoint is None:
        endpoint = NOT_PROVIDED
    else:
        ep = instance.endpoint
        endpoint = f"{ep.scheme}://{ep.address}:{ep.port}{ep.base_path}"
    exec_id = instance.execution_id.value if instance.execution_id is not None else None
    return InstanceReport(
        instance_id=instance.instance_id.value,
        endpoint=endpoint,
        ready=instance.ready if is_resolved(instance.ready) else NOT_PROVIDED,
        ownership=ownership.get(exec_id, NOT_PROVIDED) if exec_id else NOT_PROVIDED,
        lifecycle=instance.lifecycle_state.value,
        health=instance.health.value,
        execution_id=exec_id if exec_id else NOT_PROVIDED,
        pid=instance.pid if is_resolved(instance.pid) else NOT_PROVIDED,
        observed_state=instance.observed_state.value,
    )


def _accelerator_lines(
    host: HostCapabilities, envelope: CapacityEnvelope
) -> tuple[str, ...]:
    by_index = {item.index: item for item in envelope.accelerators}
    lines: list[str] = []
    for accelerator in host.accelerators:
        cap = by_index.get(accelerator.index)
        vram = (
            cap.memory.safe_bytes
            if cap is not None and is_resolved(cap.memory.safe_bytes)
            else accelerator.memory_total_bytes
        )
        lines.append(
            f"[{accelerator.index}] {accelerator.vendor.value} "
            f"{accelerator.model_name} {_bytes(vram)}  "
            f"driver {_show(accelerator.driver_version)}"
        )
    return tuple(lines)


def _latest_inference(
    facts: Sequence[OperationalFact],
) -> tuple[int | None, str | None]:
    latest = [
        fact
        for fact in facts
        if fact.event_type.value == "inference.completed"
    ]
    if not latest:
        return None, None
    fact = latest[-1]
    latency = None
    for item in fact.attributes:
        if item.startswith("latency_ms="):
            raw = item.split("=", 1)[1]
            if raw.isdigit():
                latency = int(raw)
    return latency, fact.outcome.value


_LIFECYCLE_EVENTS = frozenset(
    {
        "runtime.selected",
        "runtime.verified",
        "model.selected",
        "deployment.plan_created",
        "resource.admission_completed",
        "instance.started",
        "instance.restarted",
        "instance.stopped",
        "instance.created",
        "instance.ready",
        "inference.completed",
    }
)


def _lifecycle_lines(facts: Sequence[OperationalFact]) -> tuple[str, ...]:
    lines: list[str] = []
    for fact in facts:
        if fact.event_type.value not in _LIFECYCLE_EVENTS:
            continue
        stamp = fact.occurred_at.strftime("%H:%M:%SZ")
        lines.append(f"{stamp}  {fact.event_type.value}  {fact.summary}")
    return tuple(lines)


def _verdict(
    pools: Sequence[StoragePoolReport],
    installs: Sequence[RuntimeInstallReport],
    available_names: Sequence[str],
    plan: DeploymentPlan | None,
    instances: Sequence[InferenceInstance],
    facts: Sequence[OperationalFact],
) -> tuple[DeploymentVerdict, str | None, str | None, str | None]:
    failed = [
        fact
        for fact in facts
        if fact.outcome is OperationalOutcome.FAIL
        and fact.stage
        not in {OperationalStage.SONAR, OperationalStage.PROBE}
    ]
    infer_pass = any(
        fact.event_type.value == "inference.completed"
        and fact.outcome is OperationalOutcome.PASS
        for fact in facts
    )
    if infer_pass:
        return (
            DeploymentVerdict.PASS,
            None,
            "inference completed",
            "none",
        )
    if failed:
        last = failed[-1]
        code = last.reason_code if is_resolved(last.reason_code) else None
        detail = (
            f"{code}: {last.summary}" if isinstance(code, str) else last.summary
        )
        return (
            DeploymentVerdict.FAIL,
            last.stage.value,
            detail,
            "fix the failed stage and retry from product commands",
        )
    if instances:
        return (
            DeploymentVerdict.INCOMPLETE,
            None,
            "instance exists; inference not yet recorded",
            "kultrun instances infer",
        )
    if plan is not None:
        return (
            DeploymentVerdict.INCOMPLETE,
            None,
            "deployment plan exists; instance not started",
            "kultrun instances start",
        )
    if available_names:
        return (
            DeploymentVerdict.INCOMPLETE,
            None,
            "Available Models populated; no deployment plan yet",
            "kultrun models select --auto",
        )
    if any(item.status == "installed" for item in installs):
        return (
            DeploymentVerdict.INCOMPLETE,
            None,
            "runtime installed; Available Models not yet populated",
            "kultrun models available",
        )
    if any(is_resolved(pool.authorizing_bytes) for pool in pools):
        return (
            DeploymentVerdict.INCOMPLETE,
            None,
            "storage authorizing capacity exists; runtime not installed",
            "kultrun runtimes realize",
        )
    return (
        DeploymentVerdict.INCOMPLETE,
        None,
        "host discovered; storage and runtime not yet realized",
        "kultrun runtimes realize",
    )


def _maybe_name(value: object) -> Maybe[str]:
    if isinstance(value, str) and value.strip():
        return value
    return NOT_PROVIDED


def _maybe_int(value: object) -> Maybe[int]:
    return value if isinstance(value, int) else NOT_PROVIDED


def _show(value: object) -> str:
    if not is_resolved(value) or value is None:
        return "-"
    return str(value)


def _bytes(value: object) -> str:
    if not is_resolved(value) or not isinstance(value, int):
        return "-"
    if value >= 1024**3:
        return f"{value / 1024**3:.1f} GiB"
    if value >= 1024**2:
        return f"{value / 1024**2:.1f} MiB"
    return f"{value} B"
