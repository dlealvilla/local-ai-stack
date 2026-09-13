"""Bounded highest-pressure runtime-memory calibration.

Composition-owned. Core owns the profile; the vLLM adapter owns log
interpretation; ResourceManager admits a temporary probe reservation;
Executor owns process lifecycle. Not InferenceInstance and not a
benchmarking platform.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.evidence.contracts import Confidence
from kultrun.execution.contracts import ExecutionState
from kultrun.execution.service import ExecutionService
from kultrun.host.contracts import HostCapabilities
from kultrun.inference.endpoint import LOOPBACK, allocate_loopback_port
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.model.acquisition import AcquisitionService, request_from_entry
from kultrun.model.contracts import (
    ArtifactState,
    MemoryPlacement,
    ModelArtifact,
    ModelCatalogEntry,
    ModelRequirement,
    WeightFootprintEvidence,
)
from kultrun.model.inventory import ModelInventory
from kultrun.planning.contracts import DeploymentCapacity
from kultrun.platform.launch import executor_spec_from
from kultrun.resource.contracts import (
    AdmissionVerdict,
    RequestId,
    ResourceRequest,
    WorkloadType,
)
from kultrun.resource.manager import ResourceManager
from kultrun.runtime.contracts import (
    EligibleModelView,
    InstallationStatus,
    RuntimeInstallation,
    RuntimeInstallationId,
    RuntimeLaunchRequest,
    RuntimeMemoryProfile,
    RuntimeMemoryProfileId,
    RuntimeMemoryProfileStatus,
    RuntimeValidationStatus,
)
from kultrun.runtime.memory import (
    PressureMember,
    RuntimeMemoryClassKey,
    base_model_memory,
    calibrated_runtime_extra,
    compose_serving_vram,
    is_vllm_family,
    measured_non_kv_bytes,
    probe_order,
    raise_only,
    runtime_extra_bytes,
    runtime_extra_ratio,
    runtime_memory_class,
    select_sentinel,
    vram_pressure,
)
from kultrun.runtime.ports import (
    InferenceRuntime,
    InterpretedRuntimeMemory,
    RuntimeMemoryInterpreter,
)
from kultrun.runtime.provision import ProvisioningService
from kultrun.storage.topology import mount_for_path

PROBE_TIMEOUT_SECONDS = 1800.0
PROBE_POLL_SECONDS = 0.2
PROBE_OUTPUT_LIMIT_BYTES = 512 * 1024
VALIDATION_UNRESOLVED = "validation_unresolved"
CALIBRATED_INSUFFICIENT_VRAM = "calibrated_insufficient_vram"
PROFILE_SCHEMA = "runtime.memory_profile@1"


@dataclass(frozen=True, slots=True)
class EstimatedFeasibleCandidate:
    """Static-feasible candidate. Does not authorize AVAILABLE."""

    model_id: str
    logical_name: str
    entry: ModelCatalogEntry
    requirement: ModelRequirement
    evidence: WeightFootprintEvidence


@dataclass(frozen=True, slots=True)
class AppliedCalibration:
    """Final components after a profile is applied. Never lowers static total."""

    model_id: str
    requirement: ModelRequirement
    status: RuntimeValidationStatus
    profile_id: str | None
    sentinel_model_id: str | None
    class_key: str
    base_model_bytes: int
    runtime_extra_bytes: int
    kv_bytes: int
    safety_bytes: int
    unexpected_lowering: bool
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClassValidationRow:
    """One validation class for CLI/API provenance. Not a dashboard."""

    class_key: str
    sentinel_model_id: str
    member_ids: tuple[str, ...]
    pressures: tuple[tuple[str, float, int], ...]
    profile_status: str
    measured_non_kv_bytes: int | None
    runtime_extra_floor_bytes: int | None
    probe_invoked: bool
    unresolved_reason: str | None


@dataclass(frozen=True, slots=True)
class CalibrationOutcome:
    """Result of bounded sentinel probing. Not a recommendation."""

    applied: tuple[AppliedCalibration, ...]
    classes: tuple[ClassValidationRow, ...]
    probe_order: tuple[str, ...]
    probe_invocations: int
    capacity_stale: bool = False


class CapacityRefresh(Protocol):
    """Recapture envelope and current available after a probe side effect."""

    def __call__(
        self, host: HostCapabilities
    ) -> tuple[CapacityEnvelope, DeploymentCapacity]:
        ...


class RuntimeMemoryCalibrationService:
    """Classify estimated-feasible candidates and calibrate via one sentinel."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        interpreter: RuntimeMemoryInterpreter,
        *,
        acquisition: AcquisitionService | None = None,
        inventory: ModelInventory | None = None,
        resources: ResourceManager | None = None,
        executions: ExecutionService | None = None,
        runtime: InferenceRuntime | None = None,
        provisioning: ProvisioningService | None = None,
        state_root: Path | None = None,
        scripted: Mapping[str, InterpretedRuntimeMemory] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock
        self._interpreter = interpreter
        self._acquisition = acquisition
        self._inventory = inventory
        self._resources = resources
        self._executions = executions
        self._runtime = runtime
        self._provisioning = provisioning
        self._state_root = (
            Path(state_root).resolve() if state_root is not None else None
        )
        self._scripted = dict(scripted or {})

    def calibrate(
        self,
        *,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        estimated: Sequence[EstimatedFeasibleCandidate],
        allow_live_probe: bool,
        persist_profiles: bool,
    ) -> CalibrationOutcome:
        """One sentinel probe per class, then class-only calibration."""
        available = _int(capacity.available_vram_bytes)
        if available is None or available <= 0:
            rows = tuple(
                _unresolved_applied(
                    item,
                    class_key=_class_for(item, host, eligible, capacity).token,
                    reason="available_vram_unresolved",
                )
                for item in estimated
            )
            return CalibrationOutcome(
                applied=rows,
                classes=(),
                probe_order=(),
                probe_invocations=0,
            )

        grouped = _group(estimated, host, eligible, capacity)
        sentinels: list[PressureMember] = []
        class_members: dict[str, tuple[EstimatedFeasibleCandidate, ...]] = {}
        pressures_by_class: dict[str, tuple[PressureMember, ...]] = {}
        for token, members in grouped.items():
            pressures = tuple(
                PressureMember(
                    model_id=item.model_id,
                    required_vram_bytes=_required(item.requirement),
                    vram_pressure=vram_pressure(_required(item.requirement), available),
                )
                for item in members
            )
            class_members[token] = members
            pressures_by_class[token] = pressures
            sentinels.append(select_sentinel(pressures))

        order = probe_order(tuple(sentinels))
        live = allow_live_probe and self._can_live_probe(eligible)
        applied_by_id: dict[str, AppliedCalibration] = {}
        class_rows: list[ClassValidationRow] = []
        probes = 0
        stale = False

        for sentinel in order:
            members = class_members[_class_token_for(sentinel.model_id, grouped)]
            class_key = _class_for(members[0], host, eligible, capacity)
            cached = self._stored_profile(host.host_id.value, class_key.token)
            observation: InterpretedRuntimeMemory | None = None
            profile = cached
            invoked = False
            reason: str | None = None
            if (
                cached is not None
                and cached.status is RuntimeMemoryProfileStatus.MEASURED
            ):
                status_label = RuntimeMemoryProfileStatus.MEASURED.value
                cached_pass = True
            else:
                cached_pass = False
                status_label = RuntimeMemoryProfileStatus.UNRESOLVED.value
            if not cached_pass:
                observation, invoked, reason, stale = self._observe_sentinel(
                    host,
                    eligible,
                    envelope,
                    capacity,
                    next(
                        item
                        for item in members
                        if item.model_id == sentinel.model_id
                    ),
                    live=live,
                )
                if invoked:
                    probes += 1
                if stale:
                    return CalibrationOutcome(
                        applied=(),
                        classes=(),
                        probe_order=tuple(item.model_id for item in order),
                        probe_invocations=probes,
                        capacity_stale=True,
                    )
                sentinel_candidate = next(
                    item for item in members if item.model_id == sentinel.model_id
                )
                profile = self._profile_from_observation(
                    host,
                    eligible,
                    capacity,
                    class_key,
                    sentinel_candidate,
                    observation,
                    reason,
                )
                if persist_profiles and profile is not None:
                    self._store.put(
                        profile_store_key(host.host_id.value, class_key.token),
                        profile,
                    )
                if (
                    profile is not None
                    and profile.status is RuntimeMemoryProfileStatus.MEASURED
                ):
                    status_label = RuntimeMemoryProfileStatus.MEASURED.value
                    reason = None
                else:
                    status_label = RuntimeMemoryProfileStatus.UNRESOLVED.value
                    reason = reason or (
                        profile.failure_reason
                        if profile is not None
                        and isinstance(profile.failure_reason, str)
                        else VALIDATION_UNRESOLVED
                    )

            usable = (
                profile is not None
                and profile.status is RuntimeMemoryProfileStatus.MEASURED
            )
            cached_this_pass = cached_pass
            source_id = (
                profile.source_model_id
                if profile is not None and isinstance(profile.source_model_id, str)
                else sentinel.model_id
            )
            for member in members:
                role = "sentinel" if member.model_id == source_id else "member"
                applied_by_id[member.model_id] = apply_runtime_profile(
                    member.requirement,
                    profile=profile if usable else None,
                    role=role,
                    safetensors_bytes=_safetensors(member.evidence),
                    class_key=class_key.token,
                    sentinel_model_id=source_id,
                    cached=cached_this_pass,
                )
            non_kv = (
                _int(profile.derived_non_kv_bytes)
                if profile is not None
                else None
            )
            floor = (
                _int(profile.runtime_extra_floor_bytes)
                if profile is not None
                else None
            )
            class_rows.append(
                ClassValidationRow(
                    class_key=class_key.token,
                    sentinel_model_id=sentinel.model_id,
                    member_ids=tuple(item.model_id for item in members),
                    pressures=tuple(
                        (item.model_id, item.vram_pressure, item.required_vram_bytes)
                        for item in pressures_by_class[class_key.token]
                    ),
                    profile_status=(
                        status_label
                        if usable
                        else RuntimeMemoryProfileStatus.UNRESOLVED.value
                    ),
                    measured_non_kv_bytes=non_kv,
                    runtime_extra_floor_bytes=floor if usable else None,
                    probe_invoked=invoked,
                    unresolved_reason=None if usable else reason,
                )
            )

        applied = tuple(applied_by_id[item.model_id] for item in estimated)
        return CalibrationOutcome(
            applied=applied,
            classes=tuple(class_rows),
            probe_order=tuple(item.model_id for item in order),
            probe_invocations=probes,
        )

    def _can_live_probe(self, eligible: EligibleModelView) -> bool:
        if (
            self._runtime is None
            or self._executions is None
            or self._resources is None
            or self._acquisition is None
            or self._inventory is None
            or self._provisioning is None
            or self._state_root is None
        ):
            return False
        token = eligible.installation_id
        if not isinstance(token, str) or not token.strip():
            return False
        try:
            installation = self._provisioning.get_installation(
                RuntimeInstallationId.parse(token)
            )
        except (NotFoundError, PreconditionFailedError, ValueError):
            return False
        if installation.status is not InstallationStatus.INSTALLED:
            return False
        installer_version = installation.installer_version
        if (
            isinstance(installer_version, str)
            and installer_version.strip().lower() == "fixture"
        ):
            return False
        try:
            interpreter = _installation_python(installation, self._state_root)
        except PreconditionFailedError:
            return False
        return interpreter.is_file()

    def _stored_profile(
        self, host_id: str, class_key: str
    ) -> RuntimeMemoryProfile | None:
        found = self._store.get(
            RuntimeMemoryProfile, profile_store_key(host_id, class_key)
        )
        if found is None:
            return None
        if found.status is not RuntimeMemoryProfileStatus.MEASURED:
            return None
        return found

    def _observe_sentinel(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        sentinel: EstimatedFeasibleCandidate,
        *,
        live: bool,
    ) -> tuple[InterpretedRuntimeMemory | None, bool, str | None, bool]:
        scripted = self._scripted.get(sentinel.model_id)
        if scripted is not None:
            return scripted, True, None, False
        budget = _int(capacity.available_vram_bytes)
        if budget is None:
            return None, False, "available_vram_unresolved", False
        if live:
            return self._live_observe(
                host, eligible, envelope, capacity, sentinel, budget
            )
        synthesized = synthesize_observation(
            sentinel.requirement,
            budget,
            _safetensors(sentinel.evidence),
            self._interpreter,
        )
        return synthesized, True, None, False

    def _live_observe(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        envelope: CapacityEnvelope,
        capacity: DeploymentCapacity,
        sentinel: EstimatedFeasibleCandidate,
        budget: int,
    ) -> tuple[InterpretedRuntimeMemory | None, bool, str | None, bool]:
        assert self._acquisition is not None
        assert self._inventory is not None
        assert self._resources is not None
        assert self._executions is not None
        assert self._runtime is not None
        assert self._provisioning is not None
        assert self._state_root is not None
        try:
            artifact = self._acquire(sentinel.entry, envelope, host)
        except PreconditionFailedError as error:
            return None, False, str(getattr(error, "reason", None) or error), False
        reservation = None
        handle = None
        try:
            decision = self._resources.admit(
                _probe_request(
                    host,
                    eligible,
                    capacity,
                    sentinel,
                    artifact,
                    budget,
                    storage_mount=self._model_destination(host),
                ),
                envelope,
                artifact,
            )
            if decision.verdict is AdmissionVerdict.UNRESOLVED:
                return None, False, "probe_admission_unresolved", False
            if (
                decision.verdict is not AdmissionVerdict.ADMITTED
                or decision.reservation is None
            ):
                code = (
                    decision.reason_code
                    if isinstance(decision.reason_code, str)
                    else "probe_admission_rejected"
                )
                if code in {
                    "insufficient_safe_ram",
                    "insufficient_safe_accelerator",
                    "unresolved_safe_capacity",
                }:
                    return None, False, code, True
                return None, True, code, False
            reservation = decision.reservation
            installation = self._provisioning.get_installation(
                RuntimeInstallationId.parse(str(eligible.installation_id))
            )
            interpreter = _installation_python(installation, self._state_root)
            model_path = self._inventory.artifact_dir(artifact.artifact_id)
            port = allocate_loopback_port()
            launch_request = RuntimeLaunchRequest(
                instance_id=f"probe-{sentinel.model_id}"[:64],
                artifact_id=artifact.artifact_id.value,
                interpreter=str(interpreter),
                model_path=str(model_path),
                served_model=sentinel.logical_name,
                bind_address=LOOPBACK,
                bind_port=port,
                context_tokens=sentinel.requirement.assumed_context_tokens,
                concurrency=sentinel.requirement.assumed_batch_size,
                accelerator_index=capacity.accelerator_index,
                quantization=sentinel.entry.metadata.quantization,
                installation_id=installation.installation_id.value,
                runtime_version=installation.runtime_version,
                reserved_accelerator_bytes=budget,
                accelerator_memory_total_bytes=_device_total(
                    host, capacity.accelerator_index
                ),
            )
            spec = replace(
                self._runtime.launch_spec(launch_request),
                output_limit_bytes=PROBE_OUTPUT_LIMIT_BYTES,
            )
            handle = self._executions.start(host.host_id, executor_spec_from(spec))
            deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
            current = handle
            captured = ""
            while current.observed_state in {
                ExecutionState.PENDING,
                ExecutionState.STARTING,
                ExecutionState.RUNNING,
                ExecutionState.STOPPING,
            }:
                captured = f"{current.stdout}\n{current.stderr}"
                parsed = self._interpreter.interpret(
                    stdout=current.stdout,
                    stderr=current.stderr,
                    probe_budget_bytes=budget,
                )
                if parsed.usable:
                    return parsed, True, None, False
                if time.monotonic() > deadline:
                    return None, True, "probe_timeout", False
                time.sleep(PROBE_POLL_SECONDS)
                current = self._executions.observe(current.execution_id)
            parsed = self._interpreter.interpret(
                stdout=current.stdout,
                stderr=current.stderr,
                probe_budget_bytes=budget,
            )
            if parsed.usable:
                return parsed, True, None, False
            del captured
            return None, True, parsed.reason or "probe_exited_without_profile", False
        finally:
            if handle is not None:
                with suppress(NotFoundError, PreconditionFailedError):
                    self._executions.stop(handle.execution_id)
            if reservation is not None:
                self._resources.release(reservation.reservation_id)

    def _acquire(
        self,
        entry: ModelCatalogEntry,
        envelope: CapacityEnvelope,
        host: HostCapabilities,
    ) -> ModelArtifact:
        assert self._acquisition is not None
        assert self._inventory is not None
        request = request_from_entry(entry)
        destination = self._model_destination(host)
        receipt = self._acquisition.acquire(
            request, envelope, host.host_id, destination_mount=destination
        )
        artifact = self._inventory.get(receipt.artifact_id)
        if artifact is None or artifact.state is not ArtifactState.STORED:
            raise PreconditionFailedError(
                "probe artifact is not STORED",
                reason="artifact_not_stored",
            )
        return artifact

    def _model_destination(self, host: HostCapabilities) -> str:
        """Pool that holds state_root/models. Never the unique-SAFE heuristic."""
        if self._state_root is None:
            raise PreconditionFailedError(
                "model destination pool is unresolved",
                reason="storage_pool_unresolved",
            )
        mount = mount_for_path(self._state_root / "models", host)
        if not isinstance(mount, str):
            raise PreconditionFailedError(
                "model destination pool is unresolved",
                reason="storage_pool_unresolved",
            )
        return mount

    def _profile_from_observation(
        self,
        host: HostCapabilities,
        eligible: EligibleModelView,
        capacity: DeploymentCapacity,
        class_key: RuntimeMemoryClassKey,
        sentinel: EstimatedFeasibleCandidate,
        observation: InterpretedRuntimeMemory | None,
        failure_reason: str | None,
    ) -> RuntimeMemoryProfile | None:
        profile_id = RuntimeMemoryProfileId.parse(
            profile_store_key(host.host_id.value, class_key.token)
        )
        req = sentinel.requirement
        budget = _int(capacity.available_vram_bytes)
        if observation is None or not observation.usable or budget is None:
            return RuntimeMemoryProfile(
                profile_id=profile_id,
                status=RuntimeMemoryProfileStatus.UNRESOLVED,
                basis_fingerprint=class_key.token,
                class_key=class_key.token,
                source_model_id=sentinel.model_id,
                source_revision=sentinel.entry.metadata.source_revision,
                runtime=class_key.runtime,
                runtime_version=class_key.runtime_version,
                executor=class_key.executor,
                capability_profile_id=class_key.capability_basis,
                host_id=host.host_id,
                host_fingerprint=host.fingerprint,
                accelerator_index=capacity.accelerator_index,
                accelerator_architecture=class_key.accelerator_architecture,
                model_architecture=class_key.model_architecture,
                quantization=class_key.quantization,
                context_tokens=_int(req.assumed_context_tokens) or NOT_PROVIDED,
                concurrency=_int(req.assumed_batch_size) or NOT_PROVIDED,
                kv_dtype=(
                    class_key.kv_dtype
                    if class_key.kv_dtype != "unknown"
                    else NOT_PROVIDED
                ),
                probe_budget_bytes=budget if budget is not None else NOT_PROVIDED,
                measured_at=self._clock.now(),
                confidence=Confidence.UNKNOWN,
                failure_reason=failure_reason or VALIDATION_UNRESOLVED,
            )
        kv = observation.available_kv_bytes
        assert kv is not None
        non_kv = measured_non_kv_bytes(budget, kv)
        extra = observation.extra
        if extra is None and observation.model_load_bytes is not None:
            extra = runtime_extra_bytes(non_kv, observation.model_load_bytes)
        if extra is None or not extra.valid:
            fallback_base = base_model_memory(
                _int(req.vram_weights_bytes) or 0,
                None,
            )
            extra = runtime_extra_bytes(non_kv, fallback_base)
            fallback_used = True
        else:
            fallback_used = False
        floor = extra.extra_bytes if extra.valid else None
        ratio = (
            runtime_extra_ratio(extra.extra_bytes, observation.model_load_bytes)
            if extra.valid
            else None
        )
        notes = []
        if fallback_used:
            notes.append("model_load_absent_used_base_fallback")
        fail: Maybe[str] = NOT_PROVIDED
        if extra.valid:
            status = RuntimeMemoryProfileStatus.MEASURED
            confidence = Confidence.HIGH
        else:
            status = RuntimeMemoryProfileStatus.UNRESOLVED
            confidence = Confidence.UNKNOWN
            fail = extra.reason or VALIDATION_UNRESOLVED
        return RuntimeMemoryProfile(
            profile_id=profile_id,
            status=status,
            basis_fingerprint=class_key.token,
            class_key=class_key.token,
            source_model_id=sentinel.model_id,
            source_revision=sentinel.entry.metadata.source_revision,
            runtime=class_key.runtime,
            runtime_version=class_key.runtime_version,
            executor=class_key.executor,
            capability_profile_id=class_key.capability_basis,
            host_id=host.host_id,
            host_fingerprint=host.fingerprint,
            accelerator_index=capacity.accelerator_index,
            accelerator_architecture=class_key.accelerator_architecture,
            model_architecture=class_key.model_architecture,
            quantization=class_key.quantization,
            context_tokens=_int(req.assumed_context_tokens) or NOT_PROVIDED,
            concurrency=_int(req.assumed_batch_size) or NOT_PROVIDED,
            kv_dtype=(
                class_key.kv_dtype
                if class_key.kv_dtype != "unknown"
                else NOT_PROVIDED
            ),
            probe_budget_bytes=budget,
            vllm_model_load_bytes=(
                observation.model_load_bytes
                if observation.model_load_bytes is not None
                else NOT_PROVIDED
            ),
            vllm_available_kv_bytes=kv,
            derived_non_kv_bytes=non_kv,
            derived_runtime_extra_bytes=floor if floor is not None else NOT_PROVIDED,
            runtime_extra_floor_bytes=floor if floor is not None else NOT_PROVIDED,
            runtime_extra_ratio=ratio if ratio is not None else NOT_PROVIDED,
            static_requirement_bytes=_int(req.estimated_vram_bytes) or NOT_PROVIDED,
            static_weight_component=_int(req.vram_weights_bytes) or NOT_PROVIDED,
            static_kv_component=_int(req.vram_kv_cache_bytes) or NOT_PROVIDED,
            static_runtime_overhead=_int(req.vram_overhead_bytes) or NOT_PROVIDED,
            measured_at=self._clock.now(),
            confidence=confidence,
            notes=tuple(notes),
            failure_reason=fail,
        )


