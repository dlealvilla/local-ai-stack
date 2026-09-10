"""Copy control-plane facts into telemetry contracts.

Platform-owned. Telemetry never imports sqlite. Domain services stay
authoritative; this module observes their outputs.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostCapabilities
from kultrun.inference.contracts import ObservedState
from kultrun.kernel.clock import Clock
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.contracts import ModelRequirement, WeightFootprintEvidence
from kultrun.model.discovery import FunnelQuery
from kultrun.planning.contracts import DeploymentCapacity
from kultrun.platform.available_models import AvailableModelsService, FunnelPass
from kultrun.platform.deployment_instance import DeploymentInstanceService, InstanceView
from kultrun.platform.requirement import RequirementAssessment
from kultrun.resource.contracts import ResourceSummary
from kultrun.runtime.contracts import (
    EligibleModelView,
    FoundationSelection,
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimeMemoryProfile,
)
from kultrun.telemetry.contracts import (
    CapacitySnapshotObservation,
    DeploymentEventObservation,
    DeploymentEventType,
    DeploymentRunKind,
    DeploymentRunObservation,
    HostObservation,
    ModelSizingObservation,
    ObservationId,
    RuntimeMemoryObservation,
    RuntimeObservation,
    TelemetryEventId,
    TelemetryRunId,
)
from kultrun.telemetry.ports import TelemetryRecorder


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _text(value: object) -> str | None:
    if value is None or not is_resolved(value):
        return None
    token = getattr(value, "value", value)
    if token is None:
        return None
    text = str(token)
    return text or None


def _enum(value: object) -> str | None:
    if value is None:
        return None
    token = getattr(value, "value", value)
    return str(token)


def host_observation(
    host: HostCapabilities,
    *,
    observed_at: object,
    duration_ms: int | None = None,
    producer_build_version: str | None = None,
) -> HostObservation:
    """Copy HostCapabilities. Does not rediscover hardware."""
    gpu = host.accelerators[0] if host.accelerators else None
    mount = host.mounts[0] if host.mounts else None
    environment = host.operating_environment
    return HostObservation(
        observation_id=ObservationId.generate(),
        observed_at=observed_at,  # type: ignore[arg-type]
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        duration_ms=duration_ms,
        os_name=environment.os_name,
        os_version=environment.os_version,
        architecture=_enum(environment.architecture),
        cpu_vendor=_text(host.cpu.vendor),
        cpu_model=_text(host.cpu.model_name),
        cpu_physical_cores=_int(host.cpu.physical_cores),
        cpu_logical_cores=_int(host.cpu.logical_cores),
        ram_total_bytes=_int(host.memory.total_bytes),
        ram_available_bytes=_int(host.memory.available_bytes),
        ram_limit_bytes=_int(host.memory.limit_bytes),
        storage_mount_point=mount.mount_point if mount is not None else None,
        storage_total_bytes=_int(mount.total_bytes) if mount is not None else None,
        storage_free_bytes=_int(mount.free_bytes) if mount is not None else None,
        accelerator_count=len(host.accelerators),
        gpu_index=gpu.index if gpu is not None else None,
        gpu_vendor=_enum(gpu.vendor) if gpu is not None else None,
        gpu_model=_text(gpu.model_name) if gpu is not None else None,
        gpu_architecture=None,
        gpu_total_bytes=_int(gpu.memory_total_bytes) if gpu is not None else None,
        driver_version=_text(gpu.driver_version) if gpu is not None else None,
        producer_build_version=producer_build_version,
    )


def runtime_observation(
    *,
    observed_at: object,
    host: HostCapabilities,
    selection: FoundationSelection | None,
    profile: RuntimeCapabilityProfile | None,
    installation: RuntimeInstallation | None,
    duration_ms: int | None = None,
) -> RuntimeObservation | None:
    """Copy foundation / verification facts when any exist."""
    if selection is None and profile is None and installation is None:
        return None
    source = profile or installation
    return RuntimeObservation(
        observation_id=ObservationId.generate(),
        observed_at=observed_at,  # type: ignore[arg-type]
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        duration_ms=duration_ms,
        foundation_id=_text(selection.selection_id) if selection is not None else None,
        selection_mode=(
            _enum(selection.selection_mode) if selection is not None else None
        ),
        runtime=_text(getattr(source, "runtime", None)),
        runtime_version=_text(getattr(source, "runtime_version", None)),
        executor=_text(getattr(source, "executor", None)),
        installation_id=_text(getattr(source, "installation_id", None)),
        capability_profile_id=(
            _text(profile.profile_id) if profile is not None else None
        ),
        verification_status=_enum(profile.status) if profile is not None else None,
        foundation_role="selected_foundation" if selection is not None else None,
    )


def capacity_snapshot_observation(
    snapshot: ResourceSummary,
    *,
    observed_at: object,
    accelerator_index: int | None = None,
) -> CapacitySnapshotObservation:
    """Copy ResourceSummary. Does not recompute SAFE or available."""
    device = None
    if snapshot.accelerators:
        if accelerator_index is not None:
            device = next(
                (
                    item
                    for item in snapshot.accelerators
                    if item.index == accelerator_index
                ),
                snapshot.accelerators[0],
            )
        else:
            device = snapshot.accelerators[0]
    when = snapshot.observed_at or observed_at
    return CapacitySnapshotObservation(
        snapshot_id=ObservationId.generate(),
        observed_at=when,  # type: ignore[arg-type]
        host_id=snapshot.host_id,
        host_fingerprint=snapshot.host_fingerprint,
        safe_vram_bytes=_int(device.safe_bytes) if device is not None else None,
        committed_vram_bytes=device.reserved_bytes if device is not None else None,
        available_vram_bytes=(
            _int(device.available_bytes) if device is not None else None
        ),
        safe_ram_bytes=_int(snapshot.safe_ram_bytes),
        committed_ram_bytes=snapshot.reserved_ram_bytes,
        available_ram_bytes=_int(snapshot.available_ram_bytes),
        available_storage_bytes=_int(snapshot.available_storage_bytes),
        active_reservation_count=snapshot.active_count,
        basis_fingerprint=snapshot.snapshot_basis or None,
        accelerator_index=device.index if device is not None else accelerator_index,
    )


def model_sizing_observation(
    assessment: RequirementAssessment,
    *,
    observed_at: object,
    duration_ms: int | None = None,
    evidence: WeightFootprintEvidence | None = None,
) -> ModelSizingObservation:
    """Copy one candidate's requirement and factual weight evidence."""
    requirement = assessment.requirement
    return ModelSizingObservation(
        observation_id=ObservationId.generate(),
        observed_at=observed_at,  # type: ignore[arg-type]
        duration_ms=duration_ms,
        model_id=assessment.model_id,
        source_model_ref=assessment.source_ref,
        revision=_text(assessment.source_revision),
        architecture=None,
        quantization=None,
        runtime=assessment.runtime,
        runtime_version=assessment.runtime_version,
        requested_context=_int(
            requirement.assumed_context_tokens if requirement is not None else None
        ),
        concurrency=_int(
            requirement.assumed_batch_size if requirement is not None else None
        ),
        factual_weight_bytes=_int(
            evidence.serialized_weight_tensor_bytes if evidence is not None else None
        ),
        estimator_mode=_text(
            requirement.estimator_mode if requirement is not None else None
        ),
        estimator_provider=_text(
            requirement.estimator_provider if requirement is not None else None
        ),
        estimator_version=_text(
            requirement.estimator_version if requirement is not None else None
        ),
        estimated_minimum_vram_bytes=None,
        estimated_recommended_vram_bytes=None,
        estimated_kv_bytes=_requirement_kv(requirement),
        estimated_runtime_overhead_bytes=_int(
            requirement.vram_overhead_bytes if requirement is not None else None
        ),
        estimated_final_requirement_bytes=_int(
            requirement.estimated_vram_bytes if requirement is not None else None
        ),
        required_ram_bytes=_int(assessment.required_ram_bytes),
        required_storage_bytes=_int(assessment.incremental_storage_bytes),
        confidence=_enum(requirement.confidence) if requirement is not None else None,
        cheap_filter_result=_cheap_result(assessment),
        deep_feasibility_result=assessment.capacity_verdict or None,
        capacity_basis=assessment.snapshot_basis,
    )


