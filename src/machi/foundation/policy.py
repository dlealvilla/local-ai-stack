"""Default native-vLLM pins. AUTO fallback policy lives in fallback.py."""

from __future__ import annotations

from machi.foundation.contracts import (
    ExecutorKind,
    FoundationEngine,
    FoundationSetting,
    FoundationSettings,
    ProvisionMode,
    RuntimeRecipe,
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
ROCM_VARIANT = "rocm700"
ROCM700_VARIANT = ROCM_VARIANT
ROCM700_LINE = (7, 0)
ROCM700_GLIBC = (2, 35)
ROCM700_ARCHS = frozenset(
    {
        "gfx90a",
        "gfx942",
        "gfx950",
        "gfx1100",
        "gfx1101",
        "gfx1200",
        "gfx1201",
    }
)
# Sonames DT_NEEDED by the pinned vLLM 0.18.0+rocm700 and HIP torch wheels.
# Libraries shipped inside those wheels are not listed.
ROCM700_LIBS = (
    "libamdhip64.so.7",
    "libhiprtc.so.7",
    "librocblas.so.5",
    "librocsolver.so.0",
    "libMIOpen.so.1",
    "libhipblas.so.3",
    "libhipfft.so.0",
    "libhiprand.so.1",
    "libhipsparse.so.4",
    "libhipsolver.so.1",
    "libhipsparselt.so.0",
    "libhipblaslt.so.1",
    "librccl.so.1",
    "libroctx64.so.4",
    "libmpi.so.40",
    "libmpi_cxx.so.40",
)
ROCM_SOURCE = "https://wheels.vllm.ai/rocm/0.18.0/rocm700"
_ARCH_TEXT = ",".join(sorted(ROCM700_ARCHS))
_LIB_TEXT = ",".join(ROCM700_LIBS)


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
        _row(
            "rocm.variant",
            ROCM700_VARIANT,
            provenance,
            "published wheel identity for this vLLM pin",
            ROCM700_VARIANT,
        ),
        _row(
            "rocm.line",
            "7.0",
            provenance,
            "rocm700 is the ROCm 7.0 line, not a minimum",
            "7.0",
        ),
        _row(
            "glibc.minimum",
            "2.35",
            provenance,
            "rocm700 wheel requires this glibc",
            ">=2.35",
        ),
        _row(
            "native.libraries",
            _LIB_TEXT,
            provenance,
            "sonames the rocm700 build loads",
            _LIB_TEXT,
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
        rocm_recipe=rocm700_recipe(),
        settings=rows,
    )


def rocm700_recipe() -> RuntimeRecipe:
    """The only AMD recipe for the pinned vLLM version."""
    return RuntimeRecipe(
        recipe_id=f"vllm-{DEFAULT_VLLM}-{ROCM700_VARIANT}",
        engine=FoundationEngine.VLLM,
        vllm_version=DEFAULT_VLLM,
        variant=ROCM700_VARIANT,
        python_version=DEFAULT_PYTHON,
        rocm_line="7.0",
        glibc_minimum="2.35",
        accelerator_architectures=_ARCH_TEXT,
        native_libraries=_LIB_TEXT,
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
