import os
import stat

from pathlib import Path

from core.config import load_config


PLATFORM_STORAGE_USAGE_SCHEMA_VERSION = 1


def _resolve_relative_to_data_root(
    value,
    *,
    data_root,
):
    path = Path(
        value
    )

    if path.is_absolute():
        return path.resolve()

    return (
        data_root
        / path
    ).resolve()


def _resolve_model_root(
    config,
    *,
    data_root,
):
    """
    Reuse an explicitly configured model root when one exists.

    Otherwise use the platform layout convention:

        <data_root>/models

    On the current deployment:

        data_root = /workspace
        model root = /workspace/models
    """

    model_settings = config.get(
        "model",
        {},
    )

    configured = (
        model_settings.get(
            "root"
        )
        or model_settings.get(
            "models_root"
        )
        or model_settings.get(
            "directory"
        )
    )

    if configured:
        return _resolve_relative_to_data_root(
            configured,
            data_root=data_root,
        )

    return (
        data_root
        / "models"
    ).resolve()


def _resolve_transfer_staging_root(
    config,
    *,
    data_root,
):
    settings = config.get(
        "model_transfer",
        {},
    )

    configured = settings.get(
        "staging_root",
        "data/model-transfers",
    )

    return _resolve_relative_to_data_root(
        configured,
        data_root=data_root,
    )


def measure_path_usage(
    path,
):
    """
    Measure files physically represented by one platform scope.

    Primary accounting:
        logical_bytes

    Diagnostic accounting:
        reported_allocated_bytes

    Why logical size is primary:
    - some FUSE/network filesystems report st_blocks=0;
    - model artifacts are normally fully materialized files;
    - logical size avoids pretending zero-byte allocation on
      filesystems that hide physical block accounting.

    Hard links are counted once using device/inode identity.

    Symlinks are NOT followed because blindly following them could
    escape the intended platform storage scope or double-count
    external caches.
    """

    root = Path(
        path
    ).resolve()

    if not root.exists():
        return {
            "path": str(root),
            "exists": False,
            "logical_bytes": 0,
            "reported_allocated_bytes": 0,
            "file_count": 0,
            "directory_count": 0,
            "symlink_count": 0,
            "hardlink_duplicates_ignored": 0,
            "errors": [],
        }

    seen_files = set()

    logical_bytes = 0
    reported_allocated_bytes = 0

    file_count = 0
    directory_count = 0
    symlink_count = 0
    hardlink_duplicates_ignored = 0

    errors = []

    for current_root, directories, files in os.walk(
        root,
        topdown=True,
        followlinks=False,
    ):
        directory_count += len(
            directories
        )

        #
        # Do not descend through symlinked directories.
        #

        kept_directories = []

        for directory in directories:
            candidate = (
                Path(current_root)
                / directory
            )

            try:
                info = candidate.lstat()

            except OSError as exc:
                errors.append({
                    "path": str(candidate),
                    "error": str(exc),
                })
                continue

            if stat.S_ISLNK(
                info.st_mode
            ):
                symlink_count += 1
                continue

            kept_directories.append(
                directory
            )

        directories[:] = (
            kept_directories
        )

        for filename in files:
            candidate = (
                Path(current_root)
                / filename
            )

            try:
                info = candidate.lstat()

            except OSError as exc:
                errors.append({
                    "path": str(candidate),
                    "error": str(exc),
                })
                continue

            if stat.S_ISLNK(
                info.st_mode
            ):
                symlink_count += 1
                continue

            if not stat.S_ISREG(
                info.st_mode
            ):
                continue

            identity = (
                int(
                    info.st_dev
                ),
                int(
                    info.st_ino
                ),
            )

            if identity in seen_files:
                hardlink_duplicates_ignored += 1
                continue

            seen_files.add(
                identity
            )

            logical_bytes += int(
                info.st_size
            )

            reported_allocated_bytes += int(
                getattr(
                    info,
                    "st_blocks",
                    0,
                )
                * 512
            )

            file_count += 1

    return {
        "path": str(root),
        "exists": True,
        "logical_bytes": (
            logical_bytes
        ),
        "reported_allocated_bytes": (
            reported_allocated_bytes
        ),
        "file_count": (
            file_count
        ),
        "directory_count": (
            directory_count
        ),
        "symlink_count": (
            symlink_count
        ),
        "hardlink_duplicates_ignored": (
            hardlink_duplicates_ignored
        ),
        "errors": errors,
    }


def measure_platform_storage_usage(
    config=None,
):
    """
    Measure current platform-resident storage.

    Current WORKING scopes:

    models
        All artifacts stored inside the platform's model root.

        This intentionally includes both managed and currently
        unmanaged/local models residing there. Physical storage
        policy cannot ignore a model merely because its lifecycle
        metadata says managed=False.

    transfer_staging
        Temporary model download/import staging.

    FUTURE scopes can be added without changing Capacity Planner:
        conversion outputs
        quantization outputs
        explicitly platform-managed caches
        snapshots/checkpoints owned by the product
    """

    if config is None:
        config = load_config()

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    model_root = _resolve_model_root(
        config,
        data_root=data_root,
    )

    staging_root = (
        _resolve_transfer_staging_root(
            config,
            data_root=data_root,
        )
    )

    scopes = {
        "models": measure_path_usage(
            model_root
        ),

        "transfer_staging": (
            measure_path_usage(
                staging_root
            )
        ),
    }

    #
    # Protect against accidental overlapping accounting scopes.
    #

    resolved_paths = {
        name: Path(
            item[
                "path"
            ]
        ).resolve()
        for name, item
        in scopes.items()
    }

    overlap_warnings = []

    names = list(
        resolved_paths
    )

    for index, left_name in enumerate(
        names
    ):
        left = resolved_paths[
            left_name
        ]

        for right_name in names[
            index + 1:
        ]:
            right = resolved_paths[
                right_name
            ]

            if (
                left == right
                or left in right.parents
                or right in left.parents
            ):
                overlap_warnings.append(
                    (
                        "Storage accounting scopes overlap: "
                        + left_name
                        + " and "
                        + right_name
                    )
                )

    if overlap_warnings:
        #
        # We refuse to sum overlapping scopes because doing so
        # would knowingly double-count platform storage.
        #
        total_logical = None
        total_allocated = None

    else:
        total_logical = sum(
            item[
                "logical_bytes"
            ]
            for item
            in scopes.values()
        )

        total_allocated = sum(
            item[
                "reported_allocated_bytes"
            ]
            for item
            in scopes.values()
        )

    errors = []

    for name, item in scopes.items():
        for error in item[
            "errors"
        ]:
            errors.append({
                "scope": name,
                **error,
            })

    warnings = list(
        overlap_warnings
    )

    total_symlinks = sum(
        item[
            "symlink_count"
        ]
        for item
        in scopes.values()
    )

    if total_symlinks:
        warnings.append(
            (
                "One or more symlinks were observed and "
                "not followed. External symlink targets are "
                "not included in this platform usage total."
            )
        )

    return {
        "schema_version": (
            PLATFORM_STORAGE_USAGE_SCHEMA_VERSION
        ),

        "data_root": str(
            data_root
        ),

        "scopes": scopes,

        "total_logical_bytes": (
            total_logical
        ),

        "total_reported_allocated_bytes": (
            total_allocated
        ),

        "accounting_basis": (
            "logical_file_size"
        ),

        "scope_overlap": bool(
            overlap_warnings
        ),

        "warnings": warnings,

        "errors": errors,
    }