def runtime_memory_observation(
    profile: RuntimeMemoryProfile,
    *,
    gpu_model: str | None = None,
    gpu_architecture: str | None = None,
    factual_weight_bytes: int | None = None,
    calibrated_required_vram_bytes: int | None = None,
    measurement_quality: str | None = None,
) -> RuntimeMemoryObservation:
    """Copy an operational profile. Planning still owns the original."""
    return RuntimeMemoryObservation(
        observation_id=ObservationId.generate(),
        measured_at=profile.measured_at,
        profile_id=profile.profile_id.value,
        model_id=profile.source_model_id,
        revision=_text(profile.source_revision),
        architecture=_text(profile.model_architecture),
        quantization=_text(profile.quantization),
        host_id=profile.host_id,
        host_fingerprint=profile.host_fingerprint,
        gpu_model=gpu_model,
        gpu_architecture=gpu_architecture,
        runtime=profile.runtime,
        runtime_version=_text(profile.runtime_version),
        capability_profile_id=_text(profile.capability_profile_id),
        context_tokens=_int(profile.context_tokens),
        concurrency=_int(profile.concurrency),
        probe_budget_bytes=_int(profile.probe_budget_bytes),
        factual_weight_bytes=factual_weight_bytes
        if factual_weight_bytes is not None
        else _int(profile.static_weight_component),
        estimated_static_requirement_bytes=_int(profile.static_requirement_bytes),
        estimated_kv_bytes=_int(profile.static_kv_component),
        measured_model_load_bytes=_int(profile.vllm_model_load_bytes),
        measured_available_kv_bytes=_int(profile.vllm_available_kv_bytes),
        measured_peak_gpu_bytes=None,
        derived_non_kv_bytes=_int(profile.derived_non_kv_bytes),
        derived_runtime_extra_bytes=_int(profile.derived_runtime_extra_bytes),
        calibrated_required_vram_bytes=calibrated_required_vram_bytes,
        profile_status=_enum(profile.status),
        confidence=_enum(profile.confidence),
        measurement_quality=measurement_quality,
        failure_reason=_text(profile.failure_reason),
        class_key=profile.class_key,
        basis_fingerprint=profile.basis_fingerprint,
    )


