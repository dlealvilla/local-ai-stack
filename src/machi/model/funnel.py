"""Cheap rejection, then a qualification queue. The queue is not a recommendation."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field

from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.unresolved import NOT_PROVIDED
from machi.model.compat import RuntimeView, assess
from machi.model.contracts import (
    CompatibilityState,
    ModelFailure,
    ModelRequirement,
    WeightFormat,
)
from machi.model.estimate import ServingEstimate, estimate_serving
from machi.model.metadata import normalize_config
from machi.model.qualification import (
    POLICY_VERSION,
    DeployableMember,
    DeployableModels,
    FunnelStage,
    ModelExclusion,
    QualificationQueue,
    QualificationRequest,
    order_queue,
)

_HUGE = 10**18


@dataclass(frozen=True, slots=True)
class FunnelCandidate:
    """One explicit model. Identity is not a compatibility rule."""

    model_id: str
    revision: str
    config_text: str
    file_bytes: int | None
    weight_format: WeightFormat = WeightFormat.SAFETENSORS
    license_blocks: bool = False
    curated_priority: int = 0
    forced: bool = False
    estimated_tokens_per_second: float | None = None


@dataclass
class FunnelCounters:
    estimates: int = 0
    qualifications: int = 0


@dataclass(frozen=True, slots=True)
class CurrentCapacity:
    """One snapshot for every candidate in the pass."""

    snapshot_id: str
    accelerator_safe_bytes: int | None
    accelerator_reserved_bytes: int
    storage_available_bytes: int | None

    @property
    def accelerator_available_bytes(self) -> int | None:
        if self.accelerator_safe_bytes is None:
            return None
        remaining = self.accelerator_safe_bytes - self.accelerator_reserved_bytes
        return max(remaining, 0)


@dataclass
class FunnelResult:
    exclusions: tuple[ModelExclusion, ...]
    feasible_ids: tuple[str, ...]
    queue: QualificationQueue
    requests: dict[str, QualificationRequest]
    estimates: dict[str, ServingEstimate]
    counters: FunnelCounters = field(default_factory=FunnelCounters)


def current_capacity(
    *,
    snapshot_id: str,
    accelerator_safe_bytes: int | None,
    reserved_accelerator_bytes: int,
    storage_available_bytes: int | None,
) -> CurrentCapacity:
    """SAFE minus other holds. This pass does not subtract sibling candidates."""
    return CurrentCapacity(
        snapshot_id=snapshot_id,
        accelerator_safe_bytes=accelerator_safe_bytes,
        accelerator_reserved_bytes=reserved_accelerator_bytes,
        storage_available_bytes=storage_available_bytes,
    )


def evaluate_funnel(
    candidates: tuple[FunnelCandidate, ...],
    *,
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    current: CurrentCapacity,
    context: int,
    concurrency: int,
    generation_id: str,
    engine: str,
    engine_version: str,
    backend: str,
    hardware_class: str,
    observed_at: dt.datetime,
    refine: Callable[[ServingEstimate], ServingEstimate] | None = None,
) -> FunnelResult:
    """Exclude early. Only structural survivors are estimated."""
    del observed_at
    exclusions: list[ModelExclusion] = []
    feasible: list[str] = []
    rows: list[tuple[str, tuple[object, ...], tuple[str, ...]]] = []
    requests: dict[str, QualificationRequest] = {}
    estimates: dict[str, ServingEstimate] = {}
    counters = FunnelCounters()
    for candidate in candidates:
        metadata = normalize_config(candidate.config_text)
        architecture = (
            metadata.architecture if isinstance(metadata.architecture, str) else None
        )
        compatibility = assess(
            architecture=architecture,
            quantization=metadata.quantization,
            weight_format=candidate.weight_format,
            requires_remote_code=metadata.requires_remote_code,
            runtime=runtime,
            capacity=capacity,
            requirement=_storage_requirement(candidate.file_bytes),
            weights_exceed_accelerator=_exceeds(
                candidate.file_bytes, current.accelerator_safe_bytes
            ),
            license_blocks=candidate.license_blocks,
            metadata=metadata,
        )
        if compatibility.state is not CompatibilityState.COMPATIBLE:
            exclusions.append(_excluded(candidate.model_id, compatibility.failure))
            continue
        counters.estimates += 1
        estimate = estimate_serving(
            metadata,
            weight_bytes=candidate.file_bytes,
            storage_bytes=candidate.file_bytes,
            context=context,
            concurrency=concurrency,
        )
        if refine is not None:
            estimate = refine(estimate)
        estimates[candidate.model_id] = estimate
        deep = _deep_exclusion(candidate.model_id, estimate, current)
        if deep is not None:
            exclusions.append(deep)
            continue
        feasible.append(candidate.model_id)
        key, reasons = _order_key(candidate, estimate, current)
        rows.append((candidate.model_id, key, reasons))
        dtype = metadata.dtype if isinstance(metadata.dtype, str) else "undetermined"
        requests[candidate.model_id] = QualificationRequest(
            model_id=candidate.model_id,
            immutable_revision=candidate.revision,
            generation_id=generation_id,
            engine=engine,
            engine_version=engine_version,
            backend=backend,
            hardware_class=hardware_class,
            dtype=dtype,
            quantization=metadata.quantization.value,
            context=context,
            concurrency=concurrency,
            tensor_parallel=1,
            policy_version=POLICY_VERSION,
        )
    queue = order_queue(rows, policy_version=POLICY_VERSION)
    return FunnelResult(
        exclusions=tuple(exclusions),
        feasible_ids=tuple(feasible),
        queue=queue,
        requests=requests,
        estimates=estimates,
        counters=counters,
    )


def deployable_from_pass(
    *,
    snapshot_id: str,
    current: CurrentCapacity,
    members: tuple[DeployableMember, ...],
    observed_at: dt.datetime,
) -> DeployableModels:
    return DeployableModels(
        snapshot_id=snapshot_id,
        capacity_snapshot_id=current.snapshot_id,
        members=members,
        observed_at=observed_at,
    )


def _storage_requirement(file_bytes: int | None) -> ModelRequirement:
    if file_bytes is None:
        return ModelRequirement(
            persistent_bytes=NOT_PROVIDED,
            transient_bytes=NOT_PROVIDED,
            static_weight_bytes=NOT_PROVIDED,
        )
    return ModelRequirement(
        persistent_bytes=file_bytes,
        transient_bytes=file_bytes,
        static_weight_bytes=file_bytes,
    )


def _exceeds(file_bytes: int | None, safe: int | None) -> bool | None:
    if file_bytes is None or safe is None:
        return None
    return file_bytes > safe


def _excluded(model_id: str, failure: ModelFailure) -> ModelExclusion:
    stage = _stage(failure)
    return ModelExclusion(
        model_id=model_id,
        stage=stage,
        reason=failure.value,
        evidence=failure.value,
    )


def _stage(failure: ModelFailure) -> FunnelStage:
    if failure is ModelFailure.ATTENTION_CONFIGURATION_UNSUPPORTED:
        return FunnelStage.STRUCTURAL
    if failure in {
        ModelFailure.INSUFFICIENT_STORAGE,
        ModelFailure.INSUFFICIENT_BASELINE_CAPACITY,
    }:
        return FunnelStage.CHEAP_SIZE
    return FunnelStage.PREFILTER


def _deep_exclusion(
    model_id: str,
    estimate: ServingEstimate,
    current: CurrentCapacity,
) -> ModelExclusion | None:
    total = estimate.total_required_vram_bytes
    available = current.accelerator_available_bytes
    storage = estimate.incremental_storage_bytes
    if not isinstance(total, int) or available is None:
        return ModelExclusion(
            model_id=model_id,
            stage=FunnelStage.DEEP,
            reason="requirement_unresolved",
            evidence="serving bytes or current capacity are unresolved",
        )
    if total > available:
        return ModelExclusion(
            model_id=model_id,
            stage=FunnelStage.DEEP,
            reason="insufficient_current_vram",
            evidence="estimated serving bytes exceed current accelerator capacity",
        )
    if (
        isinstance(storage, int)
        and current.storage_available_bytes is not None
        and storage > current.storage_available_bytes
    ):
        return ModelExclusion(
            model_id=model_id,
            stage=FunnelStage.DEEP,
            reason="insufficient_current_storage",
            evidence="artifact bytes exceed current storage",
        )
    return None


def _order_key(
    candidate: FunnelCandidate,
    estimate: ServingEstimate,
    current: CurrentCapacity,
) -> tuple[tuple[object, ...], tuple[str, ...]]:
    reasons: list[str] = []
    forced = 0 if candidate.forced else 1
    reasons.append("forced" if candidate.forced else "not_forced")
    priority = -candidate.curated_priority
    if candidate.curated_priority:
        reasons.append(f"priority:{candidate.curated_priority}")
    exotic = 1 if candidate.config_text.find("sliding_window") >= 0 else 0
    if exotic:
        reasons.append("exotic_feature")
    size = candidate.file_bytes if candidate.file_bytes is not None else _HUGE
    reasons.append(f"bytes:{size if size < _HUGE else 'unknown'}")
    available = current.accelerator_available_bytes
    total = estimate.total_required_vram_bytes
    if isinstance(total, int) and available is not None:
        headroom = -(available - total)
        reasons.append("headroom_known")
    else:
        headroom = 0
    startup = size
    rate = candidate.estimated_tokens_per_second
    if rate is None:
        performance: tuple[object, ...] = (1, 0.0)
    else:
        performance = (0, -rate)
        reasons.append("estimated_rate")
    key = (
        forced,
        priority,
        exotic,
        size,
        headroom,
        startup,
        performance,
        candidate.model_id,
    )
    return key, tuple(reasons)

