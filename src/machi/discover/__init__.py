"""Block 2 Discover — observe the host. Never mutate. Never authorize.

2.1.1 OS/arch, 2.2.1 Memory, and 2.3 Accelerator Discovery are
implemented. NVIDIA and Apple are providers under the generic
observer, not the capability model. Fixtures, mounts, HostId, and
HostProfile remain later.
"""

from machi.discover.contracts import (
    AcceleratorObservation,
    MemoryObservation,
    OSArchitectureObservation,
)
from machi.discover.events import (
    accelerator_observed,
    memory_observed,
    os_arch_observed,
)
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import (
    AcceleratorObserver,
    MemoryObserver,
    OSArchitectureObserver,
)

__all__ = [
    "AcceleratorObservation",
    "AcceleratorObserver",
    "MemoryObservation",
    "MemoryObserver",
    "OSArchitectureObservation",
    "OSArchitectureObserver",
    "accelerator_observed",
    "memory_observed",
    "normalize_os_architecture",
    "os_arch_observed",
]
