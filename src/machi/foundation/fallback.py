"""Local AUTO preference. This does not retry Serve or translate models."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from machi.foundation.contracts import SupportState
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning

POLICY_VERSION = "m5.fallback.1"
RECOMPUTE_CHAIN = "foundation,model,plan,admit,serve"
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


@contract(kind="foundation.runtime_choice", version=1)
@dataclass(frozen=True, slots=True)
class RuntimeChoice(Contract):
    """Which engine the next Foundation selection may use.

    This is not a second macropath. The chosen engine still becomes a
    FoundationSelection, then its own model, plan, admission, and serve.
    """

    decision_id: str = meaning("identity of this control-plane choice")
    policy_version: str = meaning("fallback policy that produced this choice")
    requested_mode: str = meaning("auto, vllm, or ollama; explicit modes do not switch")
    primary_support: str = meaning("native vLLM support consulted, or not_consulted")
    fallback_support: str = meaning("ollama support consulted, or not_consulted")
    selected_engine: str = meaning("vllm, ollama, or none")
    outcome: str = meaning("selected or refused")
    reason: str = meaning("why this path was selected or refused")
    recompute: str = meaning("downstream stages that must be rebuilt, or none")

    def __post_init__(self) -> None:
        for label, value, limit in (
            ("decision", self.decision_id, _TOKEN_MAX),
            ("policy", self.policy_version, _TOKEN_MAX),
            ("mode", self.requested_mode, _TOKEN_MAX),
            ("primary", self.primary_support, _TOKEN_MAX),
            ("fallback", self.fallback_support, _TOKEN_MAX),
            ("engine", self.selected_engine, _TOKEN_MAX),
            ("outcome", self.outcome, _TOKEN_MAX),
            ("reason", self.reason, _REASON_MAX),
            ("recompute", self.recompute, _TOKEN_MAX),
        ):
            if not value or len(value) > limit:
                raise ValidationError(f"{label} is empty or too long")
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
    primary: SupportState,
    fallback: SupportState | None = None,
) -> RuntimeChoice:
    """Prefer healthy native vLLM. Fall back only when policy says it is unavailable."""
    if requested_mode not in _MODES:
        raise ValidationError("requested runtime is not auto, vllm, or ollama")
    if requested_mode == "vllm":
        return _explicit(requested_mode, primary, other="not_consulted")
    if requested_mode == "ollama":
        if fallback is None:
            raise ValidationError("explicit ollama requires its foundation state")
        return _explicit(
            requested_mode,
            fallback,
            other="not_consulted",
            primary_is_other=True,
        )
    if fallback is None:
        raise ValidationError("auto requires both foundation states")
    return _auto(primary, fallback)


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


def _auto(primary: SupportState, fallback: SupportState) -> RuntimeChoice:
    primary_class = _availability(primary)
    fallback_class = _availability(fallback)
    if primary_class == "available":
        return _choice(
            requested_mode="auto",
            primary_support=primary.value,
            fallback_support=fallback.value,
            selected_engine="vllm",
            outcome="selected",
            reason="native vLLM is healthy or supported",
            recompute="none",
        )
    if primary_class == "unresolved":
        return _choice(
            requested_mode="auto",
            primary_support=primary.value,
            fallback_support=fallback.value,
            selected_engine="none",
            outcome="refused",
            reason="native vLLM is unresolved and is not treated as unavailable",
            recompute="none",
        )
    if fallback_class == "available":
        return _choice(
            requested_mode="auto",
            primary_support=primary.value,
            fallback_support=fallback.value,
            selected_engine="ollama",
            outcome="selected",
            reason="native vLLM is unavailable and Ollama is healthy or supported",
            recompute=RECOMPUTE_CHAIN,
        )
    if fallback_class == "unresolved":
        return _choice(
            requested_mode="auto",
            primary_support=primary.value,
            fallback_support=fallback.value,
            selected_engine="none",
            outcome="refused",
            reason="Ollama is unresolved and is not treated as available",
            recompute="none",
        )
    return _choice(
        requested_mode="auto",
        primary_support=primary.value,
        fallback_support=fallback.value,
        selected_engine="none",
        outcome="refused",
        reason="neither native vLLM nor Ollama is available",
        recompute="none",
    )


def _explicit(
    requested_mode: str,
    state: SupportState,
    *,
    other: str,
    primary_is_other: bool = False,
) -> RuntimeChoice:
    available = _availability(state) == "available"
    engine = requested_mode
    if primary_is_other:
        primary_support = other
        fallback_support = state.value
    else:
        primary_support = state.value
        fallback_support = other
    if available:
        return _choice(
            requested_mode=requested_mode,
            primary_support=primary_support,
            fallback_support=fallback_support,
            selected_engine=engine,
            outcome="selected",
            reason=f"explicit {engine} is healthy or supported",
            recompute="none",
        )
    return _choice(
        requested_mode=requested_mode,
        primary_support=primary_support,
        fallback_support=fallback_support,
        selected_engine="none",
        outcome="refused",
        reason=f"explicit {engine} support is {state.value} and is not switched",
        recompute="none",
    )


def _choice(
    *,
    requested_mode: str,
    primary_support: str,
    fallback_support: str,
    selected_engine: str,
    outcome: str,
    reason: str,
    recompute: str,
) -> RuntimeChoice:
    identity = hashlib.sha256(
        "\n".join(
            (
                "runtime-choice",
                POLICY_VERSION,
                requested_mode,
                primary_support,
                fallback_support,
                selected_engine,
                outcome,
                reason,
                recompute,
            )
        ).encode()
    ).hexdigest()
    return RuntimeChoice(
        decision_id=f"fbk_{identity[:16]}",
        policy_version=POLICY_VERSION,
        requested_mode=requested_mode,
        primary_support=primary_support,
        fallback_support=fallback_support,
        selected_engine=selected_engine,
        outcome=outcome,
        reason=reason,
        recompute=recompute,
    )


def _availability(state: SupportState) -> str:
    if state in _AVAILABLE:
        return "available"
    if state in _UNAVAILABLE:
        return "unavailable"
    return "unresolved"
