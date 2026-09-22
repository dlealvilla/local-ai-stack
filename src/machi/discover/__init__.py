"""Block 2 Discover — observe the host. Never mutate. Never authorize.

2.1.1 OS/arch, 2.2.1 Memory, 2.3 Accelerator Discovery, and 2.4.1 Mounts
are implemented. NVIDIA, AMD, and Apple are providers under the generic
accelerator observer. Linux and macOS are mount providers under the
generic mount observer. Intel is vocabulary only. HostId and HostProfile
remain later.
"""

from machi.discover.contracts import (
    AcceleratorObservation,
    MemoryObservation,
    OSArchitectureObservation,
)
from machi.discover.events import (
    accelerator_observed,
    memory_observed,
    mounts_observed,
    os_arch_observed,
)
from machi.discover.mount_contracts import MountObservation
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import (
    AcceleratorObserver,
    MemoryObserver,
    MountObserver,
    OSArchitectureObserver,
)

__all__ = [
    "AcceleratorObservation",
    "AcceleratorObserver",
    "MemoryObservation",
    "MemoryObserver",
    "MountObservation",
    "MountObserver",
    "OSArchitectureObservation",
    "OSArchitectureObserver",
    "accelerator_observed",
    "memory_observed",
    "mounts_observed",
    "normalize_os_architecture",
    "os_arch_observed",
]
