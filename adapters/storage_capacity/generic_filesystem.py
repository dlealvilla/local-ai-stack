import json
import shutil
import subprocess

from pathlib import Path


PROVIDER = "generic_filesystem"


def _find_mount(path):
    """
    Inspect the mount containing path.

    This is descriptive evidence only.
    It does not assume that filesystem totals represent
    a customer/account quota.
    """

    try:
        result = subprocess.run(
            [
                "findmnt",
                "-J",
                "-T",
                str(path),
                "-o",
                "TARGET,SOURCE,FSTYPE,OPTIONS",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        payload = json.loads(
            result.stdout
        )

        filesystems = payload.get(
            "filesystems",
            []
        )

        if not filesystems:
            return None

        item = filesystems[0]

        return {
            "target": item.get(
                "target"
            ),
            "source": item.get(
                "source"
            ),
            "filesystem_type": item.get(
                "fstype"
            ),
            "options": item.get(
                "options"
            ),
        }

    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ):
        return None


def inspect_storage_capacity(
    *,
    path,
    config,
):
    """
    Generic filesystem observation.

    IMPORTANT:
    statvfs/shutil.disk_usage describes what the mounted
    filesystem reports. It may or may not represent the
    customer's actual quota.
    """

    path = Path(
        path
    ).resolve()

    usage = shutil.disk_usage(
        path
    )

    return {
        "provider": PROVIDER,

        "path": str(
            path
        ),

        "mount": _find_mount(
            path
        ),

        "filesystem": {
            "total_bytes": (
                usage.total
            ),
            "used_bytes": (
                usage.used
            ),
            "free_bytes": (
                usage.free
            ),
        },

        "quota": {
            "known": False,
            "total_bytes": None,
            "source": None,
        },

        "confidence": "low",

        "notes": [
            (
                "Filesystem capacity is an observation, "
                "not an authoritative customer quota."
            ),
        ],
    }
