from core.config import (
    load_config,
)

from core.storage_budget import (
    evaluate_storage_operation,
)

from core.storage_planning import (
    build_storage_plan,
)

from core.storage_probe import (
    probe_required_capacity,
)


STORAGE_COMMIT_ADMISSION_SCHEMA_VERSION = 1


def _decision(
    *,
    allowed,
    reason,
    requirement,
    storage_plan,
    operation_evaluation=None,
    verification=None,
    retryable=False,
):
    budget = (
        storage_plan.get(
            "platform_budget",
            {},
        )
        if isinstance(
            storage_plan,
            dict,
        )
        else {}
    )

    capacity = (
        storage_plan.get(
            "capacity",
            {},
        )
        if isinstance(
            storage_plan,
            dict,
        )
        else {}
    )

    resolved_capacity = (
        capacity.get(
            "resolved",
            {},
        )
        if isinstance(
            capacity,
            dict,
        )
        else {}
    )

    return {
        "schema_version": (
            STORAGE_COMMIT_ADMISSION_SCHEMA_VERSION
        ),

        "allowed": bool(
            allowed
        ),

        "decision": (
            "allow"
            if allowed
            else "deny"
        ),

        "reason": reason,

        "retryable": bool(
            retryable
        ),

        "requirement": requirement,

        "operation_evaluation": (
            operation_evaluation
        ),

        "verification": verification,

        "state": {
            "capacity_source": (
                storage_plan.get(
                    "capacity_source"
                )
                if isinstance(
                    storage_plan,
                    dict,
                )
                else None
            ),

            "capacity_basis": (
                resolved_capacity.get(
                    "basis"
                )
            ),

            "capacity_confidence": (
                resolved_capacity.get(
                    "confidence"
                )
            ),

            "platform_budget_resolved": (
                budget.get(
                    "resolved"
                )
            ),

            "platform_used_bytes": (
                budget.get(
                    "platform_used_bytes"
                )
            ),

            "available_for_new_platform_bytes": (
                budget.get(
                    "available_for_new_platform_bytes"
                )
            ),
        },

        #
        # IMPORTANT:
        #
        # probe_required_capacity() is point-in-time verification.
        # Its temporary reservation is removed before this function
        # returns.
        #
        # Actual mutation serialization / locking is therefore a
        # separate safety boundary to be integrated later.
        #
        "guarantee": {
            "planning_state_rechecked": True,

            "operation_size_required": True,

            "point_in_time_capacity_verified": bool(
                allowed
            ),

            "reservation_held_during_mutation": False,

            "mutation_serialization_required": True,
        },
    }


