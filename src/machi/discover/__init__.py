"""Block 2 Discover — observe the host. Never mutate. Never authorize.

2.1.1 OS/arch and 2.2.1 Memory are implemented. NVIDIA, fixtures, mounts,
HostId, and HostProfile remain later Components.
"""

from machi.discover.contracts import MemoryObservation, OSArchitectureObservation
from machi.discover.events import memory_observed, os_arch_observed
from machi.discover.memory import parse_linux_memory_table
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
    "parse_linux_memory_table",
]
