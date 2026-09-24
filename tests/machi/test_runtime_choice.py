"""AUTO prefers native vLLM and rebuilds an Ollama chain only as fallback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.machi.test_admit import _decision, _envelope, _manager
from tests.machi.test_ollama_serve import (
    _begin,
    _inputs,
    _Log,
    _Port,
    _qualification,
)

from machi.admit.contracts import AdmissionOutcome
from machi.foundation.contracts import (
    ExecutorKind,
    FailureCode,
    FoundationEngine,
    FoundationFamily,
    FoundationSelection,
    SupportState,
)
from machi.foundation.fallback import (
    NOT_CONSULTED,
    NOT_RECORDED,
    POLICY_VERSION,
    RECOMPUTE_CHAIN,
    decide_runtime,
    execute_runtime_choice,
)
from machi.kernel.errors import ValidationError
from machi.kernel.schema import from_dict, to_dict
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.plan.contracts import PlanFailure
from machi.plan.provider import (
    ProviderDeploymentConfiguration,
    compose_provider_plan,
)
from machi.serve.contracts import ServeOutcome
from machi.serve.provider import ProviderServeService

PROMPT = "Please answer with the private customer prompt."
OBSERVED = "2026-09-24T12:00:00+00:00"


def _selection(
    engine: FoundationEngine,
    support: SupportState,
    *,
    selection_id: str,
    capacity: str,
) -> FoundationSelection:
    failure = (
        FailureCode.NONE
        if support in {SupportState.READY, SupportState.SUPPORTED}
        else FailureCode.VERIFICATION_FAILED
    )
    return FoundationSelection(
        selection_id=selection_id,
        family=FoundationFamily.DIRECT,
        engine=engine,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=NOT_PROVIDED,
        support=support,
        failure=failure,
        candidate_id=NOT_PROVIDED,
        generation_id=NOT_PROVIDED,
        capacity_evidence_id=capacity,
        reason="fixture",
    )


def _native(
    support: SupportState,
    *,
    selection_id: str = "fsel_vllm",
    capacity: str = "cev_vllm",
) -> FoundationSelection:
    return _selection(
        FoundationEngine.VLLM,
        support,
        selection_id=selection_id,
        capacity=capacity,
    )


def _ollama(
    support: SupportState,
    *,
    selection_id: str = "fsel_ollama",
    capacity: str = "cev_ollama",
) -> FoundationSelection:
    return _selection(
        FoundationEngine.OLLAMA,
        support,
        selection_id=selection_id,
        capacity=capacity,
    )


def test_auto_keeps_a_healthy_native_path() -> None:
    primary = _native(SupportState.READY, selection_id="fsel_primary_ready")
    choice = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=primary,
        fallback=_ollama(SupportState.READY, selection_id="fsel_fallback_ready"),
    )
    assert choice.outcome == "selected"
    assert choice.selected_engine == "vllm"
    assert choice.recompute == "none"
    assert choice.policy_version == POLICY_VERSION
    assert choice.primary_selection_id == "fsel_primary_ready"
    assert choice.primary_capacity_evidence_id == "cev_vllm"
    assert choice.primary_failure == FailureCode.NONE.value
    assert choice.fallback_selection_id == "fsel_fallback_ready"
    assert choice.observed_at == OBSERVED
    called = {"provider": 0}

    def native() -> str:
        return "native"

    def provider() -> str:
        called["provider"] += 1
        return "provider"

    assert execute_runtime_choice(choice, native=native, provider=provider) == "native"
    assert called["provider"] == 0
    later = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.READY, selection_id="fsel_other"),
        fallback=_ollama(SupportState.READY),
    )
    assert choice.primary_selection_id == "fsel_primary_ready"
    assert later.primary_selection_id == "fsel_other"
    assert choice.decision_id != later.decision_id


def test_auto_fallback_recomputes_a_new_provider_chain(tmp_path: Path) -> None:
    choice = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(
            SupportState.UNSUPPORTED,
            selection_id="fsel_primary_down",
            capacity="cev_primary_down",
        ),
        fallback=_ollama(
            SupportState.READY,
            selection_id="fsel_fallback_ready",
            capacity="cev_fallback_ready",
        ),
    )
    assert choice.selected_engine == "ollama"
    assert choice.recompute == RECOMPUTE_CHAIN
    assert choice.primary_selection_id == "fsel_primary_down"
    assert choice.primary_capacity_evidence_id == "cev_primary_down"
    assert choice.fallback_selection_id == "fsel_fallback_ready"
    assert choice.fallback_capacity_evidence_id == "cev_fallback_ready"
    manager = _manager(tmp_path)
    native = manager.admit(
        _decision(host=40, accel=40, persistent=0),
        _envelope(),
        PlanFailure.NONE,
    )
    assert is_resolved(native.reservation)
    old_reservation = native.reservation.reservation_id
    old_plan = native.reservation.plan_id
    released = manager.release(old_reservation)
    assert released.outcome is AdmissionOutcome.RELEASED

    def native_path() -> tuple[str, str, str]:
        raise AssertionError("fallback must not execute the native path")

    def provider_path() -> tuple[str, str, str]:
        evidence = _qualification()
        decision = compose_provider_plan(_inputs(evidence))
        admitted = manager.admit_provider(decision, _envelope(), PlanFailure.NONE)
        reservation = admitted.reservation
        configuration = decision.configuration
        assert is_resolved(reservation)
        assert isinstance(configuration, ProviderDeploymentConfiguration)
        service = ProviderServeService(_Log(), _Port(), manager, _clock())
        started = _begin(service, configuration, reservation.reservation_id, evidence)
        assert started.outcome is ServeOutcome.READY
        assert is_resolved(started.instance)
        return (
            configuration.plan_id,
            reservation.reservation_id,
            started.instance.instance_id,
        )

    plan_id, reservation_id, instance_id = execute_runtime_choice(
        choice, native=native_path, provider=provider_path
    )
    assert plan_id != old_plan
    assert reservation_id != old_reservation
    assert instance_id
    active = manager.list_active_reservations()
    assert len(active) == 1
    assert active[0].reservation_id == reservation_id
    rendered = json.dumps(to_dict(choice))
    assert PROMPT not in rendered
    assert "prompt" not in to_dict(choice)


def test_explicit_modes_do_not_switch() -> None:
    native_down = decide_runtime(
        requested_mode="vllm",
        observed_at=OBSERVED,
        primary=_native(SupportState.UNAVAILABLE, selection_id="fsel_explicit_down"),
        fallback=_ollama(SupportState.READY, selection_id="fsel_must_not_cite"),
    )
    assert native_down.outcome == "refused"
    assert native_down.selected_engine == "none"
    assert native_down.fallback_support == NOT_CONSULTED
    assert native_down.fallback_selection_id == NOT_CONSULTED
    assert native_down.primary_selection_id == "fsel_explicit_down"
    assert "fsel_must_not_cite" not in json.dumps(to_dict(native_down))
    provider_down = decide_runtime(
        requested_mode="ollama",
        observed_at=OBSERVED,
        primary=_native(SupportState.READY, selection_id="fsel_native_ignored"),
        fallback=_ollama(
            SupportState.VERIFICATION_FAILED, selection_id="fsel_ollama_down"
        ),
    )
    assert provider_down.outcome == "refused"
    assert provider_down.selected_engine == "none"
    assert provider_down.primary_support == NOT_CONSULTED
    assert provider_down.fallback_selection_id == "fsel_ollama_down"
    assert "fsel_native_ignored" not in json.dumps(to_dict(provider_down))
    with pytest.raises(ValidationError):
        execute_runtime_choice(native_down, native=lambda: "v", provider=lambda: "o")


def test_unresolved_and_neither_do_not_fall_back() -> None:
    unresolved = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.CONDITIONALLY_SUPPORTED),
        fallback=_ollama(SupportState.READY),
    )
    assert unresolved.outcome == "refused"
    assert unresolved.selected_engine == "none"
    reconcile = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.RECONCILE_REQUIRED),
        fallback=_ollama(SupportState.SUPPORTED),
    )
    assert reconcile.outcome == "refused"
    missing = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.PROVISIONING_FAILED),
        fallback=_ollama(SupportState.VERIFICATION_FAILED),
    )
    assert missing.outcome == "refused"
    assert missing.reason == "neither native vLLM nor Ollama is available"
    ollama_unknown = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.UNSUPPORTED),
        fallback=_ollama(SupportState.RECONCILE_REQUIRED),
    )
    assert ollama_unknown.outcome == "refused"
    assert "unresolved" in ollama_unknown.reason


def test_supported_primary_is_preferred() -> None:
    choice = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.SUPPORTED),
        fallback=_ollama(SupportState.READY),
    )
    assert choice.selected_engine == "vllm"
    explicit = decide_runtime(
        requested_mode="ollama",
        observed_at=OBSERVED,
        fallback=_ollama(SupportState.SUPPORTED),
    )
    assert explicit.selected_engine == "ollama"
    assert explicit.recompute == "none"
    assert explicit.primary_engine == NOT_CONSULTED


def test_historical_runtime_choice_does_not_gain_evidence() -> None:
    current = decide_runtime(
        requested_mode="auto",
        observed_at=OBSERVED,
        primary=_native(SupportState.READY, selection_id="fsel_real"),
        fallback=_ollama(SupportState.READY, selection_id="fsel_real_fallback"),
    )
    payload = to_dict(current)
    payload["schema_version"] = 1
    for field in (
        "primary_engine",
        "primary_failure",
        "primary_selection_id",
        "primary_capacity_evidence_id",
        "fallback_engine",
        "fallback_failure",
        "fallback_selection_id",
        "fallback_capacity_evidence_id",
        "observed_at",
    ):
        payload.pop(field)
    restored = from_dict(payload)
    assert restored.schema_version == 2
    assert restored.primary_selection_id == NOT_RECORDED
    assert restored.fallback_selection_id == NOT_RECORDED
    assert restored.observed_at == NOT_RECORDED
    assert restored.primary_selection_id != "fsel_real"
    assert restored.outcome == current.outcome
    assert restored.selected_engine == current.selected_engine


def _clock():
    import datetime as dt

    from machi.kernel.clock import FixedClock

    return FixedClock(dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC))
