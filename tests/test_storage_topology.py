"""Storage topology: shared quota vs distinct pools, no first-pool shortcut."""

from __future__ import annotations

from pathlib import Path

from kultrun.host.contracts import MountFacts
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.contracts import ManagedPathPurpose, ProviderClass
from kultrun.storage.topology import (
    bind_path,
    managed_paths,
    pools_from_host,
    quota_identity_for,
)
from tests.test_capacity import host, mount


def test_runtime_model_and_cache_share_one_pool() -> None:
    subject = host(mounts=(mount("/workspace", "fuse", free=10**12, total=2 * 10**12),))
    pools = pools_from_host(subject)
    assert len(pools) == 1
    state = Path("/workspace/kultrun")
    bindings = managed_paths(subject, state, pools)
    identities = {
        item.quota_identity for item in bindings if is_resolved(item.quota_identity)
    }
    assert len(identities) == 1
    assert all(item.mount_point == "/workspace" for item in bindings)


def test_runtime_and_model_on_different_pools() -> None:
    subject = host(
        mounts=(
            mount("/data/runtime", "ext4", free=100 * 1024**3),
            mount("/data/models", "nfs", free=200 * 1024**3),
        )
    )
    pools = pools_from_host(subject)
    assert len(pools) == 2
    runtime = bind_path("/data/runtime/vllm", pools)
    model = bind_path("/data/models/qwen", pools)
    assert runtime is not None
    assert model is not None
    assert runtime.mount_point != model.mount_point
    assert runtime.quota_identity != model.quota_identity
    assert runtime.provider_class is ProviderClass.LOCAL_DISK
    assert model.provider_class is ProviderClass.NETWORK


def test_nested_mount_wins_over_parent() -> None:
    subject = host(
        mounts=(
            mount("/", "overlay", free=50 * 1024**3),
            mount("/workspace", "fuse", free=10**12),
            mount("/workspace/cache", "ext4", free=20 * 1024**3),
        )
    )
    pools = pools_from_host(subject)
    models = bind_path("/workspace/models", pools)
    cache = bind_path("/workspace/cache/pip", pools)
    etc = bind_path("/etc", pools)
    assert models is not None
    assert cache is not None
    assert etc is not None
    assert models.mount_point == "/workspace"
    assert cache.mount_point == "/workspace/cache"
    assert etc.mount_point == "/"


def test_quota_identity_is_per_mount_not_host_wide() -> None:
    fuse = MountFacts(
        mount_point="/workspace",
        device="mfs#host:9421",
        filesystem_type="fuse",
        total_bytes=NOT_PROVIDED,
        free_bytes=1,
    )
    disk = MountFacts(
        mount_point="/mnt/volume",
        device="/dev/sda1",
        filesystem_type="ext4",
        total_bytes=NOT_PROVIDED,
        free_bytes=2,
    )
    assert quota_identity_for(fuse) != quota_identity_for(disk)


def test_no_binding_when_path_is_off_every_pool() -> None:
    subject = host(mounts=(mount("/workspace", "fuse"),))
    pools = pools_from_host(subject)
    assert bind_path("/unrelated", pools) is None


def test_managed_path_purposes_cover_the_required_roots(tmp_path: Path) -> None:
    subject = host(mounts=(mount(str(tmp_path), "ext4"),))
    pools = pools_from_host(subject)
    bindings = managed_paths(subject, tmp_path, pools)
    purposes = {item.purpose for item in bindings}
    assert purposes >= {
        ManagedPathPurpose.STATE_ROOT,
        ManagedPathPurpose.RUNTIME_STAGING,
        ManagedPathPurpose.RUNTIME_FINAL,
        ManagedPathPurpose.INSTALL_CACHE,
        ManagedPathPurpose.MODEL_STAGING,
        ManagedPathPurpose.MODEL_FINAL,
        ManagedPathPurpose.DOWNLOAD_CACHE,
        ManagedPathPurpose.TEMP,
        ManagedPathPurpose.TELEMETRY,
        ManagedPathPurpose.LOGS,
    }


def test_mount_for_path_uses_longest_prefix() -> None:
    from kultrun.storage.topology import mount_for_path

    subject = host(
        mounts=(
            mount("/", "ext4", free=30 * 1024**3),
            mount("/workspace", "fuse", free=10**15),
        )
    )
    assert mount_for_path("/workspace/models", subject) == "/workspace"
    assert mount_for_path("/var/kultrun/models", subject) == "/"
