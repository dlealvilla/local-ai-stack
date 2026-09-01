MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION = 1


def _positive_integer(
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

    if value <= 0:
        return None

    return value


def _provider(
    model,
):
    source = model.get(
        "source",
        {},
    )

    if not isinstance(
        source,
        dict,
    ):
        return None

    provider = source.get(
        "provider"
    )

    if provider is None:
        return None

    return str(
        provider
    )


def resolve_model_artifact_size(
    model,
):
    """
    Resolve the best currently known candidate artifact size.

    Preferred order:

        size.installed_bytes
            Observed/normalized local artifact size.

        size.download_bytes
            External/download estimate.

    Hugging Face download_bytes currently represents repository
    storage and may differ from the precise files selected for a
    particular revision/runtime. It therefore remains medium
    confidence until the transfer plan resolves exact artifacts.
    """

    size = model.get(
        "size",
        {},
    )

    if not isinstance(
        size,
        dict,
    ):
        size = {}

    installed = (
        _positive_integer(
            size.get(
                "installed_bytes"
            )
        )
    )

    if installed is not None:
        return {
            "resolved": True,
            "bytes": installed,
            "source_field": (
                "size.installed_bytes"
            ),
            "confidence": "high",
            "exactness": (
                "observed_or_normalized_installed_size"
            ),
        }

    manifest = (
        _positive_integer(
            size.get(
                "manifest_bytes"
            )
        )
    )

    if manifest is not None:
        return {
            "resolved": True,

            "bytes": manifest,

            "source_field": (
                "size.manifest_bytes"
            ),

            "confidence": "high",

            "exactness": (
                "resolved_repository_manifest"
            ),
        }

    download = (
        _positive_integer(
            size.get(
                "download_bytes"
            )
        )
    )

    if download is not None:
        provider = _provider(
            model
        )

        return {
            "resolved": True,
            "bytes": download,
            "source_field": (
                "size.download_bytes"
            ),
            "confidence": "medium",
            "exactness": (
                "repository_storage_estimate"
                if provider == "huggingface"
                else "download_size_estimate"
            ),
        }

    return {
        "resolved": False,
        "bytes": None,
        "source_field": None,
        "confidence": "unknown",
        "exactness": "unknown",
    }


def estimate_model_install_storage(
    model,
    *,
    overhead_fraction,
    overhead_min_bytes,
):
    """
    Estimate PEAK ADDITIONAL platform storage required to install
    one candidate model.

    Current transfer architecture stages the artifact and then
    atomically moves that staged directory into the model inventory
    destination on the same platform storage.

    Therefore we do not blindly calculate:

        artifact + second full permanent copy

    Instead:

        candidate artifact
        + conservative temporary/metadata allowance

    Future update/conversion/quantization operations will have
    separate peak-storage estimators because their lifecycle may
    require simultaneous source and replacement artifacts.
    """

    try:
        overhead_fraction = float(
            overhead_fraction
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "overhead_fraction must be numeric"
        ) from exc

    try:
        overhead_min_bytes = int(
            overhead_min_bytes
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "overhead_min_bytes must be an integer"
        ) from exc

    if overhead_fraction < 0:
        raise ValueError(
            "overhead_fraction cannot be negative"
        )

    if overhead_min_bytes < 0:
        raise ValueError(
            "overhead_min_bytes cannot be negative"
        )

    artifact = (
        resolve_model_artifact_size(
            model
        )
    )

    if not artifact[
        "resolved"
    ]:
        return {
            "schema_version": (
                MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
            ),

            "operation": "install",

            "resolved": False,

            "reason": (
                "artifact_size_unresolved"
            ),

            "artifact": artifact,

            "overhead_fraction": (
                overhead_fraction
            ),

            "overhead_min_bytes": (
                overhead_min_bytes
            ),

            "overhead_bytes": None,

            "peak_additional_bytes": None,

            "confidence": "unknown",
        }

    artifact_bytes = int(
        artifact[
            "bytes"
        ]
    )

    fractional_overhead = int(
        artifact_bytes
        * overhead_fraction
    )

    overhead_bytes = max(
        fractional_overhead,
        overhead_min_bytes,
    )

    peak_additional = (
        artifact_bytes
        + overhead_bytes
    )

    return {
        "schema_version": (
            MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
        ),

        "operation": "install",

        "resolved": True,

        "reason": None,

        "artifact": artifact,

        "overhead_fraction": (
            overhead_fraction
        ),

        "overhead_min_bytes": (
            overhead_min_bytes
        ),

        "overhead_bytes": (
            overhead_bytes
        ),

        "peak_additional_bytes": (
            peak_additional
        ),

        "confidence": (
            artifact[
                "confidence"
            ]
        ),
    }


def _calculate_operation_overhead(
    artifact_bytes,
    *,
    overhead_fraction,
    overhead_min_bytes,
):
    """
    Shared conservative temporary-space allowance.

    This is deliberately separate from artifact size because later
    operation types may use different policies.
    """

    try:
        artifact_bytes = int(
            artifact_bytes
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "artifact_bytes must be an integer"
        ) from exc

    try:
        overhead_fraction = float(
            overhead_fraction
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "overhead_fraction must be numeric"
        ) from exc

    try:
        overhead_min_bytes = int(
            overhead_min_bytes
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "overhead_min_bytes must be an integer"
        ) from exc

    if artifact_bytes < 0:
        raise ValueError(
            "artifact_bytes cannot be negative"
        )

    if overhead_fraction < 0:
        raise ValueError(
            "overhead_fraction cannot be negative"
        )

    if overhead_min_bytes < 0:
        raise ValueError(
            "overhead_min_bytes cannot be negative"
        )

    fractional = int(
        artifact_bytes
        * overhead_fraction
    )

    return max(
        fractional,
        overhead_min_bytes,
    )


def measure_local_import_source(
    source_path,
):
    """
    Measure a local import source BEFORE copying it.

    The current local-files transfer adapter copies source files
    into platform staging.

    For ordinary files/directories we can therefore calculate the
    source's logical file-byte footprint before mutation.

    SAFETY:
    Symlinks are deliberately treated as unresolved in this first
    implementation.

    shutil.copytree() currently follows symlink targets when
    symlinks=False (its default). Calling such a tree "exact" without
    mirroring every symlink traversal could underestimate the copy.

    Future local-import policy may explicitly reject symlinks or add
    a bounded, cycle-safe symlink-aware scanner.
    """

    import os

    from pathlib import Path


    original = Path(
        source_path
    ).expanduser()

    try:
        source = original.resolve(
            strict=True
        )

    except (
        OSError,
        RuntimeError,
    ):
        return {
            "resolved": False,

            "reason": (
                "local_import_source_missing_or_unresolvable"
            ),

            "source_path": str(
                original
            ),

            "resolved_path": None,

            "bytes": None,

            "file_count": None,

            "directory_count": None,

            "confidence": "unknown",

            "exactness": "unknown",
        }


    if not source.is_dir():
        return {
            "resolved": False,

            "reason": (
                "local_import_source_not_directory"
            ),

            "source_path": str(
                original
            ),

            "resolved_path": str(
                source
            ),

            "bytes": None,

            "file_count": None,

            "directory_count": None,

            "confidence": "unknown",

            "exactness": "unknown",
        }


    total_bytes = 0
    file_count = 0
    directory_count = 1


    for root, directories, files in os.walk(
        source,
        topdown=True,
        followlinks=False,
    ):
        root_path = Path(
            root
        )


        #
        # A directory symlink would be followed by the current copy
        # implementation. Refuse to label the footprint exact.
        #

        for name in directories:
            candidate = (
                root_path
                / name
            )

            if candidate.is_symlink():
                return {
                    "resolved": False,

                    "reason": (
                        "local_import_contains_symlink"
                    ),

                    "source_path": str(
                        original
                    ),

                    "resolved_path": str(
                        source
                    ),

                    "symlink_path": str(
                        candidate
                    ),

                    "bytes": None,

                    "file_count": None,

                    "directory_count": None,

                    "confidence": "unknown",

                    "exactness": "unknown",
                }


        directory_count += len(
            directories
        )


        for name in files:
            candidate = (
                root_path
                / name
            )


            if candidate.is_symlink():
                return {
                    "resolved": False,

                    "reason": (
                        "local_import_contains_symlink"
                    ),

                    "source_path": str(
                        original
                    ),

                    "resolved_path": str(
                        source
                    ),

                    "symlink_path": str(
                        candidate
                    ),

                    "bytes": None,

                    "file_count": None,

                    "directory_count": None,

                    "confidence": "unknown",

                    "exactness": "unknown",
                }


            try:
                stat = candidate.stat()

            except OSError:
                return {
                    "resolved": False,

                    "reason": (
                        "local_import_source_stat_failed"
                    ),

                    "source_path": str(
                        original
                    ),

                    "resolved_path": str(
                        source
                    ),

                    "problem_path": str(
                        candidate
                    ),

                    "bytes": None,

                    "file_count": None,

                    "directory_count": None,

                    "confidence": "unknown",

                    "exactness": "unknown",
                }


            if not candidate.is_file():
                return {
                    "resolved": False,

                    "reason": (
                        "local_import_contains_special_file"
                    ),

                    "source_path": str(
                        original
                    ),

                    "resolved_path": str(
                        source
                    ),

                    "problem_path": str(
                        candidate
                    ),

                    "bytes": None,

                    "file_count": None,

                    "directory_count": None,

                    "confidence": "unknown",

                    "exactness": "unknown",
                }


            total_bytes += int(
                stat.st_size
            )

            file_count += 1


    if file_count == 0:
        return {
            "resolved": False,

            "reason": (
                "local_import_source_empty"
            ),

            "source_path": str(
                original
            ),

            "resolved_path": str(
                source
            ),

            "bytes": 0,

            "file_count": 0,

            "directory_count": (
                directory_count
            ),

            "confidence": "unknown",

            "exactness": "empty_source",
        }


    return {
        "resolved": True,

        "reason": None,

        "source_path": str(
            original
        ),

        "resolved_path": str(
            source
        ),

        "bytes": int(
            total_bytes
        ),

        "file_count": int(
            file_count
        ),

        "directory_count": int(
            directory_count
        ),

        "confidence": "high",

        "exactness": (
            "pre_copy_logical_file_size_sum"
        ),
    }


def estimate_local_import_storage(
    source_path,
    *,
    overhead_fraction,
    overhead_min_bytes,
):
    """
    Estimate peak ADDITIONAL platform storage required for a local
    import.

    Source files exist outside the new managed destination and are
    copied into platform staging.

    The staged directory is then atomically moved into Inventory on
    the same platform storage, so we count:

        measured source artifact
        + conservative temporary allowance

    not:

        staged artifact
        + second full permanent destination copy
    """

    artifact = (
        measure_local_import_source(
            source_path
        )
    )


    if not artifact[
        "resolved"
    ]:
        return {
            "schema_version": (
                MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
            ),

            "operation": (
                "local_import"
            ),

            "resolved": False,

            "reason": (
                artifact[
                    "reason"
                ]
            ),

            "artifact": artifact,

            "overhead_fraction": float(
                overhead_fraction
            ),

            "overhead_min_bytes": int(
                overhead_min_bytes
            ),

            "overhead_bytes": None,

            "peak_additional_bytes": None,

            "confidence": (
                artifact[
                    "confidence"
                ]
            ),
        }


    artifact_bytes = int(
        artifact[
            "bytes"
        ]
    )

    overhead_bytes = (
        _calculate_operation_overhead(
            artifact_bytes,

            overhead_fraction=(
                overhead_fraction
            ),

            overhead_min_bytes=(
                overhead_min_bytes
            ),
        )
    )


    return {
        "schema_version": (
            MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
        ),

        "operation": (
            "local_import"
        ),

        "resolved": True,

        "reason": None,

        "artifact": artifact,

        "overhead_fraction": float(
            overhead_fraction
        ),

        "overhead_min_bytes": int(
            overhead_min_bytes
        ),

        "overhead_bytes": int(
            overhead_bytes
        ),

        "peak_additional_bytes": int(
            artifact_bytes
            + overhead_bytes
        ),

        "confidence": "high",

        "transfer_semantics": {
            "source_copied": True,

            "staging_to_destination": (
                "same_platform_atomic_move"
            ),

            "second_full_destination_copy": False,
        },
    }


def estimate_model_update_storage(
    current_model,
    replacement_model,
    *,
    overhead_fraction,
    overhead_min_bytes,
):
    """
    Estimate peak ADDITIONAL storage for rollback-safe update.

    Current lifecycle:

        current destination exists and is ALREADY counted in current
        platform usage

        replacement downloads into staging

        destination -> rollback       (same-storage rename)

        staging -> destination        (same-storage rename)

        rollback removed after success

    Therefore peak ADDITIONAL storage is:

        replacement artifact
        + temporary allowance

    The existing artifact is retained during the swap, but it must
    NOT be added again to the additional requirement because the
    live Storage Plan already counts it.

    `peak_relevant_total_bytes` is returned only as a diagnostic:
    existing + additional.
    """

    replacement = (
        resolve_model_artifact_size(
            replacement_model
        )
    )


    current_artifact = (
        current_model.get(
            "artifact"
        )
        or {}
    )

    current_bytes = (
        _positive_integer(
            current_artifact.get(
                "disk_usage_bytes"
            )
        )
    )


    if not replacement[
        "resolved"
    ]:
        return {
            "schema_version": (
                MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
            ),

            "operation": "update",

            "resolved": False,

            "reason": (
                "replacement_artifact_size_unresolved"
            ),

            "current_artifact_bytes": (
                current_bytes
            ),

            "replacement_artifact": (
                replacement
            ),

            "overhead_bytes": None,

            "peak_additional_bytes": None,

            "peak_relevant_total_bytes": None,

            "confidence": "unknown",

            "rollback_semantics": {
                "existing_artifact_already_in_current_usage": True,

                "existing_to_rollback": (
                    "same_platform_rename"
                ),

                "staging_to_destination": (
                    "same_platform_rename"
                ),

                "rollback_full_copy_required": False,
            },
        }


    replacement_bytes = int(
        replacement[
            "bytes"
        ]
    )

    overhead_bytes = (
        _calculate_operation_overhead(
            replacement_bytes,

            overhead_fraction=(
                overhead_fraction
            ),

            overhead_min_bytes=(
                overhead_min_bytes
            ),
        )
    )

    peak_additional = (
        replacement_bytes
        + overhead_bytes
    )

    peak_relevant_total = None

    if current_bytes is not None:
        peak_relevant_total = (
            int(
                current_bytes
            )
            + peak_additional
        )


    return {
        "schema_version": (
            MODEL_STORAGE_REQUIREMENTS_SCHEMA_VERSION
        ),

        "operation": "update",

        "resolved": True,

        "reason": None,

        "current_artifact_bytes": (
            current_bytes
        ),

        "replacement_artifact": (
            replacement
        ),

        "overhead_fraction": float(
            overhead_fraction
        ),

        "overhead_min_bytes": int(
            overhead_min_bytes
        ),

        "overhead_bytes": int(
            overhead_bytes
        ),

        "peak_additional_bytes": int(
            peak_additional
        ),

        "peak_relevant_total_bytes": (
            peak_relevant_total
        ),

        "confidence": (
            replacement[
                "confidence"
            ]
        ),

        "rollback_semantics": {
            "existing_artifact_already_in_current_usage": True,

            "existing_to_rollback": (
                "same_platform_rename"
            ),

            "staging_to_destination": (
                "same_platform_rename"
            ),

            "rollback_full_copy_required": False,
        },
    }

