import os
import shutil
import uuid

from pathlib import Path

from adapters.model_transfer import (
    get_model_transfer_adapter,
)

from core.config import load_config

from core.model_inventory_metadata import (
    build_managed_transfer_record,
    get_inventory_store,
)


def _resolve_data_path(
    configured,
    config,
):
    path = Path(
        configured
    )

    if path.is_absolute():
        return path

    return (
        Path(
            config["platform"][
                "data_root"
            ]
        )
        / path
    )


def _safe_target_name(value):
    result = []

    for character in value:
        if (
            character.isalnum()
            or character
            in {
                "-",
                "_",
                ".",
            }
        ):
            result.append(
                character
            )
        else:
            result.append(
                "-"
            )

    cleaned = "".join(
        result
    ).strip("-.")

    if not cleaned:
        raise ValueError(
            "Invalid model target name."
        )

    return cleaned


def download_model(
    *,
    provider,
    source_model_id,
    revision="main",
    target_name=None,
):
    """
    Download/import an artifact into managed local model storage.

    This operation deliberately does NOT:
    - select the model
    - start the model
    - stop another model
    - change routing
    """

    config = load_config()

    transfer_config = config[
        "model_transfer"
    ]

    if not transfer_config.get(
        "enabled",
        False,
    ):
        raise RuntimeError(
            "Model transfer is disabled."
        )

    providers = transfer_config.get(
        "providers",
        [],
    )

    if provider not in providers:
        raise RuntimeError(
            f"ModelTransfer provider "
            f"'{provider}' is not enabled."
        )

    if target_name is None:
        target_name = (
            provider
            + "-"
            + source_model_id
        )

    target_name = (
        _safe_target_name(
            target_name
        )
    )

    data_root = Path(
        config["platform"][
            "data_root"
        ]
    )

    model_root = (
        data_root
        / "models"
    )

    destination = (
        model_root
        / target_name
    )

    inventory_id = (
        f"local:{target_name}"
    )

    store = get_inventory_store(
        config
    )

    if destination.exists():
        raise RuntimeError(
            "Destination already exists: "
            + str(destination)
        )

    staging_root = (
        _resolve_data_path(
            transfer_config.get(
                "staging_root",
                "data/model-transfers",
            ),
            config,
        )
    )

    operation_id = str(
        uuid.uuid4()
    )

    staging = (
        staging_root
        / operation_id
    )

    staging.mkdir(
        parents=True,
        exist_ok=False,
    )

    store.upsert_record(
        build_managed_transfer_record(
            inventory_id=inventory_id,
            model_id=target_name,
            path=destination,
            source_provider=provider,
            source_model_id=(
                source_model_id
            ),
            revision=None,
            download_state="downloading",
        ),
        config,
    )

    adapter = (
        get_model_transfer_adapter(
            provider
        )
    )

    try:
        result = adapter.download(
            source_model_id=(
                source_model_id
            ),
            revision=revision,
            destination=staging,
            config=config,
        )

        resolved_revision = (
            result.get(
                "resolved_revision"
            )
        )

        model_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Staging and model storage are both under /workspace,
        # allowing the completed artifact to appear atomically.
        os.replace(
            staging,
            destination,
        )

        store.upsert_record(
            build_managed_transfer_record(
                inventory_id=inventory_id,
                model_id=target_name,
                path=destination,
                source_provider=provider,
                source_model_id=(
                    source_model_id
                ),
                revision=(
                    resolved_revision
                ),
                download_state="completed",
            ),
            config,
        )

        return {
            "status": "completed",
            "inventory_id": inventory_id,
            "model_id": target_name,
            "path": str(
                destination
            ),
            "source": {
                "provider": provider,
                "source_model_id": (
                    source_model_id
                ),
                "requested_revision": (
                    revision
                ),
                "resolved_revision": (
                    resolved_revision
                ),
            },
        }

    except Exception as exc:
        shutil.rmtree(
            staging,
            ignore_errors=True,
        )

        store.upsert_record(
            build_managed_transfer_record(
                inventory_id=inventory_id,
                model_id=target_name,
                path=destination,
                source_provider=provider,
                source_model_id=(
                    source_model_id
                ),
                revision=None,
                download_state="failed",
                error=str(exc),
            ),
            config,
        )

        raise
