"""Declared vLLM product support. Does not import, install, or run vLLM."""

from __future__ import annotations

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.errors import ValidationError
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)

IDENTITY = Name("vllm")
NATIVE = Name("native-process")
CONTAINER = Name("container-docker")


class VllmRuntimeSupport:
    """Product family descriptor. Launch is refused until Stage 1.6C."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="vLLM (declared support)",
            executor_kind=NATIVE,
            capabilities=("declared-support",),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="vLLM (declared support)",
            support_tier=RuntimeSupportTier.PRODUCT,
            production_candidate=True,
            compatible_executor_types=(NATIVE, CONTAINER),
            supported_os_families=("linux",),
            supported_architectures=("x86_64",),
            supported_accelerator_families=("nvidia",),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
            ),
            required_components=(Name("vllm"),),
            known_formats=("safetensors",),
            limitations=(
                "declared support only; not installed or verified",
                "NVIDIA/CUDA-oriented product path",
                "container GPU exposure is unknown (K-33)",
                "version is not pinned until provisioning/verification",
            ),
            evidence=("stage-1.6B-declared-support",),
            confidence=Confidence.MEDIUM,
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        raise ValidationError(
            "vLLM is not installed; provisioning is not part of runtime resolution",
            runtime=IDENTITY.value,
        )

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
    ) -> RuntimeReadiness:
        del stdout, stderr, execution_alive, bound_address, bound_port
        return RuntimeReadiness(
            ready=False,
            reason="vLLM has not been provisioned or verified",
        )
