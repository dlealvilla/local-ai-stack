"""
Capacity Planner v1 — integrated model feasibility.

Phase 8 closes at the functional-exoskeleton boundary.

This module connects existing platform concepts into one structured,
explainable feasibility result.

WORKING V1:
    - static compatibility dimension
    - stored-artifact/start-storage dimension
    - live normalized resource pools
    - protected RAM / accelerator headroom
    - model artifact evidence
    - intentionally provisional candidate memory estimate
    - current running state
    - explainable constraints and recommendations

DEFERRED:
    - exact runtime profiling
    - KV-cache prediction
    - activation prediction
    - runtime-specific estimators
    - Resource Manager reservations
    - multi-model placement
    - unified-memory shared-backing accounting
    - sophisticated scheduling

Core owns concepts; adapters own implementations.
"""


from core.config import (
    load_config,
)

from core.hardware import (
    inspect_hardware,
)

from core.model_compatibility import (
    evaluate_model_compatibility,
)

from core.model_inventory import (
    list_model_inventory,
)

from core.requirements import (
    build_model_resource_requirements,
)

from core.resource_safety import (
    build_resource_safety,
)


MODEL_FEASIBILITY_SCHEMA_VERSION = 1

GIB = 1024 ** 3


def _deployment(
    model,
):
    value = (
        model.get(
            "deployment"
        )
        or {}
    )


    return {
        "selected": bool(
            value.get(
                "selected"
            )
        ),

        "running": (
            value.get(
                "service_state"
            )
            == "running"
        ),

        "loaded": (
            value.get(
                "load_state"
            )
            == "loaded"
        ),

        "healthy": (
            value.get(
                "healthy"
            )
        ),

        "runtime": (
            value.get(
                "runtime"
            )
        ),
    }


def _static_candidate(
    model,
):
    metadata = (
        model.get(
            "metadata"
        )
        or {}
    )

    artifact = (
        model.get(
            "artifact"
        )
        or {}
    )


    return {
        "id": (
            model.get(
                "model_id"
            )
        ),

        "name": (
            model.get(
                "model_id"
            )
        ),

        "family": (
            metadata.get(
                "family"
            )
        ),

        "architecture": (
            metadata.get(
                "architecture"
            )
        ),

        "quantization": (
            metadata.get(
                "quantization"
            )
        ),

        "format": {
            "weights": (
                metadata.get(
                    "weight_format"
                )
                or artifact.get(
                    "format"
                )
            ),
        },

        "size": {
            "installed_bytes": (
                artifact.get(
                    "disk_usage_bytes"
                )
            ),

            "download_bytes": None,
        },

        "runtime": {
            "supported": [],
        },

        "requirements": {
            "ram_bytes": None,
            "vram_bytes": None,
            "unified_memory_bytes": None,
        },

        "compatibility": {
            "status": (
                "not_evaluated"
            ),

            "reasons": [],
            "recommendations": [],
        },
    }


def _evaluate_static(
    model,
    *,
    hardware,
    config,
):
    deployment = (
        _deployment(
            model
        )
    )


    if (
        deployment[
            "running"
        ]
        and deployment[
            "loaded"
        ]
        and deployment[
            "healthy"
        ]
        is not False
    ):

        return {
            "status": (
                "compatible"
            ),

            "confidence": (
                "high"
            ),

            "reasons": [
                (
                    "The model is currently loaded and running "
                    "on this host."
                ),
            ],

            "recommendations": [],

            "basis": (
                "current_running_deployment"
            ),
        }


    try:

        evaluated = (
            evaluate_model_compatibility(
                _static_candidate(
                    model
                ),

                hardware,

                config,
            )
        )


        result = (
            evaluated.get(
                "compatibility"
            )
            or {}
        )


        status = (
            result.get(
                "status"
            )
            or "conditionally_compatible"
        )


        if status in {
            "conditional",
            "candidate",
            "unknown",
            "not_evaluated",
        }:

            status = (
                "conditionally_compatible"
            )


        return {
            "status": (
                status
            ),

            "confidence": (
                result.get(
                    "confidence"
                )
                or "low"
            ),

            "reasons": (
                result.get(
                    "reasons"
                )
                or []
            ),

            "recommendations": (
                result.get(
                    "recommendations"
                )
                or []
            ),

            "basis": (
                "static_compatibility_evaluator"
            ),
        }


    except Exception as exc:

        return {
            "status": (
                "conditionally_compatible"
            ),

            "confidence": (
                "low"
            ),

            "reasons": [
                (
                    "Static compatibility could not be fully "
                    "resolved from current Inventory metadata."
                ),
            ],

            "recommendations": [
                (
                    "Resolve richer model metadata before "
                    "production deployment."
                ),
            ],

            "basis": (
                "static_metadata_incomplete"
            ),

            "detail": (
                str(
                    exc
                )
            ),
        }


