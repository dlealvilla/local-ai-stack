"""Verification identity. Free RAM and current VRAM are never included."""

from __future__ import annotations

import hashlib

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import RuntimeInstallation


def verification_fingerprint(
    installation: RuntimeInstallation, host: HostCapabilities
) -> str:
    """Identity of the load-bearing runtime environment.

    Changes to runtime version, executor, accelerator identity or driver
    invalidate evidence. Changes to free capacity do not.
    """
    accelerators = []
    for item in host.accelerators:
        memory = (
            item.memory_total_bytes
            if is_resolved(item.memory_total_bytes)
            else "unknown"
        )
        driver = (
            item.driver_version if is_resolved(item.driver_version) else "unknown"
        )
        model = item.model_name if is_resolved(item.model_name) else "unknown"
        accelerators.append(
            f"{item.index}:{item.vendor.value}:{model}:{memory}:{driver}"
        )
    raw = "|".join(
        [
            installation.runtime_provider.value,
            installation.runtime_family.value,
            installation.runtime_version,
            installation.executor_kind.value,
            host.host_id.value,
            host.fingerprint,
            ",".join(accelerators),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
