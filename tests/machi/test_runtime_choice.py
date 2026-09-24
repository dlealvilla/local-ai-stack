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
from machi.foundation.contracts import SupportState
from machi.foundation.fallback import (
    POLICY_VERSION,
    RECOMPUTE_CHAIN,
    decide_runtime,
    execute_runtime_choice,
)
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import is_resolved
from machi.plan.contracts import PlanFailure
from machi.plan.provider import (
    ProviderDeploymentConfiguration,
    compose_provider_plan,
)
from machi.serve.contracts import ServeOutcome
from machi.serve.provider import ProviderServeService

PROMPT = "Please answer with the private customer prompt."


def test_auto_keeps_a_healthy_native_path() -> None:
    choice = decide_runtime(
        requested_mode="auto",
        primary=SupportState.READY,
        fallback=SupportState.READY,
    )
    assert choice.outcome == "selected"
    assert choice.selected_engine == "vllm"
    assert choice.recompute == "none"
    assert choice.policy_version == POLICY_VERSION
    called = {"provider": 0}

    def native() -> str:
        return "native"

    def provider() -> str:
        called["provider"] += 1
        return "provider"

    assert execute_runtime_choice(choice, native=native, provider=provider) == "native"
    assert called["provider"] == 0


def test_auto_fallback_recomputes_a_new_provider_chain(tmp_path: Path) -> None:
    choice = decide_runtime(
        requested_mode="auto",
        primary=SupportState.UNSUPPORTED,
        fallback=SupportState.READY,
    )
    assert choice.selected_engine == "ollama"
    assert choice.recompute == RECOMPUTE_CHAIN
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
        primary=SupportState.UNAVAILABLE,
        fallback=SupportState.READY,
    )
    assert native_down.outcome == "refused"
    assert native_down.selected_engine == "none"
    assert native_down.fallback_support == "not_consulted"
    provider_down = decide_runtime(
        requested_mode="ollama",
        primary=SupportState.READY,
        fallback=SupportState.VERIFICATION_FAILED,
    )
    assert provider_down.outcome == "refused"
    assert provider_down.selected_engine == "none"
    assert provider_down.primary_support == "not_consulted"
    with pytest.raises(ValidationError):
        execute_runtime_choice(native_down, native=lambda: "v", provider=lambda: "o")


def test_unresolved_and_neither_do_not_fall_back() -> None:
    unresolved = decide_runtime(
        requested_mode="auto",
        primary=SupportState.CONDITIONALLY_SUPPORTED,
        fallback=SupportState.READY,
    )
    assert unresolved.outcome == "refused"
    assert unresolved.selected_engine == "none"
    reconcile = decide_runtime(
        requested_mode="auto",
        primary=SupportState.RECONCILE_REQUIRED,
        fallback=SupportState.SUPPORTED,
    )
    assert reconcile.outcome == "refused"
    missing = decide_runtime(
        requested_mode="auto",
        primary=SupportState.PROVISIONING_FAILED,
        fallback=SupportState.VERIFICATION_FAILED,
    )
    assert missing.outcome == "refused"
    assert missing.reason == "neither native vLLM nor Ollama is available"
    ollama_unknown = decide_runtime(
        requested_mode="auto",
        primary=SupportState.UNSUPPORTED,
        fallback=SupportState.RECONCILE_REQUIRED,
    )
    assert ollama_unknown.outcome == "refused"
    assert "unresolved" in ollama_unknown.reason


def test_supported_primary_is_preferred() -> None:
    choice = decide_runtime(
        requested_mode="auto",
        primary=SupportState.SUPPORTED,
        fallback=SupportState.READY,
    )
    assert choice.selected_engine == "vllm"
    explicit = decide_runtime(
        requested_mode="ollama",
        primary=SupportState.READY,
        fallback=SupportState.SUPPORTED,
    )
    assert explicit.selected_engine == "ollama"
    assert explicit.recompute == "none"


def _clock():
    import datetime as dt

    from machi.kernel.clock import FixedClock

    return FixedClock(dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC))
