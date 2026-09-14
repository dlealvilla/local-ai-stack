"""Block 1 Install — this Machi copy on this disk.

1.2.1 StateRootBinder and 1.3.1 SelfOwnershipMarker are implemented.
1.1.1 InstallRecord and 1.4.1 InstallRunStore are not present yet.
"""

from machi.install.binder import StateRootBinder
from machi.install.contracts import LocalOwnershipEstablishment, StateRootBinding
from machi.install.events import local_ownership_marked, state_root_bound
from machi.install.marker import SelfOwnershipMarker

__all__ = [
    "LocalOwnershipEstablishment",
    "SelfOwnershipMarker",
    "StateRootBinder",
    "StateRootBinding",
    "local_ownership_marked",
    "state_root_bound",
]
