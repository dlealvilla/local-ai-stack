"""Declared MLX family. Not an executable runtime.

Apple Silicon product intent is MLX. This adapter is the architectural
place for a later managed environment, verifier, unified-memory
requirement, and launch path. It must not be AUTO-selected or launched now.
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

IDENTITY = Name("mlx")
NATIVE = Name("native-process")
UNIMPLEMENTED = "MLX is not an executable Kultrun foundation"


class MlxRuntimeSupport:
    """FUTURE MLX declaration. Does not exec, provision, or verify."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="MLX",
            executor_kind=NATIVE,
            capabilities=("declared-support",),
        )

    def support(self) -> RuntimeSupportDescriptor:
        return RuntimeSupportDescriptor(
            runtime=self.identity,
            display_name="MLX",
            support_tier=RuntimeSupportTier.FUTURE,
            production_candidate=False,
            compatible_executor_types=(NATIVE,),
            supported_os_families=("darwin",),
            supported_architectures=("arm64",),
            supported_accelerator_families=("apple",),
            required_features=(
                "process_execution",
                "structured_argv",
                "environment_variables",
            ),
            known_model_architectures=("llama", "qwen2", "mistral", "gemma2"),
            known_formats=("safetensors",),
            known_quantizations=("fp16", "bf16", "fp32", "q4", "q8"),
            limitations=(
                "FUTURE family declaration only",
                "not a production-selectable foundation",
                "no mlx-lm environment, conversion, or inference",
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


def build() -> MlxRuntimeSupport:
    return MlxRuntimeSupport()
