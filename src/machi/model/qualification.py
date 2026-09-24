"""Empirical qualification records. They are not serving sessions."""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.migrate import register_upgrade
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe
from machi.model.identity import input_token

_TOKEN_MAX = 80
_REASON_MAX = 240
POLICY_VERSION = "m6.qualify.1"
QUALIFICATION_CONCURRENCY = 1
QUALIFICATION_CAMPAIGN_LIMIT = 3


class QualificationOutcome(StrEnum):
    PASS = "pass"
    FAIL_MODEL = "fail_model"
    FAIL_HOST = "fail_host"


class FunnelStage(StrEnum):
    PREFILTER = "prefilter"
    STRUCTURAL = "structural"
    CHEAP_SIZE = "cheap_size"
    DEEP = "deep"
    QUALIFICATION = "qualification"


@contract(kind="model.qualification_policy", version=1)
@dataclass(frozen=True, slots=True)
class QualificationPolicy(Contract):
    """One candidate at a time, and only a few tries in one campaign."""

    policy_version: str = meaning("qualification policy identity")
    concurrency: int = meaning("empirical runs at once")
    max_candidates: int = meaning("campaign bound")

    def __post_init__(self) -> None:
        if self.policy_version != POLICY_VERSION:
            raise ValidationError("qualification policy version is not supported")
        if self.concurrency != QUALIFICATION_CONCURRENCY:
            raise ValidationError("qualification concurrency is 1")
        if self.max_candidates != QUALIFICATION_CAMPAIGN_LIMIT:
            raise ValidationError("qualification campaign bound is 3")


def default_qualification_policy() -> QualificationPolicy:
    return QualificationPolicy(
        policy_version=POLICY_VERSION,
        concurrency=QUALIFICATION_CONCURRENCY,
        max_candidates=QUALIFICATION_CAMPAIGN_LIMIT,
    )


