from pathlib import Path

from core.config import load_config

from core.model_inventory import (
    list_model_inventory,
)

from core.platform_storage_usage import (
    measure_path_usage,
    measure_platform_storage_usage,
)


PLATFORM_STORAGE_RECONCILIATION_SCHEMA_VERSION = 1


def _gb_to_bytes(
    value,
):
    return int(
        float(value)
        * 1_000_000_000
    )


def _extract_records(
    payload,
):
    if isinstance(
        payload,
        list,
    ):
        return payload

    if not isinstance(
        payload,
        dict,
    ):
        return []

    for key in [
        "models",
        "records",
        "items",
        "inventory",
    ]:
        value = payload.get(
            key
        )

        if isinstance(
            value,
            list,
        ):
            return value

        if isinstance(
            value,
            dict,
        ):
            return [
                item
                for item in value.values()
                if isinstance(
                    item,
                    dict,
                )
            ]

    return []


def _nested_value(
    record,
    path,
):
    value = record

    for key in path:
        if not isinstance(
            value,
            dict,
        ):
            return None

        value = value.get(
            key
        )

    return value


def _first_integer(
    record,
    paths,
):
    for path in paths:
        value = _nested_value(
            record,
            path,
        )

        if value is None:
            continue

        try:
            value = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            continue

        if value >= 0:
            return value

    return None


def _first_string(
    record,
    paths,
):
    for path in paths:
        value = _nested_value(
            record,
            path,
        )

        if (
            isinstance(
                value,
                str,
            )
            and value
        ):
            return value

    return None


def _record_identifier(
    record,
):
    return _first_string(
        record,
        [
            (
                "inventory_id",
            ),
            (
                "id",
            ),
            (
                "model_id",
            ),
            (
                "name",
            ),
        ],
    )


def _record_disk_usage(
    record,
):
    """
    Only accept fields whose semantics explicitly describe
    installed/on-disk usage.

    Generic model metadata such as parameter count or estimated
    download size must NOT silently become usage accounting.
    """

    return _first_integer(
        record,
        [
            (
                "disk_usage_bytes",
            ),
            (
                "disk_bytes",
            ),
            (
                "storage",
                "disk_usage_bytes",
            ),
            (
                "storage",
                "used_bytes",
            ),
            (
                "artifact",
                "disk_usage_bytes",
            ),
            (
                "observed",
                "disk_usage_bytes",
            ),
        ],
    )


def _record_path(
    record,
):
    return _first_string(
        record,
        [
            (
                "path",
            ),
            (
                "local_path",
            ),
            (
                "storage",
                "path",
            ),
            (
                "artifact",
                "path",
            ),
        ],
    )


