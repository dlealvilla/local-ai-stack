"""
Protected-resource policy for dynamic capacity planning.

Dependency order:

    live resource capacity
        ->
    protected reserve
        ->
    safe available before reservations
        ->
    Resource Manager reservations
        ->
    candidate model/runtime requirements
        ->
    dynamic admission

This module deliberately does NOT perform final model admission.
"""


from copy import deepcopy

from core.resource_capacity import (
    build_resource_capacity,
)


RESOURCE_SAFETY_SCHEMA_VERSION = 1

GIB = 1024 ** 3


DEFAULT_RESOURCE_SAFETY_POLICY = {
    "system_ram": {
        "reserve_fraction": 0.10,
        "minimum_reserve_bytes": (
            4 * GIB
        ),
    },

    "dedicated_vram": {
        "reserve_fraction": 0.10,
        "minimum_reserve_bytes": (
            1 * GIB
        ),
    },

    #
    # Unified memory can represent the same physical bytes as
    # system RAM. Treating them as independent pools would create
    # false capacity.
    #
    "unified_memory": {
        "strategy": (
            "shared_backing_unresolved"
        ),
    },

    #
    # Unknown accelerator-memory architectures fail closed until
    # their accounting semantics are classified.
    #
    "accelerator_memory": {
        "strategy": (
            "memory_architecture_unresolved"
        ),
    },
}


def _normalize_fraction(
    value,
):
    try:
        value = float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            "reserve_fraction must be numeric"
        )


    if (
        value < 0.0
        or value > 1.0
    ):
        raise ValueError(
            "reserve_fraction must be between "
            "0.0 and 1.0"
        )


    return value


def _normalize_nonnegative_int(
    value,
    *,
    field,
):
    try:
        value = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            field
            + " must be an integer"
        )


    if value < 0:
        raise ValueError(
            field
            + " must be non-negative"
        )


    return value


def _resolve_independent_memory_policy(
    *,
    total_bytes,
    available_bytes,
    policy,
):
    if (
        total_bytes is None
        or available_bytes is None
    ):
        return {
            "resolved": False,

            "reason": (
                "live_memory_capacity_unresolved"
            ),

            "protected_reserve_bytes": None,

            "safe_available_before_reservations_bytes": (
                None
            ),
        }


    total_bytes = (
        _normalize_nonnegative_int(
            total_bytes,
            field="total_bytes",
        )
    )

    available_bytes = (
        _normalize_nonnegative_int(
            available_bytes,
            field="available_bytes",
        )
    )


    fraction = (
        _normalize_fraction(
            policy.get(
                "reserve_fraction"
            )
        )
    )


    minimum = (
        _normalize_nonnegative_int(
            policy.get(
                "minimum_reserve_bytes"
            ),
            field=(
                "minimum_reserve_bytes"
            ),
        )
    )


    proportional = int(
        total_bytes
        * fraction
    )


    #
    # Reserve cannot exceed physical pool capacity.
    #

    protected = min(
        total_bytes,

        max(
            proportional,
            minimum,
        ),
    )


    safe_available = max(
        0,

        available_bytes
        - protected,
    )


    return {
        "resolved": True,

        "reason": None,

        "reserve_fraction": (
            fraction
        ),

        "minimum_reserve_bytes": (
            minimum
        ),

        "proportional_reserve_bytes": (
            proportional
        ),

        "protected_reserve_bytes": (
            protected
        ),

        "safe_available_before_reservations_bytes": (
            safe_available
        ),
    }


def _evaluate_pool(
    pool,
    policy,
):
    evaluated = deepcopy(
        pool
    )


    memory_type = (
        pool.get(
            "memory_type"
        )
    )


    capacity = (
        pool.get(
            "capacity"
        )
        or {}
    )


    type_policy = (
        policy.get(
            memory_type
        )
        or {}
    )


    if memory_type in {
        "system_ram",
        "dedicated_vram",
    }:

        safety = (
            _resolve_independent_memory_policy(
                total_bytes=(
                    capacity.get(
                        "total_bytes"
                    )
                ),

                available_bytes=(
                    capacity.get(
                        "available_bytes"
                    )
                ),

                policy=(
                    type_policy
                ),
            )
        )


    elif memory_type == "unified_memory":

        safety = {
            "resolved": False,

            "reason": (
                "shared_physical_memory_accounting_unresolved"
            ),

            "strategy": (
                type_policy.get(
                    "strategy",
                    "shared_backing_unresolved",
                )
            ),

            "protected_reserve_bytes": None,

            "safe_available_before_reservations_bytes": (
                None
            ),
        }


    else:

        safety = {
            "resolved": False,

            "reason": (
                "memory_architecture_unresolved"
            ),

            "strategy": (
                type_policy.get(
                    "strategy",
                    "memory_architecture_unresolved",
                )
            ),

            "protected_reserve_bytes": None,

            "safe_available_before_reservations_bytes": (
                None
            ),
        }


    evaluated[
        "safety"
    ] = safety


    return evaluated


def build_resource_safety(
    resource_capacity=None,
    *,
    policy=None,
):
    """
    Apply protected headroom to normalized live memory pools.

    This answers:

        "How much observed memory remains after the platform's
         protected reserve?"

    It intentionally does NOT subtract future explicit Resource
    Manager reservations and does NOT compare a candidate model's
    runtime requirements.
    """

    if resource_capacity is None:
        resource_capacity = (
            build_resource_capacity()
        )


    if policy is None:
        policy = (
            DEFAULT_RESOURCE_SAFETY_POLICY
        )


    policy = deepcopy(
        policy
    )


    evaluated_pools = [
        _evaluate_pool(
            pool,
            policy,
        )

        for pool in (
            resource_capacity.get(
                "resource_pools"
            )
            or []
        )
    ]


    unresolved = [
        pool[
            "pool_id"
        ]

        for pool in evaluated_pools

        if not (
            pool.get(
                "safety",
                {}
            ).get(
                "resolved"
            )
        )
    ]


    reservations = (
        resource_capacity.get(
            "reservations"
        )
    )


    reasons = []


    if unresolved:
        reasons.append(
            "one_or_more_resource_policies_unresolved"
        )


    if reservations is None:
        reasons.append(
            "resource_manager_reservations_not_implemented"
        )


    reasons.extend([
        "candidate_model_requirements_not_applied",
        "runtime_requirements_not_applied",
        "dynamic_resource_admission_not_applied",
    ])


    return {
        "schema_version": (
            RESOURCE_SAFETY_SCHEMA_VERSION
        ),

        "source": {
            "type": (
                "resource_capacity"
            ),

            "schema_version": (
                resource_capacity.get(
                    "schema_version"
                )
            ),
        },

        "policy": (
            policy
        ),

        "resource_pools": (
            evaluated_pools
        ),

        "reservations": (
            reservations
        ),

        "unresolved_pool_ids": (
            unresolved
        ),

        "dependency_chain": [
            "live_capacity_snapshot",
            "normalized_resource_pools",
            "protected_resource_reserve",
            "safe_available_before_reservations",
            "resource_manager_reservations",
            "candidate_model_requirements",
            "runtime_requirements",
            "dynamic_resource_admission",
        ],

        "admission_ready": False,

        "admission_not_ready_reasons": (
            reasons
        ),
    }
