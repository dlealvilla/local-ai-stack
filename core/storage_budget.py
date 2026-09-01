STORAGE_BUDGET_SCHEMA_VERSION = 1


def validate_platform_allocation_percent(
    value,
):
    """
    Validate administrator storage-allocation policy.

    100% means all SAFE feasible storage, never raw capacity.
    """

    try:
        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "platform_allocation_percent must be numeric"
        ) from exc

    if not (
        1.0
        <= value
        <= 100.0
    ):
        raise ValueError(
            "platform_allocation_percent must be "
            "between 1 and 100"
        )

    return value


def calculate_platform_storage_budget(
    *,
    capacity_resolution,
    platform_used_bytes,
    platform_allocation_percent,
):
    """
    Calculate how much NEW platform-managed storage may be added.

    There are two valid calculation modes.

    MODE A — TOTAL CAPACITY KNOWN
    -----------------------------
    Example:
        Provider quota = 500 GB

    We can calculate a durable total platform budget:

        total capacity
            - protected reserve
            = safe total pool

        safe total pool
            * platform allocation %
            = platform total budget

        platform total budget
            - current platform usage
            = policy remaining budget

    The actual amount that may be added now is then capped by
    current safe remaining storage.

    MODE B — ONLY CURRENT REMAINING CAPACITY KNOWN
    ----------------------------------------------
    Example:
        Sonar proves >= 80 GB currently reservable,
        but total volume quota is unknown.

    Existing platform usage is ALREADY reflected in current free
    storage and must NOT be subtracted again.

    Therefore:

        current safe remaining
            * platform allocation %
            = maximum new platform allocation

    This distinction prevents double-counting.
    """

    percent = (
        validate_platform_allocation_percent(
            platform_allocation_percent
        )
    )

    try:
        platform_used_bytes = int(
            platform_used_bytes
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "platform_used_bytes must be an integer"
        ) from exc

    if platform_used_bytes < 0:
        raise ValueError(
            "platform_used_bytes cannot be negative"
        )

    resolved = capacity_resolution.get(
        "resolved",
        {},
    )

    allocation_policy = (
        capacity_resolution.get(
            "allocation_policy",
            {},
        )
    )

    remaining_bytes = resolved.get(
        "remaining_bytes"
    )

    total_bytes = resolved.get(
        "effective_total_bytes"
    )

    reserve_bytes = allocation_policy.get(
        "reserve_bytes"
    )

    safe_remaining_bytes = (
        allocation_policy.get(
            "safe_allocatable_bytes"
        )
    )

    if (
        remaining_bytes is None
        or safe_remaining_bytes is None
    ):
        return {
            "schema_version": (
                STORAGE_BUDGET_SCHEMA_VERSION
            ),

            "resolved": False,

            "reason": (
                "safe_capacity_unresolved"
            ),

            "basis": None,

            "platform_allocation_percent": (
                percent
            ),

            "platform_used_bytes": (
                platform_used_bytes
            ),

            "safe_remaining_bytes": None,

            "safe_total_pool_bytes": None,

            "platform_total_budget_bytes": None,

            "platform_policy_remaining_bytes": None,

            "available_for_new_platform_bytes": None,
        }

    safe_remaining_bytes = int(
        safe_remaining_bytes
    )

    #
    # MODE A:
    # authoritative/credible total capacity exists.
    #

    if (
        total_bytes is not None
        and reserve_bytes is not None
    ):
        total_bytes = int(
            total_bytes
        )

        reserve_bytes = int(
            reserve_bytes
        )

        safe_total_pool = max(
            0,
            total_bytes
            - reserve_bytes,
        )

        platform_total_budget = int(
            safe_total_pool
            * (
                percent
                / 100.0
            )
        )

        platform_policy_remaining = max(
            0,
            platform_total_budget
            - platform_used_bytes,
        )

        #
        # Both constraints must hold:
        #
        # 1. Administrator platform budget.
        # 2. Host's current safe free-space limit.
        #

        available_for_new = min(
            safe_remaining_bytes,
            platform_policy_remaining,
        )

        basis = (
            "known_total_capacity"
        )

    #
    # MODE B:
    # only current remaining capacity is known.
    #

    else:
        safe_total_pool = None
        platform_total_budget = None
        platform_policy_remaining = None

        available_for_new = int(
            safe_remaining_bytes
            * (
                percent
                / 100.0
            )
        )

        basis = (
            "remaining_capacity_only"
        )

    return {
        "schema_version": (
            STORAGE_BUDGET_SCHEMA_VERSION
        ),

        "resolved": True,

        "reason": None,

        "basis": basis,

        "platform_allocation_percent": (
            percent
        ),

        "platform_used_bytes": (
            platform_used_bytes
        ),

        "safe_remaining_bytes": (
            safe_remaining_bytes
        ),

        "safe_total_pool_bytes": (
            safe_total_pool
        ),

        "platform_total_budget_bytes": (
            platform_total_budget
        ),

        "platform_policy_remaining_bytes": (
            platform_policy_remaining
        ),

        "available_for_new_platform_bytes": (
            available_for_new
        ),
    }


def evaluate_storage_operation(
    *,
    storage_budget,
    required_bytes,
):
    """
    Evaluate one proposed platform-managed storage operation.

    required_bytes must eventually include:

        final model artifact
        + transfer staging
        + conversion/quantization output
        + managed temporary/cache overhead

    It must NOT contain only the final model file size when the
    operation requires additional temporary storage.
    """

    try:
        required_bytes = int(
            required_bytes
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "required_bytes must be an integer"
        ) from exc

    if required_bytes < 0:
        raise ValueError(
            "required_bytes cannot be negative"
        )

    if not storage_budget.get(
        "resolved",
        False,
    ):
        return {
            "classification": "unknown",
            "feasible": None,
            "reason": (
                "platform_storage_budget_unresolved"
            ),
            "required_bytes": (
                required_bytes
            ),
            "available_bytes": None,
            "headroom_after_bytes": None,
        }

    available = int(
        storage_budget[
            "available_for_new_platform_bytes"
        ]
    )

    feasible = (
        required_bytes
        <= available
    )

    return {
        "classification": (
            "compatible"
            if feasible
            else "unsupported"
        ),

        "feasible": feasible,

        "reason": (
            None
            if feasible
            else (
                "platform_storage_budget_exceeded"
            )
        ),

        "required_bytes": (
            required_bytes
        ),

        "available_bytes": (
            available
        ),

        "headroom_after_bytes": (
            available
            - required_bytes
            if feasible
            else None
        ),
    }