def record_startup(
    recorder: TelemetryRecorder,
    *,
    clock: Clock,
    host: HostCapabilities,
    snapshot: ResourceSummary,
    selection: FoundationSelection | None,
    profile: RuntimeCapabilityProfile | None,
    installation: RuntimeInstallation | None,
    producer_build_version: str | None,
    capacity: DeploymentCapacity | None = None,
) -> None:
    """Host, runtime, and current-capacity copies after composition startup."""
    now = clock.now()
    recorder.record_host_observation(
        host_observation(
            host,
            observed_at=now,
            producer_build_version=producer_build_version,
        )
    )
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=DeploymentEventType.HOST_DISCOVERY_COMPLETED,
            status="observed",
        )
    )
    runtime = runtime_observation(
        observed_at=now,
        host=host,
        selection=selection,
        profile=profile,
        installation=installation,
    )
    if runtime is not None:
        recorder.record_runtime_observation(runtime)
        recorder.record_deployment_event(
            DeploymentEventObservation(
                event_id=TelemetryEventId.generate(),
                occurred_at=now,
                event_type=DeploymentEventType.FOUNDATION_SELECTED
                if selection is not None
                else DeploymentEventType.RUNTIME_VERIFIED,
                status=runtime.verification_status or "observed",
            )
        )
    index = capacity.accelerator_index if capacity is not None else None
    recorder.record_capacity_snapshot(
        capacity_snapshot_observation(
            snapshot, observed_at=now, accelerator_index=index
        )
    )


