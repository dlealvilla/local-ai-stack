"""Block 1 Install — this Machi copy on this disk.

1.2.1 StateRootBinder, 1.3.1 SelfOwnershipMarker, 1.3.2 RegistrySeed,
1.1.1 InstallRecord, and 1.4.1 InstallRunStore are implemented.
"""

from machi.install.binder import StateRootBinder
from machi.install.contracts import (
    InstallRecordEstablishment,
    InstallRunEstablishment,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    StateRootBinding,
)
from machi.install.events import (
    install_bound,
    install_record_established,
    local_ownership_marked,
    ownership_registry_seeded,
    state_root_bound,
)
from machi.install.identity import InstallIdentity
from machi.install.marker import SelfOwnershipMarker
from machi.install.registry import RegistrySeed
from machi.install.run import InstallRunStore

__all__ = [
    "InstallIdentity",
    "InstallRecordEstablishment",
    "InstallRunEstablishment",
    "InstallRunStore",
    "LocalOwnershipEstablishment",
    "LocalOwnershipRegistryEstablishment",
    "RegistrySeed",
    "SelfOwnershipMarker",
    "StateRootBinder",
    "StateRootBinding",
    "install_bound",
    "install_record_established",
    "local_ownership_marked",
    "ownership_registry_seeded",
    "state_root_bound",
]
