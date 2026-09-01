from datetime import (
    datetime,
    timezone,
)

from adapters.model_inventory_store import (
    get_model_inventory_store,
)


INVENTORY_METADATA_SCHEMA_VERSION = 1


def _now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def get_inventory_store(
    config,
):
    inventory_config = config[
        "model_inventory"
    ]

    return get_model_inventory_store(
        inventory_config[
            "provider"
        ]
    )


def build_local_discovery_record(
    model,
):
    now = _now()

    return {
        "schema_version": (
            INVENTORY_METADATA_SCHEMA_VERSION
        ),

        "inventory_id": (
            f"local:{model['name']}"
        ),

        "model_id": model[
            "name"
        ],

        "path": model[
            "path"
        ],

        "source": {
            # Existing pre-platform models have no recoverable
            # external source/revision.
            "provider": "local_files",
            "source_model_id": model[
                "name"
            ],
            "revision": None,
        },

        "integrity": {
            # FUTURE:
            # Managed downloads/imports should populate hashes.
            "checksum": None,
            "checksum_algorithm": None,
        },

        "management": {
            # False means the platform discovered the artifact
            # but did not originally download/import it.
            "managed": False,

            "created_at": now,
            "updated_at": now,

            "download_state": None,

            "update_available": None,
        },
    }


def seed_existing_local_models(
    models,
    config,
):
    """
    Register currently discovered local models without changing
    their files.

    Existing records are preserved.
    """

    store = get_inventory_store(
        config
    )

    created = 0
    existing = 0

    for model in models:
        inventory_id = (
            f"local:{model['name']}"
        )

        if store.get_record(
            inventory_id,
            config,
        ):
            existing += 1
            continue

        store.upsert_record(
            build_local_discovery_record(
                model
            ),
            config,
        )

        created += 1

    return {
        "created": created,
        "existing": existing,
    }


def build_managed_transfer_record(
    *,
    inventory_id,
    model_id,
    path,
    source_provider,
    source_model_id,
    revision,
    download_state,
    error=None,
):
    """
    Build persistent metadata for an artifact managed by
    the platform transfer subsystem.
    """

    now = _now()

    return {
        "schema_version": (
            INVENTORY_METADATA_SCHEMA_VERSION
        ),

        "inventory_id": inventory_id,

        "model_id": model_id,

        "path": str(path),

        "source": {
            "provider": source_provider,
            "source_model_id": (
                source_model_id
            ),
            "revision": revision,
        },

        "integrity": {
            # FUTURE:
            # Add verified artifact/file checksums.
            "checksum": None,
            "checksum_algorithm": None,
        },

        "management": {
            "managed": True,
            "created_at": now,
            "updated_at": now,
            "download_state": (
                download_state
            ),
            "update_available": None,
            "last_error": error,
        },
    }
