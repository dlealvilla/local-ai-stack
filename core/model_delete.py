import shutil

from pathlib import Path

from core.config import load_config
from core.model_inventory import (
    list_model_inventory,
)
from core.model_inventory_metadata import (
    get_inventory_store,
)


def delete_model(
    model_id,
):
    """
    Safely delete one platform-managed stored model.

    Hard safety rules:

    - unmanaged models cannot be deleted
    - selected models cannot be deleted
    - running models cannot be deleted
    - loaded models cannot be deleted
    - deletion is restricted to the configured model root
    """

    config = load_config()

    inventory = (
        list_model_inventory()
    )

    model = next(
        (
            item
            for item
            in inventory["models"]
            if item["model_id"]
            == model_id
        ),
        None,
    )

    if model is None:
        return {
            "ok": False,
            "error": {
                "code": "not_found",
                "detail": (
                    f"Model '{model_id}' "
                    "was not found in Inventory."
                ),
            },
        }

    management = (
        model.get(
            "management"
        )
        or {}
    )

    deployment = (
        model.get(
            "deployment"
        )
        or {}
    )

    if not management.get(
        "managed",
        False,
    ):
        return {
            "ok": False,
            "error": {
                "code": "unmanaged_model",
                "detail": (
                    "Only platform-managed model "
                    "artifacts may be deleted."
                ),
            },
        }

    if deployment.get(
        "selected"
    ):
        return {
            "ok": False,
            "error": {
                "code": "model_selected",
                "detail": (
                    "The selected deployment model "
                    "cannot be deleted."
                ),
            },
        }

    if (
        deployment.get(
            "service_state"
        )
        == "running"
    ):
        return {
            "ok": False,
            "error": {
                "code": "model_running",
                "detail": (
                    "A running model cannot be deleted."
                ),
            },
        }

    if (
        deployment.get(
            "load_state"
        )
        == "loaded"
    ):
        return {
            "ok": False,
            "error": {
                "code": "model_loaded",
                "detail": (
                    "A loaded model cannot be deleted."
                ),
            },
        }

    path = Path(
        model["path"]
    ).resolve()

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    model_root = (
        data_root
        / "models"
    ).resolve()

    # Strong path-boundary guard.
    if path.parent != model_root:
        return {
            "ok": False,
            "error": {
                "code": "unsafe_path",
                "detail": (
                    "Model path is outside the "
                    "managed model root."
                ),
            },
        }

    if not path.exists():
        return {
            "ok": False,
            "error": {
                "code": "artifact_missing",
                "detail": (
                    "Inventory record exists but "
                    "the artifact is missing."
                ),
            },
        }

    if not path.is_dir():
        return {
            "ok": False,
            "error": {
                "code": "invalid_artifact",
                "detail": (
                    "Managed model artifact is "
                    "not a directory."
                ),
            },
        }

    inventory_id = (
        model["inventory_id"]
    )

    # Remove artifact first. If metadata cleanup fails,
    # stale metadata is safer than accidentally losing
    # ownership information before filesystem deletion.
    shutil.rmtree(
        path
    )

    store = get_inventory_store(
        config
    )

    removed = store.remove_record(
        inventory_id,
        config,
    )

    if not removed:
        return {
            "ok": False,
            "error": {
                "code": "metadata_cleanup_failed",
                "detail": (
                    "Artifact was deleted but its "
                    "Inventory metadata record "
                    "could not be removed."
                ),
            },
        }

    return {
        "ok": True,
        "model_id": model_id,
        "inventory_id": inventory_id,
        "deleted_path": str(
            path
        ),
    }