def _evaluate_storage(
    model,
):
    artifact = (
        model.get(
            "artifact"
        )
        or {}
    )


    installed = (
        artifact.get(
            "disk_usage_bytes"
        )
    )


    if (
        installed is not None
        and installed > 0
    ):

        return {
            "status": (
                "satisfied"
            ),

            "confidence": (
                "high"
            ),

            "installed_bytes": (
                installed
            ),

            "additional_storage_required_to_start_bytes": (
                0
            ),

            "reason": (
                "The Inventory artifact is already stored. "
                "Starting it requires no additional model-install storage."
            ),

            "installability_evaluated": (
                False
            ),
        }


    return {
        "status": (
            "conditional"
        ),

        "confidence": (
            "low"
        ),

        "installed_bytes": (
            installed
        ),

        "additional_storage_required_to_start_bytes": (
            None
        ),

        "reason": (
            "Stored artifact size is unresolved."
        ),

        "installability_evaluated": (
            False
        ),
    }


def _provisional_memory_estimate(
    requirements,
):
    """
    WORKING / PROVISIONAL only.

    measured local weight artifact bytes
        +
    max(25 percent of artifact bytes, 1 GiB)

    This is LOW-confidence and is NOT an exact VRAM prediction.
    """

    evidence = (
        requirements.get(
            "artifact_evidence",
            {}
        ).get(
            "weight_files",
            {}
        )
    )


    weight_bytes = (
        evidence.get(
            "bytes"
        )
    )


    if (
        not evidence.get(
            "resolved"
        )
        or weight_bytes is None
        or weight_bytes <= 0
    ):

        return {
            "resolved": False,

            "confidence": (
                "unresolved"
            ),

            "weight_artifact_bytes": (
                weight_bytes
            ),

            "estimated_runtime_target_bytes": (
                None
            ),

            "reason": (
                "Local weight artifact evidence is unresolved."
            ),
        }


    overhead = max(
        1 * GIB,

        int(
            weight_bytes
            * 0.25
        ),
    )


    return {
        "resolved": True,

        "confidence": (
            "low"
        ),

        "weight_artifact_bytes": (
            weight_bytes
        ),

        "provisional_overhead_bytes": (
            overhead
        ),

        "estimated_runtime_target_bytes": (
            weight_bytes
            + overhead
        ),

        "method": (
            "artifact_bytes_plus_25_percent_or_1GiB_minimum"
        ),

        "reason": (
            "Phase 8 intentionally uses a simple replaceable "
            "working estimate rather than runtime-specific prediction."
        ),
    }


def _pool(
    resource_safety,
    memory_type,
):
    for candidate in (
        resource_safety.get(
            "resource_pools"
        )
        or []
    ):

        if candidate.get(
            "memory_type"
        ) == memory_type:

            return candidate


    return None


def _safe_bytes(
    pool,
):
    if pool is None:
        return None


    safety = (
        pool.get(
            "safety"
        )
        or {}
    )


    if not safety.get(
        "resolved"
    ):
        return None


    return safety.get(
        "safe_available_before_reservations_bytes"
    )