def record_funnel(
    recorder: TelemetryRecorder,
    *,
    clock: Clock,
    host: HostCapabilities,
    result: FunnelPass,
    duration_ms: int | None,
    profiles: Sequence[RuntimeMemoryProfile] = (),
) -> None:
    """Sizing, capacity, memory-profile copies, and funnel milestones."""
    now = clock.now()
    evidence_by_model = {
        item.evidence.model_id.value: item.evidence
        for item in result.estimated_feasible
    }
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=DeploymentEventType.MODEL_DISCOVERY_COMPLETED,
            status="observed",
            duration_ms=duration_ms,
        )
    )
    for assessment in result.assessments:
        recorder.record_model_sizing(
            model_sizing_observation(
                assessment,
                observed_at=now,
                duration_ms=duration_ms,
                evidence=evidence_by_model.get(assessment.model_id),
            )
        )
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=DeploymentEventType.MODEL_SIZING_COMPLETED,
            status="observed",
            duration_ms=duration_ms,
        )
    )
    recorder.record_capacity_snapshot(
        planning_capacity_observation(result.capacity, observed_at=now)
    )
    calibrated = {
        item.model_id: _int(item.requirement.estimated_vram_bytes)
        for item in (result.validation.applied if result.validation is not None else ())
    }
    gpu = host.accelerators[0] if host.accelerators else None
    gpu_model = _text(gpu.model_name) if gpu is not None else None
    for profile in profiles:
        recorder.record_runtime_memory_profile(
            runtime_memory_observation(
                profile,
                gpu_model=gpu_model,
                calibrated_required_vram_bytes=calibrated.get(profile.source_model_id),
                measurement_quality=_quality(profile),
            )
        )
    if result.validation is not None and result.validation.probe_invocations:
        _record_probe_events(recorder, clock, result, duration_ms)
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=DeploymentEventType.AVAILABLE_MODELS_COMPUTED,
            status=_enum(result.available.status),
            duration_ms=duration_ms,
        )
    )


def _observe(action: Callable[[], None]) -> None:
    """Swallow observation failures. Domain results stay authoritative."""
    try:
        action()
    except Exception:
        return


def bind_available_models(
    service: AvailableModelsService,
    recorder: TelemetryRecorder,
    clock: Clock,
    profiles_for: object,
) -> AvailableModelsService:
    """Record persist=True funnel evaluations. GET revalidation is silent."""
    original = service.evaluate

    def evaluate(
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        *,
        persist: bool = False,
        query: FunnelQuery | None = None,
    ) -> FunnelPass:
        started = time.perf_counter()
        result = original(
            host, eligible, envelope, capacity, persist=persist, query=query
        )
        if persist:

            def _record() -> None:
                elapsed = int((time.perf_counter() - started) * 1000)
                found = profiles_for(result) if callable(profiles_for) else ()
                record_funnel(
                    recorder,
                    clock=clock,
                    host=host,
                    result=result,
                    duration_ms=elapsed,
                    profiles=found,
                )

            _observe(_record)
        return result

    service.evaluate = evaluate  # type: ignore[method-assign]
    return service