@contract(kind="model.qualification", version=1)
@dataclass(frozen=True, slots=True)
class HistoricalQualificationEvidence(Contract):
    """Older evidence. It has no execution environment and does not cover."""

    qualification_id: str = meaning("identity of this evidence")
    artifact_id: str = meaning("warehouse artifact, or unresolved token")
    immutable_revision: str = meaning("exact model revision")
    generation_id: str = meaning("foundation generation")
    engine: str = meaning("runtime engine")
    engine_version: str = meaning("runtime version")
    backend: str = meaning("cuda or rocm")
    hardware_class: str = meaning("capability class, not a host name")
    dtype: str = meaning("execution dtype")
    quantization: str = meaning("quantization token")
    context: int = meaning("qualified context envelope")
    concurrency: int = meaning("qualified concurrency envelope")
    tensor_parallel: int = meaning("qualified tensor parallel")
    policy_version: str = meaning("policy that defined the probe")
    outcome: QualificationOutcome = meaning("pass, model failure, or host failure")
    failure: str = meaning("typed reason, or none")
    load_seconds: Maybe[float] = meaning("measured load time when recorded")
    ttft_seconds: Maybe[float] = meaning("measured time to first token")
    tokens_per_second: Maybe[float] = meaning("measured generation rate")
    peak_vram_bytes: Maybe[int] = meaning("measured accelerator peak")
    peak_ram_bytes: Maybe[int] = meaning("measured host peak")
    measured: bool = meaning("true only for figures from a real probe")
    observed_at: dt.datetime = meaning("when this evidence was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )


@contract(kind="model.qualification", version=2)
@dataclass(frozen=True, slots=True)
class QualificationEvidence(Contract):
    """Cached execution result for one qualification identity."""

    qualification_id: str = meaning("identity of this evidence")
    artifact_id: str = meaning("warehouse artifact, or unresolved token")
    immutable_revision: str = meaning("exact model revision")
    generation_id: str = meaning("foundation generation")
    engine: str = meaning("runtime engine")
    engine_version: str = meaning("runtime version")
    backend: str = meaning("cuda or rocm")
    hardware_class: str = meaning("capability class, not a host name")
    execution_environment_fingerprint: str = meaning(
        "material accelerator environment; not a device uuid"
    )
    dtype: str = meaning("execution dtype")
    quantization: str = meaning("quantization token")
    context: int = meaning("qualified context envelope")
    concurrency: int = meaning("qualified concurrency envelope")
    tensor_parallel: int = meaning("qualified tensor parallel")
    policy_version: str = meaning("policy that defined the probe")
    outcome: QualificationOutcome = meaning("pass, model failure, or host failure")
    failure: str = meaning("typed reason, or none")
    load_seconds: Maybe[float] = meaning("measured load time when recorded")
    ttft_seconds: Maybe[float] = meaning("measured time to first token")
    tokens_per_second: Maybe[float] = meaning("measured generation rate")
    peak_vram_bytes: Maybe[int] = meaning("measured accelerator peak")
    peak_ram_bytes: Maybe[int] = meaning("measured host peak")
    measured: bool = meaning("true only for figures from a real probe")
    observed_at: dt.datetime = meaning("when this evidence was recorded; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        for name, value in (
            ("qualification", self.qualification_id),
            ("artifact", self.artifact_id),
            ("revision", self.immutable_revision),
            ("generation", self.generation_id),
            ("engine", self.engine),
            ("version", self.engine_version),
            ("backend", self.backend),
            ("hardware", self.hardware_class),
            ("environment", self.execution_environment_fingerprint),
            ("dtype", self.dtype),
            ("quantization", self.quantization),
            ("policy", self.policy_version),
            ("failure", self.failure),
        ):
            if not value or (len(value) > _TOKEN_MAX and name != "failure"):
                raise ValidationError(f"{name} is empty or too long")
            if name == "failure" and len(value) > _REASON_MAX:
                raise ValidationError("failure reason is too long")
        if self.context < 1 or self.concurrency < 1 or self.tensor_parallel < 1:
            raise ValidationError("qualification envelope must be positive")


def qualification_identity(
    *,
    revision: str,
    generation_id: str,
    engine: str,
    engine_version: str,
    backend: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    dtype: str,
    quantization: str,
    context: int,
    concurrency: int,
    tensor_parallel: int,
    policy_version: str,
) -> str:
    """Load-bearing identity. Artifact bytes are cited separately."""
    token = input_token(
        revision,
        generation_id,
        engine,
        engine_version,
        backend,
        hardware_class,
        execution_environment_fingerprint,
        dtype,
        quantization,
        str(context),
        str(concurrency),
        str(tensor_parallel),
        policy_version,
    )
    return f"qev_{token[:16]}"


def covers(
    evidence: QualificationEvidence,
    *,
    revision: str,
    generation_id: str,
    engine: str,
    engine_version: str,
    backend: str,
    hardware_class: str,
    execution_environment_fingerprint: str,
    dtype: str,
    quantization: str,
    context: int,
    concurrency: int,
    tensor_parallel: int,
    policy_version: str,
) -> bool:
    """A pass covers only the same identity at or below its envelopes."""
    if evidence.schema_version != 2:
        return False
    if evidence.execution_environment_fingerprint == "not_recorded":
        return False
    if evidence.outcome is not QualificationOutcome.PASS:
        return False
    same = (
        evidence.immutable_revision == revision
        and evidence.generation_id == generation_id
        and evidence.engine == engine
        and evidence.engine_version == engine_version
        and evidence.backend == backend
        and evidence.hardware_class == hardware_class
        and evidence.execution_environment_fingerprint
        == execution_environment_fingerprint
        and evidence.dtype == dtype
        and evidence.quantization == quantization
        and evidence.tensor_parallel == tensor_parallel
        and evidence.policy_version == policy_version
    )
    if not same:
        return False
    return context <= evidence.context and concurrency <= evidence.concurrency


@contract(kind="model.exclusion", version=1)
@dataclass(frozen=True, slots=True)
class ModelExclusion(Contract):
    """Why a candidate is not deployable. The stage is part of the reason."""

    model_id: str = meaning("candidate identity")
    stage: FunnelStage = meaning("funnel stage that excluded it")
    reason: str = meaning("typed reason")
    evidence: str = meaning("short factual note")

    def __post_init__(self) -> None:
        if not self.model_id or len(self.model_id) > _TOKEN_MAX:
            raise ValidationError("exclusion model id is empty or too long")
        if not self.reason or len(self.reason) > _TOKEN_MAX:
            raise ValidationError("exclusion reason is empty or too long")
        if not self.evidence or len(self.evidence) > _REASON_MAX:
            raise ValidationError("exclusion evidence is empty or too long")


@contract(kind="model.queue_member", version=1)
@dataclass(frozen=True, slots=True)
class QueueMember(Contract):
    """One feasible candidate waiting for empirical proof."""

    model_id: str = meaning("candidate identity")
    rank: int = meaning("zero-based qualification order")
    reasons: tuple[str, ...] = meaning("inspectable ordering factors")

    def __post_init__(self) -> None:
        if not self.model_id or len(self.model_id) > _TOKEN_MAX:
            raise ValidationError("queue model id is empty or too long")
        if self.rank < 0:
            raise ValidationError("queue rank must not be negative")
        if len(self.reasons) > 12:
            raise ValidationError("too many queue reasons")


@contract(kind="model.qualification_queue", version=1)
@dataclass(frozen=True, slots=True)
class QualificationQueue(Contract):
    """What to prove next. Not a deployment recommendation."""

    queue_id: str = meaning("identity of this order")
    members: tuple[QueueMember, ...] = meaning("feasible, not yet qualified")
    policy_version: str = meaning("ordering policy")

    def __post_init__(self) -> None:
        if not self.queue_id or len(self.queue_id) > _TOKEN_MAX:
            raise ValidationError("queue id is empty or too long")
        if len(self.members) > 64:
            raise ValidationError("qualification queue is too long")


@contract(kind="model.deployable_member", version=1)
@dataclass(frozen=True, slots=True)
class DeployableMember(Contract):
    """One model that is runtime-qualified and currently feasible."""

    model_id: str = meaning("candidate identity")
    immutable_revision: str = meaning("exact revision")
    qualification_id: str = meaning("pass evidence")
    total_required_vram_bytes: Maybe[int] = meaning("estimate used for feasibility")

    def __post_init__(self) -> None:
        for label, value in (
            ("model", self.model_id),
            ("revision", self.immutable_revision),
            ("qualification", self.qualification_id),
        ):
            if not value or len(value) > _TOKEN_MAX:
                raise ValidationError(f"{label} is empty or too long")


@contract(kind="model.deployable", version=1)
@dataclass(frozen=True, slots=True)
class DeployableModels(Contract):
    """Models that may be selected now. Not the evaluated universe."""

    snapshot_id: str = meaning("identity of this deployable set")
    capacity_snapshot_id: str = meaning("current capacity this set used")
    members: tuple[DeployableMember, ...] = meaning("runtime-qualified and feasible")
    observed_at: dt.datetime = meaning("when this set was produced; UTC")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        if not self.snapshot_id or len(self.snapshot_id) > _TOKEN_MAX:
            raise ValidationError("deployable snapshot id is empty or too long")
        if not self.capacity_snapshot_id or len(self.capacity_snapshot_id) > _TOKEN_MAX:
            raise ValidationError("capacity snapshot id is empty or too long")
        if len(self.members) > 64:
            raise ValidationError("too many deployable models")


def member_ids(deployable: DeployableModels) -> frozenset[str]:
    return frozenset(item.model_id for item in deployable.members)


def select_id(deployable: DeployableModels, model_id: str) -> DeployableMember | None:
    """Selection cannot create membership."""
    for item in deployable.members:
        if item.model_id == model_id:
            return item
    return None


def recommend_id(
    deployable: DeployableModels,
    performance: dict[str, float],
) -> str | None:
    """Rank already-deployable models. Missing speed does not invent a score."""
    if not deployable.members:
        return None

    def key(item: DeployableMember) -> tuple[int, float, str]:
        rate = performance.get(item.model_id)
        if rate is None:
            return (1, 0.0, item.model_id)
        return (0, -rate, item.model_id)

    return min(deployable.members, key=key).model_id


@dataclass(frozen=True, slots=True)
class QualificationRequest:
    """What a probe must run. The probe does not choose the model."""

    model_id: str
    immutable_revision: str
    generation_id: str
    engine: str
    engine_version: str
    backend: str
    hardware_class: str
    execution_environment_fingerprint: str
    dtype: str
    quantization: str
    context: int
    concurrency: int
    tensor_parallel: int
    policy_version: str


class EmpiricalQualifier(Protocol):
    """One bounded execution. Tests supply a fake. This is not Serve."""

    def qualify(self, request: QualificationRequest) -> QualificationEvidence:
        """Return pass, a model-specific failure, or a host failure."""


@dataclass(frozen=True, slots=True)
class CampaignResult:
    """One bounded qualification campaign. Host failure stops the queue."""

    passed: tuple[QualificationEvidence, ...]
    exclusions: tuple[ModelExclusion, ...]
    stop: str
    attempts: int
    host_evidence: QualificationEvidence | None


def run_campaign(
    queue: QualificationQueue,
    qualifier: EmpiricalQualifier,
    requests: dict[str, QualificationRequest],
    *,
    policy: QualificationPolicy,
) -> CampaignResult:
    """Qualify one at a time. Stop on the first pass or a host failure."""
    passed: list[QualificationEvidence] = []
    excluded: list[ModelExclusion] = []
    attempts = 0
    stop = "exhausted"
    host_evidence: QualificationEvidence | None = None
    for member in queue.members:
        if attempts >= policy.max_candidates:
            stop = "campaign_bound"
            break
        request = requests.get(member.model_id)
        if request is None:
            excluded.append(
                ModelExclusion(
                    model_id=member.model_id,
                    stage=FunnelStage.QUALIFICATION,
                    reason="qualification_request_missing",
                    evidence="no probe request for this queue member",
                )
            )
            continue
        attempts += 1
        evidence = qualifier.qualify(request)
        if evidence.outcome is QualificationOutcome.PASS:
            passed.append(evidence)
            stop = "passed"
            break
        if evidence.outcome is QualificationOutcome.FAIL_HOST:
            host_evidence = evidence
            stop = "host_failure"
            break
        excluded.append(
            ModelExclusion(
                model_id=member.model_id,
                stage=FunnelStage.QUALIFICATION,
                reason=evidence.failure,
                evidence="model-specific qualification failure",
            )
        )
    return CampaignResult(
        passed=tuple(passed),
        exclusions=tuple(excluded),
        stop=stop,
        attempts=attempts,
        host_evidence=host_evidence,
    )


def order_queue(
    rows: Sequence[tuple[str, tuple[object, ...], tuple[str, ...]]],
    *,
    policy_version: str,
) -> QualificationQueue:
    """Deterministic order. Each row is model id, sort key, and reasons."""
    ordered = sorted(rows, key=lambda item: (item[1], item[0]))
    members = tuple(
        QueueMember(model_id=model_id, rank=index, reasons=reasons)
        for index, (model_id, _key, reasons) in enumerate(ordered)
    )
    token = input_token(*(item.model_id for item in members), policy_version)
    return QualificationQueue(
        queue_id=f"qqu_{token[:16]}",
        members=members,
        policy_version=policy_version,
    )


def _qualification_v1_to_v2(
    document: Mapping[str, object],
) -> dict[str, object]:
    """Keep every recorded field. The environment was not observed."""
    upgraded = dict(document)
    upgraded["schema_version"] = 2
    upgraded["execution_environment_fingerprint"] = "not_recorded"
    return upgraded


register_upgrade("model.qualification", 1, _qualification_v1_to_v2)
