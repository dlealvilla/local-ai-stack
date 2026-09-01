"""
Vendor-neutral live resource-capacity normalization.

This module does NOT detect hardware directly.

Observation ownership remains:

    core.capacity_snapshot

This layer converts that observed snapshot into generic resource pools
that future Capacity Planner and Resource Manager logic can consume.

Core owns the concepts.
Hardware/runtime adapters remain responsible for implementations.
"""

from core.capacity_snapshot import (
    build_capacity_snapshot,
)


RESOURCE_CAPACITY_SCHEMA_VERSION = 1


def _first_known(
    mapping,
    keys,
):
    for key in keys:

        value = mapping.get(
            key
        )

        if value is not None:
            return value

    return None


def _normalize_nonnegative_int(
    value,
):
    if value is None:
        return None

    try:
        value = int(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

    return max(
        0,
        value,
    )


def _normalize_memory_values(
    memory,
    *,
    prefix=None,
):
    """
    Normalize known memory field spellings.

    The current capacity snapshot remains authoritative.

    Aliases are accepted here so this planning layer does not couple
    itself unnecessarily to NVIDIA-specific or temporary field names.
    """

    if not isinstance(
        memory,
        dict,
    ):
        return {
            "total_bytes": None,
            "used_bytes": None,
            "available_bytes": None,
        }


    prefixes = []

    if prefix:
        prefixes.append(
            prefix
        )


    total_keys = [
        "total_bytes",
    ]

    used_keys = [
        "used_bytes",
    ]

    available_keys = [
        "available_bytes",
        "free_bytes",
    ]


    for item in prefixes:

        total_keys.extend([
            f"{item}_total_bytes",
            f"total_{item}_bytes",
        ])

        used_keys.extend([
            f"{item}_used_bytes",
            f"used_{item}_bytes",
        ])

        available_keys.extend([
            f"{item}_available_bytes",
            f"{item}_free_bytes",
            f"available_{item}_bytes",
            f"free_{item}_bytes",
        ])


    total = _normalize_nonnegative_int(
        _first_known(
            memory,
            total_keys,
        )
    )

    used = _normalize_nonnegative_int(
        _first_known(
            memory,
            used_keys,
        )
    )

    available = _normalize_nonnegative_int(
        _first_known(
            memory,
            available_keys,
        )
    )


    #
    # Derive only mathematically equivalent values.
    # Do not guess unavailable capacity.
    #

    if (
        total is not None
        and available is not None
        and used is None
    ):
        used = max(
            0,
            total
            - available,
        )


    if (
        total is not None
        and used is not None
        and available is None
    ):
        available = max(
            0,
            total
            - used,
        )


    return {
        "total_bytes": total,
        "used_bytes": used,
        "available_bytes": available,
    }


def _system_memory_source(
    memory,
):
    if not isinstance(
        memory,
        dict,
    ):
        return {}


    nested = memory.get(
        "system"
    )


    if isinstance(
        nested,
        dict,
    ):
        return nested


    #
    # Current schema may expose RAM fields directly under the
    # top-level memory domain.
    #

    return memory


def _unified_memory_source(
    memory,
):
    if not isinstance(
        memory,
        dict,
    ):
        return None


    for key in (
        "unified",
        "unified_memory",
    ):

        candidate = memory.get(
            key
        )


        if isinstance(
            candidate,
            dict,
        ):
            return candidate


    return None


def _build_system_ram_pool(
    snapshot,
):
    source = _system_memory_source(
        snapshot.get(
            "memory"
        )
        or {}
    )


    capacity = _normalize_memory_values(
        source,
        prefix="ram",
    )


    if all(
        value is None
        for value in capacity.values()
    ):
        return None


    return {
        "pool_id": (
            "memory:system_ram"
        ),

        "resource_type": (
            "memory"
        ),

        "memory_type": (
            "system_ram"
        ),

        "scope": {
            "kind": (
                "host"
            ),
        },

        "capacity": (
            capacity
        ),

        "observation": {
            "source": (
                "capacity_snapshot"
            ),

            "live": True,
        },
    }


def _build_unified_memory_pool(
    snapshot,
):
    source = _unified_memory_source(
        snapshot.get(
            "memory"
        )
        or {}
    )


    if source is None:
        return None


    capacity = _normalize_memory_values(
        source,
        prefix="unified_memory",
    )


    if all(
        value is None
        for value in capacity.values()
    ):
        return None


    return {
        "pool_id": (
            "memory:unified"
        ),

        "resource_type": (
            "memory"
        ),

        "memory_type": (
            "unified_memory"
        ),

        "scope": {
            "kind": (
                "host"
            ),
        },

        "capacity": (
            capacity
        ),

        "observation": {
            "source": (
                "capacity_snapshot"
            ),

            "live": True,
        },
    }


def _accelerator_memory_type(
    accelerator,
):
    memory = (
        accelerator.get(
            "memory"
        )
        or {}
    )


    explicit = (
        memory.get(
            "type"
        )
        or memory.get(
            "memory_type"
        )
    )


    if explicit:
        return explicit


    vendor = str(
        accelerator.get(
            "vendor"
        )
        or ""
    ).lower()


    if vendor == "nvidia":
        return (
            "dedicated_vram"
        )


    #
    # Do not invent VRAM semantics for AMD/Intel/Apple or future
    # accelerator types when the observation adapter has not
    # classified the memory architecture.
    #

    return (
        "accelerator_memory"
    )


def _build_accelerator_memory_pools(
    snapshot,
):
    pools = []


    for position, accelerator in enumerate(
        snapshot.get(
            "accelerators"
        )
        or []
    ):

        if not isinstance(
            accelerator,
            dict,
        ):
            continue


        memory = (
            accelerator.get(
                "memory"
            )
            or {}
        )


        capacity = (
            _normalize_memory_values(
                memory,
                prefix="vram",
            )
        )


        if all(
            value is None
            for value in capacity.values()
        ):
            continue


        index = (
            accelerator.get(
                "index"
            )
        )


        if index is None:
            index = position


        pools.append({
            "pool_id": (
                f"accelerator:{index}:memory"
            ),

            "resource_type": (
                "memory"
            ),

            "memory_type": (
                _accelerator_memory_type(
                    accelerator
                )
            ),

            "scope": {
                "kind": (
                    "accelerator"
                ),

                "accelerator_index": (
                    index
                ),

                "vendor": (
                    accelerator.get(
                        "vendor"
                    )
                ),

                "name": (
                    accelerator.get(
                        "name"
                    )
                ),
            },

            "capacity": (
                capacity
            ),

            "observation": {
                "source": (
                    "capacity_snapshot"
                ),

                "live": True,
            },
        })


    return pools


def build_resource_capacity(
    snapshot=None,
):
    """
    Build a vendor-neutral live memory-capacity view.

    This answers:

        "What memory pools exist, and what is observed available now?"

    It deliberately does NOT yet answer:

        "Can model X start now?"

    Candidate model requirements, runtime overhead, safety reserves,
    concurrency and Resource Manager reservations are later dependency
    layers.
    """

    if snapshot is None:
        snapshot = (
            build_capacity_snapshot()
        )


    if not isinstance(
        snapshot,
        dict,
    ):
        raise TypeError(
            "capacity snapshot must be a mapping"
        )


    pools = []


    system_ram = (
        _build_system_ram_pool(
            snapshot
        )
    )


    if system_ram is not None:
        pools.append(
            system_ram
        )


    unified = (
        _build_unified_memory_pool(
            snapshot
        )
    )


    if unified is not None:
        pools.append(
            unified
        )


    pools.extend(
        _build_accelerator_memory_pools(
            snapshot
        )
    )


    workload = (
        snapshot.get(
            "workload"
        )
        or {}
    )


    return {
        "schema_version": (
            RESOURCE_CAPACITY_SCHEMA_VERSION
        ),

        "source": {
            "type": (
                "capacity_snapshot"
            ),

            "schema_version": (
                snapshot.get(
                    "schema_version"
                )
            ),

            "generated_at": (
                snapshot.get(
                    "generated_at"
                )
            ),
        },

        "resource_pools": (
            pools
        ),

        #
        # Phase 9 Resource Manager will own explicit reservations.
        #
        "reservations": (
            workload.get(
                "reservations"
            )
        ),

        "dependency_chain": [
            "live_capacity_snapshot",
            "normalized_resource_pools",
            "resource_safety_policy",
            "resource_manager_reservations",
            "candidate_model_requirements",
            "runtime_requirements",
            "dynamic_resource_admission",
        ],

        "admission_ready": False,

        "admission_not_ready_reasons": [
            "resource_safety_policy_not_applied",
            "candidate_model_requirements_not_applied",
            "runtime_requirements_not_applied",
            (
                "resource_manager_reservations_not_implemented"
                if workload.get(
                    "reservations"
                )
                is None
                else "dynamic_admission_not_applied"
            ),
        ],
    }
