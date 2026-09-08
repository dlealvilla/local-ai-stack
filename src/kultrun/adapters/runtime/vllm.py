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
from kultrun.runtime.pins import VLLM_VERSION

IDENTITY = Name("vllm")
NATIVE = Name("native-process")
CONTAINER = Name("container-docker")


class VllmRuntimeSupport:
    """Product family descriptor. Launch is refused until verification."""

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
            preferred_version=VLLM_VERSION,
            known_formats=("safetensors",),
            limitations=(
                "declared support plus exact provisioning pin; not verified",
                "NVIDIA/CUDA-oriented product path",
                "container GPU exposure is unknown (K-33)",
                f"provisioning pin vllm=={VLLM_VERSION} is not engine proof",
            ),
            evidence=("stage-1.6C-provisioning-pin",),
            confidence=Confidence.MEDIUM,
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        raise ValidationError(
            "vLLM launch is not part of provisioning; verification is later",
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
            reason="vLLM has not been verified",
        )
