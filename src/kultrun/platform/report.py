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
    MinimumFeasibilityAssessment,
    MinimumFeasibilityVerdict,
    ModelCandidateReport,
    OccupancyReport,
    OperationalFact,
    OperationalOutcome,
    OperationalStage,
    ReportLayer,
    RuntimeCandidateReport,
    RuntimeInstallReport,
    StoragePoolReport,
)
from kultrun.platform.minimum import minimum_host_profile
from kultrun.platform.observation import attr_value, chronological_facts
from kultrun.resource.contracts import ReservationState, ResourceReservation
from kultrun.runtime.contracts import (
    FoundationSelection,
    RuntimeCandidate,
    RuntimeInstallation,
    RuntimeProvisioningPlan,
)
from kultrun.storage.contracts import EmpiricalProbeEvidence, StorageCapacityEvidence
from kultrun.storage.remaining import remaining_after_usage
from kultrun.storage.topology import family_of, is_credible_family


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
    intended_storage_pool: str | None = None,
    minimum: MinimumFeasibilityAssessment | None = None,
    occupancy_items: Sequence[object] = (),
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
            trusted=is_credible_family(family_of(item.filesystem_type)),
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
    runtime_rows = tuple(
        RuntimeCandidateReport(
            candidate_id=item.candidate_id.value,
            runtime=item.runtime.value,
            version=item.version if is_resolved(item.version) else NOT_PROVIDED,
            executor=item.executor.value,
            executor_type=item.executor_type.value,
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
    live_minimum = minimum
    gate_minimum = _gate_minimum(live_minimum, ordered)
    verdict, failed_at, reason, next_action = _verdict(
        pools,
        install_rows,
        available_names,
        deployment_plan,
        instances,
        ordered,
        gate_minimum,
    )
    ownership = {
        handle.execution_id.value: handle.ownership.value for handle in executions
    }
    reservation_id, admission_verdict = _admission_view(ordered, reservations)
    catalog_count = available.discovered_count if available is not None else None
    compatible_count = available.compatibility_count if available is not None else None
    available_count = available.available_count if available is not None else None
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
        admission_verdict=(admission_verdict if admission_verdict else NOT_PROVIDED),
        catalog_count=catalog_count if catalog_count is not None else NOT_PROVIDED,
        compatible_count=(
            compatible_count if compatible_count is not None else NOT_PROVIDED
        ),
        available_count=(
            available_count if available_count is not None else NOT_PROVIDED
        ),
        manual_intervention=_manual_intervention(ordered),
        intended_storage_pool=(
            intended_storage_pool if intended_storage_pool else NOT_PROVIDED
        ),
        minimum=gate_minimum,
        current_minimum=live_minimum,
        occupancy=_occupancy_rows(occupancy_items),
        cleanup_required_by_lifecycle=_cleanup_flag(ordered, "cleanup_lifecycle"),
        cleanup_required_for_capacity=_cleanup_flag(ordered, "cleanup_capacity"),
        cleanup_expected_bytes=_fact_int(ordered, "storage.reclaim_planned", "bytes"),
        cleanup_actual_bytes=_fact_int(ordered, "storage.reclaim_completed", "bytes"),
        plan_quantization=_maybe_name(
            deployment_plan.quantization if deployment_plan is not None else None
        ),
        plan_executor=_maybe_name(
            deployment_plan.executor_kind if deployment_plan is not None else None
        ),
        plan_revision=_maybe_name(
            deployment_plan.source_revision if deployment_plan is not None else None
        ),
        plan_context_tokens=_maybe_int(
            deployment_plan.context_tokens if deployment_plan is not None else None
        ),
        runtime_discovered=len(runtime_rows) or NOT_PROVIDED,
        runtime_product_selectable=_funnel_count(
            runtime_rows, _count_tier(runtime_rows, "product")
        ),
        runtime_host_compatible=_funnel_count(
            runtime_rows, _count_host_ok(runtime_rows)
        ),
        runtime_executor_compatible=_funnel_count(
            runtime_rows, _count_executor_ok(runtime_rows)
        ),
        runtime_capacity_feasible=_funnel_count(
            runtime_rows, _count_feasible(runtime_rows)
        ),
        model_policy_compatible=_policy_compatible(available),
        model_storage_feasible=_model_stage_count(available, "infeasible_storage"),
        model_ram_feasible=_model_stage_count(available, "infeasible_ram"),
        model_vram_feasible=_model_stage_count(available, "infeasible_vram"),
        minimum_source=_minimum_source(ordered, live_minimum),
    )
    return replace(
        report,
        layers=_build_layers(report, ordered),
        decisions=_decision_snapshots(report, ordered),
        selected_stack=_selected_stack(report),
    )


def format_deployment_report(report: DeploymentReport, *, debug: bool = False) -> str:
    """Guided human report. One consumer of the structured projection."""
    lines: list[str] = []
    lines.extend(_layer_run(report))
    lines.extend(_layer_host(report))
    lines.extend(_layer_cleanup(report, debug=debug))
    lines.extend(_layer_minimum(report))
    lines.extend(_layer_storage(report))
    lines.extend(_layer_foundation(report))
    lines.extend(_layer_runtime(report))
    lines.extend(_layer_models(report, debug=debug))
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
        "Purpose: What machine is Kultrun operating on?",
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
    dest = _destination_mount(report)
    lines.append(f"  Destination      {dest}")
    lines.append("")
    return lines


def _layer_cleanup(report: DeploymentReport, *, debug: bool) -> list[str]:
    named = _layer_named(report, "cleanup")
    lines = [
        "LAYER 2 — MANAGED-STATE RECONCILIATION",
        "Purpose: What prior Kultrun state exists, what should survive, "
        "and what should be removed?",
        *_flow(named),
        f"  cleanup_required_by_lifecycle   "
        f"{str(report.cleanup_required_by_lifecycle).lower()}",
        f"  cleanup_required_for_capacity   "
        f"{str(report.cleanup_required_for_capacity).lower()}",
        f"  Expected reclaimed               {_bytes(report.cleanup_expected_bytes)}",
        f"  Actual reclaimed                {_bytes(report.cleanup_actual_bytes)}",
        "  Inventory",
    ]
    by_class: dict[str, list[OccupancyReport]] = {
        "active": [],
        "reusable": [],
        "reclaimable": [],
        "protected": [],
        "unknown": [],
    }
    for item in report.occupancy:
        by_class.setdefault(item.occupancy_class, []).append(item)
    labels = (
        ("active", "ACTIVE"),
        ("reusable", "REUSABLE"),
        ("reclaimable", "CLEANUP ELIGIBLE"),
        ("protected", "PROTECTED"),
        ("unknown", "UNKNOWN"),
    )
    for key, title in labels:
        rows = by_class.get(key, [])
        total = sum(item.occupied_bytes for item in rows)
        lines.append(f"    {title:<18} {_bytes(total)}")
        if debug:
            for item in rows:
                lines.append(
                    f"      {item.resource_type} {_bytes(item.occupied_bytes)}  "
                    f"{_show(item.managed_root)}"
                )
    lines.append("")
    return lines


def _layer_minimum(report: DeploymentReport) -> list[str]:
    assessment = report.minimum
    named = _layer_named(report, "minimum")
    purpose = (
        named.purpose
        if named is not None
        else "Determine whether this host can support a minimum Kultrun deployment."
    )
    lines = [
        "LAYER 3 — MINIMUM FEASIBILITY",
        f"Purpose: {purpose}",
        *_flow(named),
    ]
    if assessment is None:
        lines.append("  Status           not assessed")
        lines.append("")
        return lines
    source = _show(report.minimum_source)
    if source == "realize":
        token = assessment.verdict.value.upper()
        lines.append(f"  Deployment-time assessment  {token}")
        if report.current_minimum is not None:
            live = report.current_minimum
            lines.append(
                "  Current remaining SAFE       "
                f"{_bytes(live.current_safe_bytes)}  "
                "(post-install; not a retrospective FAIL)"
            )
    lines.append(f"  Profile          {assessment.profile_version}")
    lines.append(
        f"  OVERALL          {assessment.verdict.value.upper()}"
        + ("  (requires reclamation)" if assessment.requires_reclamation else "")
    )
    dest = _show(assessment.destination_mount)
    if dest == "-":
        dest = _show(report.intended_storage_pool)
    lines.append(f"  Destination      {dest if dest != '-' else 'not selected'}")
    profile = minimum_host_profile()
    ram_ok = (
        is_resolved(report.ram_safe_bytes)
        and report.ram_safe_bytes >= profile.min_ram_safe_bytes
    )
    vram_ok = bool(report.accelerators)
    storage_ok = assessment.verdict is MinimumFeasibilityVerdict.PASS or (
        is_resolved(assessment.potential_safe_bytes)
        and assessment.potential_safe_bytes >= assessment.net_new_bytes
    )
    exec_ok = any(
        item.host_possibility.value == "plausible"
        and item.support_tier.lower() == "product"
        for item in assessment.foundations
    )
    platform_ok = report.os_name in profile.supported_os_families
    arch_ok = report.architecture in profile.supported_architectures
    lines.append("  Checks")
    lines.append("    Requirement        Required       Observed      Result")
    lines.append(
        f"    Platform           {', '.join(profile.supported_os_families):<13} "
        f"{report.os_name:<13} {'PASS' if platform_ok else 'FAIL'}"
    )
    lines.append(
        f"    Architecture       {', '.join(profile.supported_architectures):<13} "
        f"{report.architecture:<13} {'PASS' if arch_ok else 'FAIL'}"
    )
    lines.append(
        f"    RAM                {_bytes(profile.min_ram_safe_bytes):<13} "
        f"{_bytes(report.ram_safe_bytes):<13} {'PASS' if ram_ok else 'FAIL'}"
    )
    gpu = report.accelerators[0] if report.accelerators else "none"
    lines.append(
        f"    Accelerator        {profile.required_accelerator_family:<13} {gpu}"
    )
    lines.append(
        f"    VRAM               {_bytes(profile.min_vram_bytes):<13} "
        f"{'present' if vram_ok else 'none':<13} {'PASS' if vram_ok else 'FAIL'}"
    )
    storage_observed = assessment.current_safe_bytes
    if source == "realize" and is_resolved(assessment.potential_safe_bytes):
        storage_observed = assessment.potential_safe_bytes
    lines.append(
        f"    Storage            {_bytes(profile.min_storage_peak_bytes):<13} "
        f"{_bytes(storage_observed):<13} "
        f"{'PASS' if storage_ok else 'FAIL'}"
    )
    lines.append(
        f"    Execution path     PRODUCT        "
        f"{'available' if exec_ok else 'none':<13} "
        f"{'PASS' if exec_ok else 'FAIL'}"
    )
    lines.append("  Storage")
    lines.append(
        f"    Current authoritative available  "
        f"{_bytes(assessment.current_authorizing_bytes)}"
    )
    lines.append(
        f"    Current SAFE                      {_bytes(assessment.current_safe_bytes)}"
    )
    lines.append("    Kultrun-managed existing state:")
    lines.append(f"      Active                      {_bytes(assessment.active_bytes)}")
    lines.append(
        f"      Reusable                     {_bytes(assessment.reusable_bytes)}"
    )
    lines.append(
        f"      Reclaimable                  {_bytes(assessment.reclaimable_bytes)}"
    )
    lines.append(
        f"      Protected                   {_bytes(assessment.protected_bytes)}"
    )
    lines.append(
        f"      Unknown                      {_bytes(assessment.unknown_bytes)}"
    )
    lines.append(
        f"    Potential post-reclaim authorizing  "
        f"{_bytes(assessment.potential_authorizing_bytes)}"
    )
    lines.append(
        f"    Potential post-reclaim SAFE           "
        f"{_bytes(assessment.potential_safe_bytes)}"
    )
    lines.append(
        f"    Minimum peak requirement            "
        f"{_bytes(assessment.required_peak_bytes)}"
    )
    lines.append(
        f"    Net new requirement                 {_bytes(assessment.net_new_bytes)}"
    )
    if is_resolved(assessment.hard_maximum_bytes):
        lines.append(
            f"    Hard quota                         "
            f"{_bytes(assessment.hard_maximum_bytes)}"
        )
    if assessment.condition:
        lines.append(f"  Condition        {assessment.condition}")
    if is_resolved(assessment.reason_code):
        lines.append(f"  Reason           {_show(assessment.reason_code)}")
    lines.append("  Foundation Possibilities")
    if not assessment.foundations:
        lines.append("    none")
    for item in assessment.foundations:
        host_pos = item.host_possibility.value.replace("_", " ").upper()
        lines.append(f"    {item.family}")
        lines.append(f"      Host          {host_pos}")
        lines.append(f"      Product      {item.support_tier.upper()}")
        if item.reason:
            lines.append(f"      Reason       {item.reason}")
    lines.append("")
    return lines


def _layer_storage(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 4 — STORAGE & CAPACITY",
        "Purpose: What can Kultrun actually consume safely?",
        *_flow(_layer_named(report, "storage")),
    ]
    for pool in report.storage_pools:
        lines.extend(_format_pool(pool, debug=False))
    dest = _destination_mount(report)
    if dest != "not selected":
        lines.append(f"  Intended destination  {dest}")
    lines.append("")
    return lines


def _layer_foundation(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 5 — EXECUTION FOUNDATION",
        "Purpose: Which execution foundations were considered, filtered, "
        "recommended, and selected?",
        *_flow(_layer_named(report, "foundation")),
        f"  Candidates discovered       {_show(report.runtime_discovered)}",
        f"  Product-selectable          {_show(report.runtime_product_selectable)}",
        f"  Host-compatible             {_show(report.runtime_host_compatible)}",
        f"  Executor-compatible         {_show(report.runtime_executor_compatible)}",
        f"  Capacity-feasible           {_show(report.runtime_capacity_feasible)}",
        "  Candidate            Host/Exec     Product    Result",
    ]
    verified = _foundation_verified(report)
    for item in report.runtime_candidates:
        codes = _human_reason_codes(item, verified)
        reason = ",".join(codes)
        executor = _executor_short(item)
        name = f"{item.runtime}/{executor}"
        result = _foundation_result(item)
        mark = ""
        if item.selected:
            mark = "selected"
        elif item.recommended:
            mark = "recommended"
        extra = "  ".join(part for part in (result, reason, mark) if part)
        lines.append(
            f"  {name:<22} {item.compatibility.upper():<12} "
            f"{item.support_tier.upper():<10} {extra}"
        )
    if not report.runtime_candidates:
        lines.append("  none")
    rec = _foundation_label(report, recommended=True)
    sel = _foundation_label(report)
    lines.append(f"  Recommended      {rec if rec != '-' else 'not selected'}")
    lines.append(f"  Selected        {sel if sel != '-' else 'not selected'}")
    mode = _show(report.selection_mode)
    lines.append(f"  Selection mode  {mode.upper() if mode != '-' else '-'}")
    for snap in report.decisions:
        if snap.decision == "FOUNDATION_SELECTION" and is_resolved(snap.reason):
            lines.append(f"  Reason           {_show(snap.reason)}")
    lines.append("")
    return lines


def _layer_runtime(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 6 — RUNTIME ENVIRONMENT",
        "Purpose: Could the selected foundation actually be provisioned and verified?",
        *_flow(_layer_named(report, "runtime")),
    ]
    if not report.runtime_installs:
        lines.append("  none")
        lines.append("")
        return lines
    for install in report.runtime_installs:
        lines.append(f"  Runtime          {install.runtime}")
        lines.append(f"  Version          {install.version}")
        lines.append(f"  Executor         {_executor_label(report)}")
        lines.append(f"  Destination      {_show(install.storage_pool_mount)}")
        if report.minimum is not None:
            lines.append(
                f"  Estimated peak   {_bytes(report.minimum.required_peak_bytes)}"
            )
        lines.append(f"  Installed        {_bytes(install.installed_bytes)}")
        lines.append(f"  Status          {install.status}")
        lines.append(f"  Verification    {_show(install.verification).upper()}")
    lines.append("")
    return lines


def _layer_models(report: DeploymentReport, *, debug: bool = False) -> list[str]:
    catalog = _show(report.catalog_count)
    compatible = _show(report.compatible_count)
    available = _show(report.available_count)
    if catalog == "-":
        catalog = str(len(report.model_candidates) or "-")
    if available == "-":
        available = str(len(report.available_models) or 0)
    lines = [
        "LAYER 7 — MODEL FEASIBILITY",
        "Purpose: How did the catalog become the Available Models set?",
        *_flow(_layer_named(report, "model_feasibility")),
        f"  Catalog discovered         {catalog}",
        f"  Runtime compatible         {compatible}",
        f"  Policy compatible          {_show(report.model_policy_compatible)}",
        f"  Storage feasible           {_show(report.model_storage_feasible)}",
        f"  RAM feasible               {_show(report.model_ram_feasible)}",
        f"  VRAM feasible              {_show(report.model_vram_feasible)}",
        f"  Available Models           {available}",
        "  Model                      Runtime  Storage  Result",
    ]
    shown = 0
    for model in report.model_candidates:
        if not debug and not model.available and not _important_block(model):
            continue
        if model.available:
            result = "AVAILABLE"
        else:
            result = f"BLOCKED {_show(model.blocked_reason)}"
        runtime = "PASS" if model.available or _important_block(model) else "-"
        storage = (
            "FAIL"
            if _show(model.blocked_reason) == "infeasible_storage"
            else ("PASS" if model.available else "-")
        )
        lines.append(f"  {model.logical_name:<26} {runtime:<8} {storage:<8} {result}")
        shown += 1
    if shown == 0:
        lines.append("  none")
    lines.append("")
    return lines


def _layer_selection(report: DeploymentReport) -> list[str]:
    mode = _show(report.selection_mode)
    lines = [
        "LAYER 8 — MODEL SELECTION",
        "Purpose: Which Available Model was chosen and why?",
        *_flow(_layer_named(report, "model_selection")),
        f"  Available               {len(report.available_models)}",
        f"  Recommended             {_show(report.recommended_model)}",
        f"  Selected               {_show(report.selected_model)}",
        f"  Mode                   {mode.upper() if mode != '-' else '-'}",
    ]
    for snap in report.decisions:
        if snap.decision == "MODEL_SELECTION" and is_resolved(snap.reason):
            lines.append(f"  Reason                 {_show(snap.reason)}")
    lines.append("")
    return lines


def _layer_plan(report: DeploymentReport) -> list[str]:
    return [
        "LAYER 9 — DEPLOYMENT PLAN",
        "Purpose: Exactly what configuration will Kultrun attempt to run?",
        *_flow(_layer_named(report, "plan")),
        f"  Runtime           {_foundation_label(report)}",
        f"  Model             {_show(report.selected_model)}",
        f"  Revision          {_show(report.plan_revision)}",
        f"  Quantization      {_show(report.plan_quantization)}",
        f"  Executor          {_show(report.plan_executor)}",
        f"  Storage pool      {_show(report.plan_storage_pool)}",
        f"  Context           {_show(report.plan_context_tokens)}",
        f"  RAM               {_bytes(report.plan_ram_bytes)}",
        f"  VRAM              {_bytes(report.plan_vram_bytes)}",
        f"  Storage           {_bytes(report.plan_storage_bytes)}",
        f"  Plan              {_show(report.deployment_plan_id)}",
        "",
    ]


def _layer_admission(report: DeploymentReport) -> list[str]:
    return [
        "LAYER 10 — RESOURCE ADMISSION",
        "Purpose: Can the physical machine safely admit this DeploymentPlan now?",
        *_flow(_layer_named(report, "admission")),
        f"  RAM requested      {_bytes(report.plan_ram_bytes)}",
        f"  VRAM requested     {_bytes(report.plan_vram_bytes)}",
        f"  Storage requested  {_show(report.plan_storage_pool)} "
        f"{_bytes(report.plan_storage_bytes)}",
        f"  Decision           {_show(report.admission_verdict).upper()}",
        f"  Reservation        {_show(report.reservation_id)}",
        "",
    ]


def _layer_instance(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 11 — INSTANCE & INFERENCE",
        "Purpose: Did the planned service actually execute successfully?",
        *_flow(_layer_named(report, "instance")),
    ]
    for instance in report.instances:
        lines.append(
            f"  Instance         {instance.lifecycle}/"
            f"{_show(instance.observed_state)}  "
            f"ready {_show(instance.ready)}"
        )
    if not report.instances:
        lines.append("  none")
    requests = [
        item
        for item in report.inferences
        if not is_resolved(item.purpose) or str(item.purpose) == "request"
    ]
    for index, item in enumerate(requests, start=1):
        lines.append(f"  INFERENCE {index}")
        lines.append(f"    Result         {_show(item.outcome).upper()}")
        lines.append(f"    Latency        {_show(item.latency_ms)} ms")
        if is_resolved(item.input_tokens) or is_resolved(item.output_tokens):
            lines.append(
                f"    Tokens         in {_show(item.input_tokens)}  "
                f"out {_show(item.output_tokens)}"
            )
        if is_resolved(item.finish_reason):
            lines.append(f"    Finish         {_show(item.finish_reason)}")
    if report.lifecycle:
        lines.append("  Lifecycle")
        for event in report.lifecycle:
            if "inference.completed" in event:
                continue
            lines.append(f"    {event}")
    lines.append("")
    return lines


def _layer_outcome(report: DeploymentReport) -> list[str]:
    lines = [
        "LAYER 12 — FINAL OUTCOME",
        "Purpose: What stack did Kultrun ultimately create, and did the "
        "deployment succeed?",
        *_flow(_layer_named(report, "outcome")),
        "  SELECTED STACK",
        f"  {_show(report.selected_stack)}",
        "",
        f"OVERALL: {report.verdict.value.upper()}",
        f"  Cleanup            {_cleanup_verdict(report)}",
        "  Minimum Feasibility "
        + (report.minimum.verdict.value.upper() if report.minimum is not None else "-"),
        f"  Runtime            {_foundation_label(report)}",
        f"  Model              {_show(report.selected_model)}",
        f"  Admission          {_show(report.admission_verdict).upper()}",
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
    if layer.candidates:
        lines.append(f"  Candidates       {'; '.join(layer.candidates)}")
    if layer.process:
        lines.append(f"  Process          {'; '.join(layer.process)}")
    if layer.decision:
        lines.append(f"  Decision         {'; '.join(layer.decision)}")
    if is_resolved(layer.selected):
        lines.append(f"  Selected         {_show(layer.selected)}")
    if is_resolved(layer.reason):
        lines.append(f"  Why              {_show(layer.reason)}")
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
    if verified:
        return tuple(
            code for code in item.reason_codes if code != "required_component_missing"
        )
    return item.reason_codes


def _foundation_label(report: DeploymentReport, *, recommended: bool = False) -> str:
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
    body = line.split("] ", 1)[-1]
    model = body.split("  physical", 1)[0].strip()
    if "  driver" in model:
        model = model.split("  driver", 1)[0].strip()
    return f"{report.os_name} / {model}"


def _destination_mount(report: DeploymentReport) -> str:
    dest = _show(report.plan_storage_pool)
    if dest != "-":
        return dest
    intended = _show(report.intended_storage_pool)
    if intended != "-":
        return intended
    return "not selected"


def _selected_stack(report: DeploymentReport) -> str:
    dest = _destination_mount(report)
    pool = next(
        (item for item in report.storage_pools if item.mount_point == dest),
        None,
    )
    tech = _technology(pool.filesystem_type) if pool is not None else ""
    storage = f"{dest} {tech}".strip() if dest != "not selected" else "not selected"
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
        purpose = attr_value(fact, "purpose")
        rows.append(
            InferenceObservation(
                occurred_at=fact.occurred_at,
                outcome=fact.outcome.value,
                latency_ms=_int_attr(fact, "latency_ms"),
                input_tokens=_int_attr(fact, "input_tokens"),
                output_tokens=_int_attr(fact, "output_tokens"),
                finish_reason=finish if finish else NOT_PROVIDED,
                purpose=purpose if purpose else NOT_PROVIDED,
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
            consumed_by=("managed-state reconciliation", "minimum feasibility"),
        ),
        ReportLayer(
            identity="cleanup",
            title="Managed-State Reconciliation",
            purpose=(
                "Inventory owned state; retain active/reusable/protected/"
                "unknown; remove cleanup-eligible."
            ),
            status=(
                "pass"
                if is_resolved(report.cleanup_actual_bytes)
                or (
                    not report.cleanup_required_by_lifecycle
                    and not report.cleanup_required_for_capacity
                )
                else ("info" if report.occupancy else "incomplete")
            ),
            kultrun=(
                "OwnershipRecord",
                "ManagedOccupancyItem",
                "StorageReclaimPlan",
            ),
            inputs=("ownership registry", "local markers", "live/reusable roots"),
            process=(
                "classify occupancy",
                "delete cleanup-eligible dual-owned roots",
                "reconcile managed usage",
            ),
            decision=(
                (
                    f"lifecycle={report.cleanup_required_by_lifecycle} "
                    f"capacity={report.cleanup_required_for_capacity}"
                ),
            ),
            outputs=("Reconciled occupancy", "updated managed usage"),
            consumed_by=("minimum feasibility", "storage remaining"),
        ),
        ReportLayer(
            identity="minimum",
            title="Minimum Feasibility",
            purpose=(
                "Determine whether this host can support a minimum Kultrun deployment."
            ),
            status=_minimum_layer_status(report),
            kultrun=(
                "MinimumDeployableHostProfile",
                "MinimumFeasibilityAssessment",
                "CapacityEnvelope",
                "PoolOccupancy",
            ),
            inputs=(
                "HostCapabilityProfile",
                "reconciled occupancy",
                "capacity evidence",
            ),
            process=("strict PASS/FAIL against minimum-host-v1",),
            decision=(
                (
                    report.minimum.verdict.value.upper()
                    if report.minimum is not None
                    else "not assessed"
                ),
            ),
            outputs=("MinimumFeasibilityAssessment", "FoundationPossibility"),
            consumed_by=("Storage & Capacity", "foundation selection"),
            selected=(
                report.minimum.verdict.value.upper()
                if report.minimum is not None
                else NOT_PROVIDED
            ),
        ),
        ReportLayer(
            identity="storage",
            title="Storage & Capacity",
            purpose="Establish authorizing storage, never reported FUSE free space.",
            status="pass" if storage_ready else "incomplete",
            kultrun=("StoragePool", "Storage Sonar", "CapacityEnvelope"),
            inputs=("host mounts", "MinimumFeasibilityAssessment"),
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
            candidates=tuple(
                f"{item.runtime}/{_executor_short(item)}"
                for item in report.runtime_candidates
            ),
            selected=_foundation_label(report)
            if is_resolved(report.selected_runtime)
            else NOT_PROVIDED,
            reason=(
                "highest-ranked feasible PRODUCT foundation"
                if is_resolved(report.selected_runtime)
                else NOT_PROVIDED
            ),
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
            candidates=tuple(
                item.logical_name for item in report.model_candidates if item.available
            ),
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
            selected=_show(report.selected_model)
            if is_resolved(report.selected_model)
            else NOT_PROVIDED,
            reason=(
                "highest-ranked model in the current Available Models set"
                if is_resolved(report.selected_model)
                else NOT_PROVIDED
            ),
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


def _minimum_layer_status(report: DeploymentReport) -> str:
    if report.minimum is None:
        return "incomplete"
    if report.minimum.verdict is MinimumFeasibilityVerdict.FAIL:
        return "fail"
    return "pass"


def _failed_layer_title(report: DeploymentReport) -> str:
    mapping = {
        "host": "Host Discovery",
        "cleanup": "Managed-State Reconciliation",
        "occupancy": "Managed-State Reconciliation",
        "reclaim": "Managed-State Reconciliation",
        "minimum": "Minimum Feasibility",
        "feasibility": "Minimum Feasibility",
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
    if token in {"feasibility", "minimum"}:
        return "HostCapabilities + authorizing storage evidence"
    if token == "model":
        return "Verified runtime + current capacity"
    if token in {"runtime", "plan"}:
        return "FoundationSelection + CapacityEnvelope"
    if token == "admission":
        return "DeploymentPlan + CurrentCapacitySnapshot"
    return "previous layer output"


def _last_valid_output(report: DeploymentReport) -> str:
    token = _show(report.failed_at)
    if token in {"feasibility", "minimum"}:
        return "HostCapabilityProfile"
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
        specialist = evidence.probe_name if is_resolved(evidence.probe_name) else None
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
            label = (
                "EDQUOT" if "quota" in code else ("ENOSPC" if "space" in code else code)
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
        duration = (installation.completed_at - installation.started_at).total_seconds()
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
            funnel_stage="available",
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
            required_vram_bytes=item.required_vram_bytes,
            required_ram_bytes=NOT_PROVIDED,
            required_storage_bytes=item.weight_lower_bound_bytes,
            context_tokens=NOT_PROVIDED,
            funnel_stage=item.stage.value,
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
        physical = accelerator.memory_total_bytes
        safe = (
            cap.memory.safe_bytes
            if cap is not None and is_resolved(cap.memory.safe_bytes)
            else NOT_PROVIDED
        )
        lines.append(
            f"[{accelerator.index}] {accelerator.vendor.value} "
            f"{accelerator.model_name}  physical {_bytes(physical)}  "
            f"SAFE {_bytes(safe)}  driver {_show(accelerator.driver_version)}"
        )
    return tuple(lines)


def _latest_inference(
    facts: Sequence[OperationalFact],
) -> tuple[int | None, str | None]:
    latest = [
        fact
        for fact in facts
        if fact.event_type.value == "inference.completed"
        and _is_request_inference(fact)
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
    minimum: MinimumFeasibilityAssessment | None = None,
) -> tuple[DeploymentVerdict, str | None, str | None, str | None]:
    failed = [
        fact
        for fact in facts
        if fact.outcome is OperationalOutcome.FAIL
        and fact.stage not in {OperationalStage.SONAR, OperationalStage.PROBE}
    ]
    infer_pass = any(
        fact.event_type.value == "inference.completed"
        and fact.outcome is OperationalOutcome.PASS
        and _is_request_inference(fact)
        for fact in facts
    )
    if infer_pass:
        return (
            DeploymentVerdict.PASS,
            None,
            "inference completed",
            "none",
        )
    del minimum
    if failed:
        last = failed[-1]
        code = last.reason_code if is_resolved(last.reason_code) else None
        detail = f"{code}: {last.summary}" if isinstance(code, str) else last.summary
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


_IMPORTANT_MODEL_REASONS = frozenset(
    {
        "infeasible_storage",
        "infeasible_ram",
        "infeasible_vram",
        "infeasible_unified",
        "weights_exceed_available_placement",
        "unsupported_quantization",
        "runtime_incompatible",
    }
)


def _cleanup_verdict(report: DeploymentReport) -> str:
    if is_resolved(report.cleanup_actual_bytes):
        return "PASS"
    if not report.cleanup_required_by_lifecycle:
        return "PASS"
    return "see Layer 2"


def _occupancy_rows(items: Sequence[object]) -> tuple[OccupancyReport, ...]:
    rows: list[OccupancyReport] = []
    seen: dict[str, OccupancyReport] = {}
    priority = {
        "active": 4,
        "reusable": 3,
        "protected": 2,
        "reclaimable": 1,
        "unknown": 0,
    }
    for item in items:
        occupancy = getattr(item, "occupancy_class", "unknown")
        resource = getattr(item, "resource_type", "unknown")
        occupied = getattr(item, "occupied_bytes", 0)
        reason = getattr(item, "reason", "")
        root = getattr(item, "managed_root", NOT_PROVIDED)
        class_token = occupancy.value if hasattr(occupancy, "value") else str(occupancy)
        type_token = resource.value if hasattr(resource, "value") else str(resource)
        row = OccupancyReport(
            occupancy_class=class_token,
            resource_type=type_token,
            occupied_bytes=occupied if isinstance(occupied, int) else 0,
            reason=str(reason),
            managed_root=root if isinstance(root, str) else NOT_PROVIDED,
        )
        key = row.managed_root if isinstance(row.managed_root, str) else row.reason
        existing = seen.get(str(key))
        if existing is None or priority.get(class_token, 0) > priority.get(
            existing.occupancy_class, 0
        ):
            seen[str(key)] = row
    rows.extend(seen.values())
    return tuple(rows)


def _cleanup_flag(facts: Sequence[OperationalFact], key: str) -> bool:
    for fact in reversed(facts):
        raw = attr_value(fact, key)
        if raw is not None:
            return raw.lower() in {"true", "1", "yes"}
    return False


def _fact_int(facts: Sequence[OperationalFact], event: str, key: str) -> Maybe[int]:
    for fact in reversed(facts):
        if fact.event_type.value != event:
            continue
        raw = attr_value(fact, key)
        if raw is None:
            continue
        token = raw.lstrip("-")
        if token.isdigit():
            return int(raw)
    return NOT_PROVIDED


def _funnel_count(rows: Sequence[object], value: int) -> Maybe[int]:
    return value if rows else NOT_PROVIDED


def _count_tier(rows: Sequence[RuntimeCandidateReport], token: str) -> int:
    return sum(1 for item in rows if item.support_tier.lower() == token)


def _count_host_ok(rows: Sequence[RuntimeCandidateReport]) -> int:
    return sum(
        1
        for item in rows
        if "unsupported_platform" not in item.reason_codes
        and "host_os_unsupported" not in item.reason_codes
    )


def _count_executor_ok(rows: Sequence[RuntimeCandidateReport]) -> int:
    return sum(1 for item in rows if "executor_unavailable" not in item.reason_codes)


def _count_feasible(rows: Sequence[RuntimeCandidateReport]) -> int:
    return sum(
        1
        for item in rows
        if item.compatibility.lower() in {"compatible", "conditional"}
    )


def _policy_compatible(available: AvailableModelView | None) -> Maybe[int]:
    if available is None:
        return NOT_PROVIDED
    blocked = sum(1 for item in available.exclusions if item.reason == "policy_blocked")
    return max(0, available.compatibility_count - blocked)


def _model_stage_count(
    available: AvailableModelView | None, blocked_reason: str
) -> Maybe[int]:
    if available is None:
        return NOT_PROVIDED
    members = available.available_count
    if blocked_reason == "infeasible_storage":
        extra = sum(
            1
            for item in available.exclusions
            if item.reason in {"infeasible_ram", "infeasible_vram"}
            or item.stage.value == "runtime_calibration"
        )
        return members + extra
    if blocked_reason == "infeasible_ram":
        extra = sum(
            1
            for item in available.exclusions
            if item.reason == "infeasible_vram"
            or item.stage.value == "runtime_calibration"
        )
        return members + extra
    extra = sum(
        1 for item in available.exclusions if item.stage.value == "runtime_calibration"
    )
    return members + extra


def _minimum_source(
    facts: Sequence[OperationalFact], minimum: MinimumFeasibilityAssessment | None
) -> Maybe[str]:
    for fact in reversed(facts):
        if fact.event_type.value == "minimum.feasibility_completed":
            return "realize"
    if minimum is not None:
        return "live"
    return NOT_PROVIDED


def _gate_minimum(
    live: MinimumFeasibilityAssessment | None, facts: Sequence[OperationalFact]
) -> MinimumFeasibilityAssessment | None:
    if live is None:
        return None
    realized = None
    fact = None
    for item in reversed(facts):
        if item.event_type.value == "minimum.feasibility_completed":
            realized = attr_value(item, "verdict")
            fact = item
            break
    if realized != "pass":
        return live
    failed = live.verdict is MinimumFeasibilityVerdict.FAIL
    gated = replace(
        live,
        verdict=MinimumFeasibilityVerdict.PASS,
        condition="" if failed else live.condition,
        reason_code=NOT_PROVIDED if failed else live.reason_code,
        requires_reclamation=False if failed else live.requires_reclamation,
    )
    if fact is None:
        return gated
    return replace(
        gated,
        current_authorizing_bytes=_overlay_maybe(
            fact, "current_authorizing_bytes", gated.current_authorizing_bytes
        ),
        current_safe_bytes=_overlay_maybe(
            fact, "current_safe_bytes", gated.current_safe_bytes
        ),
        potential_authorizing_bytes=_overlay_maybe(
            fact, "potential_authorizing_bytes", gated.potential_authorizing_bytes
        ),
        potential_safe_bytes=_overlay_maybe(
            fact, "potential_safe_bytes", gated.potential_safe_bytes
        ),
        required_peak_bytes=_overlay_required(
            fact, "required_peak_bytes", gated.required_peak_bytes
        ),
        net_new_bytes=_overlay_required(fact, "net_new_bytes", gated.net_new_bytes),
        reclaimable_bytes=_overlay_required(
            fact, "reclaimable_bytes", gated.reclaimable_bytes
        ),
        reusable_bytes=_overlay_required(fact, "reusable_bytes", gated.reusable_bytes),
        active_bytes=_overlay_required(fact, "active_bytes", gated.active_bytes),
        protected_bytes=_overlay_required(
            fact, "protected_bytes", gated.protected_bytes
        ),
        unknown_bytes=_overlay_required(fact, "unknown_bytes", gated.unknown_bytes),
    )


def _overlay_maybe(
    fact: OperationalFact, field: str, current: Maybe[int]
) -> Maybe[int]:
    parsed = _int_attr(fact, field)
    return parsed if is_resolved(parsed) else current


def _overlay_required(fact: OperationalFact, field: str, current: int) -> int:
    parsed = _int_attr(fact, field)
    return parsed if is_resolved(parsed) else current


def _executor_short(item: RuntimeCandidateReport) -> str:
    token = item.executor
    if token in {"native-process", "process"}:
        return "native-process"
    if "docker" in token or "container" in token:
        return "container"
    extra = _show(item.executor_type)
    if extra in {"process", "native-process"}:
        return "native-process"
    if extra != "-":
        return extra
    return token or "unknown"


def _foundation_result(item: RuntimeCandidateReport) -> str:
    if item.support_tier.lower() != "product":
        if "unsupported_platform" in item.reason_codes:
            return "NOT PLAUSIBLE"
        return "NOT SELECTABLE"
    if item.compatibility in {"compatible", "conditional"}:
        return "FEASIBLE"
    if "unsupported_platform" in item.reason_codes:
        return "NOT PLAUSIBLE"
    return "FILTERED"


def _important_block(model: ModelCandidateReport) -> bool:
    return _show(model.blocked_reason) in _IMPORTANT_MODEL_REASONS


def _is_request_inference(fact: OperationalFact) -> bool:
    purpose = attr_value(fact, "purpose")
    return purpose is None or purpose == "request"
