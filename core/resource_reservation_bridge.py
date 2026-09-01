"""Phase 8 -> Phase 9 resource reservation bridge.

AI_DEPLOYMENT_PHASE9_RESOURCE_RESERVATION_BRIDGE_V1

This module is intentionally thin.

Phase 8 owns:
- resource observation;
- safety margins;
- safe resource-pool capacities;
- model feasibility;
- runtime requirement estimation.

Phase 9 owns:
- active workload reservations;
- dynamic admission;
- workload lifecycle.

The bridge preserves Phase 8 pool IDs and consumes the exact Phase 8 v1
schema instead of inventing another hardware vocabulary.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from core.model_feasibility import evaluate_all_inventory_models
from core.resource_capacity import build_resource_capacity
from core.resource_safety import build_resource_safety


ResourceMap = dict[str, int]


class ResourceReservationBridgeError(RuntimeError):
    """Phase 8 state cannot safely be translated into Phase 9 resources."""


TARGET_REQUIREMENT_BY_MEMORY_TYPE = {
    "system_ram": "system_ram_bytes",
    "dedicated_vram": "dedicated_vram_bytes",
    "unified_memory": "unified_memory_bytes",
}


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int) and value >= 0:
        return value

    return None


def _positive_int(value: Any) -> int | None:
    value = _nonnegative_int(value)

    if value is None or value <= 0:
        return None

    return value


def _resolved_pool_records(
    resource_safety: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(resource_safety, Mapping):
        raise ResourceReservationBridgeError(
            "resource_safety must be a mapping"
        )

    pools = resource_safety.get("resource_pools")

    if not isinstance(pools, list):
        raise ResourceReservationBridgeError(
            "resource_safety.resource_pools must be a list"
        )

    unresolved = {
        str(pool_id)
        for pool_id in (
            resource_safety.get("unresolved_pool_ids")
            or []
        )
    }

    result: list[dict[str, Any]] = []
    seen_pool_ids: set[str] = set()

    for raw_pool in pools:
        if not isinstance(raw_pool, Mapping):
            raise ResourceReservationBridgeError(
                "every resource pool must be a mapping"
            )

        pool_id = raw_pool.get("pool_id")
        memory_type = raw_pool.get("memory_type")

        if not isinstance(pool_id, str) or not pool_id.strip():
            raise ResourceReservationBridgeError(
                "resource pool has no valid pool_id"
            )

        pool_id = pool_id.strip()

        if pool_id in seen_pool_ids:
            raise ResourceReservationBridgeError(
                f"duplicate Phase 8 pool_id: {pool_id}"
            )

        seen_pool_ids.add(pool_id)

        if pool_id in unresolved:
            continue

        if not isinstance(memory_type, str) or not memory_type.strip():
            raise ResourceReservationBridgeError(
                f"resource pool {pool_id} has no memory_type"
            )

        safety = raw_pool.get("safety")

        if not isinstance(safety, Mapping):
            raise ResourceReservationBridgeError(
                f"resource pool {pool_id} has no safety mapping"
            )

        if safety.get("resolved") is not True:
            continue

        safe_bytes = _nonnegative_int(
            safety.get(
                "safe_available_before_reservations_bytes"
            )
        )

        if safe_bytes is None:
            raise ResourceReservationBridgeError(
                "resolved resource pool has no valid "
                "safety.safe_available_before_reservations_bytes: "
                f"{pool_id}"
            )

        result.append(
            {
                "pool_id": pool_id,
                "memory_type": memory_type.strip(),
                "safe_available_before_reservations_bytes":
                    safe_bytes,
            }
        )

    if not result:
        raise ResourceReservationBridgeError(
            "no resolved Phase 8 resource pools are available"
        )

    return result


def reservation_capacities_from_resource_safety(
    resource_safety: Mapping[str, Any],
) -> ResourceMap:
    """Return Phase 9 capacities while preserving Phase 8 pool IDs."""

    return {
        pool["pool_id"]:
            pool["safe_available_before_reservations_bytes"]
        for pool in _resolved_pool_records(resource_safety)
    }


def _pools_by_memory_type(
    resource_safety: Mapping[str, Any],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)

    for pool in _resolved_pool_records(resource_safety):
        result[pool["memory_type"]].append(
            pool["pool_id"]
        )

    return dict(result)


def _single_pool_for_memory_type(
    pools_by_type: Mapping[str, list[str]],
    memory_type: str,
) -> str:
    pools = list(
        pools_by_type.get(memory_type) or []
    )

    if not pools:
        raise ResourceReservationBridgeError(
            "no resolved resource pool exists for memory type "
            f"{memory_type}"
        )

    if len(pools) != 1:
        raise ResourceReservationBridgeError(
            "multiple resource pools exist for memory type "
            f"{memory_type}; Phase 9 v1 refuses to guess placement"
        )

    return pools[0]


def _exact_target_requirements(
    model: Mapping[str, Any],
    *,
    pools_by_type: Mapping[str, list[str]],
) -> ResourceMap | None:
    requirements = model.get(
        "model_resource_requirements"
    )

    if not isinstance(requirements, Mapping):
        return None

    if requirements.get("runtime_requirements_ready") is not True:
        return None

    target = requirements.get("target_requirements")

    if not isinstance(target, Mapping):
        raise ResourceReservationBridgeError(
            "runtime requirements are marked ready but "
            "target_requirements is not a mapping"
        )

    result: ResourceMap = {}

    for memory_type, target_key in (
        TARGET_REQUIREMENT_BY_MEMORY_TYPE.items()
    ):
        required_bytes = _positive_int(
            target.get(target_key)
        )

        if required_bytes is None:
            continue

        pool_id = _single_pool_for_memory_type(
            pools_by_type,
            memory_type,
        )

        result[pool_id] = required_bytes

    if not result:
        raise ResourceReservationBridgeError(
            "runtime requirements are marked ready but "
            "no positive target requirements are resolved"
        )

    return result


def _provisional_requirement(
    model: Mapping[str, Any],
    *,
    pools_by_type: Mapping[str, list[str]],
) -> ResourceMap:
    dimensions = model.get("dimensions")

    if not isinstance(dimensions, Mapping):
        raise ResourceReservationBridgeError(
            "model has no dimensions mapping"
        )

    memory = dimensions.get("memory")

    if not isinstance(memory, Mapping):
        raise ResourceReservationBridgeError(
            "model has no memory feasibility dimension"
        )

    provisional = memory.get("provisional_estimate")

    if not isinstance(provisional, Mapping):
        raise ResourceReservationBridgeError(
            "model has no provisional memory estimate"
        )

    if provisional.get("resolved") is not True:
        raise ResourceReservationBridgeError(
            "provisional memory estimate is unresolved"
        )

    target_bytes = _positive_int(
        provisional.get(
            "estimated_runtime_target_bytes"
        )
    )

    if target_bytes is None:
        raise ResourceReservationBridgeError(
            "resolved provisional memory estimate has no positive "
            "estimated_runtime_target_bytes"
        )

    # Phase 8's current memory feasibility explicitly evaluates the
    # provisional runtime target against dedicated VRAM when available.
    #
    # For Phase 9 v1 we preserve that conservative placement:
    # dedicated VRAM -> unified memory -> system RAM.
    #
    # We deliberately refuse to split one provisional requirement across
    # multiple pools or multiple accelerators.
    for memory_type in (
        "dedicated_vram",
        "unified_memory",
        "system_ram",
    ):
        pools = pools_by_type.get(memory_type) or []

        if not pools:
            continue

        pool_id = _single_pool_for_memory_type(
            pools_by_type,
            memory_type,
        )

        return {
            pool_id: target_bytes,
        }

    raise ResourceReservationBridgeError(
        "no resolved memory pool is available for "
        "the provisional runtime estimate"
    )


def resolve_model_reservation_requirement(
    model: Mapping[str, Any],
    *,
    resource_safety: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve one model to a Phase 9 reservation requirement.

    Resolution order:

    1. Exact target requirements, only when Phase 8 says
       runtime_requirements_ready=True.
    2. Explicitly resolved Phase 8 provisional estimate.
    3. Fail closed.

    Phase 9 never invents a runtime-memory number.
    """

    if not isinstance(model, Mapping):
        raise ResourceReservationBridgeError(
            "model feasibility record must be a mapping"
        )

    model_id = model.get("model_id")

    if not isinstance(model_id, str) or not model_id.strip():
        raise ResourceReservationBridgeError(
            "model feasibility record has no model_id"
        )

    model_id = model_id.strip()

    pools_by_type = _pools_by_memory_type(
        resource_safety
    )

    exact = _exact_target_requirements(
        model,
        pools_by_type=pools_by_type,
    )

    if exact is not None:
        requirements = model.get(
            "model_resource_requirements"
        ) or {}

        return {
            "model_id": model_id,
            "resolved": True,
            "basis": "exact_target_requirements",
            "confidence": "runtime_resolved",
            "requirements": exact,
            "runtime_requirements_ready":
                requirements.get(
                    "runtime_requirements_ready"
                ),
        }

    provisional = _provisional_requirement(
        model,
        pools_by_type=pools_by_type,
    )

    memory = (
        model.get("dimensions", {})
        .get("memory", {})
    )

    provisional_metadata = (
        memory.get("provisional_estimate", {})
    )

    requirements_metadata = model.get(
        "model_resource_requirements"
    ) or {}

    return {
        "model_id": model_id,
        "resolved": True,
        "basis": "provisional_estimate",
        "confidence":
            provisional_metadata.get("confidence")
            or memory.get("confidence"),
        "requirements": provisional,
        "runtime_requirements_ready":
            requirements_metadata.get(
                "runtime_requirements_ready"
            ),
        "provisional_method":
            provisional_metadata.get("method"),
        "provisional_reason":
            provisional_metadata.get("reason"),
    }


