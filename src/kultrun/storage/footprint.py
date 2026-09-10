"""Base and runtime storage requirements. Conservative bounds, not slogans."""

from __future__ import annotations

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import StorageRequirement
from kultrun.storage.limits import LOW_SPACE_THRESHOLD_BYTES

_GIB = 1024**3

#: Sanity ranges only. Never used as the admitting requirement.
KULTRUN_PACKAGE_RANGE = (int(0.1 * _GIB), int(0.5 * _GIB))
VLLM_RUNTIME_RANGE = (8 * _GIB, 15 * _GIB)
BASE_WITHOUT_MODEL_RANGE = (9 * _GIB, 17 * _GIB)
PROVISION_PEAK_RANGE = (15 * _GIB, 25 * _GIB)

#: Conservative v1 defaults used when a runtime has no measured size yet.
#: These are estimates with LOW confidence, not hard-coded universal truth.
DEFAULT_KULTRUN_PERSISTENT_BYTES = int(0.3 * _GIB)
DEFAULT_VLLM_PERSISTENT_BYTES = 12 * _GIB
DEFAULT_INSTALL_CACHE_BYTES = 0  # --no-cache-dir: no managed pip cache
DEFAULT_RUNTIME_STAGING_BYTES = 12 * _GIB
DEFAULT_TELEMETRY_BASELINE_BYTES = 64 * 1024**2
DEFAULT_RESERVE_BYTES = LOW_SPACE_THRESHOLD_BYTES


def conservative_peak(*parts: Maybe[int]) -> Maybe[int]:
    """Sum resolved parts. Any unknown part makes the peak unknown."""
    total = 0
    for part in parts:
        if not is_resolved(part):
            return NOT_PROVIDED
        total += part
    return total


def base_platform_requirement(
    *,
    mount_point: Maybe[str] = NOT_PROVIDED,
    quota_identity: Maybe[str] = NOT_PROVIDED,
    runtime_persistent: int = DEFAULT_VLLM_PERSISTENT_BYTES,
) -> StorageRequirement:
    """Non-model burden. Conservative, not a midpoint."""
    persistent = (
        DEFAULT_KULTRUN_PERSISTENT_BYTES
        + runtime_persistent
        + DEFAULT_TELEMETRY_BASELINE_BYTES
    )
    # Capacity withholds reserve when forming SAFE. Do not add it again here
    # or ResourceManager double-counts the same 5 GiB.
    peak = persistent + DEFAULT_RUNTIME_STAGING_BYTES + DEFAULT_INSTALL_CACHE_BYTES
    return StorageRequirement(
        confidence=Confidence.LOW,
        persistent_bytes=persistent,
        peak_transient_bytes=DEFAULT_RUNTIME_STAGING_BYTES,
        cache_bytes=DEFAULT_INSTALL_CACHE_BYTES,
        reserve_bytes=DEFAULT_RESERVE_BYTES,
        required_peak_free_bytes=peak,
        mount_point=mount_point,
        quota_identity=quota_identity,
        source="storage.footprint.v1-estimate",
        notes=(
            "sanity: kultrun 0.1-0.5 GiB, vLLM 8-15 GiB, "
            "base without model 9-17 GiB, provisioning peak 15-25 GiB",
            "pip --no-cache-dir; no unmanaged user cache is deleted",
        ),
    )


def runtime_provisioning_requirement(
    *,
    mount_point: Maybe[str] = NOT_PROVIDED,
    quota_identity: Maybe[str] = NOT_PROVIDED,
    persistent_bytes: int = DEFAULT_VLLM_PERSISTENT_BYTES,
    measured: bool = False,
) -> StorageRequirement:
    """What realizing a managed runtime would cost on its destination pool."""
    staging = persistent_bytes
    peak = persistent_bytes + staging + DEFAULT_INSTALL_CACHE_BYTES
    return StorageRequirement(
        confidence=Confidence.MEDIUM if measured else Confidence.LOW,
        persistent_bytes=persistent_bytes,
        peak_transient_bytes=staging,
        cache_bytes=DEFAULT_INSTALL_CACHE_BYTES,
        reserve_bytes=DEFAULT_RESERVE_BYTES,
        required_peak_free_bytes=peak,
        mount_point=mount_point,
        quota_identity=quota_identity,
        source=(
            "storage.footprint.measured"
            if measured
            else "storage.footprint.v1-estimate"
        ),
        notes=("isolated venv + pip --no-cache-dir",),
    )


def model_acquisition_requirement(
    *,
    persistent_bytes: Maybe[int],
    peak_bytes: Maybe[int],
    mount_point: Maybe[str] = NOT_PROVIDED,
    quota_identity: Maybe[str] = NOT_PROVIDED,
) -> StorageRequirement:
    """Exact artifact metadata when present. Peak admits, not the midpoint."""
    peak = peak_bytes if is_resolved(peak_bytes) else persistent_bytes
    return StorageRequirement(
        confidence=Confidence.HIGH if is_resolved(persistent_bytes) else Confidence.LOW,
        persistent_bytes=persistent_bytes,
        peak_transient_bytes=(
            peak - persistent_bytes
            if is_resolved(peak) and is_resolved(persistent_bytes)
            else NOT_PROVIDED
        ),
        required_peak_free_bytes=peak,
        mount_point=mount_point,
        quota_identity=quota_identity,
        source="model.requirement",
        notes=("artifact persistent vs acquisition peak are distinct",),
    )


MODEL_SIZE_RANGES = (
    ("0.5-3B", int(0.5 * _GIB), 3 * _GIB),
    ("7-8B", 4 * _GIB, 8 * _GIB),
    ("12-14B", 8 * _GIB, 15 * _GIB),
    ("30-32B", 18 * _GIB, 25 * _GIB),
    ("70B", 35 * _GIB, 50 * _GIB),
)
