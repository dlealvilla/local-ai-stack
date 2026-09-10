"""MooseFS-compatible quota, only when the optional mfs tooling is present."""

from __future__ import annotations

import shutil
import subprocess

from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.ports import (
    CapacityProbeResult,
    StorageEnvironment,
)


class MooseFSQuotaProbe:
    """Read MooseFS quota if `mfsgetquota` exists. Never a hard dependency."""

    name = "moosefs-quota"
    technology = "moosefs"

    def supports(self, environment: StorageEnvironment) -> bool:
        family = (
            str(environment.filesystem_type).lower()
            if is_resolved(environment.filesystem_type)
            else ""
        )
        device = (
            str(environment.device).lower() if is_resolved(environment.device) else ""
        )
        return (
            "mfs" in family
            or "moosefs" in family
            or "mfs" in device
            or "moosefs" in device
        )

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        binary = shutil.which("mfsgetquota")
        if binary is None:
            return CapacityProbeResult(
                available=False,
                executed=False,
                detail="mfsgetquota is not installed; optional MooseFS tooling",
            )
        try:
            completed = subprocess.run(
                [binary, environment.mount_point],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return CapacityProbeResult(
                available=True,
                executed=False,
                detail=str(error),
            )
        available, hard, parsed = _parse_mfs(completed.stdout)
        return CapacityProbeResult(
            available_bytes=available,
            hard_maximum_bytes=hard,
            available=True,
            executed=True,
            detail=parsed or completed.stdout[:200],
        )


def _parse_mfs(output: str) -> tuple[Maybe[int], Maybe[int], str]:
    """Best-effort parse of `mfsgetquota`. Unknown stays unresolved."""
    del output
    return NOT_PROVIDED, NOT_PROVIDED, "mfsgetquota output not numerically parsed in v1"