def reservation_requirement_resolutions_by_model(
    feasibility_result: Mapping[str, Any],
    *,
    resource_safety: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    if not isinstance(feasibility_result, Mapping):
        raise ResourceReservationBridgeError(
            "feasibility_result must be a mapping"
        )

    models = feasibility_result.get("models")

    if not isinstance(models, list):
        raise ResourceReservationBridgeError(
            "feasibility_result.models must be a list"
        )

    result: dict[str, dict[str, Any]] = {}

    for model in models:
        resolution = resolve_model_reservation_requirement(
            model,
            resource_safety=resource_safety,
        )

        model_id = resolution["model_id"]

        if model_id in result:
            raise ResourceReservationBridgeError(
                f"duplicate model_id in feasibility result: {model_id}"
            )

        result[model_id] = resolution

    return result


def reservation_requirements_by_model(
    feasibility_result: Mapping[str, Any],
    *,
    resource_safety: Mapping[str, Any],
) -> dict[str, ResourceMap]:
    resolutions = (
        reservation_requirement_resolutions_by_model(
            feasibility_result,
            resource_safety=resource_safety,
        )
    )

    return {
        model_id: dict(
            resolution["requirements"]
        )
        for model_id, resolution in resolutions.items()
    }


def build_live_reservation_view() -> dict[str, Any]:
    """Build the read-only Phase 8 -> Phase 9 handoff view."""

    resource_capacity = build_resource_capacity()

    resource_safety = build_resource_safety(
        resource_capacity=resource_capacity,
    )

    feasibility = evaluate_all_inventory_models()

    capacities = (
        reservation_capacities_from_resource_safety(
            resource_safety
        )
    )

    resolutions = (
        reservation_requirement_resolutions_by_model(
            feasibility,
            resource_safety=resource_safety,
        )
    )

    requirements_by_model = {
        model_id: dict(
            resolution["requirements"]
        )
        for model_id, resolution in resolutions.items()
    }

    return {
        "capacities": capacities,
        "requirements_by_model":
            requirements_by_model,
        "requirement_resolutions_by_model":
            resolutions,
        "phase8": {
            "resource_safety_admission_ready":
                resource_safety.get(
                    "admission_ready"
                ),
            "resource_safety_unresolved_pool_ids":
                list(
                    resource_safety.get(
                        "unresolved_pool_ids"
                    )
                    or []
                ),
            "model_count":
                feasibility.get("model_count"),
            "planner_stage":
                feasibility.get("planner_stage"),
        },
    }
