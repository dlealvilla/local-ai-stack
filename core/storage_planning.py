from core.config import load_config

from core.platform_storage_reconciliation import (
    reconcile_platform_storage_usage,
)

from core.storage_budget import (
    calculate_platform_storage_budget,
)

from core.storage_capacity_calibration import (
    calibrate_storage_capacity,
)

from core.storage_capacity_resolution import (
    resolve_storage_capacity,
)


STORAGE_PLANNING_SCHEMA_VERSION = 1


def build_storage_plan(
    *,
    platform_used_bytes=None,
    config=None,
    calibrate_if_required=False,
    maximum_probe_bytes=None,
):
    """
    Build one dependency-consistent storage plan.

    IMPORTANT:
    Cached empirical capacity evidence is dynamic planning evidence,
    not immutable host/model metadata.

    Cache validation itself depends on CURRENT reconciled platform
    usage, so the observation sequence is:

        current platform storage usage
            ->
        cached-capacity validity
            ->
        capacity evidence resolution
            ->
        protected reserve
            ->
        administrator allocation percentage
            ->
        platform storage budget
            ->
        model-operation storage feasibility

    A valid cached calibration must still satisfy:

        TTL
        storage identity
        storage generation
        current reconciled platform usage

    Actual large storage mutations will later receive a final
    current-state operation admission / reservation verification.

    platform_used_bytes remains an optional explicit budgeting input
    for tests and integration callers.

    IMPORTANT:
    The explicit override does NOT control cache validity.
    Cache validity always uses the actually measured/reconciled
    platform storage usage.
    """

    if config is None:
        config = load_config()

    from core.storage_capacity_cache import (
        get_capacity_cache_status,
    )

    #
    # 1. Observe CURRENT platform-managed usage first.
    #
    # This is required before capacity-cache validation because the
    # cached calibration is tied to the platform usage snapshot that
    # existed when the calibration was recorded.
    #

    usage_reconciliation = (
        reconcile_platform_storage_usage(
            config
        )
    )

    usage = (
        usage_reconciliation[
            "filesystem"
        ][
            "raw"
        ]
    )

    measured_platform_used = (
        usage_reconciliation.get(
            "total_platform_used_bytes"
        )
    )

    if measured_platform_used is not None:
        measured_platform_used = int(
            measured_platform_used
        )

    #
    # The explicit override remains useful for synthetic testing or
    # future callers, but it must never make stale cached capacity
    # evidence appear valid.
    #

    if platform_used_bytes is None:
        resolved_platform_used = (
            measured_platform_used
        )

        usage_source = (
            "reconciled_platform_storage"
        )

    else:
        resolved_platform_used = int(
            platform_used_bytes
        )

        usage_source = (
            "explicit_override"
        )

    #
    # 2. Validate reusable empirical capacity evidence against the
    # ACTUAL current platform usage.
    #

    if measured_platform_used is None:
        cache_status = {
            "valid": False,

            "reason": (
                "platform_usage_unresolved"
            ),
        }

    else:
        cache_status = (
            get_capacity_cache_status(
                current_platform_used_bytes=(
                    measured_platform_used
                ),

                config=config,
            )
        )

    #
    # 3. Resolve capacity.
    #
    # Explicit fresh calibration always wins for that call.
    #
    # Otherwise a VALID cache contributes its empirical lower/upper
    # bounds to the EXISTING consensus resolver.
    #
    # Invalid cache contents are never passed to the resolver.
    #

    if calibrate_if_required:
        calibration = (
            calibrate_storage_capacity(
                config=config,

                maximum_probe_bytes=(
                    maximum_probe_bytes
                ),
            )
        )

        capacity = calibration[
            "after"
        ]

        if calibration.get(
            "performed",
            False,
        ):
            capacity_source = (
                "fresh_calibration"
            )

        else:
            capacity_source = (
                "live_capacity_evidence"
            )

    else:
        calibration = None

        if cache_status.get(
            "valid",
            False,
        ):
            cached_evidence = (
                cache_status.get(
                    "empirical_evidence"
                )
                or []
            )

            capacity = (
                resolve_storage_capacity(
                    config,

                    empirical_evidence=(
                        cached_evidence
                    ),
                )
            )

            capacity_source = (
                "valid_capacity_cache"
            )

        else:
            capacity = (
                resolve_storage_capacity(
                    config
                )
            )

            capacity_source = (
                "live_capacity_evidence"
            )

    #
    # 4. Apply policy and current usage to calculate the platform
    # storage budget.
    #

    settings = config.get(
        "storage_capacity",
        {},
    )

    allocation_percent = (
        settings.get(
            "platform_allocation_percent",
            100.0,
        )
    )

    if resolved_platform_used is None:
        budget = {
            "schema_version": 1,

            "resolved": False,

            "reason": (
                "platform_usage_unresolved"
            ),

            "basis": None,

            "platform_allocation_percent": float(
                allocation_percent
            ),

            "platform_used_bytes": None,

            "safe_remaining_bytes": None,

            "safe_total_pool_bytes": None,

            "platform_total_budget_bytes": None,

            "platform_policy_remaining_bytes": None,

            "available_for_new_platform_bytes": None,
        }

    else:
        budget = (
            calculate_platform_storage_budget(
                capacity_resolution=capacity,

                platform_used_bytes=(
                    resolved_platform_used
                ),

                platform_allocation_percent=(
                    allocation_percent
                ),
            )
        )

    return {
        "schema_version": (
            STORAGE_PLANNING_SCHEMA_VERSION
        ),

        "capacity": capacity,

        "capacity_source": (
            capacity_source
        ),

        "capacity_cache": (
            cache_status
        ),

        "calibration": calibration,

        "platform_usage": usage,

        "platform_usage_reconciliation": (
            usage_reconciliation
        ),

        "platform_usage_source": (
            usage_source
        ),

        "platform_budget": budget,

        "dependency_chain": [
            "current_platform_storage_usage",
            "capacity_cache_validation",
            "capacity_evidence",
            "resolved_remaining_capacity",
            "protected_storage_reserve",
            "safe_current_remaining_capacity",
            "platform_allocation_percent",
            "platform_storage_budget",
            "available_for_new_platform_storage",
            "model_operation_storage_feasibility",
        ],
    }