def reconcile_platform_storage_usage(
    config=None,
):
    """
    Cross-check platform storage using two independent views:

    1. Model Inventory metadata
    2. Filesystem measurement

    Directional safety rule:

        Remaining/free-space disagreement
            -> smaller credible value wins

        Used-space disagreement
            -> LARGER credible value wins

    We therefore never average two usage measurements in a way
    that could understate current consumption.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    relative_tolerance = float(
        settings.get(
            "consensus_relative_tolerance",
            0.10,
        )
    )

    absolute_tolerance = (
        _gb_to_bytes(
            settings.get(
                "consensus_absolute_gb",
                2.0,
            )
        )
    )

    filesystem_usage = (
        measure_platform_storage_usage(
            config
        )
    )

    inventory_payload = (
        list_model_inventory()
    )

    records = _extract_records(
        inventory_payload
    )

    record_results = []

    inventory_recorded_bytes = 0
    records_with_usage = 0

    measured_inventory_paths_bytes = 0
    measured_paths = set()

    inventory_errors = []

    for record in records:
        if not isinstance(
            record,
            dict,
        ):
            continue

        identifier = (
            _record_identifier(
                record
            )
            or "unknown"
        )

        recorded_bytes = (
            _record_disk_usage(
                record
            )
        )

        path_value = (
            _record_path(
                record
            )
        )

        if recorded_bytes is not None:
            inventory_recorded_bytes += (
                recorded_bytes
            )

            records_with_usage += 1

        measured_bytes = None

        if path_value:
            path = Path(
                path_value
            )

            if not path.is_absolute():
                path = (
                    Path(
                        config[
                            "platform"
                        ][
                            "data_root"
                        ]
                    )
                    / path
                )

            path = path.resolve()

            #
            # Avoid counting the same physical directory twice
            # if duplicate inventory records ever appear.
            #

            if path not in measured_paths:
                measured_paths.add(
                    path
                )

                measurement = (
                    measure_path_usage(
                        path
                    )
                )

                if measurement[
                    "exists"
                ]:
                    measured_bytes = (
                        measurement[
                            "logical_bytes"
                        ]
                    )

                    measured_inventory_paths_bytes += (
                        measured_bytes
                    )

        record_results.append({
            "inventory_id": (
                identifier
            ),

            "path": (
                path_value
            ),

            "recorded_disk_usage_bytes": (
                recorded_bytes
            ),

            "measured_path_bytes": (
                measured_bytes
            ),
        })

    inventory_usage_available = (
        records_with_usage > 0
    )

    filesystem_model_bytes = (
        filesystem_usage[
            "scopes"
        ][
            "models"
        ][
            "logical_bytes"
        ]
    )

    staging_bytes = (
        filesystem_usage[
            "scopes"
        ][
            "transfer_staging"
        ][
            "logical_bytes"
        ]
    )

    credible_model_usage_values = [
        int(
            filesystem_model_bytes
        )
    ]

    if inventory_usage_available:
        credible_model_usage_values.append(
            int(
                inventory_recorded_bytes
            )
        )

    #
    # Used-space safety rule:
    # choose the LARGEST credible observation.
    #

    reconciled_model_bytes = max(
        credible_model_usage_values
    )

    if inventory_usage_available:
        difference_bytes = abs(
            int(
                filesystem_model_bytes
            )
            - int(
                inventory_recorded_bytes
            )
        )

        comparison_reference = max(
            int(
                filesystem_model_bytes
            ),
            int(
                inventory_recorded_bytes
            ),
        )

        allowed_difference = max(
            int(
                comparison_reference
                * relative_tolerance
            ),
            absolute_tolerance,
        )

        agreement = (
            difference_bytes
            <= allowed_difference
        )

    else:
        difference_bytes = None
        allowed_difference = None
        agreement = None

    #
    # Files inside model_root that are not explained by recorded
    # inventory usage may represent caches, hub metadata, xet data,
    # orphaned files, or other platform storage.
    #

    unattributed_model_root_bytes = max(
        0,
        int(
            filesystem_model_bytes
        )
        - int(
            inventory_recorded_bytes
        ),
    )

    total_platform_used_bytes = (
        reconciled_model_bytes
        + int(
            staging_bytes
        )
    )

    warnings = list(
        filesystem_usage.get(
            "warnings",
            []
        )
    )

    if not inventory_usage_available:
        warnings.append(
            (
                "Model Inventory did not expose usable "
                "disk-usage fields. Filesystem measurement "
                "was used for storage accounting."
            )
        )

    if agreement is False:
        warnings.append(
            (
                "Inventory and filesystem model usage disagree "
                "beyond configured tolerance. The larger "
                "credible used-space estimate was selected."
            )
        )

    if unattributed_model_root_bytes > 0:
        warnings.append(
            (
                "The model root contains bytes not attributed "
                "to recorded inventory model usage. These bytes "
                "remain included in platform storage accounting."
            )
        )

    if filesystem_usage.get(
        "errors"
    ):
        warnings.append(
            (
                "Filesystem accounting encountered one or more "
                "measurement errors."
            )
        )

    if agreement is True:
        confidence = "high"

    elif (
        inventory_usage_available
        and agreement is False
    ):
        confidence = "medium"

    else:
        confidence = "medium"

    return {
        "schema_version": (
            PLATFORM_STORAGE_RECONCILIATION_SCHEMA_VERSION
        ),

        "inventory": {
            "record_count": len(
                records
            ),

            "records_with_disk_usage": (
                records_with_usage
            ),

            "recorded_model_bytes": (
                inventory_recorded_bytes
                if inventory_usage_available
                else None
            ),

            "measured_inventory_paths_bytes": (
                measured_inventory_paths_bytes
            ),

            "records": (
                record_results
            ),

            "errors": (
                inventory_errors
            ),
        },

        "filesystem": {
            "model_scope_bytes": (
                filesystem_model_bytes
            ),

            "transfer_staging_bytes": (
                staging_bytes
            ),

            "raw": (
                filesystem_usage
            ),
        },

        "reconciliation": {
            "relative_tolerance": (
                relative_tolerance
            ),

            "absolute_tolerance_bytes": (
                absolute_tolerance
            ),

            "difference_bytes": (
                difference_bytes
            ),

            "allowed_difference_bytes": (
                allowed_difference
            ),

            "agreement": (
                agreement
            ),

            "selection_rule": (
                "largest_credible_used_space"
            ),

            "reconciled_model_bytes": (
                reconciled_model_bytes
            ),

            "unattributed_model_root_bytes": (
                unattributed_model_root_bytes
            ),

            "confidence": (
                confidence
            ),
        },

        "total_platform_used_bytes": (
            total_platform_used_bytes
        ),

        "warnings": (
            warnings
        ),
    }
