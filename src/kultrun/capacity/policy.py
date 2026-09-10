"""The default headroom policy, and why each number is what it is.

Every value here is **chosen conservatively, not measured.** That is the
honest position at Stage 1.2 and it is recorded as debt: reserves derived
from real workloads belong to Milestone 3, and empirical storage bounds to
Stage 2.2.

Conservative-and-versioned is the deliberate direction. A policy that
reserves too much can be tightened once evidence exists, with the old
decision still explicable through `policy_version`. A policy tuned to look
generous cannot be loosened safely, because the workloads it already
admitted are running.
"""

from __future__ import annotations

from typing import Final

from kultrun.capacity.contracts import HeadroomPolicy

_GIB: Final = 1024**3

#: Bumped whenever any value below changes, so an envelope produced under an
#: older policy stays explicable rather than merely stale.
POLICY_VERSION: Final = "1.6L.0-storage-truth"

#: Filesystem families whose reported size does not corroborate usable
#: capacity: their totals describe a backend or an aggregate rather than an
#: entitlement this deployment holds.
#:
#: Generic filesystem type names, never a vendor or product. The Stage 1.1
#: reference host mounts one of these advertising 2.15 PB, and the previous
#: attempt met the same shape as "239 TB free" and then could not complete a
#: 6.70 GiB install.
FAMILIES_REQUIRING_EVIDENCE: Final = (
    "fuse",
    "fuseblk",
    "fuse.sshfs",
    "nfs",
    "nfs4",
    "cifs",
    "smb",
    "smb2",
    "smb3",
    "ceph",
    "glusterfs",
    "lustre",
    "beegfs",
    "9p",
    "afs",
    "davfs",
    "s3fs",
    "gcsfuse",
    "objectfs",
)

#: Filesystem families whose reported free space *is* credible evidence of
#: usable capacity: local block filesystems, where the number describes a
#: device this deployment holds.
#:
#: An allow-list rather than a deny-list, so an unrecognised family is
#: disbelieved by default. The alternative fails open: any filesystem nobody
#: had thought about would be trusted, which is how a surprising mount
#: becomes a capacity claim.
FAMILIES_WITH_CREDIBLE_SIZE: Final = (
    "ext2",
    "ext3",
    "ext4",
    "xfs",
    "btrfs",
    "zfs",
    "f2fs",
    "jfs",
    "reiserfs",
    "apfs",
    "hfs",
    "hfsplus",
    "ntfs",
    "ntfs3",
    "vfat",
    "exfat",
    "ufs",
    # A container's writable layer. The number describes this container's
    # storage rather than a shared backend, so it is credible for it.
    "overlay",
    "overlayfs",
)

#: Volatile: real space, but it is memory and does not survive a restart. Not
#: a durable pool, and counting it as storage would double-count RAM.
VOLATILE_FAMILIES: Final = ("tmpfs", "ramfs", "devtmpfs")

#: The most Kultrun will treat as effective in a pool it cannot verify.
#:
#: Not a claim about the pool — a bound on how much may be believed having
#: verified nothing. 64 GiB is comfortably more than the first model needs
#: and obviously less than any large volume, so it unblocks Milestone 1
#: without asserting anything. It also matches the per-probe ceiling the
#: previous implementation settled on, which means Stage 2.2's first probe
#: validates exactly this boundary rather than an unrelated one.
UNVERIFIED_POOL_CEILING_BYTES: Final = 64 * _GIB

#: Above this, an unbelievable reported size is worth verifying rather than
#: merely bounding. Below it, the policy ceiling already bounds the pool to
#: something smaller than the report, so a probe would cost real time to
#: learn nothing that changes a decision.
#:
#: 1 TiB because the shapes that motivate this advertise hundreds of
#: terabytes. An ordinary disk never triggers.
SANITY_TRIGGER_BYTES: Final = 1024**4

#: Kept back from system memory. The previous attempt used a 0.75 weight
#: budget for both RAM and accelerator memory, so 25% is the one reserve
#: figure with any operational history behind it. The 2 GiB floor exists
#: because 25% of a small container is not enough for the kernel, page cache
#: and everything Kultrun does not manage.
MEMORY_RESERVE_FRACTION: Final = 0.25
MEMORY_RESERVE_FLOOR_BYTES: Final = 2 * _GIB

#: Kept back from accelerator memory, for runtime overhead, allocator
#: fragmentation and CUDA context. Same 25% as the previous attempt used.
#: The floor is larger relative to device size because a runtime's fixed
#: overhead does not shrink with the device.
ACCELERATOR_RESERVE_FRACTION: Final = 0.25
ACCELERATOR_RESERVE_FLOOR_BYTES: Final = 1 * _GIB

#: Kept back from a pool so a managed write cannot reach a full filesystem.
#: A smaller fraction than memory because running out of disk degrades
#: rather than kills, and a 5 GiB floor because the failure mode on a nearly
#: full root filesystem is severe out of proportion to the bytes involved.
STORAGE_RESERVE_FRACTION: Final = 0.10
STORAGE_RESERVE_FLOOR_BYTES: Final = 5 * _GIB


def default_policy() -> HeadroomPolicy:
    """The policy Kultrun runs under when an administrator has set none."""
    return HeadroomPolicy(
        policy_version=POLICY_VERSION,
        memory_reserve_fraction=MEMORY_RESERVE_FRACTION,
        memory_reserve_floor_bytes=MEMORY_RESERVE_FLOOR_BYTES,
        accelerator_reserve_fraction=ACCELERATOR_RESERVE_FRACTION,
        accelerator_reserve_floor_bytes=ACCELERATOR_RESERVE_FLOOR_BYTES,
        storage_reserve_fraction=STORAGE_RESERVE_FRACTION,
        storage_reserve_floor_bytes=STORAGE_RESERVE_FLOOR_BYTES,
        unverified_pool_ceiling_bytes=UNVERIFIED_POOL_CEILING_BYTES,
        families_requiring_evidence=FAMILIES_REQUIRING_EVIDENCE,
        families_with_credible_size=FAMILIES_WITH_CREDIBLE_SIZE,
        sanity_trigger_bytes=SANITY_TRIGGER_BYTES,
    )
