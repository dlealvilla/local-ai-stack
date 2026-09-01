import copy
import os
import shutil
import uuid

from datetime import (
    datetime,
    timezone,
)
from pathlib import Path

from adapters.model_transfer import (
    get_model_transfer_adapter,
)

from core.config import load_config
from core.model_inventory import (
    list_model_inventory,
)
from core.model_inventory_metadata import (
    get_inventory_store,
)


def _now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def _error(
    code,
    detail,
):
    return {
        "ok": False,
        "error": {
            "code": code,
            "detail": detail,
        },
    }


def _resolve_staging_root(
    config,
):
    transfer = config[
        "model_transfer"
    ]

    configured = Path(
        transfer.get(
            "staging_root",
            "data/model-transfers",
        )
    )

    if configured.is_absolute():
        return configured

    return (
        Path(
            config[
                "platform"
            ][
                "data_root"
            ]
        )
        / configured
    )


def update_model(
    model_id,
    *,
    revision="main",
):
    """
    Safely update one platform-managed Hugging Face model.

    Hard safety rules:

    - unmanaged models are blocked
    - selected models are blocked
    - running models are blocked
    - loaded models are blocked
    - non-Hugging-Face sources are blocked for now
    - artifact paths outside the managed model root are blocked

    The replacement is downloaded to staging first.

    The existing model is retained temporarily as a rollback copy.
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
        return _error(
            "not_found",
            (
                f"Model '{model_id}' "
                "was not found in Inventory."
            ),
        )

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

    source = (
        model.get(
            "source"
        )
        or {}
    )

    if not management.get(
        "managed",
        False,
    ):
        return _error(
            "unmanaged_model",
            (
                "Only platform-managed models "
                "may be updated."
            ),
        )

    if deployment.get(
        "selected"
    ):
        return _error(
            "model_selected",
            (
                "The selected deployment model "
                "cannot be updated in place."
            ),
        )

    if (
        deployment.get(
            "service_state"
        )
        == "running"
    ):
        return _error(
            "model_running",
            (
                "A running model cannot be "
                "updated in place."
            ),
        )

    if (
        deployment.get(
            "load_state"
        )
        == "loaded"
    ):
        return _error(
            "model_loaded",
            (
                "A loaded model cannot be "
                "updated in place."
            ),
        )

    provider = source.get(
        "provider"
    )

    # WORKING MVP:
    # Revision-based update semantics currently exist only
    # for managed Hugging Face repositories.
    if provider != "huggingface":
        return _error(
            "update_not_supported",
            (
                "In-place update is currently "
                "supported only for managed "
                "Hugging Face models."
            ),
        )

    source_model_id = source.get(
        "source_model_id"
    )

    if not source_model_id:
        return _error(
            "source_missing",
            (
                "Managed model has no source "
                "repository identifier."
            ),
        )

    transfer_config = config[
        "model_transfer"
    ]

    if not transfer_config.get(
        "enabled",
        False,
    ):
        return _error(
            "transfer_disabled",
            "Model transfer is disabled.",
        )

    if provider not in transfer_config.get(
        "providers",
        [],
    ):
        return _error(
            "provider_not_enabled",
            (
                f"ModelTransfer provider "
                f"'{provider}' is not enabled."
            ),
        )

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

    if path.parent != model_root:
        return _error(
            "unsafe_path",
            (
                "Model path is outside the "
                "managed model root."
            ),
        )

    if not path.exists():
        return _error(
            "artifact_missing",
            (
                "Inventory record exists but "
                "the model artifact is missing."
            ),
        )

    if not path.is_dir():
        return _error(
            "invalid_artifact",
            (
                "Managed model artifact is "
                "not a directory."
            ),
        )

    inventory_id = model[
        "inventory_id"
    ]

    store = get_inventory_store(
        config
    )

    existing_record = (
        store.get_record(
            inventory_id,
            config,
        )
    )

    if not existing_record:
        return _error(
            "metadata_missing",
            (
                "Persistent managed Inventory "
                "metadata is missing."
            ),
        )

    staging_root = (
        _resolve_staging_root(
            config
        )
    )

    staging_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    operation_id = str(
        uuid.uuid4()
    )

    staging = (
        staging_root
        / operation_id
    )

    rollback = (
        staging_root
        / (
            operation_id
            + ".rollback"
        )
    )

    staging.mkdir(
        parents=True,
        exist_ok=False,
    )

    previous_revision = (
        existing_record.get(
            "source",
            {},
        ).get(
            "revision"
        )
    )

    updating_record = copy.deepcopy(
        existing_record
    )

    updating_record.setdefault(
        "management",
        {},
    )

    updating_record[
        "management"
    ][
        "download_state"
    ] = "updating"

    updating_record[
        "management"
    ][
        "updated_at"
    ] = _now()

    updating_record[
        "management"
    ][
        "last_error"
    ] = None

    store.upsert_record(
        updating_record,
        config,
    )

    adapter = (
        get_model_transfer_adapter(
            provider
        )
    )

    swapped = False

    try:
        result = adapter.download(
            source_model_id=(
                source_model_id
            ),
            revision=(
                revision or "main"
            ),
            destination=staging,
            config=config,
        )

        resolved_revision = (
            result.get(
                "resolved_revision"
            )
        )

        if not resolved_revision:
            raise RuntimeError(
                "Transfer completed without "
                "a resolved revision."
            )

        if not staging.exists():
            raise RuntimeError(
                "Transfer staging directory "
                "does not exist."
            )

        if not any(
            staging.iterdir()
        ):
            raise RuntimeError(
                "Transfer staging directory "
                "is empty."
            )

        os.replace(
            path,
            rollback,
        )

        try:
            os.replace(
                staging,
                path,
            )

            swapped = True

        except Exception:
            os.replace(
                rollback,
                path,
            )
            raise

        completed_record = copy.deepcopy(
            existing_record
        )

        completed_record.setdefault(
            "source",
            {},
        )

        completed_record[
            "source"
        ][
            "revision"
        ] = resolved_revision

        completed_record.setdefault(
            "management",
            {},
        )

        completed_record[
            "management"
        ][
            "download_state"
        ] = "completed"

        completed_record[
            "management"
        ][
            "updated_at"
        ] = _now()

        completed_record[
            "management"
        ][
            "update_available"
        ] = False

        completed_record[
            "management"
        ][
            "last_error"
        ] = None

        store.upsert_record(
            completed_record,
            config,
        )

        shutil.rmtree(
            rollback,
            ignore_errors=True,
        )

        return {
            "ok": True,
            "model_id": model_id,
            "inventory_id": inventory_id,
            "provider": provider,
            "source_model_id": (
                source_model_id
            ),
            "requested_revision": (
                revision
            ),
            "previous_revision": (
                previous_revision
            ),
            "resolved_revision": (
                resolved_revision
            ),
            "changed_revision": (
                previous_revision
                != resolved_revision
            ),
            "path": str(
                path
            ),
        }

    except Exception as exc:
        if (
            swapped
            and rollback.exists()
        ):
            shutil.rmtree(
                path,
                ignore_errors=True,
            )

            os.replace(
                rollback,
                path,
            )

        elif (
            not path.exists()
            and rollback.exists()
        ):
            os.replace(
                rollback,
                path,
            )

        shutil.rmtree(
            staging,
            ignore_errors=True,
        )

        failed_record = copy.deepcopy(
            existing_record
        )

        failed_record.setdefault(
            "management",
            {},
        )

        failed_record[
            "management"
        ][
            "download_state"
        ] = "completed"

        failed_record[
            "management"
        ][
            "updated_at"
        ] = _now()

        failed_record[
            "management"
        ][
            "last_error"
        ] = str(
            exc
        )

        try:
            store.upsert_record(
                failed_record,
                config,
            )
        except Exception:
            pass

        return _error(
            "update_failed",
            str(
                exc
            ),
        )