def apply_runtime_profile(
    requirement: ModelRequirement,
    *,
    profile: RuntimeMemoryProfile | None,
    role: str,
    safetensors_bytes: int | None,
    class_key: str,
    sentinel_model_id: str,
    cached: bool,
) -> AppliedCalibration:
    """Compose non-overlapping VRAM from a profile. Never lowers static demand."""
    static_total = _int(requirement.estimated_vram_bytes) or 0
    provider_base = _int(requirement.vram_weights_bytes) or 0
    static_extra = _int(requirement.vram_overhead_bytes) or 0
    kv = _int(requirement.vram_kv_cache_bytes) or 0
    safety = _int(requirement.safety_allowance_bytes) or 0
    activation = _int(requirement.activation_bytes) or 0
    notes: list[str] = []
    if profile is None or profile.status is not RuntimeMemoryProfileStatus.MEASURED:
        floored = base_model_memory(provider_base, safetensors_bytes)
        requirement = _with_components(
            requirement,
            base=floored,
            extra=static_extra,
            kv=kv,
            safety=safety,
            total=raise_only(
                static_total,
                compose_serving_vram(
                    base_model_bytes=floored,
                    runtime_extra_bytes=static_extra,
                    kv_bytes=kv,
                    safety_bytes=safety,
                    activation_bytes=activation,
                ),
            )[0],
            measured=False,
            notes=("runtime validation unresolved",),
        )
        return AppliedCalibration(
            model_id=requirement.model_id.value,
            requirement=requirement,
            status=RuntimeValidationStatus.UNRESOLVED,
            profile_id=None,
            sentinel_model_id=sentinel_model_id,
            class_key=class_key,
            base_model_bytes=floored,
            runtime_extra_bytes=static_extra,
            kv_bytes=kv,
            safety_bytes=safety,
            unexpected_lowering=False,
            notes=("runtime validation unresolved",),
        )

    if role == "sentinel" and isinstance(profile.vllm_model_load_bytes, int):
        base = profile.vllm_model_load_bytes
        notes.append("base_model_memory=measured_model_load")
    else:
        base = base_model_memory(provider_base, safetensors_bytes)
        notes.append("base_model_memory=max(provider,safetensors)")

    extra = static_extra
    if role == "sentinel":
        measured_extra = _int(profile.derived_runtime_extra_bytes)
        if measured_extra is not None:
            extra = max(static_extra, measured_extra)
            notes.append("runtime_extra=measured")
        elif isinstance(profile.derived_non_kv_bytes, int):
            fallback = runtime_extra_bytes(profile.derived_non_kv_bytes, base)
            if fallback.valid and fallback.extra_bytes is not None:
                extra = max(static_extra, fallback.extra_bytes)
                notes.append("runtime_extra=non_kv_minus_base")
    else:
        extra = calibrated_runtime_extra(
            static_runtime_extra=static_extra,
            sentinel_floor=_int(profile.runtime_extra_floor_bytes),
            sentinel_ratio=(
                profile.runtime_extra_ratio
                if isinstance(profile.runtime_extra_ratio, float)
                else None
            ),
            candidate_base_bytes=base,
        )
        notes.append("runtime_extra=class_transfer")

    composed = compose_serving_vram(
        base_model_bytes=base,
        runtime_extra_bytes=extra,
        kv_bytes=kv,
        safety_bytes=safety,
        activation_bytes=activation,
    )
    total, lowered = raise_only(static_total, composed)
    if lowered:
        notes.append("calibration_would_lower_static_requirement")
    if cached:
        status = RuntimeValidationStatus.CACHED_RUNTIME_CALIBRATION
    elif role == "sentinel":
        status = RuntimeValidationStatus.MEASURED_RUNTIME
    else:
        status = RuntimeValidationStatus.CALIBRATED_FROM_HIGH_PRESSURE_SENTINEL
    requirement = _with_components(
        requirement,
        base=base,
        extra=extra,
        kv=kv,
        safety=safety,
        total=total,
        measured=role == "sentinel" and not cached,
        notes=tuple(notes),
    )
    return AppliedCalibration(
        model_id=requirement.model_id.value,
        requirement=requirement,
        status=status,
        profile_id=profile.profile_id.value,
        sentinel_model_id=sentinel_model_id,
        class_key=class_key,
        base_model_bytes=base,
        runtime_extra_bytes=extra,
        kv_bytes=kv,
        safety_bytes=safety,
        unexpected_lowering=lowered,
        notes=tuple(notes),
    )


