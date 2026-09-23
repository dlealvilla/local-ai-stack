"""Qualification funnel. Local fakes only. No weight download and no server."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path

from tests.machi.test_plan import _inputs

from machi.adapters.model.runtime_query import predicate_from_probe
from machi.adapters.model.vllm_refine import refine_vllm
from machi.adapters.plan.vllm import build_vllm_recipe
from machi.capacity.contracts import (
    CapacityEnvelope,
    EvidenceStrength,
    MemoryCapacity,
    StorageDomainCapacity,
)
from machi.capacity.policy import default_capacity_settings
from machi.capacity.sonar import not_attempted
from machi.kernel.unresolved import NOT_PROVIDED
from machi.model.compat import RuntimeView
from machi.model.contracts import (
    CompatibilityState,
    ModelFailure,
    ProviderQualification,
    WeightFormat,
)
from machi.model.funnel import (
    FunnelCandidate,
    current_capacity,
    deployable_from_pass,
    evaluate_funnel,
)
from machi.model.predicates import PredicateRule, PredicateSupport
from machi.model.qualification import (
    POLICY_VERSION,
    DeployableMember,
    QualificationEvidence,
    QualificationOutcome,
    QualificationRequest,
    default_qualification_policy,
    recommend_id,
    run_campaign,
    select_id,
)
from machi.plan.compose import compose_plan
from machi.plan.contracts import PlanFailure, PlanPreference

FIXED = dt.datetime(2026, 9, 23, 9, 0, tzinfo=dt.UTC)
ARCH = "LlamaForCausalLM"


def _envelope() -> CapacityEnvelope:
    return CapacityEnvelope(
        evidence_id="cev_funnel",
        input_token="capacity-funnel",
        memory=MemoryCapacity(
            physical_bytes=NOT_PROVIDED,
            execution_limit_bytes=NOT_PROVIDED,
            hard_ceiling_bytes=NOT_PROVIDED,
            reserve_bytes=0,
            safe_bytes=64_000_000_000,
            strength=EvidenceStrength.REPORTED,
            reason="host",
        ),
        accelerators=(),
        storage_domains=(
            StorageDomainCapacity(
                domain_id="dom_funnel",
                backing_resolved=True,
                reported_available_bytes=80_000_000_000,
                specialist_remaining_bytes=NOT_PROVIDED,
                hard_bound_bytes=80_000_000_000,
                reserve_bytes=0,
                safe_bytes=80_000_000_000,
                protected_occupancy_bytes=NOT_PROVIDED,
                reclaimable_bytes=NOT_PROVIDED,
                potential_after_reclaim_bytes=NOT_PROVIDED,
                usable=True,
                strength=EvidenceStrength.REPORTED,
                sonar=not_attempted(),
                reason="disk",
            ),
        ),
        settings=default_capacity_settings(),
        observed_at=FIXED,
        provider="native",
    )


def _config(*, hidden: int, heads: int, layers: int = 2, remote: bool = False) -> str:
    remote_text = ""
    if remote:
        remote_text = ',"auto_map":{"AutoModel":"modeling.Custom"}'
    return (
        '{"architectures":["'
        + ARCH
        + '"],"torch_dtype":"bfloat16","hidden_size":'
        + str(hidden)
        + ',"num_attention_heads":'
        + str(heads)
        + ',"num_key_value_heads":3,"num_hidden_layers":'
        + str(layers)
        + ',"max_position_embeddings":2048'
        + remote_text
        + "}"
    )


def _predicates():
    from machi.model.predicates import RuntimePredicate

    return (
        RuntimePredicate(
            name="flash",
            subject="head_size",
            support=PredicateSupport.FINITE,
            rule=PredicateRule.MULTIPLE_OF,
            parameter=8,
            ceiling=256,
            value="",
        ),
        RuntimePredicate(
            name="triton",
            subject="head_size",
            support=PredicateSupport.FINITE,
            rule=PredicateRule.AT_LEAST,
            parameter=32,
            ceiling=NOT_PROVIDED,
            value="",
        ),
        RuntimePredicate(
            name="flex",
            subject="head_size",
            support=PredicateSupport.VACUOUS,
            rule=PredicateRule.ANY,
            parameter=NOT_PROVIDED,
            ceiling=NOT_PROVIDED,
            value="",
        ),
        RuntimePredicate(
            name="dtype",
            subject="dtype",
            support=PredicateSupport.FINITE,
            rule=PredicateRule.EQUALS,
            parameter=NOT_PROVIDED,
            ceiling=NOT_PROVIDED,
            value="bfloat16",
        ),
    )


def _runtime() -> RuntimeView:
    return RuntimeView(
        architectures=frozenset({ARCH}),
        quantizations=frozenset({"awq"}),
        foundation_id="fgen_funnel",
        provider_qualification=ProviderQualification.QUALIFIED,
        capability_known=True,
        predicates=_predicates(),
    )


def _candidate(
    model_id: str,
    *,
    hidden: int = 576,
    heads: int = 9,
    file_bytes: int | None = 1_000,
    remote: bool = False,
    architecture: str | None = ARCH,
    forced: bool = False,
    rate: float | None = None,
) -> FunnelCandidate:
    text = _config(hidden=hidden, heads=heads, remote=remote)
    if architecture is None:
        text = text.replace(ARCH, "MissingForCausalLM", 1)
    elif architecture != ARCH:
        text = text.replace(ARCH, architecture, 1)
    return FunnelCandidate(
        model_id=model_id,
        revision=f"rev-{model_id}",
        config_text=text,
        file_bytes=file_bytes,
        weight_format=WeightFormat.SAFETENSORS,
        forced=forced,
        estimated_tokens_per_second=rate,
    )


def _funnel(candidates: tuple[FunnelCandidate, ...]):
    return evaluate_funnel(
        candidates,
        runtime=_runtime(),
        capacity=_envelope(),
        current=current_capacity(
            snapshot_id="cap_funnel",
            accelerator_safe_bytes=40_000_000_000,
            reserved_accelerator_bytes=0,
            storage_available_bytes=80_000_000_000,
        ),
        context=128,
        concurrency=1,
        generation_id="fgen_funnel",
        engine="vllm",
        engine_version="0.18.0",
        backend="cuda",
        hardware_class="ampere_48",
        observed_at=FIXED,
        refine=refine_vllm,
    )


class _Probe:
    def __init__(self, outcomes: dict[str, QualificationOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def qualify(self, request: QualificationRequest) -> QualificationEvidence:
        self.calls.append(request.model_id)
        outcome = self.outcomes[request.model_id]
        failure = "none" if outcome is QualificationOutcome.PASS else "shape"
        if outcome is QualificationOutcome.FAIL_HOST:
            failure = "accelerator_unavailable"
        return QualificationEvidence(
            qualification_id=f"qev_{request.model_id}",
            artifact_id="unacquired",
            immutable_revision=request.immutable_revision,
            generation_id=request.generation_id,
            engine=request.engine,
            engine_version=request.engine_version,
            backend=request.backend,
            hardware_class=request.hardware_class,
            dtype=request.dtype,
            quantization=request.quantization,
            context=request.context,
            concurrency=request.concurrency,
            tensor_parallel=request.tensor_parallel,
            policy_version=request.policy_version,
            outcome=outcome,
            failure=failure,
            load_seconds=NOT_PROVIDED,
            ttft_seconds=NOT_PROVIDED,
            tokens_per_second=NOT_PROVIDED,
            peak_vram_bytes=NOT_PROVIDED,
            peak_ram_bytes=NOT_PROVIDED,
            measured=False,
            observed_at=FIXED,
        )


def test_probe_classification_rejects_vacuous_and_keeps_finite_rules() -> None:
    flash = predicate_from_probe(
        {
            "name": "FLASH_ATTN",
            "accepted": [n for n in range(1, 257) if n % 8 == 0],
            "probed_max": 256,
        }
    )
    triton = predicate_from_probe(
        {
            "name": "TRITON_ATTN",
            "accepted": [n for n in range(1, 257) if n >= 32],
            "probed_max": 256,
        }
    )
    flex = predicate_from_probe(
        {
            "name": "FLEX_ATTENTION",
            "accepted": list(range(1, 257)),
            "probed_max": 256,
        }
    )
    assert flash.support is PredicateSupport.FINITE
    assert flash.rule is PredicateRule.MULTIPLE_OF
    assert flash.parameter == 8
    assert triton.support is PredicateSupport.FINITE
    assert triton.rule is PredicateRule.AT_LEAST
    assert triton.parameter == 32
    assert flex.support is PredicateSupport.VACUOUS


def test_historical_head_size_is_not_compatible_or_queued() -> None:
    """Head size 4 matches the stored tiny Llama shape. The name is not the rule."""
    result = _funnel((_candidate("narrow", hidden=16, heads=4, file_bytes=6_477_074),))
    assert result.feasible_ids == ()
    assert result.queue.members == ()
    assert result.counters.estimates == 0
    exclusion = result.exclusions[0]
    assert exclusion.reason == ModelFailure.ATTENTION_CONFIGURATION_UNSUPPORTED.value
    assert exclusion.stage.value == "structural"


def test_cheap_rejections_never_qualify_and_small_ranks_first() -> None:
    candidates = (
        _candidate("remote", remote=True),
        _candidate("other", architecture="OtherForCausalLM"),
        _candidate("huge", file_bytes=10**15),
        _candidate("narrow", hidden=16, heads=4),
        _candidate("small", file_bytes=1_000),
        _candidate("large", file_bytes=50_000_000),
    )
    result = _funnel(candidates)
    excluded = {item.model_id: item.stage.value for item in result.exclusions}
    assert excluded["remote"] == "prefilter"
    assert excluded["other"] == "prefilter"
    assert excluded["huge"] == "cheap_size"
    assert excluded["narrow"] == "structural"
    assert result.feasible_ids == ("small", "large")
    assert result.counters.estimates == 2
    assert [item.model_id for item in result.queue.members] == ["small", "large"]
    probe = _Probe(
        {
            "small": QualificationOutcome.PASS,
            "large": QualificationOutcome.PASS,
        }
    )
    campaign = run_campaign(
        result.queue,
        probe,
        result.requests,
        policy=default_qualification_policy(),
    )
    assert campaign.stop == "passed"
    assert campaign.attempts == 1
    assert probe.calls == ["small"]
    assert "large" not in probe.calls


def test_model_failure_advances_and_host_failure_stops() -> None:
    result = _funnel(
        (_candidate("small", file_bytes=1_000), _candidate("large", file_bytes=2_000))
    )
    failing = _Probe(
        {
            "small": QualificationOutcome.FAIL_MODEL,
            "large": QualificationOutcome.PASS,
        }
    )
    campaign = run_campaign(
        result.queue,
        failing,
        result.requests,
        policy=default_qualification_policy(),
    )
    assert campaign.attempts == 2
    assert failing.calls == ["small", "large"]
    assert campaign.exclusions[0].model_id == "small"
    assert campaign.passed[0].outcome is QualificationOutcome.PASS
    host = _Probe(
        {
            "small": QualificationOutcome.FAIL_HOST,
            "large": QualificationOutcome.PASS,
        }
    )
    stopped = run_campaign(
        result.queue,
        host,
        result.requests,
        policy=default_qualification_policy(),
    )
    assert stopped.stop == "host_failure"
    assert stopped.attempts == 1
    assert host.calls == ["small"]
    assert stopped.passed == ()
    assert stopped.exclusions == ()


def test_queue_order_is_not_the_recommendation() -> None:
    result = _funnel(
        (
            _candidate("small", file_bytes=1_000),
            _candidate("large", file_bytes=2_000, rate=40.0),
        )
    )
    assert [item.model_id for item in result.queue.members] == ["small", "large"]
    deployable = deployable_from_pass(
        snapshot_id="dep_test",
        current=current_capacity(
            snapshot_id="cap_funnel",
            accelerator_safe_bytes=40_000_000_000,
            reserved_accelerator_bytes=0,
            storage_available_bytes=80_000_000_000,
        ),
        members=(
            DeployableMember(
                model_id="small",
                immutable_revision="rev-small",
                qualification_id="qev_small",
                total_required_vram_bytes=1_000,
            ),
            DeployableMember(
                model_id="large",
                immutable_revision="rev-large",
                qualification_id="qev_large",
                total_required_vram_bytes=2_000,
            ),
        ),
        observed_at=FIXED,
    )
    assert recommend_id(deployable, {"large": 40.0}) == "large"
    assert select_id(deployable, "small") is not None
    assert select_id(deployable, "narrow") is None


def test_plan_refuses_a_context_outside_the_qualification_envelope() -> None:
    inputs = _inputs(
        preference=PlanPreference(
            context_length=2048,
            concurrency=1,
            accelerator_count=1,
        )
    )
    narrowed = replace(inputs.qualification, context=1024, concurrency=1)
    decision = compose_plan(replace(inputs, qualification=narrowed), build_vllm_recipe)
    assert decision.failure is PlanFailure.QUALIFICATION_DOES_NOT_COVER


def test_same_snapshot_is_used_for_every_candidate() -> None:
    current = current_capacity(
        snapshot_id="cap_shared",
        accelerator_safe_bytes=2_000_000_000,
        reserved_accelerator_bytes=1_900_000_000,
        storage_available_bytes=80_000_000_000,
    )
    result = evaluate_funnel(
        (_candidate("one"), _candidate("two", file_bytes=2_000)),
        runtime=_runtime(),
        capacity=_envelope(),
        current=current,
        context=128,
        concurrency=1,
        generation_id="fgen_funnel",
        engine="vllm",
        engine_version="0.18.0",
        backend="cuda",
        hardware_class="ampere_48",
        observed_at=FIXED,
        refine=refine_vllm,
    )
    assert result.feasible_ids == ()
    assert {item.reason for item in result.exclusions} == {"insufficient_current_vram"}
    assert current.accelerator_available_bytes == 100_000_000


def test_domain_does_not_hardcode_the_failed_shape(tmp_path: Path) -> None:
    del tmp_path
    root = Path("src/machi/model")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "head_dim >= 16" not in text
    assert "tiny-random-LlamaForCausalLM" not in text
    assert "import vllm" not in text
    assert "llmfit" not in text
    assert "accelerate" not in text


def test_policy_is_one_at_a_time_and_three_per_campaign() -> None:
    policy = default_qualification_policy()
    assert policy.concurrency == 1
    assert policy.max_candidates == 3
    assert policy.policy_version == POLICY_VERSION
    assert CompatibilityState.COMPATIBLE.value == "compatible"