def bind_deployment_instance(
    service: DeploymentInstanceService,
    recorder: TelemetryRecorder,
    clock: Clock,
) -> DeploymentInstanceService:
    """Time start/stop without changing instance semantics."""
    original_start = service.start
    original_stop = service.stop

    def start(
        instance_id: object,
        host: HostCapabilities,
        *,
        ledger_health: object,
        serving_mode: str = "healthy",
    ) -> InstanceView:
        run_id = TelemetryRunId.generate()
        started_at = clock.now()
        started = time.perf_counter()
        _observe(
            lambda: recorder.start_deployment_run(
                DeploymentRunObservation(
                    deployment_run_id=run_id,
                    started_at=started_at,
                    run_kind=DeploymentRunKind.DEPLOYMENT,
                    host_id=host.host_id,
                    instance_id=_text(instance_id),
                    state="started",
                )
            )
        )
        _observe(
            lambda: recorder.record_deployment_event(
                DeploymentEventObservation(
                    event_id=TelemetryEventId.generate(),
                    occurred_at=started_at,
                    event_type=DeploymentEventType.RUNTIME_LAUNCH_STARTED,
                    correlation_id=run_id.value,
                    status="started",
                )
            )
        )
        try:
            view = original_start(
                instance_id,  # type: ignore[arg-type]
                host,
                ledger_health=ledger_health,  # type: ignore[arg-type]
                serving_mode=serving_mode,
            )
        except Exception as error:
            elapsed = int((time.perf_counter() - started) * 1000)
            reason = _failure_code(error)
            _observe(
                lambda: recorder.record_deployment_event(
                    DeploymentEventObservation(
                        event_id=TelemetryEventId.generate(),
                        occurred_at=clock.now(),
                        event_type=DeploymentEventType.RUNTIME_FAILED,
                        correlation_id=run_id.value,
                        status="failed",
                        duration_ms=elapsed,
                    )
                )
            )
            _observe(
                lambda: recorder.finish_deployment_run(
                    DeploymentRunObservation(
                        deployment_run_id=run_id,
                        started_at=started_at,
                        ended_at=clock.now(),
                        duration_ms=elapsed,
                        host_id=host.host_id,
                        instance_id=_text(instance_id),
                        state="failed",
                        failure_reason_code=reason,
                    )
                )
            )
            raise
        try:
            return _finish_start(recorder, clock, run_id, started_at, started, view)
        except Exception:
            return view

    def stop(instance_id: object, host: HostCapabilities) -> InstanceView:
        started = time.perf_counter()
        view = original_stop(instance_id, host)  # type: ignore[arg-type]
        elapsed = int((time.perf_counter() - started) * 1000)
        _observe(
            lambda: recorder.record_deployment_event(
                DeploymentEventObservation(
                    event_id=TelemetryEventId.generate(),
                    occurred_at=clock.now(),
                    event_type=DeploymentEventType.INFERENCE_INSTANCE_STOPPED,
                    correlation_id=_text(instance_id),
                    status=_enum(view.instance.observed_state),
                    duration_ms=elapsed,
                )
            )
        )
        return view

    service.start = start  # type: ignore[method-assign]
    service.stop = stop  # type: ignore[method-assign]
    return service


def _finish_start(
    recorder: TelemetryRecorder,
    clock: Clock,
    run_id: TelemetryRunId,
    started_at: object,
    started: float,
    view: InstanceView,
) -> InstanceView:
    elapsed = int((time.perf_counter() - started) * 1000)
    instance = view.instance
    ready = instance.observed_state is ObservedState.RUNNING and (
        not is_resolved(instance.ready) or instance.ready is True
    )
    event = (
        DeploymentEventType.RUNTIME_READY
        if ready
        else DeploymentEventType.RUNTIME_FAILED
    )
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=clock.now(),
            event_type=event,
            correlation_id=run_id.value,
            status=_enum(instance.observed_state),
            duration_ms=elapsed,
        )
    )
    recorder.finish_deployment_run(
        DeploymentRunObservation(
            deployment_run_id=run_id,
            started_at=started_at,  # type: ignore[arg-type]
            ended_at=clock.now(),
            duration_ms=elapsed,
            host_id=instance.host_id,
            selected_model=_text(instance.model_id),
            selected_revision=_text(instance.model_revision),
            runtime=_text(instance.runtime),
            executor=_text(instance.executor),
            plan_id=_text(instance.plan_id),
            artifact_id=_text(instance.artifact_id),
            reservation_id=_text(instance.reservation_id),
            instance_id=instance.instance_id.value,
            state=_enum(instance.observed_state),
            failure_reason_code=_text(instance.failure_reason),
        )
    )
    return view


