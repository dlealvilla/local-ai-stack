"""Block 2 Discover — observe the host. Never mutate. Never authorize.

2.1.1 OS/arch and 2.2.1 Memory are implemented. Accelerator discovery
is a generic later capability; NVIDIA is one future provider, not the
capability. Fixtures, mounts, HostId, and HostProfile remain later.
"""

from machi.discover.contracts import MemoryObservation, OSArchitectureObservation
from machi.discover.events import memory_observed, os_arch_observed
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import MemoryObserver, OSArchitectureObserver

__all__ = [
    "MemoryObservation",
    "MemoryObserver",
    "OSArchitectureObservation",
    "OSArchitectureObserver",
    "memory_observed",
    "normalize_os_architecture",
    "os_arch_observed",
]
