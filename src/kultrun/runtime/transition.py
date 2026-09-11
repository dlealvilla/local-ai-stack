"""Foundation switch classification. Not a live process mutation.

Same-family model A → model B is not vLLM → llama.cpp. A family change is
a heavyweight rebootstrap: stop, release, re-verify, recompute, fresh plan,
fresh ResourceRequest, ResourceManager admission, then launch.
"""

from __future__ import annotations

from kultrun.host.contracts import HostId
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.runtime.contracts import (
    FoundationTransition,
    FoundationTransitionAction,
    FoundationTransitionKind,
)

REBOOTSTRAP_ACTIONS: tuple[str, ...] = (
    FoundationTransitionAction.STOP_LIVE_INFERENCE.value,
    FoundationTransitionAction.RELEASE_RESERVATIONS.value,
    FoundationTransitionAction.SELECT_FOUNDATION.value,
    FoundationTransitionAction.REALIZE_OR_REUSE_INSTALLATION.value,
    FoundationTransitionAction.VERIFY_RUNTIME.value,
    FoundationTransitionAction.RECOMPUTE_DOWNSTREAM.value,
    FoundationTransitionAction.FRESH_DEPLOYMENT_PLAN.value,
    FoundationTransitionAction.FRESH_RESOURCE_REQUEST.value,
    FoundationTransitionAction.RESOURCE_MANAGER_ADMISSION.value,
    FoundationTransitionAction.LAUNCH_INFERENCE_INSTANCE.value,
)

MODEL_SWITCH_ACTIONS: tuple[str, ...] = (
    FoundationTransitionAction.STOP_LIVE_INFERENCE.value,
    FoundationTransitionAction.RELEASE_RESERVATIONS.value,
    FoundationTransitionAction.FRESH_DEPLOYMENT_PLAN.value,
    FoundationTransitionAction.FRESH_RESOURCE_REQUEST.value,
    FoundationTransitionAction.RESOURCE_MANAGER_ADMISSION.value,
    FoundationTransitionAction.LAUNCH_INFERENCE_INSTANCE.value,
)

REUSE_ON_REBOOTSTRAP: tuple[str, ...] = (
    "host_capabilities",
    "storage_evidence",
    "runtime_installation",
)

MUST_RECOMPUTE_ON_REBOOTSTRAP: tuple[str, ...] = (
    "runtime_capability_profile",
    "eligible_model_view",
    "model_requirement",
    "available_models",
    "model_selection",
    "deployment_plan",
    "resource_request",
    "resource_reservation",
    "inference_instance",
)

REUSE_ON_MODEL_SWITCH: tuple[str, ...] = (
    "host_capabilities",
    "storage_evidence",
    "runtime_installation",
    "runtime_capability_profile",
)

MUST_RECOMPUTE_ON_MODEL_SWITCH: tuple[str, ...] = (
    "eligible_model_view",
    "model_requirement",
    "available_models",
    "model_selection",
    "deployment_plan",
    "resource_request",
    "resource_reservation",
    "inference_instance",
)


def classify_transition(
    host_id: HostId,
    *,
    from_family: str | None,
    to_family: str | None,
    from_candidate_id: str | None = None,
    to_candidate_id: str | None = None,
    production_executable: bool = False,
) -> FoundationTransition:
    """Classify a requested foundation change. Does not stop or launch."""
    from_token: Maybe[str] = from_family if from_family else NOT_PROVIDED
    to_token: Maybe[str] = to_family if to_family else NOT_PROVIDED
    from_id: Maybe[str] = from_candidate_id if from_candidate_id else NOT_PROVIDED
    to_id: Maybe[str] = to_candidate_id if to_candidate_id else NOT_PROVIDED
    if to_family is None:
        return FoundationTransition(
            host_id=host_id,
            transition_kind=FoundationTransitionKind.NONE,
            from_family=from_token,
            to_family=to_token,
            from_candidate_id=from_id,
            to_candidate_id=to_id,
            production_executable=False,
            reasons=("no_target_foundation",),
        )
    if from_family is None or from_family == to_family:
        if from_candidate_id == to_candidate_id and from_family is not None:
            return FoundationTransition(
                host_id=host_id,
                transition_kind=FoundationTransitionKind.NONE,
                from_family=from_token,
                to_family=to_token,
                from_candidate_id=from_id,
                to_candidate_id=to_id,
                production_executable=production_executable,
                reasons=("same_foundation_candidate",),
            )
        return FoundationTransition(
            host_id=host_id,
            transition_kind=FoundationTransitionKind.MODEL_SWITCH,
            from_family=from_token,
            to_family=to_token,
            from_candidate_id=from_id,
            to_candidate_id=to_id,
            production_executable=production_executable,
            required_actions=MODEL_SWITCH_ACTIONS,
            reusable=REUSE_ON_MODEL_SWITCH,
            must_recompute=MUST_RECOMPUTE_ON_MODEL_SWITCH,
            reasons=("same_foundation_family",),
        )
    return FoundationTransition(
        host_id=host_id,
        transition_kind=FoundationTransitionKind.FOUNDATION_REBOOTSTRAP,
        from_family=from_token,
        to_family=to_token,
        from_candidate_id=from_id,
        to_candidate_id=to_id,
        production_executable=production_executable,
        required_actions=REBOOTSTRAP_ACTIONS,
        reusable=REUSE_ON_REBOOTSTRAP,
        must_recompute=MUST_RECOMPUTE_ON_REBOOTSTRAP,
        reasons=("different_foundation_family",),
    )
