from datetime import (
    datetime,
    timezone,
)
from pathlib import Path
import os
import shutil

from core.config import load_config
from core.hardware import inspect_hardware
from core.model_inventory import (
    list_model_inventory,
)


CAPACITY_SNAPSHOT_SCHEMA_VERSION = 1


def _read_available_ram_bytes():
    """
    Read currently available host RAM without introducing
    an additional dependency.

    Linux exposes MemAvailable in /proc/meminfo.
    """

    path = Path(
        "/proc/meminfo"
    )

    if not path.exists():
        return None

    try:
        for line in path.read_text().splitlines():
            if line.startswith(
                "MemAvailable:"
            ):
                parts = line.split()

                if len(parts) >= 2:
                    return (
                        int(parts[1])
                        * 1024
                    )

    except (
        OSError,
        ValueError,
    ):
        return None

    return None


def _gib_to_bytes(value):
    if not isinstance(
        value,
        (int, float),
    ):
        return None

    return int(
        value
        * (1024 ** 3)
    )


def _build_accelerators(
    hardware,
):
    accelerators = []

    for index, gpu in enumerate(
        hardware.get(
            "gpus",
            []
        )
    ):
        total = _gib_to_bytes(
            gpu.get(
                "vram_total_gb"
            )
        )

        free = _gib_to_bytes(
            gpu.get(
                "vram_free_gb"
            )
        )

        used = None

        if (
            total is not None
            and free is not None
        ):
            used = max(
                0,
                total - free,
            )

        accelerators.append({
            "index": index,
            "vendor": gpu.get(
                "vendor"
            ),
            "name": gpu.get(
                "name"
            ),
            "memory": {
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
            },
        })

    return accelerators


def build_capacity_snapshot():
    """
    Build one normalized read-only snapshot of resources
    relevant to model capacity planning.

    This does NOT perform admission control.

    Compatibility asks:
        Could this model plausibly run on this host?

    Capacity asks:
        What resources are actually available now?

    Resource Manager later asks:
        May this workload be admitted/reserved?
    """

    config = load_config()
    hardware = inspect_hardware()

    inventory = (
        list_model_inventory()
    )

    models = inventory.get(
        "models",
        []
    )

    data_root = Path(
        config[
            "platform"
        ][
            "data_root"
        ]
    ).resolve()

    storage = shutil.disk_usage(
        data_root
    )

    ram_total = _gib_to_bytes(
        hardware.get(
            "ram_total_gb"
        )
    )

    ram_available = (
        _read_available_ram_bytes()
    )

    ram_used = None

    if (
        ram_total is not None
        and ram_available is not None
    ):
        ram_used = max(
            0,
            ram_total
            - ram_available,
        )

    installed_model_bytes = sum(
        int(
            model.get(
                "artifact",
                {},
            ).get(
                "disk_usage_bytes"
            )
            or 0
        )
        for model in models
    )

    managed_model_bytes = sum(
        int(
            model.get(
                "artifact",
                {},
            ).get(
                "disk_usage_bytes"
            )
            or 0
        )
        for model in models
        if (
            model.get(
                "management",
                {},
            ).get(
                "managed"
            )
            is True
        )
    )

    selected_models = [
        model["model_id"]
        for model in models
        if (
            model.get(
                "deployment",
                {},
            ).get(
                "selected"
            )
        )
    ]

    running_models = [
        model["model_id"]
        for model in models
        if (
            model.get(
                "deployment",
                {},
            ).get(
                "service_state"
            )
            == "running"
        )
    ]

    loaded_models = [
        model["model_id"]
        for model in models
        if (
            model.get(
                "deployment",
                {},
            ).get(
                "load_state"
            )
            == "loaded"
        )
    ]

    return {
        "schema_version": (
            CAPACITY_SNAPSHOT_SCHEMA_VERSION
        ),

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "host": {
            "operating_system": (
                hardware.get(
                    "operating_system"
                )
            ),
            "architecture": (
                hardware.get(
                    "architecture"
                )
            ),
            "cpu_model": (
                hardware.get(
                    "cpu_model"
                )
            ),
            "cpu_cores": (
                hardware.get(
                    "cpu_cores"
                )
            ),
        },

        "memory": {
            "total_bytes": (
                ram_total
            ),
            "used_bytes": (
                ram_used
            ),
            "available_bytes": (
                ram_available
            ),

            # WORKING:
            # Linux MemAvailable is live operating-system state.
            "availability_source": (
                "/proc/meminfo:MemAvailable"
                if ram_available
                is not None
                else None
            ),
        },

        "accelerators": (
            _build_accelerators(
                hardware
            )
        ),

        "storage": {
            "path": str(
                data_root
            ),
            "total_bytes": (
                storage.total
            ),
            "used_bytes": (
                storage.used
            ),
            "free_bytes": (
                storage.free
            ),

            # Important distinction for network/cloud volumes.
            #
            # WORKING:
            # These values are what the mounted filesystem reports.
            #
            # FUTURE:
            # A provider/storage adapter may supply an account quota
            # or customer-specific allocation that differs from this.
            "scope": (
                "mounted_filesystem_observation"
            ),
            "quota_known": False,
        },

        "inventory": {
            "model_count": len(
                models
            ),
            "installed_model_bytes": (
                installed_model_bytes
            ),
            "managed_model_bytes": (
                managed_model_bytes
            ),
        },

        "workload": {
            "selected_model_ids": (
                selected_models
            ),
            "running_model_ids": (
                running_models
            ),
            "loaded_model_ids": (
                loaded_models
            ),

            # FUTURE:
            # Resource Manager will provide explicit reservations.
            "reservations": None,
        },
    }