def evaluate_storage_commit_admission(
    requirement,
    *,
    config=None,
    storage_plan=None,
    verify_now=True,
    probe=None,
):
    """
    Evaluate whether one storage-mutating operation may COMMIT now.

    This is stricter than planning-time compatibility.

    Hard commit requires:

        1. resolved operation requirement
        2. HIGH-confidence artifact sizing
        3. current resolved platform storage budget
        4. peak additional storage fits that current budget
        5. operation-sized point-in-time verification succeeds

    Medium-confidence estimates, including the current Hugging Face
    repository-size estimate, are deliberately NOT promoted to hard
    commit authorization.

    The caller may inject a probe for deterministic tests.

    This function does NOT execute the model mutation.
    """

    if config is None:
        config = load_config()

    if not isinstance(
        requirement,
        dict,
    ):
        raise ValueError(
            "requirement must be a dictionary"
        )

    if storage_plan is None:
        storage_plan = (
            build_storage_plan(
                config=config,
                calibrate_if_required=False,
            )
        )

    #
    # 1. Requirement must be resolved.
    #

    if not requirement.get(
        "resolved",
        False,
    ):
        return _decision(
            allowed=False,

            reason=(
                "operation_storage_requirement_unresolved"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            retryable=True,
        )

    required_bytes = (
        requirement.get(
            "peak_additional_bytes"
        )
    )

    try:
        required_bytes = int(
            required_bytes
        )

    except (
        TypeError,
        ValueError,
    ):
        return _decision(
            allowed=False,

            reason=(
                "operation_peak_storage_invalid"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            retryable=False,
        )

    if required_bytes <= 0:
        return _decision(
            allowed=False,

            reason=(
                "operation_peak_storage_invalid"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            retryable=False,
        )

    #
    # 2. Commit requires high-confidence sizing.
    #
    # Planning may use medium-confidence estimates, but execution
    # must not silently convert an estimate into an exact promise.
    #

    confidence = (
        requirement.get(
            "confidence"
        )
        or "unknown"
    )

    if confidence != "high":
        return _decision(
            allowed=False,

            reason=(
                "operation_size_confidence_insufficient_for_commit"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            retryable=True,
        )

    #
    # 3. Current dynamic platform budget must be resolved.
    #

    budget = storage_plan.get(
        "platform_budget",
        {},
    )

    if not budget.get(
        "resolved",
        False,
    ):
        return _decision(
            allowed=False,

            reason=(
                "current_platform_storage_budget_unresolved"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            retryable=True,
        )

    #
    # 4. Peak ADDITIONAL requirement must fit the current dynamic
    # platform budget.
    #

    operation = (
        evaluate_storage_operation(
            storage_budget=budget,

            required_bytes=(
                required_bytes
            ),
        )
    )

    if not operation.get(
        "feasible",
        False,
    ):
        return _decision(
            allowed=False,

            reason=(
                "current_platform_storage_budget_exceeded"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            retryable=True,
        )

    #
    # 5. Planning fit is not enough for commit.
    #
    # If immediate verification was deliberately disabled, return
    # NO-GO rather than pretending the operation is authorized.
    #

    if not verify_now:
        return _decision(
            allowed=False,

            reason=(
                "final_operation_sized_verification_required"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            retryable=True,
        )

    if probe is None:

        def probe(
            requested_bytes,
        ):
            return probe_required_capacity(
                requested_bytes,
                config=config,
            )

    #
    # 6. Perform point-in-time operation-sized verification.
    #

    verification = probe(
        required_bytes
    )

    if not isinstance(
        verification,
        dict,
    ):
        return _decision(
            allowed=False,

            reason=(
                "operation_sized_verification_invalid"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            verification=(
                verification
            ),

            retryable=True,
        )

    supported = bool(
        verification.get(
            "supported",
            False,
        )
    )

    success = bool(
        verification.get(
            "success",
            False,
        )
    )

    accepted = bool(
        verification.get(
            "reservation_accepted",
            success,
        )
    )

    probe_reason = verification.get(
        "reason"
    )

    #
    # Probe mechanism unavailable.
    #

    if not supported:
        return _decision(
            allowed=False,

            reason=(
                "operation_sized_verification_unsupported"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            verification=(
                verification
            ),

            retryable=True,
        )

    #
    # Policy ceiling is NOT proof that storage is unavailable.
    #
    # It means our current verification mechanism is not permitted
    # to test a request this large.
    #

    if (
        not success
        and probe_reason
        == "probe_limit_exceeded"
    ):
        return _decision(
            allowed=False,

            reason=(
                "operation_sized_verification_policy_ceiling"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            verification=(
                verification
            ),

            retryable=True,
        )

    #
    # ENOSPC / quota failure is current empirical evidence that the
    # operation should not proceed.
    #

    if (
        not success
        or not accepted
    ):
        return _decision(
            allowed=False,

            reason=(
                "operation_sized_verification_failed"
            ),

            requirement=requirement,

            storage_plan=storage_plan,

            operation_evaluation=(
                operation
            ),

            verification=(
                verification
            ),

            retryable=True,
        )

    #
    # All current commit gates passed.
    #

    return _decision(
        allowed=True,

        reason=None,

        requirement=requirement,

        storage_plan=storage_plan,

        operation_evaluation=(
            operation
        ),

        verification=(
            verification
        ),

        retryable=False,
    )
