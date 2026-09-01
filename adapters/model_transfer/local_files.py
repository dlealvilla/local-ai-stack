import shutil
from pathlib import Path


PROVIDER = "local_files"


def download(
    *,
    source_model_id,
    revision,
    destination,
    config,
):
    """
    Import an existing local model directory into managed storage.

    The source is copied, never moved or deleted.
    """

    source = Path(
        source_model_id
    ).expanduser().resolve()

    destination = Path(
        destination
    ).resolve()

    if not source.exists():
        raise RuntimeError(
            f"Local import source does not exist: {source}"
        )

    if not source.is_dir():
        raise RuntimeError(
            "Local import source must be a directory."
        )

    if source == destination:
        raise RuntimeError(
            "Import source and destination cannot be identical."
        )

    for child in source.iterdir():
        target = destination / child.name

        if child.is_dir():
            shutil.copytree(
                child,
                target,
                dirs_exist_ok=True,
            )
        else:
            shutil.copy2(
                child,
                target,
            )

    return {
        "source_path": str(source),
        "requested_revision": None,
        "resolved_revision": None,
        "local_path": str(destination),
    }