def _record_probe_events(
    recorder: TelemetryRecorder,
    clock: Clock,
    result: FunnelPass,
    duration_ms: int | None,
) -> None:
    run_id = TelemetryRunId.generate()
    now = clock.now()
    failed = any(
        item.unresolved_reason
        for item in result.validation.classes  # type: ignore[union-attr]
    )
    recorder.start_deployment_run(
        DeploymentRunObservation(
            deployment_run_id=run_id,
            started_at=now,
            run_kind=DeploymentRunKind.RUNTIME_MEMORY_PROBE,
            ended_at=now,
            duration_ms=duration_ms,
            state="failed" if failed else "completed",
        )
    )
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=DeploymentEventType.RUNTIME_MEMORY_PROBE_STARTED,
            correlation_id=run_id.value,
            status="started",
        )
    )
    recorder.record_deployment_event(
        DeploymentEventObservation(
            event_id=TelemetryEventId.generate(),
            occurred_at=now,
            event_type=(
                DeploymentEventType.RUNTIME_MEMORY_PROBE_FAILED
                if failed
                else DeploymentEventType.RUNTIME_MEMORY_PROBE_COMPLETED
            ),
            correlation_id=run_id.value,
            status="failed" if failed else "completed",
            duration_ms=duration_ms,
        )
    )
    recorder.finish_deployment_run(
        DeploymentRunObservation(
            deployment_run_id=run_id,
            started_at=now,
            run_kind=DeploymentRunKind.RUNTIME_MEMORY_PROBE,
            ended_at=now,
            duration_ms=duration_ms,
            state="failed" if failed else "completed",
        )
    )


def _requirement_kv(requirement: ModelRequirement | None) -> int | None:
    if requirement is None:
        return None
    cached = _int(requirement.vram_kv_cache_bytes)
    if cached is not None:
        return cached
    return _int(requirement.vram_kv_bytes_per_token)


def _cheap_result(assessment: RequirementAssessment) -> str | None:
    for code in assessment.reasons:
        if "weight" in code or code.endswith("impossible"):
            return code
    return None


def _quality(profile: RuntimeMemoryProfile) -> str:
    if _int(profile.vllm_available_kv_bytes) is not None:
        available = _int(profile.vllm_available_kv_bytes)
        if available is not None and available < 0:
            return "negative_available_kv"
    return _enum(profile.status) or "observed"


def _failure_code(error: BaseException) -> str:
    reason = getattr(error, "reason", None)
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    return type(error).__name__


def planning_capacity_observation(
    capacity: DeploymentCapacity,
    *,
    observed_at: object,
) -> CapacitySnapshotObservation:
    """Copy DeploymentCapacity fields only. Does not derive committed bytes."""
    return CapacitySnapshotObservation(
        snapshot_id=ObservationId.generate(),
        observed_at=observed_at,  # type: ignore[arg-type]
        host_id=capacity.host_id,
        host_fingerprint=capacity.host_fingerprint,
        safe_vram_bytes=_int(capacity.safe_vram_bytes),
        committed_vram_bytes=None,
        available_vram_bytes=_int(capacity.available_vram_bytes),
        safe_ram_bytes=_int(capacity.safe_ram_bytes),
        committed_ram_bytes=None,
        available_ram_bytes=_int(capacity.available_ram_bytes),
        available_storage_bytes=_int(capacity.available_storage_bytes),
        active_reservation_count=None,
        basis_fingerprint=_text(capacity.snapshot_basis),
        accelerator_index=capacity.accelerator_index,
    )
