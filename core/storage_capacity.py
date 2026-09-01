import os
import re
import subprocess

from pathlib import Path

from adapters.storage_capacity import (
    get_storage_capacity_provider,
)

from core.config import load_config


STORAGE_CAPACITY_SCHEMA_VERSION = 1


def _mount_source(
    path,
):
    try:
        result = subprocess.run(
            [
                "findmnt",
                "-n",
                "-T",
                str(path),
                "-o",
                "SOURCE",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        return (
            result.stdout.strip()
            or None
        )

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
    ):
        return None


def detect_storage_capacity_provider(
    *,
    path,
):
    """
    Detect the most specific known storage-capacity adapter.

    Detection is capability/environment based rather than
    hard-coding a server model.
    """

    source = _mount_source(
        path
    )

    runpod_volume = os.environ.get(
        "RUNPOD_VOLUME_ID"
    )

    if runpod_volume:
        return {
            "provider": (
                "runpod_network_volume"
            ),
            "reason": (
                "RUNPOD_VOLUME_ID is present."
            ),
        }

    if (
        source
        and (
            "runpod.net" in source.lower()
            or re.search(
                r"/networkvolumes/",
                source,
                re.IGNORECASE,
            )
        )
    ):
        return {
            "provider": (
                "runpod_network_volume"
            ),
            "reason": (
                "Mounted filesystem source "
                "identifies a RunPod Network Volume."
            ),
        }

    return {
        "provider": (
            "generic_filesystem"
        ),
        "reason": (
            "No more specific storage provider "
            "was detected."
        ),
    }


def inspect_storage_capacity(
    config=None,
):
    """
    Resolve storage capacity through the most appropriate
    replaceable adapter.
    """

    if config is None:
        config = load_config()

    settings = config.get(
        "storage_capacity",
        {},
    )

    configured_provider = (
        settings.get(
            "provider",
            "auto",
        )
    )

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    if configured_provider == "auto":
        detection = (
            detect_storage_capacity_provider(
                path=data_root
            )
        )

        provider_name = (
            detection[
                "provider"
            ]
        )

    else:
        provider_name = (
            configured_provider
        )

        detection = {
            "provider": (
                provider_name
            ),
            "reason": (
                "Provider explicitly configured."
            ),
        }

    provider = (
        get_storage_capacity_provider(
            provider_name
        )
    )

    result = (
        provider.inspect_storage_capacity(
            path=data_root,
            config=config,
        )
    )

    return {
        "schema_version": (
            STORAGE_CAPACITY_SCHEMA_VERSION
        ),

        "detection": detection,

        **result,
    }
