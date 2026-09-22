"""Resolve a native vLLM candidate. No install and no silent substitution."""

from __future__ import annotations

from machi.capacity.contracts import CapacityEnvelope
from machi.discover.contracts import (
    AcceleratorMemoryTopology,
    AcceleratorObservation,
    AcceleratorVendor,
    OSArchitectureObservation,
    OSFamily,
)
from machi.foundation.contracts import (
    AcceleratorBackend,
    ExecutorKind,
    FailureCode,
    FoundationCandidate,
    FoundationEngine,
    FoundationFamily,
    SupportState,
)
from machi.foundation.policy import (
    CUDA_SOURCE,
    DEFAULT_PYTHON,
    DEFAULT_VLLM,
    MINIMUM_MEMORY_BYTES,
    PERSISTENT_BYTES,
    ROCM_SOURCE,
    TRANSIENT_BYTES,
)
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved


def resolve_candidate(
    *,
    os_observation: OSArchitectureObservation | None,
    accelerators: AcceleratorObservation | None,
    capacity: CapacityEnvelope | None,
    backend: str,
    prerequisite_ready: bool | None,
) -> FoundationCandidate:
    """Pick CUDA or ROCm, or a typed refusal. Explicit vLLM does not fall back."""
    if os_observation is None or not is_resolved(os_observation.os_family):
        return _refused(
            FailureCode.HOST_UNSUPPORTED,
            "operating system was not observed",
        )
    if os_observation.os_family is not OSFamily.LINUX:
        return _refused(
            FailureCode.HOST_UNSUPPORTED,
            "native vLLM foundation is Linux-only in this increment",
        )
    chosen = _backend(accelerators, backend)
    if chosen is None:
        return _refused(
            FailureCode.ACCELERATOR_UNSUPPORTED,
            "no discrete NVIDIA or AMD accelerator was observed",
        )
    if prerequisite_ready is False:
        return _refused(
            FailureCode.PREREQUISITE_BLOCKED,
            "prerequisite readiness is not ready",
            backend=chosen,
        )
    if capacity is None:
        return _refused(
            FailureCode.INSUFFICIENT_CAPACITY,
            "capacity envelope was not provided",
            backend=chosen,
        )
    if not _memory_ok(capacity) or not _storage_ok(capacity):
        return _refused(
            FailureCode.INSUFFICIENT_CAPACITY,
            "safe memory or storage is below the foundation requirement",
            backend=chosen,
        )
    spec, source = _package(chosen)
    return FoundationCandidate(
        candidate_id=f"vllm-{DEFAULT_VLLM}-{chosen.value}",
        family=FoundationFamily.DIRECT,
        engine=FoundationEngine.VLLM,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=chosen,
        python_version=DEFAULT_PYTHON,
        vllm_version=DEFAULT_VLLM,
        package_spec=spec,
        package_source=source,
        support=SupportState.SUPPORTED,
        failure=FailureCode.NONE,
        reason="native vLLM candidate matches the host accelerator",
    )


def _backend(
    accelerators: AcceleratorObservation | None,
    requested: str,
) -> AcceleratorBackend | None:
    vendors: set[AcceleratorVendor] = set()
    if accelerators is not None:
        for device in accelerators.devices:
            if not is_resolved(device.vendor):
                continue
            if (
                is_resolved(device.memory_topology)
                and device.memory_topology is AcceleratorMemoryTopology.UNIFIED
            ):
                continue
            vendors.add(device.vendor)
    has_cuda = AcceleratorVendor.NVIDIA in vendors
    has_rocm = AcceleratorVendor.AMD in vendors
    if requested == "cuda":
        return AcceleratorBackend.CUDA if has_cuda else None
    if requested == "rocm":
        return AcceleratorBackend.ROCM if has_rocm else None
    if has_cuda:
        return AcceleratorBackend.CUDA
    if has_rocm:
        return AcceleratorBackend.ROCM
    return None


def _memory_ok(capacity: CapacityEnvelope) -> bool:
    safe = capacity.memory.safe_bytes
    return is_resolved(safe) and int(safe) >= MINIMUM_MEMORY_BYTES


def _storage_ok(capacity: CapacityEnvelope) -> bool:
    needed = PERSISTENT_BYTES + TRANSIENT_BYTES
    for domain in capacity.storage_domains:
        if not domain.usable:
            continue
        if is_resolved(domain.safe_bytes) and int(domain.safe_bytes) >= needed:
            return True
    return False


def _package(backend: AcceleratorBackend) -> tuple[str, str]:
    if backend is AcceleratorBackend.CUDA:
        return f"vllm=={DEFAULT_VLLM}", CUDA_SOURCE
    return f"vllm=={DEFAULT_VLLM}+rocm700", ROCM_SOURCE


def _refused(
    failure: FailureCode,
    reason: str,
    *,
    backend: AcceleratorBackend | None = None,
) -> FoundationCandidate:
    chosen = backend if backend is not None else NOT_PROVIDED
    return FoundationCandidate(
        candidate_id=f"refused-{failure.value}",
        family=FoundationFamily.DIRECT,
        engine=FoundationEngine.VLLM,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=chosen,
        python_version=DEFAULT_PYTHON,
        vllm_version=DEFAULT_VLLM,
        package_spec="unresolved",
        package_source="none",
        support=_support(failure),
        failure=failure,
        reason=reason,
    )


def _support(failure: FailureCode) -> SupportState:
    if failure is FailureCode.PREREQUISITE_BLOCKED:
        return SupportState.BLOCKED_BY_PREREQUISITE
    if failure is FailureCode.INSUFFICIENT_CAPACITY:
        return SupportState.INSUFFICIENT_CAPACITY
    return SupportState.UNSUPPORTED
