"""Linux filesystem quota via the optional system `quota` tool.

Not a mandatory dependency. GPL quota-tools are never bundled.
"""

from __future__ import annotations

import shutil
import subprocess

from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)

_LOCAL = {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs"}


class LinuxQuotaProbe:
    """Best-effort project/user quota. Missing tooling is not a crash."""

    name = "linux-quota"
    technology = "linux-quota"

    def supports(self, environment: StorageEnvironment) -> bool:
        if environment.os_name != "linux":
            return False
        family = (
            environment.filesystem_type
            if is_resolved(environment.filesystem_type)
            else ""
        )
        return str(family).lower() in _LOCAL

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        binary = shutil.which("quota")
        if binary is None:
            return CapacityProbeResult(
                available=False,
                executed=False,
                detail="quota tool is not installed; optional system dependency",
            )
        try:
            completed = subprocess.run(
                [binary, "-w", environment.mount_point],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return CapacityProbeResult(
                available=True,
                executed=False,
                detail=str(error),
            )
        return CapacityProbeResult(
            available=True,
            executed=True,
            available_bytes=NOT_PROVIDED,
            detail=(
                "quota ran; unstructured output is not parsed in v1: "
                f"exit {completed.returncode}"
            ),
        )
