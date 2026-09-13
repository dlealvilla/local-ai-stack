"""Minimum deployable-host gate. Composition, not a second storage detector.

Formula (destination pool only):

    potential_authorizing = min(
        current_authorizing_remaining + reclaimable_same_domain,
        hard_maximum if known else unbounded,
    )
    potential_safe = withhold(potential_authorizing)   # 10% / 5 GiB once
    net_new = max(0, required_peak - reusable)
    storage PASS iff potential_safe >= net_new

Reusable reduces requirement. It is never added to capacity.
Reserve is not applied to reclaimable bytes separately.
Unlike quota domains are never summed.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from kultrun.capacity.envelope import storage_safe_bytes
from kultrun.capacity.policy import default_policy
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.platform.contracts import (
    FoundationPossibility,
    HostPossibility,
    MinimumDeployableHostProfile,
    MinimumFeasibilityAssessment,
    MinimumFeasibilityVerdict,
)
from kultrun.runtime.contracts import RuntimeSupportDescriptor, RuntimeSupportTier
from kultrun.storage.contracts import (
    ManagedOccupancyClass,
    ManagedOccupancyItem,
    StorageCapacityEvidence,
    StoragePool,
)
from kultrun.storage.footprint import runtime_provisioning_requirement
from kultrun.storage.inventory import same_quota_domain, totals_by_pool
from kultrun.storage.topology import bind_path

PROFILE_VERSION = "minimum-host-v1"
_GIB = 1024**3
#: SAFE RAM floor. 2 GiB is the memory reserve floor; 8 GiB is a conservative
#: host working set for the PRODUCT vLLM path, not a serving SLA.
MIN_RAM_SAFE_BYTES = 8 * _GIB
#: Physical VRAM floor for the NVIDIA PRODUCT path. Not a selected-model size.
MIN_VRAM_BYTES = 8 * _GIB


def minimum_host_profile() -> MinimumDeployableHostProfile:
    """v1 profile derived from PRODUCT descriptors and footprint recipes."""
    peak = runtime_provisioning_requirement().required_peak_free_bytes
    required_peak = peak if isinstance(peak, int) else 24 * _GIB
    return MinimumDeployableHostProfile(
        profile_version=PROFILE_VERSION,
        supported_os_families=("linux", "darwin"),
        supported_architectures=("x86_64", "arm64"),
        min_ram_safe_bytes=MIN_RAM_SAFE_BYTES,
        min_vram_bytes=MIN_VRAM_BYTES,
        min_storage_peak_bytes=required_peak,
        required_accelerator_family="nvidia",
    )


def assess_minimum(
    host: HostCapabilities,
    *,
    destination: StoragePool | None,
    evidence: StorageCapacityEvidence | None,
    items: Sequence[ManagedOccupancyItem],
    descriptors: Sequence[RuntimeSupportDescriptor],
    ram_safe_bytes: object,
    profile: MinimumDeployableHostProfile | None = None,
) -> MinimumFeasibilityAssessment:
    """PASS or FAIL. requires_reclamation remains PASS with a condition."""
    profile = profile or minimum_host_profile()
    foundations = foundation_possibilities(host, descriptors)
    os_name = host.operating_environment.os_name
    arch = host.operating_environment.architecture.value
    if os_name not in profile.supported_os_families:
        return _fail(
            host,
            profile,
            "unsupported_platform",
            foundations,
            destination,
            items,
            evidence,
            condition=f"OS family {os_name} is not supported",
        )
    if arch not in profile.supported_architectures:
        return _fail(
            host,
            profile,
            "unsupported_architecture",
            foundations,
            destination,
            items,
            evidence,
            condition=f"architecture {arch} is not supported",
        )
    if (
        not isinstance(ram_safe_bytes, int)
        or ram_safe_bytes < profile.min_ram_safe_bytes
    ):
        return _fail(
            host,
            profile,
            "minimum_ram",
            foundations,
            destination,
            items,
            evidence,
            condition="SAFE RAM is below the minimum deployable host profile",
        )
    product_ok = any(
        item.host_possibility is HostPossibility.PLAUSIBLE
        and item.support_tier == RuntimeSupportTier.PRODUCT.value
        for item in foundations
    )
    if not product_ok:
        nvidia = any(
            accelerator.vendor.value == profile.required_accelerator_family
            for accelerator in host.accelerators
        )
        code = (
            "accelerator_requirement"
            if not nvidia and profile.required_accelerator_family
            else "no_plausible_foundation"
        )
        return _fail(
            host,
            profile,
            code,
            foundations,
            destination,
            items,
            evidence,
            condition="no PRODUCT foundation is plausible on this host",
        )
    if profile.required_accelerator_family:
        matching = [
            item
            for item in host.accelerators
            if item.vendor.value == profile.required_accelerator_family
        ]
        if not matching:
            return _fail(
                host,
                profile,
                "accelerator_requirement",
                foundations,
                destination,
                items,
                evidence,
                condition="NVIDIA accelerator class is required",
            )
        vram = matching[0].memory_total_bytes
        if not is_resolved(vram) or vram < profile.min_vram_bytes:
            return _fail(
                host,
                profile,
                "accelerator_requirement",
                foundations,
                destination,
                items,
                evidence,
                condition="physical VRAM is below the minimum PRODUCT floor",
            )
    if destination is None:
        return _fail(
            host,
            profile,
            "minimum_storage",
            foundations,
            None,
            items,
            evidence,
            condition="managed storage destination is unresolved",
        )
    return _storage_gate(host, profile, foundations, destination, items, evidence)


def foundation_possibilities(
    host: HostCapabilities,
    descriptors: Sequence[RuntimeSupportDescriptor],
) -> tuple[FoundationPossibility, ...]:
    """One row per family. Host match is not product maturity."""
    families: dict[str, RuntimeSupportDescriptor] = {}
    for item in descriptors:
        families.setdefault(item.runtime.value, item)
    rows: list[FoundationPossibility] = []
    for descriptor in families.values():
        plausible, reason = _host_match(host, descriptor)
        rows.append(
            FoundationPossibility(
                family=descriptor.runtime.value,
                host_possibility=(
                    HostPossibility.PLAUSIBLE
                    if plausible
                    else HostPossibility.NOT_PLAUSIBLE
                ),
                support_tier=descriptor.support_tier.value,
                reason=reason,
            )
        )
    return tuple(rows)


def nearby_state_roots(current: Path) -> tuple[Path, ...]:
    """Discover sibling Kultrun state roots. Ownership is still dual-proof."""
    current = Path(current).resolve()
    found = {current}
    install = current.parent
    base = install.parent
    if not base.is_dir():
        return (current,)
    try:
        entries = list(base.iterdir())
    except OSError:
        return (current,)
    for entry in entries:
        candidate = entry / "state" if entry.is_dir() else None
        if candidate is None or not candidate.is_dir():
            continue
        marker = candidate / ".kultrun-owner.json"
        registry = candidate / "storage.ownership_record"
        if marker.is_file() or registry.is_dir():
            found.add(candidate.resolve())
    return tuple(sorted(found, key=str))


def _storage_gate(
    host: HostCapabilities,
    profile: MinimumDeployableHostProfile,
    foundations: Sequence[FoundationPossibility],
    destination: StoragePool,
    items: Sequence[ManagedOccupancyItem],
    evidence: StorageCapacityEvidence | None,
) -> MinimumFeasibilityAssessment:
    authorizing = _authorizing(evidence)
    hard = (
        evidence.hard_maximum_bytes
        if evidence is not None and is_resolved(evidence.hard_maximum_bytes)
        else NOT_PROVIDED
    )
    occupancy = totals_by_pool(items).get(destination.mount_point)
    reclaimable = 0
    reusable = 0
    active = 0
    protected = 0
    unknown = 0
    if occupancy is not None and same_quota_domain(
        occupancy.mount_point,
        occupancy.quota_identity,
        occupancy.pool_fingerprint,
        destination,
    ):
        reclaimable = occupancy.reclaimable_bytes
        reusable = occupancy.reusable_bytes
        active = occupancy.active_bytes
        protected = occupancy.protected_bytes
        unknown = occupancy.unknown_bytes
    else:
        reclaimable = _bytes_on_destination(
            items, destination, ManagedOccupancyClass.RECLAIMABLE
        )
        reusable = _bytes_on_destination(
            items, destination, ManagedOccupancyClass.REUSABLE
        )
        active = _bytes_on_destination(items, destination, ManagedOccupancyClass.ACTIVE)
        protected = _bytes_on_destination(
            items, destination, ManagedOccupancyClass.PROTECTED
        )
        unknown = _bytes_on_destination(
            items, destination, ManagedOccupancyClass.UNKNOWN
        )
    required = profile.min_storage_peak_bytes
    net_new = max(0, required - reusable)
    current_safe = (
        storage_safe_bytes(authorizing, default_policy())
        if isinstance(authorizing, int)
        else NOT_PROVIDED
    )
    if not isinstance(authorizing, int):
        return _fail(
            host,
            profile,
            "minimum_storage",
            foundations,
            destination,
            items,
            evidence,
            reclaimable=reclaimable,
            reusable=reusable,
            required=required,
            net_new=net_new,
            hard=hard,
            active=active,
            protected=protected,
            unknown=unknown,
            condition="authorizing destination capacity is unresolved",
        )
    potential_auth = authorizing + reclaimable
    if isinstance(hard, int):
        potential_auth = min(potential_auth, hard)
    potential_safe = storage_safe_bytes(potential_auth, default_policy())
    if not is_resolved(potential_safe) or potential_safe < net_new:
        return _fail(
            host,
            profile,
            "minimum_storage" if reclaimable == 0 else "reclamation_not_safe",
            foundations,
            destination,
            items,
            evidence,
            reclaimable=reclaimable,
            reusable=reusable,
            required=required,
            net_new=net_new,
            hard=hard,
            potential_auth=potential_auth,
            potential_safe=potential_safe if is_resolved(potential_safe) else None,
            current_safe=current_safe if is_resolved(current_safe) else None,
            authorizing=authorizing,
            active=active,
            protected=protected,
            unknown=unknown,
            condition="potential post-reclaim SAFE is below net new peak",
        )
    requires = (
        not is_resolved(current_safe) or current_safe < net_new
    ) and reclaimable > 0
    condition = ""
    if requires:
        condition = (
            f"Reclaim {_fmt(reclaimable)} of inactive Kultrun state "
            "before provisioning."
        )
    return MinimumFeasibilityAssessment(
        host_id=host.host_id,
        profile_version=profile.profile_version,
        verdict=MinimumFeasibilityVerdict.PASS,
        reason_code=NOT_PROVIDED,
        requires_reclamation=requires,
        current_authorizing_bytes=authorizing,
        current_safe_bytes=current_safe if is_resolved(current_safe) else NOT_PROVIDED,
        reclaimable_bytes=reclaimable,
        reusable_bytes=reusable,
        potential_authorizing_bytes=potential_auth,
        potential_safe_bytes=potential_safe,
        required_peak_bytes=required,
        net_new_bytes=net_new,
        hard_maximum_bytes=hard if isinstance(hard, int) else NOT_PROVIDED,
        destination_mount=destination.mount_point,
        condition=condition,
        foundations=tuple(foundations),
        active_bytes=active,
        protected_bytes=protected,
        unknown_bytes=unknown,
    )


def _fail(
    host: HostCapabilities,
    profile: MinimumDeployableHostProfile,
    code: str,
    foundations: Sequence[FoundationPossibility],
    destination: StoragePool | None,
    items: Sequence[ManagedOccupancyItem],
    evidence: StorageCapacityEvidence | None,
    *,
    condition: str,
    reclaimable: int = 0,
    reusable: int = 0,
    required: int | None = None,
    net_new: int | None = None,
    hard: object = NOT_PROVIDED,
    potential_auth: int | None = None,
    potential_safe: object = None,
    current_safe: object = None,
    authorizing: int | None = None,
    active: int = 0,
    protected: int = 0,
    unknown: int = 0,
) -> MinimumFeasibilityAssessment:
    required_peak = (
        required if isinstance(required, int) else profile.min_storage_peak_bytes
    )
    net = net_new if isinstance(net_new, int) else max(0, required_peak - reusable)
    auth = authorizing if isinstance(authorizing, int) else _authorizing(evidence)
    return MinimumFeasibilityAssessment(
        host_id=host.host_id,
        profile_version=profile.profile_version,
        verdict=MinimumFeasibilityVerdict.FAIL,
        reason_code=code,
        requires_reclamation=False,
        current_authorizing_bytes=auth if isinstance(auth, int) else NOT_PROVIDED,
        current_safe_bytes=(
            current_safe if isinstance(current_safe, int) else NOT_PROVIDED
        ),
        reclaimable_bytes=reclaimable,
        reusable_bytes=reusable,
        potential_authorizing_bytes=(
            potential_auth if isinstance(potential_auth, int) else NOT_PROVIDED
        ),
        potential_safe_bytes=(
            potential_safe if isinstance(potential_safe, int) else NOT_PROVIDED
        ),
        required_peak_bytes=required_peak,
        net_new_bytes=net,
        hard_maximum_bytes=hard if isinstance(hard, int) else NOT_PROVIDED,
        destination_mount=(
            destination.mount_point if destination is not None else NOT_PROVIDED
        ),
        condition=condition,
        foundations=tuple(foundations),
        active_bytes=active,
        protected_bytes=protected,
        unknown_bytes=unknown,
    )


def _host_match(
    host: HostCapabilities, descriptor: RuntimeSupportDescriptor
) -> tuple[bool, str]:
    os_name = host.operating_environment.os_name
    arch = host.operating_environment.architecture.value
    if descriptor.supported_os_families and os_name not in (
        descriptor.supported_os_families
    ):
        return False, f"OS {os_name} is not in {descriptor.runtime.value} support"
    if (
        descriptor.supported_architectures
        and arch not in descriptor.supported_architectures
    ):
        return False, (
            f"architecture {arch} is not in {descriptor.runtime.value} support"
        )
    needed = descriptor.supported_accelerator_families
    if not needed:
        return True, "CPU-capable family; no accelerator class required"
    vendors = {item.vendor.value for item in host.accelerators}
    if any(item in vendors for item in needed):
        return True, f"{needed[0]} accelerator class present"
    return False, f"required accelerator class {', '.join(needed)} is absent"


def _authorizing(evidence: StorageCapacityEvidence | None) -> int | None:
    if evidence is None:
        return None
    value = evidence.authorizing_available_bytes
    return value if isinstance(value, int) else None


def _bytes_on_destination(
    items: Sequence[ManagedOccupancyItem],
    destination: StoragePool,
    occupancy: ManagedOccupancyClass,
) -> int:
    total = 0
    for item in items:
        if item.occupancy_class is not occupancy:
            continue
        if not isinstance(item.mount_point, str):
            continue
        if not same_quota_domain(
            item.mount_point, item.quota_identity, item.pool_fingerprint, destination
        ):
            continue
        total += item.occupied_bytes
    return total


def _fmt(value: int) -> str:
    if value >= _GIB:
        return f"{value / _GIB:.1f} GiB"
    return f"{value} B"


def destination_pool(
    state_root: Path, pools: Sequence[StoragePool]
) -> StoragePool | None:
    """Intended managed destination. Never the first pool by accident."""
    return bind_path(Path(state_root).resolve(), pools)
