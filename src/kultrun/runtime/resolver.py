"""Host-driven runtime candidate generation. No model is required."""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.host.contracts import AcceleratorVendor, HostCapabilities
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.runtime.contracts import (
    CompatibilityClass,
    RuntimeCandidate,
    RuntimeCandidateId,
    RuntimePolicy,
    SupportTier,
)
from kultrun.runtime.ports import RuntimeProvisioner

VLLM_PROVIDER = Name("vllm")
VLLM_FAMILY = Name("vllm")
FIXTURE_PROVIDER = Name("fixture-vllm")
LLAMA_PROVIDER = Name("llama.cpp")
MLX_PROVIDER = Name("mlx")
NATIVE = Name("native-process")
DOCKER = Name("docker")


class RuntimeResolver:
    """Produce RuntimeCandidate[] from host facts and registered provisioners."""

    def __init__(
        self,
        provisioners: Sequence[RuntimeProvisioner] = (),
        *,
        allow_fixture: bool = False,
    ) -> None:
        self._provisioners = {item.identity: item for item in provisioners}
        self._allow_fixture = allow_fixture

    def candidates(
        self,
        host: HostCapabilities,
        policy: RuntimePolicy | None = None,
    ) -> tuple[RuntimeCandidate, ...]:
        resolved = policy or RuntimePolicy(allow_fixture_runtime=self._allow_fixture)
        allow_fixture = resolved.allow_fixture_runtime or self._allow_fixture
        items = [
            *_vllm_paths(host, self._provisioners),
            *_future_paths(host),
        ]
        if allow_fixture:
            items.append(_fixture_path(host, FIXTURE_PROVIDER in self._provisioners))
        requested = resolved.requested_runtime
        if is_resolved(requested):
            wanted = str(requested)
            items = tuple(
                item
                for item in items
                if item.runtime_family.value == wanted
                or item.runtime_provider.value == wanted
            )
        return tuple(
            sorted(
                items,
                key=lambda item: (item.preference, item.runtime_provider.value),
            )
        )

    def select(
        self,
        host: HostCapabilities,
        policy: RuntimePolicy | None = None,
    ) -> RuntimeCandidate | None:
        """AUTO preferred compatible path, or the only explicit match."""
        resolved = policy or RuntimePolicy(allow_fixture_runtime=self._allow_fixture)
        ranked = self.candidates(host, resolved)
        if is_resolved(resolved.requested_runtime):
            if len(ranked) != 1:
                return None
            match = ranked[0]
            if match.compatibility is not CompatibilityClass.COMPATIBLE:
                return None
            return match
        for item in ranked:
            if item.compatibility is not CompatibilityClass.COMPATIBLE:
                continue
            if item.support_tier is SupportTier.REFERENCE:
                continue
            if item.support_tier is SupportTier.FUTURE:
                continue
            if item.support_tier is SupportTier.FIXTURE and not (
                resolved.allow_fixture_runtime or self._allow_fixture
            ):
                continue
            return item
        return None


def _nvidia(host: HostCapabilities) -> bool:
    return any(item.vendor is AcceleratorVendor.NVIDIA for item in host.accelerators)


def _apple(host: HostCapabilities) -> bool:
    return any(item.vendor is AcceleratorVendor.APPLE for item in host.accelerators)


def _native(host: HostCapabilities) -> bool:
    return host.execution.native_process


def _docker(host: HostCapabilities) -> bool:
    return bool(is_resolved(host.execution.docker) and host.execution.docker)


def _vllm_paths(
    host: HostCapabilities,
    provisioners: dict[Name, RuntimeProvisioner],
) -> list[RuntimeCandidate]:
    has_gpu = _nvidia(host)
    installed = VLLM_PROVIDER in provisioners
    native_ok = has_gpu and _native(host)
    docker_ok = has_gpu and _docker(host)
    return [
        RuntimeCandidate(
            candidate_id=RuntimeCandidateId.generate(),
            runtime_provider=VLLM_PROVIDER,
            runtime_family=VLLM_FAMILY,
            executor_kind=NATIVE,
            host_id=host.host_id,
            compatibility=(
                CompatibilityClass.COMPATIBLE
                if native_ok
                else CompatibilityClass.UNSUPPORTED
            ),
            support_tier=SupportTier.PRODUCT,
            required_backend="nvidia-cuda",
            required_components=("python", "vllm"),
            preference=10 if native_ok else 80,
            reason=(
                "NVIDIA host with native process execution"
                if native_ok
                else "vLLM native path needs an NVIDIA accelerator"
            ),
            provisioning_available=installed,
            known_limitations=("real vLLM is isolated from the core environment",),
        ),
        RuntimeCandidate(
            candidate_id=RuntimeCandidateId.generate(),
            runtime_provider=VLLM_PROVIDER,
            runtime_family=VLLM_FAMILY,
            executor_kind=DOCKER,
            host_id=host.host_id,
            compatibility=(
                CompatibilityClass.COMPATIBLE
                if docker_ok
                else CompatibilityClass.UNSUPPORTED
            ),
            support_tier=SupportTier.PRODUCT,
            required_backend="nvidia-cuda",
            required_components=("docker", "vllm"),
            preference=20 if docker_ok else 90,
            reason=(
                "NVIDIA host with a usable Docker daemon"
                if docker_ok
                else "Docker executor is unavailable or no NVIDIA accelerator"
            ),
            provisioning_available=False,
            known_limitations=("container executor is a seam; not provisioned in 1.6",),
        ),
    ]


def _fixture_path(host: HostCapabilities, available: bool) -> RuntimeCandidate:
    return RuntimeCandidate(
        candidate_id=RuntimeCandidateId.generate(),
        runtime_provider=FIXTURE_PROVIDER,
        runtime_family=VLLM_FAMILY,
        executor_kind=NATIVE,
        host_id=host.host_id,
        compatibility=CompatibilityClass.COMPATIBLE,
        support_tier=SupportTier.FIXTURE,
        required_backend=NOT_PROVIDED if not _nvidia(host) else "nvidia-cuda",
        required_components=(),
        preference=1,
        reason="fixture vLLM path for architecture and T2 evidence",
        provisioning_available=available,
        known_limitations=(
            "not a production runtime",
            "launches the reference serving workload",
        ),
    )


def _future_paths(host: HostCapabilities) -> list[RuntimeCandidate]:
    return [
        RuntimeCandidate(
            candidate_id=RuntimeCandidateId.generate(),
            runtime_provider=LLAMA_PROVIDER,
            runtime_family=LLAMA_PROVIDER,
            executor_kind=NATIVE,
            host_id=host.host_id,
            compatibility=CompatibilityClass.UNSUPPORTED,
            support_tier=SupportTier.FUTURE,
            preference=50,
            reason="no production llama.cpp adapter in Stage 1.6",
            provisioning_available=False,
        ),
        RuntimeCandidate(
            candidate_id=RuntimeCandidateId.generate(),
            runtime_provider=MLX_PROVIDER,
            runtime_family=MLX_PROVIDER,
            executor_kind=NATIVE,
            host_id=host.host_id,
            compatibility=CompatibilityClass.UNSUPPORTED,
            support_tier=SupportTier.FUTURE,
            preference=60,
            reason=(
                "MLX is unsupported on this host"
                if not _apple(host)
                else "no production MLX adapter in Stage 1.6"
            ),
            provisioning_available=False,
        ),
    ]

