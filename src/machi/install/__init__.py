"""Block 1 Install — this Machi copy on this disk.

M1.2.1 implements only StateRootBinder. Later Components in this
package (InstallRecord, SelfOwnershipMarker, InstallRunStore) are
not present yet.
"""

from machi.install.binder import StateRootBinder
from machi.install.contracts import StateRootBinding
from machi.install.events import state_root_bound

__all__ = ["StateRootBinder", "StateRootBinding", "state_root_bound"]
