"""Default Capacity policy. Writes stay off until an explicit bounded run."""

from __future__ import annotations

from machi.capacity.contracts import (
    CapacitySetting,
    CapacitySettingProvenance,
    CapacitySettings,
    CapacitySettingSupport,
    SonarWritePolicy,
)

GIB = 1024 * 1024 * 1024
DEFAULT_MEMORY_RESERVE = GIB // 2
DEFAULT_ACCELERATOR_RESERVE = GIB // 4
DEFAULT_STORAGE_RESERVE = GIB
DEFAULT_SONAR_MAX_TIER = 256 * GIB

# Production Sonar ladder. Tests pass a smaller schedule with the same roles.
UPWARD_GIB = (64, 128, 256)
REFINE_GIB = (96, 192)
DOWNWARD_GIB = (48, 32, 24, 16)


def production_schedule() -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    """Upward, refinement, and downward tiers in bytes."""
    return (
        tuple(item * GIB for item in UPWARD_GIB),
        tuple(item * GIB for item in REFINE_GIB),
        tuple(item * GIB for item in DOWNWARD_GIB),
    )


def default_capacity_settings(
    *,
    sonar_writes: SonarWritePolicy = SonarWritePolicy.DISABLED,
    sonar_max_tier_bytes: int = DEFAULT_SONAR_MAX_TIER,
    memory_reserve_bytes: int = DEFAULT_MEMORY_RESERVE,
    accelerator_reserve_bytes: int = DEFAULT_ACCELERATOR_RESERVE,
    storage_reserve_bytes: int = DEFAULT_STORAGE_RESERVE,
    admin_fallback: str = "allow",
    provenance: CapacitySettingProvenance = CapacitySettingProvenance.PRODUCT_DEFAULT,
) -> CapacitySettings:
    """Safe defaults. Sonar writes do not run until explicitly bounded."""
    rows = (
        _setting(
            "memory.reserve_bytes",
            str(memory_reserve_bytes),
            provenance,
            "headroom below the RAM hard ceiling",
            "non-negative integer",
        ),
        _setting(
            "accelerator.reserve_bytes",
            str(accelerator_reserve_bytes),
            provenance,
            "headroom below each discrete accelerator total",
            "non-negative integer",
        ),
        _setting(
            "storage.reserve_bytes",
            str(storage_reserve_bytes),
            provenance,
            "bytes Sonar and SAFE storage must leave untouched",
            "non-negative integer",
        ),
        _setting(
            "sonar.writes",
            sonar_writes.value,
            provenance,
            "product default does not write; a bounded run must opt in",
            "disabled,bounded",
        ),
        _setting(
            "sonar.max_tier_bytes",
            str(sonar_max_tier_bytes),
            provenance,
            "largest tier a bounded Sonar run may attempt",
            "positive integer",
        ),
        _setting(
            "admin.fallback",
            admin_fallback,
            provenance,
            "an administrator ceiling is last resort and cannot raise a hard proof",
            "allow,deny",
        ),
    )
    return CapacitySettings(
        memory_reserve_bytes=memory_reserve_bytes,
        accelerator_reserve_bytes=accelerator_reserve_bytes,
        storage_reserve_bytes=storage_reserve_bytes,
        sonar_writes=sonar_writes,
        sonar_max_tier_bytes=sonar_max_tier_bytes,
        admin_fallback=admin_fallback,
        settings=rows,
    )


def _setting(
    name: str,
    value: str,
    provenance: CapacitySettingProvenance,
    reason: str,
    allowed: str,
) -> CapacitySetting:
    return CapacitySetting(
        name=name,
        value=value,
        provenance=provenance,
        reason=reason,
        allowed_values=allowed,
        support_state=CapacitySettingSupport.SUPPORTED,
        mutability="runtime",
        invalidation="recompute",
    )
