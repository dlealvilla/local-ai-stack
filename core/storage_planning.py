from core.config import load_config

from core.platform_storage_reconciliation import (
    reconcile_platform_storage_usage,
)

from core.storage_budget import (
    calculate_platform_storage_budget,
    evaluate_storage_operation,
)

from core.storage_capacity_calibration import (
    calibrate_storage_capacity,
)

from core.storage_capacity_evidence import (
    build_storage_evidence,
)

from core.storage_capacity_resolution import (
    resolve_storage_capacity,
)

from core.storage_characterization import (
    MODE_TRANSACTION,
    characterize_storage,
)


STORAGE_PLANNING_SCHEMA_VERSION = 1


def build_storage_plan(
    *,
    platform_used_bytes=None,
    config=None,
    calibrate_if_required=False,
    maximum_probe_bytes=None,
    empirical_evidence=None,
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

    empirical_evidence supplies already-observed capacity facts to the
    existing consensus resolver for THIS plan only. Supplying them
    writes nothing to the capacity cache, so a fact established to
    answer one decision cannot quietly become the platform's reported
    capacity.
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

        cache_valid = cache_status.get(
            "valid",
            False,
        )

        cached_evidence = (
            (
                cache_status.get(
                    "empirical_evidence"
                )
                or []
            )
            if cache_valid
            else []
        )

        evidence = [
            *cached_evidence,
            *(
                empirical_evidence
                or []
            ),
        ]

        capacity = (
            resolve_storage_capacity(
                config,

                empirical_evidence=(
                    evidence
                    or None
                ),
            )
        )

        if empirical_evidence:
            capacity_source = (
                "supplied_empirical_evidence"
            )

        elif cache_valid:
            capacity_source = (
                "valid_capacity_cache"
            )

        else:
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


#
# Each round costs one probe-free plan rebuild, so this is arithmetic
# rather than a search. Two rounds settle the current reserve policy;
# the remainder exist so a differently shaped future policy cannot be
# silently truncated into a wrong answer.
#
COMMIT_LOWER_BOUND_ROUNDS = 4


def _verified_lower_bound_evidence(
    lower_bound_bytes,
    *,
    required_bytes,
):
    """State exactly what a completed transaction probe proved.

    remaining_lower_bound means "at least this much was successfully
    reservable". It is deliberately neither a quota_total nor a
    remaining_point, because a probe that reserved N bytes says
    nothing about how much more exists, and either of those types
    would let one operation's proof be read back as a characterized
    description of the host.
    """

    return build_storage_evidence(
        evidence_id=(
            "commit_verified_lower_bound"
        ),

        source=(
            "storage_transaction_"
            "characterization"
        ),

        scope=(
            "commit_time_operation"
        ),

        evidence_type=(
            "remaining_lower_bound"
        ),

        value_bytes=(
            lower_bound_bytes
        ),

        confidence="medium",

        detail=(
            "Transaction-mode characterization "
            "reserved this many bytes for a commit "
            "requiring "
            + str(
                int(
                    required_bytes
                )
            )
            + " bytes."
        ),
    )


def _plan_with_lower_bound(
    lower_bound_bytes,
    *,
    required_bytes,
    config,
):
    """Rebuild the plan as if this lower bound were verified.

    The rounds below discard what they build. Only a plan built from
    an actually proven bound is ever returned to a caller.
    """

    return build_storage_plan(
        config=config,

        calibrate_if_required=False,

        empirical_evidence=[
            _verified_lower_bound_evidence(
                lower_bound_bytes,

                required_bytes=(
                    required_bytes
                ),
            ),
        ],
    )


def _lower_bound_needed_for_commit(
    required_bytes,
    *,
    config,
):
    """How much must be proven before this commit could be admitted.

    More than the operation itself: the protected reserve and the
    administrator allocation percentage are subtracted from whatever
    capacity is resolved, so proving exactly the operation size would
    leave the budget short by exactly the reserve and deny the very
    operation the proof was gathered for.

    That policy is asked rather than restated. A second copy of the
    reserve rule living here would be free to disagree with the one
    the budget layer actually applies.
    """

    target = int(
        required_bytes
    )

    for _ in range(
        COMMIT_LOWER_BOUND_ROUNDS
    ):
        plan = _plan_with_lower_bound(
            target,

            required_bytes=(
                required_bytes
            ),

            config=config,
        )

        budget = (
            plan.get(
                "platform_budget"
            )
            or {}
        )

        if not budget.get(
            "resolved",
            False,
        ):
            return None

        operation = (
            evaluate_storage_operation(
                storage_budget=budget,

                required_bytes=(
                    required_bytes
                ),
            )
        )

        if operation.get(
            "feasible",
            False,
        ):
            return target

        available = budget.get(
            "available_for_new_platform_bytes"
        )

        reserve = (
            (
                plan.get(
                    "capacity"
                )
                or {}
            ).get(
                "allocation_policy"
            )
            or {}
        ).get(
            "reserve_bytes"
        )

        if not isinstance(
            available,
            int,
        ) or not isinstance(
            reserve,
            int,
        ):
            return None

        #
        # Two deficits, and the larger governs. The shortfall alone
        # converges slowly once the reserve has already clamped the
        # budget to zero; the reserve alone ignores an allocation
        # percentage below 100.
        #
        candidate = max(
            target
            + (
                required_bytes
                - available
            ),

            required_bytes
            + reserve,
        )

        if candidate <= target:
            return None

        target = candidate

    return None


def build_storage_plan_for_commit(
    requirement,
    *,
    config=None,
    storage_plan=None,
    characterize=None,
):
    """Answer the storage question this one mutation actually asks.

    A host whose capacity has never been characterized resolves no
    platform storage budget, and commit admission then correctly
    refuses every mutation. Waiting for a full host characterization
    would make the first acquisition depend on a search for the
    pool's ceiling, which is precision no admission decision needs
    and which cost roughly 48 minutes the last time it ran.

    So the narrower question is asked instead: can THIS operation be
    satisfied right now? Transaction-mode characterization answers it
    against real bytes and stops as soon as the answer is decided,
    and the proof is folded into a plan rebuilt for this decision
    alone.

    The proof never reaches the capacity cache and never becomes the
    platform's reported capacity. "At least N bytes were reservable
    at commit time" is not "this host has N bytes of characterized
    capacity", and a figure produced to authorize one download must
    not come back later as a description of the server.

    Admission is not bypassed, weakened or replaced. A proof changes
    only what the plan can see; the caller runs exactly the admission
    it would otherwise have run, including that admission's own
    operation-sized verification.

    The unmodified plan is returned whenever the budget already
    resolves, the requirement is unusable or the proof comes back
    inconclusive, so every existing outcome keeps its existing
    meaning.
    """

    if config is None:
        config = load_config()

    if storage_plan is None:
        storage_plan = (
            build_storage_plan(
                config=config,

                calibrate_if_required=False,
            )
        )

    budget = (
        storage_plan.get(
            "platform_budget"
        )
        or {}
    )

    if budget.get(
        "resolved",
        False,
    ):
        return storage_plan

    if not requirement.get(
        "resolved",
        False,
    ):
        return storage_plan

    try:
        required_bytes = int(
            requirement.get(
                "peak_additional_bytes"
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return storage_plan

    if required_bytes <= 0:
        return storage_plan

    target = (
        _lower_bound_needed_for_commit(
            required_bytes,

            config=config,
        )
    )

    if target is None:
        return storage_plan

    if characterize is None:
        characterize = (
            characterize_storage
        )

    #
    # TRANSACTION mode only. HOST mode describes the server and is
    # the wrong question at commit time; the old accuracy-maximizing
    # calibration coordinator is the wrong mechanism entirely.
    #
    characterization = characterize(
        mode=MODE_TRANSACTION,

        required_bytes=target,

        config=config,
    )

    proven = (
        characterization
        or {}
    ).get(
        "conservative_usable_bytes"
    )

    #
    # A bounded, inconclusive or infeasible result proves nothing, and
    # nothing is exactly what may be assumed from it.
    #
    if (
        not isinstance(
            proven,
            int,
        )
        or proven < target
    ):
        return storage_plan

    return _plan_with_lower_bound(
        proven,

        required_bytes=(
            required_bytes
        ),

        config=config,
    )