def _evaluate_memory(
    model,
    *,
    requirements,
    resource_safety,
):
    deployment = (
        _deployment(
            model
        )
    )


    safe_ram = (
        _safe_bytes(
            _pool(
                resource_safety,
                "system_ram",
            )
        )
    )


    safe_vram = (
        _safe_bytes(
            _pool(
                resource_safety,
                "dedicated_vram",
            )
        )
    )


    estimate = (
        _provisional_memory_estimate(
            requirements
        )
    )


    if (
        deployment[
            "running"
        ]
        and deployment[
            "loaded"
        ]
    ):

        return {
            "status": (
                "satisfied"
            ),

            "confidence": (
                "high"
            ),

            "startability": (
                "already_running"
            ),

            "reason": (
                "The current instance is already loaded and running."
            ),

            "safe_system_ram_bytes": (
                safe_ram
            ),

            "safe_dedicated_vram_bytes": (
                safe_vram
            ),

            "provisional_estimate": (
                estimate
            ),

            "reservations_applied": (
                False
            ),
        }


    if not estimate[
        "resolved"
    ]:

        return {
            "status": (
                "unknown"
            ),

            "confidence": (
                "low"
            ),

            "startability": (
                "unknown"
            ),

            "reason": (
                "Candidate memory requirement is unresolved."
            ),

            "safe_system_ram_bytes": (
                safe_ram
            ),

            "safe_dedicated_vram_bytes": (
                safe_vram
            ),

            "provisional_estimate": (
                estimate
            ),

            "reservations_applied": (
                False
            ),
        }


    required = (
        estimate[
            "estimated_runtime_target_bytes"
        ]
    )


    if safe_vram is not None:

        if required > safe_vram:

            return {
                "status": (
                    "blocked"
                ),

                "confidence": (
                    "medium"
                ),

                "startability": (
                    "blocked_now"
                ),

                "blocking_constraint": (
                    "dedicated_vram"
                ),

                "reason": (
                    "The provisional candidate memory target exceeds "
                    "currently safe dedicated VRAM."
                ),

                "safe_system_ram_bytes": (
                    safe_ram
                ),

                "safe_dedicated_vram_bytes": (
                    safe_vram
                ),

                "provisional_estimate": (
                    estimate
                ),

                "reservations_applied": (
                    False
                ),

                "recommendations": [
                    (
                        "Stop or unload an accelerator workload."
                    ),
                    (
                        "Use a smaller or more aggressively quantized model."
                    ),
                    (
                        "Use a future offload/runtime configuration "
                        "requiring less dedicated VRAM."
                    ),
                ],
            }


        return {
            "status": (
                "conditional"
            ),

            "confidence": (
                "low"
            ),

            "startability": (
                "candidate"
            ),

            "reason": (
                "The provisional target fits current safe VRAM, "
                "but runtime-specific requirements and Resource Manager "
                "reservations are not yet applied."
            ),

            "safe_system_ram_bytes": (
                safe_ram
            ),

            "safe_dedicated_vram_bytes": (
                safe_vram
            ),

            "provisional_estimate": (
                estimate
            ),

            "reservations_applied": (
                False
            ),
        }


    if (
        safe_ram is not None
        and required > safe_ram
    ):

        return {
            "status": (
                "blocked"
            ),

            "confidence": (
                "medium"
            ),

            "startability": (
                "blocked_now"
            ),

            "blocking_constraint": (
                "system_ram"
            ),

            "reason": (
                "The provisional candidate memory target exceeds "
                "currently safe system RAM."
            ),

            "safe_system_ram_bytes": (
                safe_ram
            ),

            "safe_dedicated_vram_bytes": (
                None
            ),

            "provisional_estimate": (
                estimate
            ),

            "reservations_applied": (
                False
            ),
        }


    return {
        "status": (
            "conditional"
        ),

        "confidence": (
            "low"
        ),

        "startability": (
            "candidate"
        ),

        "reason": (
            "No independent dedicated-VRAM pool is available. "
            "CPU or unified-memory execution requires a suitable "
            "runtime and, where applicable, shared-memory accounting."
        ),

        "safe_system_ram_bytes": (
            safe_ram
        ),

        "safe_dedicated_vram_bytes": (
            None
        ),

        "provisional_estimate": (
            estimate
        ),

        "reservations_applied": (
            False
        ),
    }


def _overall(
    *,
    static,
    storage,
    memory,
):
    if static.get(
        "status"
    ) == "unsupported":

        return {
            "status": (
                "unsupported"
            ),

            "startability": (
                "blocked"
            ),

            "primary_constraint": (
                "static_compatibility"
            ),
        }


    if memory.get(
        "startability"
    ) == "already_running":

        return {
            "status": (
                "compatible"
            ),

            "startability": (
                "running"
            ),

            "primary_constraint": (
                None
            ),
        }


    if memory.get(
        "status"
    ) == "blocked":

        return {
            "status": (
                "conditionally_compatible"
            ),

            "startability": (
                "blocked"
            ),

            "primary_constraint": (
                memory.get(
                    "blocking_constraint"
                )
                or "memory"
            ),
        }


    if storage.get(
        "status"
    ) != "satisfied":

        return {
            "status": (
                "conditionally_compatible"
            ),

            "startability": (
                memory.get(
                    "startability"
                )
                or "unknown"
            ),

            "primary_constraint": (
                "storage"
            ),
        }


    return {
        "status": (
            "conditionally_compatible"
        ),

        "startability": (
            memory.get(
                "startability"
            )
            or "unknown"
        ),

        "primary_constraint": (
            None
        ),
    }


