from core.config import load_config
from core.models import list_local_models
from core.planner import build_initial_plan
from core.platform_state import build_platform_state

from core.model_inventory_metadata import (
    get_inventory_store,
)


MODEL_INVENTORY_SCHEMA_VERSION = 1
MODEL_INVENTORY_RECORD_SCHEMA_VERSION = 1


def _size_bytes(model):
    size_gb = model.get(
        "size_gb"
    )

    if not isinstance(
        size_gb,
        (int, float),
    ):
        return None

    return int(
        size_gb * 1024 ** 3
    )


def _same_model(
    local_model,
    selected_model,
):
    if selected_model is None:
        return False

    if (
        local_model.get("path")
        and selected_model.get("path")
        and local_model["path"]
        == selected_model["path"]
    ):
        return True

    return (
        local_model.get("name")
        == selected_model.get("name")
    )


def _inference_service(state):
    for service in (
        state.get(
            "deployment",
            {}
        ).get(
            "services",
            []
        )
    ):
        if (
            service.get("role")
            == "inference"
        ):
            return service

    return None


def list_model_inventory():
    """
    Combine persistent artifact metadata with live observed
    deployment state.

    Persisted:
        source/revision/integrity/management metadata

    Observed:
        disk presence, loaded/running state, runtime, health
    """

    config = load_config()
    plan = build_initial_plan()
    state = build_platform_state()

    inventory_store = (
        get_inventory_store(
            config
        )
    )

    metadata_records = {
        record["inventory_id"]: record
        for record
        in inventory_store.list_records(
            config
        )
    }

    selected_model = plan.get(
        "selected_model"
    )

    inference_service = (
        _inference_service(
            state
        )
    )

    executor = (
        state.get(
            "deployment",
            {}
        ).get(
            "runtime",
            {}
        ).get(
            "executor"
        )
    )

    records = []

    for model in list_local_models():

        inventory_id = (
            f"local:{model['name']}"
        )

        persisted = (
            metadata_records.get(
                inventory_id
            )
            or {}
        )

        selected = _same_model(
            model,
            selected_model,
        )

        inference_running = False
        inference_healthy = None

        if (
            selected
            and inference_service
        ):
            inference_running = bool(
                inference_service.get(
                    "observed",
                    {}
                ).get(
                    "running",
                    False,
                )
            )

            inference_healthy = (
                inference_service.get(
                    "health",
                    {}
                ).get(
                    "healthy"
                )
            )

        source = persisted.get(
            "source"
        ) or {
            "provider": "local_files",
            "source_model_id": (
                model["name"]
            ),
            "revision": None,
        }

        records.append({
            "schema_version": (
                MODEL_INVENTORY_RECORD_SCHEMA_VERSION
            ),

            "inventory_id": inventory_id,

            "model_id": model[
                "name"
            ],

            "path": model[
                "path"
            ],

            "source": source,

            "artifact": {
                "state": "stored",

                "disk_usage_bytes": (
                    _size_bytes(
                        model
                    )
                ),

                "weight_formats": (
                    model.get(
                        "weight_formats",
                        [],
                    )
                ),

                "integrity": (
                    persisted.get(
                        "integrity"
                    )
                ),
            },

            "management": (
                persisted.get(
                    "management"
                )
            ),

            "deployment": {
                "selected": selected,

                "load_state": (
                    "loaded"
                    if inference_running
                    else "unloaded"
                ),

                "service_state": (
                    "running"
                    if inference_running
                    else "stopped"
                ),

                "healthy": (
                    inference_healthy
                    if selected
                    else None
                ),

                "runtime": (
                    inference_service.get(
                        "provider"
                    )
                    if (
                        selected
                        and inference_service
                    )
                    else None
                ),

                "executor": (
                    executor
                    if selected
                    else None
                ),
            },

            "resources": {
                "memory_reservation_bytes": None,

                "configured_gpu_memory_utilization": (
                    config.get(
                        "performance",
                        {}
                    ).get(
                        "gpu_memory_utilization"
                    )
                    if selected
                    else None
                ),
            },

            "activity": {
                "active_requests": None,
                "last_used_at": None,
            },

            "metadata": {
                "architecture": model.get(
                    "architecture"
                ),

                "family": model.get(
                    "model_type"
                ),

                "quantization": model.get(
                    "quantization_method"
                ),

                "context_length": model.get(
                    "max_position_embeddings"
                ),
            },
        })

    return {
        "schema_version": (
            MODEL_INVENTORY_SCHEMA_VERSION
        ),

        "models": records,
    }