def synthesize_observation(
    requirement: ModelRequirement,
    budget_bytes: int,
    safetensors_bytes: int | None,
    interpreter: RuntimeMemoryInterpreter,
) -> InterpretedRuntimeMemory:
    """Fixture probe: identity-preserving extra from static components."""
    del interpreter
    base = base_model_memory(
        _int(requirement.vram_weights_bytes) or 0, safetensors_bytes
    )
    extra = _int(requirement.vram_overhead_bytes) or 0
    available_kv = budget_bytes - base - extra
    non_kv = measured_non_kv_bytes(budget_bytes, available_kv)
    return InterpretedRuntimeMemory(
        model_load_bytes=base,
        available_kv_bytes=available_kv,
        usable=True,
        extra=runtime_extra_bytes(non_kv, base),
    )


def format_runtime_validation(outcome: CalibrationOutcome) -> str:
    """Compact CLI validation section printed before Available Models."""
    lines = [
        "RUNTIME MEMORY VALIDATION",
        "",
        f"Estimated-feasible candidates: {len(outcome.applied)}",
        f"Validation classes: {len(outcome.classes)}",
        "",
    ]
    for index, row in enumerate(outcome.classes, start=1):
        pressure = next(
            (item[1] for item in row.pressures if item[0] == row.sentinel_model_id),
            None,
        )
        lines.extend(
            [
                f"CLASS {index}",
                f"  sentinel: {row.sentinel_model_id}",
                f"  members: {', '.join(row.member_ids)}",
                f"  pressure: {_pressure_text(pressure)}",
                f"  profile: {row.profile_status.upper()}",
                f"  measured non-KV: {_gib(row.measured_non_kv_bytes)}",
                f"  runtime-extra floor: {_gib(row.runtime_extra_floor_bytes)}",
            ]
        )
        if row.unresolved_reason:
            lines.append(f"  reason: {row.unresolved_reason}")
        lines.append("")
    if outcome.probe_order:
        lines.append("PROBE ORDER")
        for index, ident in enumerate(outcome.probe_order, start=1):
            lines.append(f"  {index}. {ident}")
        lines.append("")
    if outcome.applied:
        lines.extend(["CALIBRATED REQUIREMENTS", ""])
        for item in outcome.applied:
            required = _int(item.requirement.estimated_vram_bytes)
            lines.append(
                f"  {item.model_id}  {item.status.value}  required {_gib(required)}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def format_estimated_feasible(items: Sequence[EstimatedFeasibleCandidate]) -> str:
    """Print estimated-feasible identities. Not Available Models."""
    lines = [
        "ESTIMATED-FEASIBLE MODELS",
        f"Count: {len(items)}",
        "",
    ]
    if not items:
        lines.append("(none)")
        lines.append("")
    for index, item in enumerate(items, start=1):
        required = _int(item.requirement.estimated_vram_bytes)
        lines.append(
            f"{index}. {item.logical_name}  required {_gib(required)}"
        )
    lines.append("")
    return "\n".join(lines)


def profile_store_key(host_id: str, class_key: str) -> str:
    digest = hashlib.sha256(
        f"{PROFILE_SCHEMA}|{host_id}|{class_key}".encode()
    ).hexdigest()
    return f"rmp_{digest[:16]}"


def _group(
    estimated: Sequence[EstimatedFeasibleCandidate],
    host: HostCapabilities,
    eligible: EligibleModelView,
    capacity: DeploymentCapacity,
) -> dict[str, tuple[EstimatedFeasibleCandidate, ...]]:
    grouped: dict[str, list[EstimatedFeasibleCandidate]] = {}
    for item in estimated:
        token = _class_for(item, host, eligible, capacity).token
        grouped.setdefault(token, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}


def _class_for(
    item: EstimatedFeasibleCandidate,
    host: HostCapabilities,
    eligible: EligibleModelView,
    capacity: DeploymentCapacity,
) -> RuntimeMemoryClassKey:
    candidate = next(
        (row for row in eligible.candidates if row.model_id == item.model_id),
        None,
    )
    architecture = (
        candidate.architecture
        if candidate is not None and isinstance(candidate.architecture, str)
        else item.entry.metadata.architecture
    )
    quantization = (
        candidate.quantization
        if candidate is not None and isinstance(candidate.quantization, str)
        else item.entry.metadata.quantization
    )
    return runtime_memory_class(
        runtime=eligible.runtime,
        runtime_version=eligible.runtime_version,
        executor=eligible.executor,
        capability_basis=eligible.profile_id,
        accelerator_architecture=_accelerator_architecture(
            host, capacity.accelerator_index
        ),
        model_architecture=architecture,
        quantization=quantization,
        context_tokens=item.requirement.assumed_context_tokens,
        concurrency=item.requirement.assumed_batch_size,
        model_id=item.model_id,
    )


def _class_token_for(
    model_id: str, grouped: Mapping[str, tuple[EstimatedFeasibleCandidate, ...]]
) -> str:
    for token, members in grouped.items():
        if any(item.model_id == model_id for item in members):
            return token
    raise KeyError(model_id)


def _unresolved_applied(
    item: EstimatedFeasibleCandidate, *, class_key: str, reason: str
) -> AppliedCalibration:
    extra = _int(item.requirement.vram_overhead_bytes) or 0
    kv = _int(item.requirement.vram_kv_cache_bytes) or 0
    safety = _int(item.requirement.safety_allowance_bytes) or 0
    base = _int(item.requirement.vram_weights_bytes) or 0
    return AppliedCalibration(
        model_id=item.model_id,
        requirement=item.requirement,
        status=RuntimeValidationStatus.UNRESOLVED,
        profile_id=None,
        sentinel_model_id=item.model_id,
        class_key=class_key,
        base_model_bytes=base,
        runtime_extra_bytes=extra,
        kv_bytes=kv,
        safety_bytes=safety,
        unexpected_lowering=False,
        notes=(reason,),
    )


def _with_components(
    requirement: ModelRequirement,
    *,
    base: int,
    extra: int,
    kv: int,
    safety: int,
    total: int,
    measured: bool,
    notes: tuple[str, ...],
) -> ModelRequirement:
    return replace(
        requirement,
        vram_weights_bytes=base,
        vram_overhead_bytes=extra,
        vram_kv_cache_bytes=kv,
        safety_allowance_bytes=safety,
        estimated_vram_bytes=total,
        measured=measured,
        assumptions=tuple(dict.fromkeys((*requirement.assumptions, *notes))),
    )


def _probe_request(
    host: HostCapabilities,
    eligible: EligibleModelView,
    capacity: DeploymentCapacity,
    sentinel: EstimatedFeasibleCandidate,
    artifact: ModelArtifact,
    budget: int,
    *,
    storage_mount: str | None = None,
) -> ResourceRequest:
    ram = sentinel.requirement.ram_bytes
    dest = storage_mount
    if dest is None and is_resolved(artifact.storage_mount):
        dest = artifact.storage_mount
    return ResourceRequest(
        request_id=RequestId.generate(),
        host_id=host.host_id,
        artifact_id=artifact.artifact_id,
        model_id=sentinel.entry.metadata.model_id,
        plan_fingerprint=f"runtime-memory-probe|{sentinel.model_id}",
        placement=MemoryPlacement.DISCRETE_GPU,
        ram_bytes=ram,
        accelerator_bytes=budget,
        unified_bytes=NOT_PROVIDED,
        logical_name=sentinel.logical_name,
        runtime=eligible.runtime,
        accelerator_index=capacity.accelerator_index,
        estimator_provider=sentinel.requirement.estimator_provider,
        model_revision=artifact.revision,
        quantization=sentinel.entry.metadata.quantization,
        context_tokens=sentinel.requirement.assumed_context_tokens,
        host_fingerprint=host.fingerprint,
        workload_type=WorkloadType.EVALUATION,
        storage_pool_mount=dest if isinstance(dest, str) else NOT_PROVIDED,
    )


def _accelerator_architecture(
    host: HostCapabilities, index: int | None
) -> str | None:
    if index is None:
        return None
    for accelerator in host.accelerators:
        if accelerator.index != index:
            continue
        vendor = accelerator.vendor.value
        model = (
            accelerator.model_name
            if isinstance(accelerator.model_name, str)
            else None
        )
        return f"{vendor}:{model}" if model else vendor
    return None


def _device_total(host: HostCapabilities, index: int | None) -> Maybe[int]:
    if index is None:
        return NOT_PROVIDED
    for accelerator in host.accelerators:
        if accelerator.index == index:
            total = accelerator.memory_total_bytes
            return total if isinstance(total, int) else NOT_PROVIDED
    return NOT_PROVIDED


def _installation_python(installation: RuntimeInstallation, state_root: Path) -> Path:
    raw = installation.python_executable
    if not is_resolved(raw) or not str(raw).strip():
        raise PreconditionFailedError(
            "runtime installation has no interpreter",
            reason="runtime_installation_unusable",
        )
    path = Path(str(raw))
    if not path.is_absolute():
        path = state_root / path
    resolved = path.parent.resolve() / path.name
    if not resolved.is_file():
        raise PreconditionFailedError(
            "runtime interpreter is missing",
            reason="runtime_installation_unusable",
        )
    return resolved


def _required(requirement: ModelRequirement) -> int:
    value = _int(requirement.estimated_vram_bytes)
    if value is None:
        raise ValueError("estimated-feasible requirement must have VRAM")
    return value


def _safetensors(evidence: WeightFootprintEvidence) -> int | None:
    value = evidence.serialized_weight_tensor_bytes
    return value if isinstance(value, int) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _gib(value: int | None) -> str:
    if value is None:
        return "-"
    text = format(value / (1024**3), ".2f").rstrip("0").rstrip(".")
    return f"{text} GiB"


def _pressure_text(value: float | None) -> str:
    if value is None:
        return "-"
    return format(value, ".4f")


def requires_runtime_validation(runtime: object) -> bool:
    """vLLM serving requires resolved runtime-memory calibration."""
    return is_vllm_family(runtime)
