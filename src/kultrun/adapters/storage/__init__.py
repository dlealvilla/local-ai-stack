"""Storage reservation adapters.

Technology-specific probes live here. Generic storage core never imports them.
"""

from kultrun.adapters.storage.ceph import CephfsQuotaProbe
from kultrun.adapters.storage.empirical_write import RealWritePort
from kultrun.adapters.storage.fuse_identify import FuseIdentifyProbe
from kultrun.adapters.storage.linux_quota import LinuxQuotaProbe
from kultrun.adapters.storage.macos import MacosCapacityProbe
from kultrun.adapters.storage.moosefs import MooseFSQuotaProbe
from kultrun.adapters.storage.nfs import NFSQuotaProbe
from kultrun.adapters.storage.posix_stat import PosixStatvfsProbe
from kultrun.adapters.storage.windows import WindowsCapacityProbe
from kultrun.adapters.storage.zfs import ZfsDatasetProbe
from kultrun.storage.probes import ProbeRegistry


def default_probe_registry() -> ProbeRegistry:
    """Replaceable probes used by the composition root."""
    return ProbeRegistry(
        (
            LinuxQuotaProbe(),
            FuseIdentifyProbe(),
            MooseFSQuotaProbe(),
            NFSQuotaProbe(),
            ZfsDatasetProbe(),
            CephfsQuotaProbe(),
            WindowsCapacityProbe(),
            MacosCapacityProbe(),
        )
    )


__all__ = [
    "PosixStatvfsProbe",
    "RealWritePort",
    "default_probe_registry",
]
