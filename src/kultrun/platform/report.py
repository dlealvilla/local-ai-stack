"""Deployment report projection. Facts stay in their owning domains.

The report is not a second source of truth. It is composed from persisted
contracts and live HostCapabilities/CapacityEnvelope so Admin UI, local
analytics, and physical acceptance all read the same product state.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence

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
    DeploymentReport,
    DeploymentReportId,
    DeploymentVerdict,
    InstanceReport,
    ModelCandidateReport,
    OperationalFact,
    OperationalOutcome,
    RuntimeCandidateReport,
    RuntimeInstallReport,
    StoragePoolReport,
)
from kultrun.runtime.contracts import (
    FoundationSelection,
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
) -> DeploymentReport:
    """Project current product state. Does not mutate anything."""
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
            facts=facts,
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
    latest_latency, latest_infer = _latest_inference(facts)
    verdict, failed_at, reason, next_action = _verdict(
        pools,
        install_rows,
        available_names,
        deployment_plan,
        instances,
        facts,
    )
    ownership = {
        handle.execution_id.value: handle.ownership.value for handle in executions
    }
    return DeploymentReport(
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
        instances=tuple(_instance_row(item, ownership) for item in instances),
        latest_inference_latency_ms=(
            latest_latency if latest_latency is not None else NOT_PROVIDED
        ),
        latest_inference_outcome=(
            latest_infer if latest_infer is not None else NOT_PROVIDED
        ),
        verdict=verdict,
        failed_at=failed_at if failed_at else NOT_PROVIDED,
        reason=reason if reason else NOT_PROVIDED,
        next_action=next_action if next_action else NOT_PROVIDED,
    )


def format_deployment_report(report: DeploymentReport) -> str:
    """Human-readable acceptance report. One consumer of the structured report."""
    lines = [
        f"Kultrun deployment report  {report.kultrun_build}",
        f"host {report.host_id.value}  composed {report.composed_at.isoformat()}",
        "",
        "HOST",
        f"  OS            {report.os_name} {_show(report.os_version)} "
        f"{report.architecture}",
        f"  CPU           {_show(report.cpu)}",
        f"  RAM           total {_bytes(report.ram_total_bytes)}  "
        f"safe {_bytes(report.ram_safe_bytes)}",
    ]
    if report.accelerators:
        for line in report.accelerators:
            lines.append(f"  GPU           {line}")
    else:
        lines.append("  GPU           none")
    lines.append("")
    lines.append("STORAGE")
    for pool in report.storage_pools:
        lines.extend(_format_pool(pool))
    lines.extend(["", "RUNTIME CANDIDATES"])
    for item in report.runtime_candidates:
        mark = (
            " selected"
            if item.selected
            else (" recommended" if item.recommended else "")
        )
        codes = ",".join(item.reason_codes) if item.reason_codes else "-"
        lines.append(
            f"  {item.runtime} {_show(item.version)} {item.executor}  "
            f"{item.support_tier}/{item.compatibility}  {codes}{mark}"
        )
    if not report.runtime_candidates:
        lines.append("  none")
    lines.append(f"  recommended   {_show(report.recommended_runtime)}")
    lines.append(f"  selected      {_show(report.selected_runtime)}")
    lines.extend(["", "RUNTIME INSTALLATION"])
    for install in report.runtime_installs:
        lines.append(
            f"  {install.runtime}=={install.version}  {install.status}  "
            f"pool {_show(install.storage_pool_mount)}  "
            f"{_bytes(install.installed_bytes)}  verify {_show(install.verification)}"
        )
    if not report.runtime_installs:
        lines.append("  none")
    lines.extend(["", "MODEL CANDIDATES"])
    for model in report.model_candidates:
        state = (
            "AVAILABLE"
            if model.available
            else f"BLOCKED {_show(model.blocked_reason)}"
        )
        lines.append(
            f"  {model.logical_name} {_show(model.quantization)}  {state}  "
            f"vram {_bytes(model.required_vram_bytes)}  "
            f"ram {_bytes(model.required_ram_bytes)}"
        )
    if not report.model_candidates:
        lines.append("  none")
    lines.append(f"  available     {', '.join(report.available_models) or '-'}")
    lines.append(f"  recommended    {_show(report.recommended_model)}")
    lines.append(
        f"  selected      {_show(report.selected_model)}  "
        f"{_show(report.selection_mode)}"
    )
    lines.extend(["", "DEPLOYMENT"])
    lines.append(f"  plan          {_show(report.deployment_plan_id)}")
    lines.append(f"  storage pool  {_show(report.plan_storage_pool)}")
    lines.append(
        f"  ram {_bytes(report.plan_ram_bytes)}  "
        f"vram {_bytes(report.plan_vram_bytes)}  "
        f"storage {_bytes(report.plan_storage_bytes)}"
    )
    lines.extend(["", "INSTANCE / INFERENCE"])
    for instance in report.instances:
        lines.append(
            f"  {instance.instance_id}  {instance.lifecycle}/{instance.health}  "
            f"ready {_show(instance.ready)}  {_show(instance.endpoint)}  "
            f"own {_show(instance.ownership)}"
        )
    if not report.instances:
        lines.append("  none")
    lines.append(
        f"  last infer    {_show(report.latest_inference_outcome)}  "
        f"{_show(report.latest_inference_latency_ms)} ms"
    )
    lines.extend(
        [
            "",
            "FINAL RESULT",
            f"OVERALL: {report.verdict.value.upper()}",
            f"FAILED AT: {_show(report.failed_at)}",
            f"REASON: {_show(report.reason)}",
            f"NEXT ACTION: {_show(report.next_action)}",
        ]
    )
    return "\n".join(lines) + "\n"


def _format_pool(pool: StoragePoolReport) -> list[str]:
    trusted = "trusted" if pool.reported_trusted else "UNTRUSTED"
    lines = [
        f"  {pool.mount_point}",
        f"    Technology: {_show(pool.filesystem_type)}",
        f"    Reported free: {_bytes(pool.reported_free_bytes)} [{trusted}]",
        f"    Specialist: {_show(pool.specialist_probe)} "
        f"{_show(pool.specialist_result)}",
        "    Sonar:",
    ]
    if pool.sonar_tiers:
        for tier in pool.sonar_tiers:
            lines.append(f"      {tier}")
    else:
        lines.append("      (not run)")
    lines.append(f"    Authorizing: {_bytes(pool.authorizing_bytes)}")
    lines.append(f"    SAFE: {_bytes(pool.safe_bytes)}")
    lines.append(f"    Managed usage: {_bytes(pool.managed_bytes)}")
    lines.append(f"    Remaining proven: {_bytes(pool.remaining_bytes)}")
    if pool.selected_reason:
        lines.append(f"    Reason: {pool.selected_reason}")
    return lines


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
        and any(item.startswith("mount=" + mount) for item in fact.attributes)
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


def _verdict(
    pools: Sequence[StoragePoolReport],
    installs: Sequence[RuntimeInstallReport],
    available_names: Sequence[str],
    plan: DeploymentPlan | None,
    instances: Sequence[InferenceInstance],
    facts: Sequence[OperationalFact],
) -> tuple[DeploymentVerdict, str | None, str | None, str | None]:
    failed = [fact for fact in facts if fact.outcome is OperationalOutcome.FAIL]
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
        return (
            DeploymentVerdict.FAIL,
            last.stage.value,
            last.summary,
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
