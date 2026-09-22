"""Default native-vLLM pins. The fallback runtime is not selected."""

from __future__ import annotations

from machi.foundation.contracts import (
    ExecutorKind,
    FoundationSetting,
    FoundationSettings,
    ProvisionMode,
    SettingProvenance,
    SettingSupport,
)

BACKEND_CHOICES = ("auto", "cuda", "rocm")
DEFAULT_PYTHON = "3.12"
DEFAULT_VLLM = "0.18.0"
DEFAULT_TIMEOUT = 3600
PERSISTENT_BYTES = 12 * 1024 * 1024 * 1024
TRANSIENT_BYTES = 8 * 1024 * 1024 * 1024
MINIMUM_MEMORY_BYTES = 8 * 1024 * 1024 * 1024
CUDA_SOURCE = "pypi:torch-backend=auto"
ROCM_SOURCE = "https://wheels.vllm.ai/rocm/0.18.0/rocm700"


def default_foundation_settings(
    *,
    mode: ProvisionMode = ProvisionMode.INSPECT_ONLY,
    backend: str = "auto",
    provenance: SettingProvenance = SettingProvenance.PRODUCT_DEFAULT,
) -> FoundationSettings:
    """Inspect by default. Provisioning is an explicit mode."""
    rows = (
        _row(
            "executor",
            ExecutorKind.NATIVE_PROCESS.value,
            provenance,
            "native process only",
            "native_process",
        ),
        _row(
            "python.version",
            DEFAULT_PYTHON,
            provenance,
            "managed interpreter pin",
            "3.12",
        ),
        _row(
            "vllm.version",
            DEFAULT_VLLM,
            provenance,
            "exact vLLM pin",
            DEFAULT_VLLM,
        ),
        _row(
            "backend",
            backend,
            provenance,
            "auto selects cuda or rocm from the host",
            "auto,cuda,rocm",
        ),
        _row(
            "provision.mode",
            mode.value,
            provenance,
            "inspect does not install",
            "inspect_only,plan_only,provision",
        ),
        _row(
            "environment.root",
            "state_root_generations",
            provenance,
            "generations stay under the owned root",
            "state_root_generations",
        ),
        _row(
            "reuse.policy",
            "reuse_verified",
            provenance,
            "a verified generation is not rebuilt",
            "reuse_verified",
        ),
        _row(
            "cache.policy",
            "state_root",
            provenance,
            "package cache stays under the owned root",
            "state_root",
        ),
        _row(
            "upgrade.policy",
            "new_generation",
            provenance,
            "a different pin is a new generation",
            "new_generation",
        ),
        _row(
            "timeout.seconds",
            str(DEFAULT_TIMEOUT),
            provenance,
            "one process invocation",
            "1..3600",
        ),
    )
    return FoundationSettings(
        python_version=DEFAULT_PYTHON,
        vllm_version=DEFAULT_VLLM,
        executor=ExecutorKind.NATIVE_PROCESS,
        backend=backend,
        provision_mode=mode,
        environment_root_policy="state_root_generations",
        reuse_policy="reuse_verified",
        timeout_seconds=DEFAULT_TIMEOUT,
        settings=rows,
    )


def _row(
    name: str,
    value: str,
    provenance: SettingProvenance,
    reason: str,
    allowed: str,
) -> FoundationSetting:
    return FoundationSetting(
        name=name,
        value=value,
        provenance=provenance,
        reason=reason,
        allowed_values=allowed,
        support_state=SettingSupport.SUPPORTED,
        mutability="runtime",
        invalidation="re_resolve",
    )
