"""Declared llama.cpp family. Not an executable runtime.

This adapter exists so RuntimeResolver, FoundationSelection, eligibility,
and later provisioning/verification have a stable family identity. Launch,
provision, and inference are refused until a later bounded stage
implements them.
"""

from __future__ import annotations

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeSupportTier,
)

IDENTITY = Name("llama.cpp")
NATIVE = Name("native-process")
CONTAINER = Name("container-docker")
UNIMPLEMENTED = "llama.cpp is not an executable Kultrun foundation"


class LlamaCppRuntimeSupport:
    """FUTURE llama.cpp declaration. Does not exec, provision, or verify."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="llama.cpp",
            executor_kind=NATIVE,
            capabilities=("declared-support",),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="llama.cpp",
            support_tier=RuntimeSupportTier.FUTURE,
            production_candidate=False,
            compatible_executor_types=(NATIVE, CONTAINER),
            supported_os_families=("linux", "darwin"),
            supported_architectures=("x86_64", "arm64"),
            supported_accelerator_families=(),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
            ),
            known_model_architectures=("llama", "qwen2", "mistral", "phi3"),
            known_formats=("gguf",),
            known_quantizations=("q4_0", "q4_k_m", "q5_k_m", "q8_0", "fp16"),
            limitations=(
                "FUTURE family declaration only",
                "not a production-selectable foundation",
                "no llama-server binary, GGUF acquisition, or inference",
            ),
            evidence=("stage-1.6R0-runtime-breadth-exoskeleton",),
            confidence=Confidence.LOW,
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        raise PreconditionFailedError(
            UNIMPLEMENTED,
            reason="runtime_launch_unsupported",
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
        expected_served_model: str | None = None,
        probe_timeout: float | None = None,
    ) -> RuntimeReadiness:
        del stdout, stderr, execution_alive, bound_address, bound_port
        del expected_served_model, probe_timeout
        return RuntimeReadiness(ready=False, reason=UNIMPLEMENTED)


def build() -> LlamaCppRuntimeSupport:
    return LlamaCppRuntimeSupport()
