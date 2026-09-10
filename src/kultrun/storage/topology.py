"""Bind managed paths to StoragePool and quota identity.

Does not invent a StorageDomain. A pool is the mount plus the quota that
bounds it. Several managed paths may spend from one shared budget.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from kultrun.host.contracts import HostCapabilities, MountFacts
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    ManagedPathBinding,
    ManagedPathPurpose,
    ProviderClass,
    StoragePool,
    StoragePoolId,
)

_VOLATILE = frozenset({"tmpfs", "ramfs", "devtmpfs"})
_LOCAL_DISK = frozenset(
    {
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
    }
)
_VIRTUAL = frozenset({"overlay", "overlayfs"})
_NETWORK = frozenset(
    {
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
    }
)

_PURPOSE_DEFAULTS: dict[ManagedPathPurpose, str] = {
    ManagedPathPurpose.STATE_ROOT: "",
    ManagedPathPurpose.RUNTIME_STAGING: "runtimes/.staging",
    ManagedPathPurpose.RUNTIME_FINAL: "runtimes",
    ManagedPathPurpose.INSTALL_CACHE: "cache/install",
    ManagedPathPurpose.MODEL_STAGING: "models/.staging",
    ManagedPathPurpose.MODEL_FINAL: "models",
    ManagedPathPurpose.DOWNLOAD_CACHE: "cache/download",
    ManagedPathPurpose.TEMP: "tmp",
    ManagedPathPurpose.TELEMETRY: "telemetry",
    ManagedPathPurpose.LOGS: "logs",
}


def is_credible_family(family: str | None) -> bool:
    """Whether generic filesystem statistics are a native capacity API."""
    return family in _LOCAL_DISK or family in _VIRTUAL


def family_of(filesystem_type: Maybe[str]) -> str | None:
    if isinstance(filesystem_type, str) and filesystem_type.strip():
        return filesystem_type.strip().lower()
    return None


def quota_identity_for(mount: MountFacts) -> str:
    """Stable quota domain for one mount. Not a host-wide scalar."""
    family = family_of(mount.filesystem_type) or "unknown"
    device = mount.device if is_resolved(mount.device) else mount.mount_point
    return f"{family}:{device}:{mount.mount_point}"


def fingerprint_for(mount: MountFacts) -> str:
    material = "|".join(
        (
            mount.mount_point,
            str(mount.device if is_resolved(mount.device) else ""),
            family_of(mount.filesystem_type) or "",
            quota_identity_for(mount),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def pool_id_for(host_id: str, mount: MountFacts) -> StoragePoolId:
    digest = hashlib.sha256(
        f"{host_id}|{mount.mount_point}|{quota_identity_for(mount)}".encode()
    ).hexdigest()[:16]
    return StoragePoolId(f"pool_{digest}")


def provider_class_for(filesystem_type: Maybe[str]) -> ProviderClass:
    family = family_of(filesystem_type)
    if family is None:
        return ProviderClass.UNKNOWN
    if family in _VOLATILE:
        return ProviderClass.UNKNOWN
    if family in _LOCAL_DISK:
        return ProviderClass.LOCAL_DISK
    if family in _VIRTUAL:
        return ProviderClass.VIRTUAL
    if family in _NETWORK:
        return ProviderClass.NETWORK
    return ProviderClass.UNKNOWN


def pools_from_host(
    host: HostCapabilities, *, generation: int = 0
) -> tuple[StoragePool, ...]:
    """One StoragePool per durable mount. Volatile mounts are omitted."""
    pools: list[StoragePool] = []
    for mount in host.mounts:
        family = family_of(mount.filesystem_type)
        if family in _VOLATILE:
            continue
        pools.append(
            StoragePool(
                pool_id=pool_id_for(host.host_id.value, mount),
                host_id=host.host_id,
                mount_point=mount.mount_point,
                provider_class=provider_class_for(mount.filesystem_type),
                fingerprint=fingerprint_for(mount),
                generation=generation,
                filesystem_type=mount.filesystem_type,
                quota_identity=quota_identity_for(mount),
            )
        )
    return tuple(pools)


def mount_for_path(path: str | Path, host: HostCapabilities) -> str | None:
    """Destination pool mount for a managed path. None if nothing binds."""
    pool = bind_path(path, pools_from_host(host))
    return None if pool is None else pool.mount_point


def bind_path(path: str | Path, pools: Sequence[StoragePool]) -> StoragePool | None:
    """Longest mount-point prefix. Nested mounts win. No first-pool fallback."""
    resolved = str(Path(path))
    matches: list[StoragePool] = []
    for pool in pools:
        mount = pool.mount_point.rstrip("/") or pool.mount_point
        if (
            resolved == mount
            or resolved.startswith(mount.rstrip("/") + "/")
            or (mount == "/" and resolved.startswith("/"))
        ):
            matches.append(pool)
    if not matches:
        return None
    return max(matches, key=lambda item: len(item.mount_point.rstrip("/")))


def managed_paths(
    host: HostCapabilities,
    state_root: Path,
    pools: Sequence[StoragePool],
    *,
    overrides: dict[ManagedPathPurpose, Path] | None = None,
) -> tuple[ManagedPathBinding, ...]:
    """Bind the significant Kultrun paths to the pool they spend from."""
    root = Path(state_root).resolve()
    locations = dict(_PURPOSE_DEFAULTS)
    extra = overrides or {}
    bindings: list[ManagedPathBinding] = []
    for purpose, relative in locations.items():
        path = extra.get(purpose) or (root if relative == "" else root / relative)
        resolved = Path(path).resolve()
        pool = bind_path(resolved, pools)
        bindings.append(
            ManagedPathBinding(
                host_id=host.host_id,
                purpose=purpose,
                path=str(resolved),
                mount_point=pool.mount_point if pool is not None else NOT_PROVIDED,
                quota_identity=(
                    pool.quota_identity if pool is not None else NOT_PROVIDED
                ),
                persistent=purpose
                not in {
                    ManagedPathPurpose.TEMP,
                    ManagedPathPurpose.RUNTIME_STAGING,
                    ManagedPathPurpose.MODEL_STAGING,
                    ManagedPathPurpose.INSTALL_CACHE,
                },
            )
        )
    return tuple(bindings)