def evaluate_model_feasibility(
    model,
    *,
    hardware=None,
    config=None,
    resource_safety=None,
):
    if hardware is None:

        hardware = (
            inspect_hardware()
        )


    if config is None:

        config = (
            load_config()
        )


    if resource_safety is None:

        resource_safety = (
            build_resource_safety()
        )


    requirements = (
        build_model_resource_requirements(
            model
        )
    )


    static = (
        _evaluate_static(
            model,

            hardware=hardware,

            config=config,
        )
    )


    storage = (
        _evaluate_storage(
            model
        )
    )


    memory = (
        _evaluate_memory(
            model,

            requirements=requirements,

            resource_safety=(
                resource_safety
            ),
        )
    )


    overall = (
        _overall(
            static=static,

            storage=storage,

            memory=memory,
        )
    )


    recommendations = []


    for source in (
        static.get(
            "recommendations"
        )
        or []
    ) + (
        memory.get(
            "recommendations"
        )
        or []
    ):

        if source not in recommendations:

            recommendations.append(
                source
            )


    reservations_note = (
        "Resource Manager reservations are not yet implemented; "
        "candidate startability remains conservative."
    )


    if reservations_note not in recommendations:

        recommendations.append(
            reservations_note
        )


    return {
        "schema_version": (
            MODEL_FEASIBILITY_SCHEMA_VERSION
        ),

        "model_id": (
            model.get(
                "model_id"
            )
        ),

        "overall": (
            overall
        ),

        "dimensions": {
            "static_compatibility": (
                static
            ),

            "storage": (
                storage
            ),

            "memory": (
                memory
            ),
        },

        "model_resource_requirements": (
            requirements
        ),

        "resource_context": {
            "resource_safety_schema_version": (
                resource_safety.get(
                    "schema_version"
                )
            ),

            "reservations_implemented": (
                False
            ),
        },

        "recommendations": (
            recommendations
        ),

        "planner_stage": (
            "phase8_capacity_planner_v1"
        ),

        "estimator_stage": (
            "provisional"
        ),
    }


def evaluate_inventory_model_feasibility(
    *,
    model_id,
):
    inventory = (
        list_model_inventory()
    )


    model = next(
        (
            candidate

            for candidate in inventory[
                "models"
            ]

            if candidate.get(
                "model_id"
            )
            == model_id
        ),

        None,
    )


    if model is None:

        return {
            "ok": False,

            "error": {
                "code": (
                    "not_found"
                ),

                "detail": (
                    "Inventory model not found: "
                    + repr(
                        model_id
                    )
                ),
            },
        }


    try:

        result = (
            evaluate_model_feasibility(
                model
            )
        )


    except Exception as exc:

        return {
            "ok": False,

            "error": {
                "code": (
                    "feasibility_failed"
                ),

                "detail": (
                    str(
                        exc
                    )
                ),
            },
        }


    return {
        "ok": True,

        "action": (
            "evaluate_model_feasibility"
        ),

        "result": (
            result
        ),
    }


def evaluate_all_inventory_models():
    inventory = (
        list_model_inventory()
    )


    hardware = (
        inspect_hardware()
    )

    config = (
        load_config()
    )

    resource_safety = (
        build_resource_safety()
    )


    models = [
        evaluate_model_feasibility(
            model,

            hardware=hardware,

            config=config,

            resource_safety=(
                resource_safety
            ),
        )

        for model in inventory[
            "models"
        ]
    ]


    return {
        "schema_version": (
            MODEL_FEASIBILITY_SCHEMA_VERSION
        ),

        "model_count": (
            len(
                models
            )
        ),

        "models": (
            models
        ),

        "planner_stage": (
            "phase8_capacity_planner_v1"
        ),
    }
