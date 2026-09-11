"""ZFS dataset capacity. Pool-free is not an entitlement."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment


class ZfsDatasetProbe:
    """Map a path to a ZFS dataset and read available/quota/refquota."""

    name = "zfs-dataset"
    technology = "zfs"

    def supports(self, environment: StorageEnvironment) -> bool:
        family = (
            str(environment.filesystem_type).lower()
            if is_resolved(environment.filesystem_type)
            else ""
        )
        return family == "zfs"

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        binary = shutil.which("zfs")
        if binary is None:
            return CapacityProbeResult(
                available=False,
                executed=False,
                detail="zfs is not installed; optional ZFS tooling",
            )
        dataset = _dataset_for_path(binary, environment.mount_point)
        if dataset is None:
            return CapacityProbeResult(
                available=True,
                executed=True,
                detail="no ZFS dataset matched this mount",
            )
        values = _zfs_get(
            binary,
            dataset,
            ("available", "quota", "refquota", "used"),
        )
        available = values.get("available")
        quota = values.get("quota")
        refquota = values.get("refquota")
        used = values.get("used")
        caps = [
            value for value in (quota, refquota) if isinstance(value, int) and value > 0
        ]
        if caps:
            ceiling = min(caps)
            if isinstance(used, int):
                remaining = max(0, ceiling - used)
            else:
                remaining = ceiling
            return CapacityProbeResult(
                available_bytes=remaining,
                hard_maximum_bytes=ceiling,
                available=True,
                executed=True,
                detail=f"zfs dataset {dataset} quota/refquota remaining",
            )
        if isinstance(available, int):
            return CapacityProbeResult(
                available_bytes=available,
                available=True,
                executed=True,
                detail=f"zfs dataset {dataset} available (no quota/refquota)",
            )
        return CapacityProbeResult(
            available=True,
            executed=True,
            detail=f"zfs dataset {dataset} had no numeric available",
        )


def _dataset_for_path(binary: str, mount_point: str) -> str | None:
    try:
        completed = subprocess.run(
            [binary, "list", "-H", "-o", "name,mountpoint"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    target = (
        str(Path(mount_point).resolve()) if Path(mount_point).exists() else mount_point
    )
    best: tuple[int, str] | None = None
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, mount = parts[0], parts[1]
        if mount == "-":
            continue
        if target == mount or target.startswith(mount.rstrip("/") + "/"):
            score = len(mount)
            if best is None or score > best[0]:
                best = (score, name)
    return None if best is None else best[1]


def _zfs_get(
    binary: str, dataset: str, properties: tuple[str, ...]
) -> dict[str, Maybe[int]]:
    try:
        completed = subprocess.run(
            [
                binary,
                "get",
                "-Hp",
                "-o",
                "property,value",
                ",".join(properties),
                dataset,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    values: dict[str, Maybe[int]] = {}
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name, raw = parts[0], parts[1]
        if raw in {"-", "none"}:
            values[name] = NOT_PROVIDED
            continue
        if raw.isdigit():
            values[name] = int(raw)
    return values
