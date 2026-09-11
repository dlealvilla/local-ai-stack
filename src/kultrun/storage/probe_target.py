"""Bind a physical Sonar workspace to the StoragePool it claims to describe.

A probe result from domain A must never authorize domain B. Global
``state_root`` is a control-plane location; it is a valid probe parent only
when it already resides on the same pool, mount, fingerprint and quota
identity as the pool being characterized.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kultrun.kernel.errors import PreconditionFailedError
from kultrun.storage.contracts import StoragePool
from kultrun.storage.topology import bind_path

#: Owned Sonar directory name. Mirrored in ``storage.sonar`` so this
#: module does not import the probe engine.
PROBE_DIRECTORY = ".kultrun-sonar"


class StorageTargetMismatchError(PreconditionFailedError):
    """The chosen probe path is not on the StoragePool being characterized."""

    def __init__(self, message: str, /, **context: object) -> None:
        super().__init__(message, reason="storage_target_mismatch", **context)


def canonical_path(path: str | Path) -> Path:
    """Absolute path. Missing targets stay as normalized paths, not guesses."""
    try:
        return Path(path).expanduser().resolve()
    except OSError:
        return Path(path).absolute()


def pool_for_path(
    path: str | Path, pools: Sequence[StoragePool]
) -> StoragePool | None:
    """Longest-prefix pool for a physical path. None if nothing binds."""
    return bind_path(canonical_path(path), pools) or bind_path(path, pools)


def same_storage_domain(
    path: str | Path, pool: StoragePool, pools: Sequence[StoragePool]
) -> bool:
    """True when ``path`` resolves onto ``pool``'s mount/quota/fingerprint."""
    found = pool_for_path(path, pools)
    if found is None:
        return False
    if found.host_id != pool.host_id:
        return False
    if found.mount_point != pool.mount_point:
        return False
    if found.fingerprint != pool.fingerprint:
        return False
    return found.quota_identity == pool.quota_identity


def assert_same_domain(
    path: str | Path, pool: StoragePool, pools: Sequence[StoragePool]
) -> StoragePool:
    """Refuse a probe whose physical path is not the claimed pool."""
    found = pool_for_path(path, pools)
    if found is None or not same_storage_domain(path, pool, pools):
        raise StorageTargetMismatchError(
            "empirical probe path is not on the claimed storage pool",
            claimed_mount=pool.mount_point,
            claimed_fingerprint=pool.fingerprint,
            claimed_quota=pool.quota_identity,
            probe_path=str(path),
            resolved_mount=None if found is None else found.mount_point,
            resolved_fingerprint=None if found is None else found.fingerprint,
            resolved_quota=None if found is None else found.quota_identity,
        )
    return found


def probe_parent_for(
    pool: StoragePool,
    pools: Sequence[StoragePool],
    override: Path | None = None,
) -> Path:
    """Writable parent on ``pool``. A mismatched override is never used."""
    if override is not None and same_storage_domain(override, pool, pools):
        parent = Path(override)
    else:
        parent = Path(pool.mount_point)
    assert_same_domain(parent, pool, pools)
    return parent


def probe_roots_for(pools: Sequence[StoragePool]) -> tuple[Path, ...]:
    """Per-pool Sonar directories. Used as Step 0 extra/allowed roots."""
    return tuple(Path(pool.mount_point) / PROBE_DIRECTORY for pool in pools)
