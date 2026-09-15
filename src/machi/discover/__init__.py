"""Block 2 Discover — observe the host. Never mutate. Never authorize.

2.1.1 OS/arch adapter is implemented. Memory, NVIDIA, fixtures, mounts,
HostId, and HostProfile remain later Components.
"""

from machi.discover.contracts import OSArchitectureObservation
from machi.discover.events import os_arch_observed
from machi.discover.normalize import normalize_os_architecture
from machi.discover.ports import OSArchitectureObserver

__all__ = [
    "OSArchitectureObservation",
    "OSArchitectureObserver",
    "normalize_os_architecture",
    "os_arch_observed",
]
