"""Classify declared runtime support against current host and executor facts.

Does not import execution, model, resource, or planning. Composition passes
executor capability objects that structurally match ExecutorCapabilityView.
Does not install, verify, or exec anything.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Protocol, runtime_checkable

from kultrun.evidence.contracts import Confidence
from kultrun.host.contracts import Architecture, HostCapabilities
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.runtime.contracts import (
    CompatibilityClass,
    ResolutionReasonCode,
    RuntimeCandidate,
    RuntimeCandidateId,
    RuntimePolicy,
    RuntimeResolution,
    RuntimeResolverMode,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)

CANDIDATE_SCHEMA = "runtime.candidate@1"

_CLASS_RANK = {
    CompatibilityClass.COMPATIBLE: 0,
    CompatibilityClass.CONDITIONAL: 1,
    CompatibilityClass.UNRESOLVED: 2,
    CompatibilityClass.UNSUPPORTED: 3,
}

_TIER_RANK = {
    RuntimeSupportTier.PRODUCT: 0,
    RuntimeSupportTier.REFERENCE: 1,
    RuntimeSupportTier.TEST_ONLY: 2,
    RuntimeSupportTier.FUTURE: 3,
}

_AVAIL_RANK = {
    "available": 0,
    "unresolved": 1,
    "unavailable": 2,
}

_FEATURE_ATTR = {
    "process_execution": "process_execution",
    "structured_argv": "structured_argv",
    "environment_variables": "environment_variables",
    "working_directory": "working_directory",
    "port_binding": "port_binding",
    "accelerator_exposure": "accelerator_exposure",
    "stdout_capture": "bounded_stdout",
    "stderr_capture": "bounded_stderr",
    "lifecycle_observation": "lifecycle_observation",
    "graceful_termination": "graceful_termination",
    "forced_termination": "forced_termination",
    "isolation": "isolation",
}


@runtime_checkable
class ExecutorCapabilityView(Protocol):
    """Structural view of executor evidence. Not ExecutorCapabilityProfile.

    Attributes are read-only properties so a frozen capability-profile
    dataclass matches without `runtime` importing `execution`.
    """

    @property
    def executor(self) -> Name: ...

    @property
    def executor_type(self) -> Name: ...

    @property
    def availability(self) -> object: ...

    @property
    def process_execution(self) -> object: ...

    @property
    def structured_argv(self) -> object: ...

    @property
    def environment_variables(self) -> object: ...

    @property
    def working_directory(self) -> object: ...

    @property
    def port_binding(self) -> object: ...

    @property
    def accelerator_exposure(self) -> object: ...

    @property
    def bounded_stdout(self) -> object: ...

    @property
    def bounded_stderr(self) -> object: ...

    @property
    def lifecycle_observation(self) -> object: ...

    @property
    def graceful_termination(self) -> object: ...

    @property
    def forced_termination(self) -> object: ...

    @property
    def isolation(self) -> object: ...

    @property
    def host_id(self) -> object: ...

    @property
    def host_fingerprint(self) -> object: ...

    @property
    def limitations(self) -> tuple[str, ...]: ...

    @property
    def evidence(self) -> tuple[str, ...]: ...


def resolve(
    host: HostCapabilities,
    executors: Sequence[ExecutorCapabilityView],
    descriptors: Sequence[RuntimeSupportDescriptor],
    policy: RuntimePolicy,
    *,
    components: Mapping[str, str] | None = None,
) -> RuntimeResolution:
    """Derive candidates from current facts. Never installs or executes."""
    presence = dict(components or {})
    chosen, excluded, notes = _select_descriptors(descriptors, policy)
    evaluated: list[RuntimeCandidate] = []
    for descriptor in chosen:
        matching = [
            profile
            for profile in executors
            if _executor_declared(descriptor, profile)
            and _executor_allowed(policy, profile)
        ]
        if not matching:
            continue
        for profile in matching:
            evaluated.append(
                _evaluate(host, descriptor, profile, policy, presence)
            )
    if (
        policy.mode is RuntimeResolverMode.EXPLICIT
        and isinstance(policy.requested_runtime, str)
        and not any(
            item.runtime.value == policy.requested_runtime for item in evaluated
        )
        and policy.requested_runtime not in excluded
    ):
        notes = (
            *notes,
            f"requested runtime {policy.requested_runtime!r} has no descriptor",
        )
    ranked = _rank(evaluated, policy)
    plausible = tuple(
        item
        for item in ranked
        if item.compatibility
        in {CompatibilityClass.COMPATIBLE, CompatibilityClass.CONDITIONAL}
    )
    unsupported = tuple(
        item
        for item in ranked
        if item.compatibility is CompatibilityClass.UNSUPPORTED
    )
    unresolved = tuple(
        item
        for item in ranked
        if item.compatibility is CompatibilityClass.UNRESOLVED
    )
    preferred = _preferred(plausible, policy)
    return RuntimeResolution(
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        policy=policy,
        candidates=plausible,
        unsupported=unsupported,
        unresolved=unresolved,
        preferred_candidate_id=(
            preferred.candidate_id.value if preferred is not None else NOT_PROVIDED
        ),
        excluded_runtimes=tuple(excluded),
        notes=notes,
    )


class RuntimeResolver:
    """Named classifier. Delegates to resolve(); installs and executes nothing."""

    def resolve(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy,
        *,
        components: Mapping[str, str] | None = None,
    ) -> RuntimeResolution:
        return resolve(
            host, executors, descriptors, policy, components=components
        )


def path_presence(names: Sequence[str]) -> dict[str, str]:
    """PATH probe only. Never imports or installs the named component."""
    return {
        name: "present" if shutil.which(name) else "missing" for name in names
    }


def fingerprint_candidate_id(
    *,
    runtime: str,
    version: str,
    executor: str,
    host_id: str,
    host_fingerprint: str,
) -> RuntimeCandidateId:
    """Stable id for one path. Same inputs always yield the same id."""
    material = "|".join(
        (
            CANDIDATE_SCHEMA,
            runtime,
            version,
            executor,
            host_id,
            host_fingerprint,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return RuntimeCandidateId(f"rcand_{digest}")


def _select_descriptors(
    descriptors: Sequence[RuntimeSupportDescriptor],
    policy: RuntimePolicy,
) -> tuple[tuple[RuntimeSupportDescriptor, ...], tuple[str, ...], tuple[str, ...]]:
    if policy.mode is RuntimeResolverMode.EXPLICIT:
        requested = (
            policy.requested_runtime
            if isinstance(policy.requested_runtime, str)
            else ""
        )
        matched = tuple(
            item for item in descriptors if item.runtime.value == requested
        )
        return matched, (), ()
    kept: list[RuntimeSupportDescriptor] = []
    excluded: list[str] = []
    for descriptor in descriptors:
        code = _auto_exclusion(descriptor, policy)
        if code is None:
            kept.append(descriptor)
        else:
            excluded.append(descriptor.runtime.value)
    return tuple(kept), tuple(excluded), ()


def _auto_exclusion(
    descriptor: RuntimeSupportDescriptor, policy: RuntimePolicy
) -> ResolutionReasonCode | None:
    if (
        descriptor.support_tier is RuntimeSupportTier.TEST_ONLY
        and not policy.allow_test_only
    ):
        return ResolutionReasonCode.TEST_ONLY_RUNTIME_EXCLUDED
    if (
        descriptor.support_tier is RuntimeSupportTier.REFERENCE
        and not policy.allow_reference_runtimes
    ):
        return ResolutionReasonCode.REFERENCE_RUNTIME_EXCLUDED
    if descriptor.support_tier is RuntimeSupportTier.FUTURE and not policy.allow_future:
        return ResolutionReasonCode.FUTURE_RUNTIME_EXCLUDED
    if not descriptor.production_candidate and not (
        policy.allow_test_only or policy.allow_reference_runtimes
    ):
        return ResolutionReasonCode.POLICY_DISALLOWED
    return None


def _executor_declared(
    descriptor: RuntimeSupportDescriptor, profile: ExecutorCapabilityView
) -> bool:
    allowed = {item.value for item in descriptor.compatible_executor_types}
    if not allowed:
        return True
    return profile.executor.value in allowed or profile.executor_type.value in allowed


def _executor_allowed(policy: RuntimePolicy, profile: ExecutorCapabilityView) -> bool:
    if not policy.allowed_executor_providers:
        return True
    return profile.executor.value in policy.allowed_executor_providers


def _evaluate(
    host: HostCapabilities,
    descriptor: RuntimeSupportDescriptor,
    profile: ExecutorCapabilityView,
    policy: RuntimePolicy,
    presence: Mapping[str, str],
) -> RuntimeCandidate:
    codes: list[ResolutionReasonCode] = []
    missing: list[str] = []
    matched: list[str] = []
    evidence = [
        f"runtime={descriptor.runtime.value}",
        f"executor={profile.executor.value}",
        f"os={host.operating_environment.os_name}",
        f"arch={host.operating_environment.architecture.value}",
        f"executor_availability={_token(profile.availability)}",
        *descriptor.evidence,
        *profile.evidence[:4],
    ]
    _host_os(host, descriptor, codes)
    _host_arch(host, descriptor, codes)
    _accelerators(host, descriptor, codes)
    _executor_availability(profile, codes)
    _executor_features(descriptor, profile, codes, matched, missing)
    _components(descriptor, presence, codes, missing)
    compatibility = _classify(codes)
    version = (
        descriptor.preferred_version
        if is_resolved(descriptor.preferred_version)
        else NOT_PROVIDED
    )
    version_token = version if isinstance(version, str) else "unspecified"
    fingerprint = (
        host.fingerprint if is_resolved(host.fingerprint) else "unknown"
    )
    candidate_id = fingerprint_candidate_id(
        runtime=descriptor.runtime.value,
        version=version_token,
        executor=profile.executor.value,
        host_id=host.host_id.value,
        host_fingerprint=fingerprint,
    )
    return RuntimeCandidate(
        candidate_id=candidate_id,
        runtime=descriptor.runtime,
        runtime_family=descriptor.runtime,
        runtime_provider=descriptor.runtime,
        version=version,
        executor=profile.executor,
        executor_type=profile.executor_type,
        host_id=host.host_id,
        host_fingerprint=host.fingerprint,
        compatibility=compatibility,
        support_tier=descriptor.support_tier,
        reason_codes=tuple(codes),
        reason=_reason_text(compatibility, codes, descriptor, profile),
        required_executor_capabilities=descriptor.required_features,
        matched_executor_capabilities=tuple(matched),
        missing_prerequisites=tuple(missing),
        evidence=tuple(evidence),
        confidence=_confidence(compatibility),
        policy_mode=policy.mode,
    )


def _host_os(
    host: HostCapabilities,
    descriptor: RuntimeSupportDescriptor,
    codes: list[ResolutionReasonCode],
) -> None:
    families = tuple(item.lower() for item in descriptor.supported_os_families)
    if not families:
        return
    os_name = host.operating_environment.os_name.strip().lower()
    if not os_name or os_name == "unknown":
        codes.append(ResolutionReasonCode.HOST_OS_UNKNOWN)
        return
    if os_name not in families:
        codes.append(ResolutionReasonCode.HOST_OS_UNSUPPORTED)


def _host_arch(
    host: HostCapabilities,
    descriptor: RuntimeSupportDescriptor,
    codes: list[ResolutionReasonCode],
) -> None:
    supported = tuple(item.lower() for item in descriptor.supported_architectures)
    if not supported:
        return
    architecture = host.operating_environment.architecture
    if architecture is Architecture.UNKNOWN:
        codes.append(ResolutionReasonCode.HOST_ARCH_UNKNOWN)
        return
    if architecture.value not in supported:
        codes.append(ResolutionReasonCode.HOST_ARCH_UNSUPPORTED)


def _accelerators(
    host: HostCapabilities,
    descriptor: RuntimeSupportDescriptor,
    codes: list[ResolutionReasonCode],
) -> None:
    required = tuple(
        item.lower() for item in descriptor.supported_accelerator_families
    )
    if not required:
        return
    vendors = {item.vendor.value.lower() for item in host.accelerators}
    if not vendors.intersection(required):
        codes.append(ResolutionReasonCode.ACCELERATOR_UNSUPPORTED)


def _executor_availability(
    profile: ExecutorCapabilityView, codes: list[ResolutionReasonCode]
) -> None:
    availability = _token(profile.availability)
    if availability == "unavailable":
        codes.append(ResolutionReasonCode.EXECUTOR_UNAVAILABLE)
    elif availability == "unresolved":
        codes.append(ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN)


def _executor_features(
    descriptor: RuntimeSupportDescriptor,
    profile: ExecutorCapabilityView,
    codes: list[ResolutionReasonCode],
    matched: list[str],
    missing: list[str],
) -> None:
    for feature in descriptor.required_features:
        attr = _FEATURE_ATTR.get(feature)
        if attr is None:
            codes.append(ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN)
            missing.append(feature)
            continue
        status = _token(getattr(profile, attr))
        if status == "supported":
            matched.append(feature)
        elif status == "unknown":
            codes.append(ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN)
            missing.append(feature)
        else:
            codes.append(ResolutionReasonCode.EXECUTOR_CAPABILITY_MISSING)
            missing.append(feature)
    gpu_required = bool(descriptor.supported_accelerator_families)
    isolation = _token(profile.isolation)
    accel = _token(profile.accelerator_exposure)
    if gpu_required and isolation == "supported" and accel == "unknown":
        if ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN not in codes:
            codes.append(ResolutionReasonCode.EXECUTOR_CAPABILITY_UNKNOWN)
        caveat = "accelerator_exposure"
        if caveat not in missing:
            missing.append(caveat)


def _components(
    descriptor: RuntimeSupportDescriptor,
    presence: Mapping[str, str],
    codes: list[ResolutionReasonCode],
    missing: list[str],
) -> None:
    for component in descriptor.required_components:
        status = presence.get(component.value)
        if status is None:
            codes.append(ResolutionReasonCode.REQUIRED_COMPONENT_UNKNOWN)
            missing.append(component.value)
        elif status == "present":
            continue
        elif status == "missing":
            codes.append(ResolutionReasonCode.REQUIRED_COMPONENT_MISSING)
            missing.append(component.value)
        else:
            codes.append(ResolutionReasonCode.REQUIRED_COMPONENT_UNKNOWN)
            missing.append(component.value)


def _classify(codes: Sequence[ResolutionReasonCode]) -> CompatibilityClass:
    hard = {
        ResolutionReasonCode.HOST_OS_UNSUPPORTED,
        ResolutionReasonCode.HOST_ARCH_UNSUPPORTED,
        ResolutionReasonCode.ACCELERATOR_UNSUPPORTED,
        ResolutionReasonCode.EXECUTOR_UNAVAILABLE,
        ResolutionReasonCode.EXECUTOR_TYPE_UNSUPPORTED,
        ResolutionReasonCode.EXECUTOR_CAPABILITY_MISSING,
        ResolutionReasonCode.POLICY_DISALLOWED,
    }
    unknown = {
        ResolutionReasonCode.HOST_OS_UNKNOWN,
        ResolutionReasonCode.HOST_ARCH_UNKNOWN,
        ResolutionReasonCode.RUNTIME_SUPPORT_UNKNOWN,
    }
    if any(code in hard for code in codes):
        return CompatibilityClass.UNSUPPORTED
    if any(code in unknown for code in codes):
        return CompatibilityClass.UNRESOLVED
    if codes:
        return CompatibilityClass.CONDITIONAL
    return CompatibilityClass.COMPATIBLE


def _reason_text(
    compatibility: CompatibilityClass,
    codes: Sequence[ResolutionReasonCode],
    descriptor: RuntimeSupportDescriptor,
    profile: ExecutorCapabilityView,
) -> str:
    path = f"{descriptor.runtime.value} via {profile.executor.value}"
    if compatibility is CompatibilityClass.COMPATIBLE:
        return f"{path} matches declared support on this host"
    if not codes:
        return f"{path} is {compatibility.value}"
    joined = ", ".join(code.value for code in codes)
    return f"{path}: {joined}"


def _confidence(compatibility: CompatibilityClass) -> Confidence:
    if compatibility is CompatibilityClass.COMPATIBLE:
        return Confidence.HIGH
    if compatibility is CompatibilityClass.CONDITIONAL:
        return Confidence.MEDIUM
    return Confidence.LOW


# K-56: Ranking is intentionally deterministic/static in Stage 1.6B.
# Future evidence-based runtime scoring belongs behind RuntimeRankingPolicy.
def _rank(
    candidates: Sequence[RuntimeCandidate], policy: RuntimePolicy
) -> tuple[RuntimeCandidate, ...]:
    def key(item: RuntimeCandidate) -> tuple[object, ...]:
        runtime_pref = _index(policy.preferred_runtime_order, item.runtime.value)
        executor_pref = _index(policy.preferred_executor_order, item.executor.value)
        return (
            _CLASS_RANK[item.compatibility],
            _TIER_RANK[item.support_tier],
            _AVAIL_RANK.get(_availability_from_codes(item), 1),
            runtime_pref,
            executor_pref,
            item.runtime.value,
            item.executor.value,
            item.candidate_id.value,
        )

    ordered = sorted(candidates, key=key)
    return tuple(replace(item, rank=index) for index, item in enumerate(ordered))


def _availability_from_codes(item: RuntimeCandidate) -> str:
    if ResolutionReasonCode.EXECUTOR_UNAVAILABLE in item.reason_codes:
        return "unavailable"
    return "available"


def _index(order: Sequence[str], name: str) -> int:
    try:
        return list(order).index(name)
    except ValueError:
        return len(order) + 1


def _preferred(
    plausible: Sequence[RuntimeCandidate], policy: RuntimePolicy
) -> RuntimeCandidate | None:
    for item in plausible:
        if item.compatibility is CompatibilityClass.COMPATIBLE:
            return item
        if (
            item.compatibility is CompatibilityClass.CONDITIONAL
            and policy.prefer_conditional
        ):
            return item
    return None


def _token(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).strip().lower()
