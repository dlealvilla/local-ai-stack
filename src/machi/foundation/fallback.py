"""Local AUTO preference. This does not retry Serve or translate models."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar

from machi.foundation.contracts import (
    FoundationEngine,
    FoundationSelection,
    SupportState,
)
from machi.kernel.errors import ValidationError
from machi.kernel.migrate import register_upgrade
from machi.kernel.schema import Contract, contract, meaning

POLICY_VERSION = "m5.fallback.1"
RECOMPUTE_CHAIN = "foundation,model,plan,admit,serve"
NOT_CONSULTED = "not_consulted"
NOT_RECORDED = "not_recorded"
_MODES = frozenset({"auto", "vllm", "ollama"})
_AVAILABLE = frozenset({SupportState.READY, SupportState.SUPPORTED})
_UNAVAILABLE = frozenset(
    {
        SupportState.UNSUPPORTED,
        SupportState.UNAVAILABLE,
        SupportState.BLOCKED_BY_PREREQUISITE,
        SupportState.INSUFFICIENT_CAPACITY,
        SupportState.PROVISIONING_FAILED,
        SupportState.VERIFICATION_FAILED,
    }
)
_TOKEN_MAX = 80
_REASON_MAX = 240
ResultT = TypeVar("ResultT")


@contract(kind="foundation.runtime_choice", version=2)
@dataclass(frozen=True, slots=True)
class RuntimeChoice(Contract):
    """Which engine the next Foundation selection may use.

    This is not a second macropath. The chosen engine still becomes a
    FoundationSelection, then its own model, plan, admission, and serve.
    Concrete ids are references to evidence already recorded elsewhere.
    """

    decision_id: str = meaning("identity of this control-plane choice")
    policy_version: str = meaning("fallback policy that produced this choice")
    requested_mode: str = meaning("auto, vllm, or ollama; explicit modes do not switch")
    primary_engine: str = meaning("vllm when consulted, otherwise not_consulted")
    primary_support: str = meaning("native vLLM support consulted, or not_consulted")
    primary_failure: str = meaning(
        "primary failure code, not_recorded, or not_consulted"
    )
    primary_selection_id: str = meaning(
        "primary FoundationSelection id, not_recorded, or not_consulted"
    )
    primary_capacity_evidence_id: str = meaning(
        "primary capacity evidence id, not_recorded, or not_consulted"
    )
    fallback_engine: str = meaning("ollama when consulted, otherwise not_consulted")
    fallback_support: str = meaning("ollama support consulted, or not_consulted")
    fallback_failure: str = meaning(
        "fallback failure code, not_recorded, or not_consulted"
    )
    fallback_selection_id: str = meaning(
        "fallback FoundationSelection id, not_recorded, or not_consulted"
    )
    fallback_capacity_evidence_id: str = meaning(
        "fallback capacity evidence id, not_recorded, or not_consulted"
    )
    selected_engine: str = meaning("vllm, ollama, or none")
    outcome: str = meaning("selected or refused")
    reason: str = meaning("why this path was selected or refused")
    recompute: str = meaning("downstream stages that must be rebuilt, or none")
    observed_at: str = meaning(
        "when the consulted foundation evidence was observed, or not_recorded"
    )

    def __post_init__(self) -> None:
        for label, value, limit in (
            ("decision", self.decision_id, _TOKEN_MAX),
            ("policy", self.policy_version, _TOKEN_MAX),
            ("mode", self.requested_mode, _TOKEN_MAX),
            ("engine", self.selected_engine, _TOKEN_MAX),
            ("outcome", self.outcome, _TOKEN_MAX),
            ("reason", self.reason, _REASON_MAX),
            ("recompute", self.recompute, _TOKEN_MAX),
            ("observed", self.observed_at, _TOKEN_MAX),
        ):
            if not value or len(value) > limit:
                raise ValidationError(f"{label} is empty or too long")
        _side(
            "primary",
            self.primary_engine,
            self.primary_support,
            self.primary_failure,
            self.primary_selection_id,
            self.primary_capacity_evidence_id,
            "vllm",
        )
        _side(
            "fallback",
            self.fallback_engine,
            self.fallback_support,
            self.fallback_failure,
            self.fallback_selection_id,
            self.fallback_capacity_evidence_id,
            "ollama",
        )
        if self.policy_version != POLICY_VERSION:
            raise ValidationError("runtime choice policy is not supported")
        if self.requested_mode not in _MODES:
            raise ValidationError("requested runtime is not auto, vllm, or ollama")
        if self.selected_engine not in {"vllm", "ollama", "none"}:
            raise ValidationError("selected engine is not vllm, ollama, or none")
        if self.outcome not in {"selected", "refused"}:
            raise ValidationError("runtime choice outcome is not selected or refused")


def decide_runtime(
    *,
    requested_mode: str,
    observed_at: str,
    primary: FoundationSelection | None = None,
    fallback: FoundationSelection | None = None,
) -> RuntimeChoice:
    """Prefer healthy native vLLM. Fall back only when policy says it is unavailable."""
    if requested_mode not in _MODES:
        raise ValidationError("requested runtime is not auto, vllm, or ollama")
    if not observed_at or len(observed_at) > _TOKEN_MAX:
        raise ValidationError("observed is empty or too long")
    if requested_mode == "vllm":
        if primary is None:
            raise ValidationError("explicit vllm requires its foundation selection")
        return _explicit(requested_mode, primary, observed_at=observed_at)
    if requested_mode == "ollama":
        if fallback is None:
            raise ValidationError("explicit ollama requires its foundation selection")
        return _explicit(
            requested_mode,
            fallback,
            observed_at=observed_at,
            primary_is_other=True,
        )
    if primary is None or fallback is None:
        raise ValidationError("auto requires both foundation selections")
    return _auto(primary, fallback, observed_at=observed_at)


def execute_runtime_choice(
    choice: RuntimeChoice,
    *,
    native: Callable[[], ResultT],
    provider: Callable[[], ResultT],
) -> ResultT:
    """Run the already chosen path. A refusal is not a hidden retry."""
    if choice.outcome != "selected":
        raise ValidationError("a refused runtime choice is not executed")
    if choice.selected_engine == "vllm":
        if choice.recompute != "none":
            raise ValidationError("native selection does not rebuild a provider chain")
        return native()
    if choice.selected_engine == "ollama":
        if choice.requested_mode == "auto" and choice.recompute != RECOMPUTE_CHAIN:
            raise ValidationError("fallback must rebuild the downstream chain")
        return provider()
    raise ValidationError("no runtime was selected")


def _auto(
    primary: FoundationSelection,
    fallback: FoundationSelection,
    *,
    observed_at: str,
) -> RuntimeChoice:
    primary_side = _from_selection(primary, FoundationEngine.VLLM)
    fallback_side = _from_selection(fallback, FoundationEngine.OLLAMA)
    primary_class = _availability(primary.support)
    fallback_class = _availability(fallback.support)
    if primary_class == "available":
        return _choice(
            requested_mode="auto",
            primary=primary_side,
            fallback=fallback_side,
            selected_engine="vllm",
            outcome="selected",
            reason="native vLLM is healthy or supported",
            recompute="none",
            observed_at=observed_at,
        )
    if primary_class == "unresolved":
        return _choice(
            requested_mode="auto",
            primary=primary_side,
            fallback=fallback_side,
            selected_engine="none",
            outcome="refused",
            reason="native vLLM is unresolved and is not treated as unavailable",
            recompute="none",
            observed_at=observed_at,
        )
    if fallback_class == "available":
        return _choice(
            requested_mode="auto",
            primary=primary_side,
            fallback=fallback_side,
            selected_engine="ollama",
            outcome="selected",
            reason="native vLLM is unavailable and Ollama is healthy or supported",
            recompute=RECOMPUTE_CHAIN,
            observed_at=observed_at,
        )
    if fallback_class == "unresolved":
        return _choice(
            requested_mode="auto",
            primary=primary_side,
            fallback=fallback_side,
            selected_engine="none",
            outcome="refused",
            reason="Ollama is unresolved and is not treated as available",
            recompute="none",
            observed_at=observed_at,
        )
    return _choice(
        requested_mode="auto",
        primary=primary_side,
        fallback=fallback_side,
        selected_engine="none",
        outcome="refused",
        reason="neither native vLLM nor Ollama is available",
        recompute="none",
        observed_at=observed_at,
    )


def _explicit(
    requested_mode: str,
    selection: FoundationSelection,
    *,
    observed_at: str,
    primary_is_other: bool = False,
) -> RuntimeChoice:
    engine = (
        FoundationEngine.OLLAMA if primary_is_other else FoundationEngine.VLLM
    )
    consulted = _from_selection(selection, engine)
    absent = _unconsulted()
    available = _availability(selection.support) == "available"
    if primary_is_other:
        primary_side, fallback_side = absent, consulted
    else:
        primary_side, fallback_side = consulted, absent
    if available:
        return _choice(
            requested_mode=requested_mode,
            primary=primary_side,
            fallback=fallback_side,
            selected_engine=requested_mode,
            outcome="selected",
            reason=f"explicit {requested_mode} is healthy or supported",
            recompute="none",
            observed_at=observed_at,
        )
    return _choice(
        requested_mode=requested_mode,
        primary=primary_side,
        fallback=fallback_side,
        selected_engine="none",
        outcome="refused",
        reason=(
            f"explicit {requested_mode} support is {selection.support.value} "
            "and is not switched"
        ),
        recompute="none",
        observed_at=observed_at,
    )


def _choice(
    *,
    requested_mode: str,
    primary: Mapping[str, str],
    fallback: Mapping[str, str],
    selected_engine: str,
    outcome: str,
    reason: str,
    recompute: str,
    observed_at: str,
) -> RuntimeChoice:
    identity = hashlib.sha256(
        "\n".join(
            (
                "runtime-choice",
                POLICY_VERSION,
                requested_mode,
                primary["engine"],
                primary["support"],
                primary["failure"],
                primary["selection_id"],
                primary["capacity_evidence_id"],
                fallback["engine"],
                fallback["support"],
                fallback["failure"],
                fallback["selection_id"],
                fallback["capacity_evidence_id"],
                selected_engine,
                outcome,
                reason,
                recompute,
                observed_at,
            )
        ).encode()
    ).hexdigest()
    return RuntimeChoice(
        decision_id=f"fbk_{identity[:16]}",
        policy_version=POLICY_VERSION,
        requested_mode=requested_mode,
        primary_engine=primary["engine"],
        primary_support=primary["support"],
        primary_failure=primary["failure"],
        primary_selection_id=primary["selection_id"],
        primary_capacity_evidence_id=primary["capacity_evidence_id"],
        fallback_engine=fallback["engine"],
        fallback_support=fallback["support"],
        fallback_failure=fallback["failure"],
        fallback_selection_id=fallback["selection_id"],
        fallback_capacity_evidence_id=fallback["capacity_evidence_id"],
        selected_engine=selected_engine,
        outcome=outcome,
        reason=reason,
        recompute=recompute,
        observed_at=observed_at,
    )


def _from_selection(
    selection: FoundationSelection, engine: FoundationEngine
) -> dict[str, str]:
    if selection.engine is not engine:
        raise ValidationError("runtime choice evidence is for a different engine")
    return {
        "engine": engine.value,
        "support": selection.support.value,
        "failure": selection.failure.value,
        "selection_id": selection.selection_id,
        "capacity_evidence_id": selection.capacity_evidence_id,
    }


def _unconsulted() -> dict[str, str]:
    return {
        "engine": NOT_CONSULTED,
        "support": NOT_CONSULTED,
        "failure": NOT_CONSULTED,
        "selection_id": NOT_CONSULTED,
        "capacity_evidence_id": NOT_CONSULTED,
    }


def _availability(state: SupportState) -> str:
    if state in _AVAILABLE:
        return "available"
    if state in _UNAVAILABLE:
        return "unavailable"
    return "unresolved"


def _side(
    label: str,
    engine: str,
    support: str,
    failure: str,
    selection_id: str,
    capacity_evidence_id: str,
    expected_engine: str,
) -> None:
    values = (engine, support, failure, selection_id, capacity_evidence_id)
    if support == NOT_CONSULTED:
        if any(item != NOT_CONSULTED for item in values):
            raise ValidationError(
                f"an unconsulted {label} runtime must not carry evidence"
            )
        return
    if engine != expected_engine:
        raise ValidationError(f"{label} engine does not match the consulted side")
    for value in values:
        if not value or value == NOT_CONSULTED or len(value) > _TOKEN_MAX:
            raise ValidationError(f"{label} evidence is empty or too long")


def _runtime_choice_v1_to_v2(document: Mapping[str, object]) -> dict[str, object]:
    """Keep the recorded choice. v1 did not cite foundation evidence ids."""
    upgraded = dict(document)
    upgraded["schema_version"] = 2
    primary = document.get("primary_support") != NOT_CONSULTED
    fallback = document.get("fallback_support") != NOT_CONSULTED
    primary_gap = NOT_RECORDED if primary else NOT_CONSULTED
    fallback_gap = NOT_RECORDED if fallback else NOT_CONSULTED
    upgraded["primary_engine"] = "vllm" if primary else NOT_CONSULTED
    upgraded["fallback_engine"] = "ollama" if fallback else NOT_CONSULTED
    upgraded["primary_failure"] = primary_gap
    upgraded["primary_selection_id"] = primary_gap
    upgraded["primary_capacity_evidence_id"] = primary_gap
    upgraded["fallback_failure"] = fallback_gap
    upgraded["fallback_selection_id"] = fallback_gap
    upgraded["fallback_capacity_evidence_id"] = fallback_gap
    upgraded["observed_at"] = NOT_RECORDED
    return upgraded


register_upgrade("foundation.runtime_choice", 1, _runtime_choice_v1_to_v2)
