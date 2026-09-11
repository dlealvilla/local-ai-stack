"""Linux filesystem quota via the optional system `quota` tool.

Not a mandatory dependency. GPL quota-tools are never bundled.
"""

from __future__ import annotations

import shutil
import subprocess

from kultrun.adapters.storage.quota_parse import parse_linux_quota_w
from kultrun.kernel.unresolved import is_resolved
from kultrun.storage.ports import CapacityProbeResult, StorageEnvironment

_LOCAL = {"ext2", "ext3", "ext4", "xfs", "btrfs", "f2fs", "zfs"}


class LinuxQuotaProbe:
    """Best-effort user/group quota. Missing tooling is not a crash."""

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
                [binary, "-w"],
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
        text = f"{completed.stdout}\n{completed.stderr}"
        available, hard, parsed = parse_linux_quota_w(
            text, filesystem=_filesystem_hint(environment)
        )
        if is_resolved(available):
            return CapacityProbeResult(
                available_bytes=available,
                hard_maximum_bytes=hard,
                available=True,
                executed=True,
                detail=parsed,
            )
        return CapacityProbeResult(
            available=True,
            executed=True,
            detail=(
                f"{parsed}; exit {completed.returncode}. "
                "No user/group remaining bytes (unlimited or unreadable)"
            ),
        )


def _filesystem_hint(environment: StorageEnvironment) -> str | None:
    device = environment.device if is_resolved(environment.device) else None
    if isinstance(device, str) and device.strip():
        return device.strip()
    return environment.mount_point
