"""What identifies a host across restarts.

The fingerprint is the key by which cached evidence is judged reusable from
Milestone 2 onward, so what it covers is a load-bearing decision rather than
a detail.

It covers **stable facts only**: architecture, CPU identity and layout,
total memory, accelerator identity and count, and mount identity. It
excludes available memory, free space and anything else that moves between
one minute and the next — a fingerprint over volatile values would
invalidate every expensive probe on every restart, turning Milestone 2's
most costly work into something that is never reused.

It also excludes **provider-local handles**, under the invariant in
`docs/ARCHITECTURE.md` Part II §6. A handle can change across a process
restart, and a fingerprint built on one would be unstable for a reason
nothing in Kultrun could diagnose.
"""

from __future__ import annotations

import hashlib
import json

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import is_resolved

#: Recorded here rather than left implicit, because widening it later is a
#: change to what "the same host" means.
STABLE_INPUTS = (
    "operating_environment.architecture",
    "cpu.vendor",
    "cpu.model_name",
    "cpu.physical_cores",
    "cpu.logical_cores",
    "memory.total_bytes",
    "accelerators[].vendor",
    "accelerators[].model_name",
    "accelerators[].memory_total_bytes",
    "mounts[].mount_point",
    "mounts[].filesystem_type",
    "mounts[].total_bytes",
)


def compute(capabilities: HostCapabilities) -> str:
    """A stable digest of the facts that make this the same host.

    Unresolved inputs contribute the literal marker rather than being
    skipped: a host whose core count could not be read is a different
    fingerprint from one where it could, because the evidence available
    about it genuinely differs.
    """
    payload = {
        "architecture": capabilities.operating_environment.architecture.value,
        "cpu": [
            _stable(capabilities.cpu.vendor),
            _stable(capabilities.cpu.model_name),
            _stable(capabilities.cpu.physical_cores),
            _stable(capabilities.cpu.logical_cores),
        ],
        "memory_total_bytes": _stable(capabilities.memory.total_bytes),
        "accelerators": [
            [
                accelerator.vendor.value,
                _stable(accelerator.model_name),
                _stable(accelerator.memory_total_bytes),
            ]
            for accelerator in capabilities.accelerators
        ],
        "mounts": [
            [
                mount.mount_point,
                _stable(mount.filesystem_type),
                _stable(mount.total_bytes),
            ]
            for mount in capabilities.mounts
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _stable(value: object) -> object:
    return value if is_resolved(value) else "<unresolved>"
