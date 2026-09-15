"""Block 1 Install — this Machi copy on this disk.

1.2.1 StateRootBinder, 1.3.1 SelfOwnershipMarker, 1.3.2 RegistrySeed,
and 1.1.1 InstallRecord are implemented. 1.4.1 InstallRunStore is not
present yet.
"""

from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecordEstablishment,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    StateRootBinding,
)
from machi.install.events import (
    install_record_established,
    local_ownership_marked,
    ownership_registry_seeded,
    state_root_bound,
)
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed

__all__ = [
    "InstallIdentity",
    "InstallRecordEstablishment",
    "LocalOwnershipEstablishment",
    "LocalOwnershipRegistryEstablishment",
    "RegistrySeed",
    "SelfOwnershipMarker",
    "StateRootBinder",
    "StateRootBinding",
    "install_record_established",
    "local_ownership_marked",
    "ownership_registry_seeded",
    "state_root_bound",
]
