"""Product foundation preference. Hard feasibility first; ranking second.

Does not import resource, planning, model, execution, or inference.
Does not live in ResourceManager. Does not treat 32 GiB as a ranking rule.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.runtime.contracts import (
    FoundationPreferenceDecision,
    FoundationPreferenceOutcome,
    HostStorageClass,
    RuntimeCandidate,
    RuntimeFamily,
    RuntimePreferencePolicy,
)
from kultrun.runtime.families import family_of, is_apple_silicon
from kultrun.runtime.plan import is_provisionable
from kultrun.storage.contracts import StorageCapacityEvidence
from kultrun.storage.feasibility import reservable_bytes

REASON_APPLE_MLX = "apple_silicon_prefers_mlx"
REASON_APPLE_MLX_UNAVAILABLE = "apple_silicon_mlx_not_feasible"
REASON_NEITHER = "no_feasible_foundation"
REASON_ONLY_ONE = "only_one_hard_feasible"
REASON_CONSTRAINED = "constrained_storage_prefers_llama_cpp"
REASON_COMFORTABLE = "comfortable_storage_prefers_vllm"
REASON_UNRESOLVED_STORAGE = "unresolved_storage_prefers_llama_cpp"
REASON_HARNESS_FALLBACK = "non_product_family_fallback"


def classify_storage(
    storage_evidence: Mapping[str, StorageCapacityEvidence] | None,
    dest_mount: str | None,
    comfortable_storage_bytes: int,
) -> HostStorageClass:
    """SAFE on the destination pool. Unresolved is never treated as zero."""
    if not storage_evidence:
        return HostStorageClass.UNRESOLVED
    if dest_mount is not None:
        evidence = storage_evidence.get(dest_mount)
        if evidence is None:
            return HostStorageClass.UNRESOLVED
        safe = reservable_bytes(evidence)
    else:
        known = [
            value
            for item in storage_evidence.values()
            if (value := reservable_bytes(item)) is not None
        ]
        safe = max(known) if known else None
    if safe is None:
        return HostStorageClass.UNRESOLVED
    if safe < comfortable_storage_bytes:
        return HostStorageClass.CONSTRAINED
    return HostStorageClass.COMFORTABLE


def recommend_foundation(
    host: HostCapabilities,
    candidates: Sequence[RuntimeCandidate],
    *,
    storage_evidence: Mapping[str, StorageCapacityEvidence] | None = None,
    dest_mount: str | None = None,
    policy: RuntimePreferencePolicy | None = None,
) -> FoundationPreferenceDecision:
    """Choose among already-feasible candidates. Never rescues infeasible ones."""
    resolved = policy or RuntimePreferencePolicy()
    feasible = tuple(item for item in candidates if is_provisionable(item))
    families = tuple(dict.fromkeys(family_of(item) for item in feasible))
    storage = classify_storage(
        storage_evidence, dest_mount, resolved.comfortable_storage_bytes
    )
    apple = is_apple_silicon(host)
    if not feasible:
        return _decision(
            host,
            FoundationPreferenceOutcome.BLOCKED,
            apple,
            storage,
            resolved,
            families,
            (REASON_NEITHER,),
        )
    if apple:
        mlx = _first(feasible, RuntimeFamily.MLX.value)
        if mlx is None:
            return _decision(
                host,
                FoundationPreferenceOutcome.BLOCKED,
                apple,
                storage,
                resolved,
                families,
                (REASON_APPLE_MLX_UNAVAILABLE,),
            )
        return _decision(
            host,
            FoundationPreferenceOutcome.RECOMMENDED,
            apple,
            storage,
            resolved,
            families,
            (REASON_APPLE_MLX,),
            family=RuntimeFamily.MLX.value,
            candidate=mlx,
        )
    vllm = _first(feasible, RuntimeFamily.VLLM.value)
    llama = _first(feasible, RuntimeFamily.LLAMA_CPP.value)
    if vllm is None and llama is None:
        chosen = feasible[0]
        return _decision(
            host,
            FoundationPreferenceOutcome.RECOMMENDED,
            apple,
            storage,
            resolved,
            families,
            (REASON_HARNESS_FALLBACK,),
            family=family_of(chosen),
            candidate=chosen,
        )
    if vllm is None:
        return _decision(
            host,
            FoundationPreferenceOutcome.RECOMMENDED,
            apple,
            storage,
            resolved,
            families,
            (REASON_ONLY_ONE,),
            family=RuntimeFamily.LLAMA_CPP.value,
            candidate=llama,
        )
    if llama is None:
        return _decision(
            host,
            FoundationPreferenceOutcome.RECOMMENDED,
            apple,
            storage,
            resolved,
            families,
            (REASON_ONLY_ONE,),
            family=RuntimeFamily.VLLM.value,
            candidate=vllm,
        )
    if storage is HostStorageClass.COMFORTABLE:
        return _decision(
            host,
            FoundationPreferenceOutcome.RECOMMENDED,
            apple,
            storage,
            resolved,
            families,
            (REASON_COMFORTABLE,),
            family=RuntimeFamily.VLLM.value,
            candidate=vllm,
        )
    reason = (
        REASON_UNRESOLVED_STORAGE
        if storage is HostStorageClass.UNRESOLVED
        else REASON_CONSTRAINED
    )
    return _decision(
        host,
        FoundationPreferenceOutcome.RECOMMENDED,
        apple,
        storage,
        resolved,
        families,
        (reason,),
        family=RuntimeFamily.LLAMA_CPP.value,
        candidate=llama,
    )


def _first(
    candidates: Sequence[RuntimeCandidate], family: str
) -> RuntimeCandidate | None:
    return next((item for item in candidates if family_of(item) == family), None)


def _decision(
    host: HostCapabilities,
    outcome: FoundationPreferenceOutcome,
    apple: bool,
    storage: HostStorageClass,
    policy: RuntimePreferencePolicy,
    families: tuple[str, ...],
    reasons: tuple[str, ...],
    *,
    family: str | None = None,
    candidate: RuntimeCandidate | None = None,
) -> FoundationPreferenceDecision:
    return FoundationPreferenceDecision(
        host_id=host.host_id,
        outcome=outcome,
        apple_silicon=apple,
        storage_class=storage,
        recommended_family=family if family is not None else NOT_PROVIDED,
        recommended_candidate_id=(
            candidate.candidate_id.value if candidate is not None else NOT_PROVIDED
        ),
        feasible_families=families,
        reasons=reasons,
        policy_version=policy.policy_version,
        comfortable_storage_bytes=policy.comfortable_storage_bytes,
    )
