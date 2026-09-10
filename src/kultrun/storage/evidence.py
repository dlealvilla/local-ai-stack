"""Normalize and arbitrate storage-capacity evidence.

Compares available-to-available on one domain. A 50 GB quota total is
never compared against 6 GB currently free. The 10% rule is:

    abs(native_available - probe_available) / max(native_available, probe_available)

A heuristic disbelief ceiling may be recorded as a belief bound. It never
becomes authorizing SAFE — Capacity withholds SAFE from operational evidence,
and unverified FUSE/network pools keep SAFE unresolved.
"""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.evidence.contracts import Confidence, Provenance
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.storage.contracts import (
    EmpiricalProbeEvidence,
    StorageCapacityEvidence,
    StorageEvidenceStatus,
)
from kultrun.storage.limits import DISAGREEMENT_RATIO, POLICY_VERSION

PRODUCER = Name("storage.sonar")


def disagreement_ratio(native: int, probe: int) -> float:
    """Symmetric relative difference. Both operands must be available bytes."""
    if native < 0 or probe < 0:
        raise ValueError("available bytes cannot be negative")
    largest = max(native, probe)
    if largest == 0:
        return 0.0
    return abs(native - probe) / largest


def cap_by_hard(value: int, hard: Maybe[int]) -> int:
    """A probe may not authorize beyond a smaller known hard entitlement."""
    if is_resolved(hard) and hard < value:
        return hard
    return value


def apply_manual_bound(
    operational: Maybe[int],
    hard: Maybe[int],
    empirical_upper: Maybe[int],
    manual: Maybe[int],
) -> Maybe[int]:
    """Administrator bound never overrides a smaller hard or empirical failure."""
    if not is_resolved(manual):
        return operational
    ceiling = manual
    if is_resolved(hard):
        ceiling = min(ceiling, hard)
    if is_resolved(empirical_upper):
        ceiling = min(ceiling, empirical_upper - 1) if empirical_upper > 0 else 0
    if is_resolved(operational):
        return min(operational, ceiling)
    return ceiling


def arbitrate(
    *,
    host_id: HostId,
    mount_point: str,
    quota_identity: Maybe[str],
    pool_fingerprint: str,
    clock: Clock,
    reported_available: Maybe[int] = NOT_PROVIDED,
    native_available: Maybe[int] = NOT_PROVIDED,
    probe_available: Maybe[int] = NOT_PROVIDED,
    hard_maximum: Maybe[int] = NOT_PROVIDED,
    belief_bound: Maybe[int] = NOT_PROVIDED,
    native_source: Maybe[str] = NOT_PROVIDED,
    probe_name: Maybe[str] = NOT_PROVIDED,
    probe_compatible: bool = False,
    probe_executed: bool = False,
    administrator_bound: Maybe[int] = NOT_PROVIDED,
    empirical: EmpiricalProbeEvidence | None = None,
    native_trusted: bool = True,
) -> StorageCapacityEvidence:
    """Produce one pool's evidence. Does not compute SAFE headroom."""
    ratio: Maybe[float] = NOT_PROVIDED
    selected: Maybe[int] = NOT_PROVIDED
    status = StorageEvidenceStatus.UNRESOLVED
    reason = "no comparable available figure"
    confidence = Confidence.UNKNOWN

    native = native_available if is_resolved(native_available) else reported_available
    probe = probe_available
    if (
        empirical is not None
        and is_resolved(empirical.verified_lower_bound_bytes)
        and not is_resolved(probe)
    ):
        probe = empirical.verified_lower_bound_bytes
        probe_name = "empirical-fallback"
        probe_compatible = True
        probe_executed = True

    if is_resolved(native) and is_resolved(probe):
        ratio = disagreement_ratio(native, probe)
        if ratio <= DISAGREEMENT_RATIO:
            selected = cap_by_hard(native if native_trusted else probe, hard_maximum)
            status = StorageEvidenceStatus.CORROBORATED
            reason = (
                "native available used; probe corroborates within 10%"
                if native_trusted
                else "probe available used; native is not an entitlement"
            )
            confidence = Confidence.HIGH
        else:
            selected = cap_by_hard(probe, hard_maximum)
            status = StorageEvidenceStatus.CONTRADICTED
            reason = (
                "native available disagreed with probe by more than 10%; "
                "probe used, hard entitlement still caps"
            )
            confidence = Confidence.MEDIUM
            if is_resolved(hard_maximum) and probe > hard_maximum:
                reason = (
                    "probe exceeded a smaller hard entitlement; "
                    "operational available is the hard bound"
                )
                status = StorageEvidenceStatus.BOUNDED
    elif is_resolved(probe):
        selected = cap_by_hard(probe, hard_maximum)
        status = StorageEvidenceStatus.PROBED
        reason = "technology probe supplied available bytes"
        confidence = Confidence.MEDIUM
    elif is_resolved(native):
        selected = cap_by_hard(native, hard_maximum)
        if native_trusted:
            status = StorageEvidenceStatus.AUTHORITATIVE
            reason = "native/declared available; no independent probe figure"
            confidence = Confidence.MEDIUM
        else:
            selected = NOT_PROVIDED
            status = StorageEvidenceStatus.UNRESOLVED
            reason = (
                "native/declared figure is not an entitlement for this "
                "storage family; authorizing SAFE stays unresolved"
            )
            confidence = Confidence.LOW
    elif empirical is not None and is_resolved(empirical.verified_lower_bound_bytes):
        selected = cap_by_hard(empirical.verified_lower_bound_bytes, hard_maximum)
        status = StorageEvidenceStatus.BOUNDED
        reason = "empirical fallback lower bound"
        confidence = Confidence.MEDIUM
        if empirical.probe_ceiling_reached and not is_resolved(
            empirical.observed_failure_upper_bytes
        ):
            reason = (
                "empirical search reached its ceiling without failure; "
                "upper bound unknown"
            )

    if is_resolved(administrator_bound):
        selected = apply_manual_bound(
            selected,
            hard_maximum,
            empirical.observed_failure_upper_bytes if empirical else NOT_PROVIDED,
            administrator_bound,
        )
        if status is StorageEvidenceStatus.UNRESOLVED and is_resolved(selected):
            status = StorageEvidenceStatus.BOUNDED
            reason = "administrator-provided bound; weaker than hard evidence"
            confidence = Confidence.LOW
            native_source = "administrator"

    if empirical is not None and is_resolved(empirical.observed_failure_upper_bytes):
        upper = empirical.observed_failure_upper_bytes
        if is_resolved(selected) and selected >= upper:
            selected = max(0, upper - 1)
            status = StorageEvidenceStatus.BOUNDED
            reason = "empirical failure is a hard upper bound"

    operational = selected
    return StorageCapacityEvidence(
        host_id=host_id,
        mount_point=mount_point,
        quota_identity=quota_identity,
        pool_fingerprint=pool_fingerprint,
        observed_at=clock.now(),
        status=status,
        confidence=confidence,
        provenance=Provenance(
            producer=PRODUCER,
            producer_version=NOT_PROVIDED,
            observed_at=clock.now(),
            policy_version=POLICY_VERSION,
        ),
        reported_available_bytes=reported_available,
        declared_available_bytes=native_available,
        probe_available_bytes=probe,
        hard_maximum_bytes=hard_maximum,
        operational_available_bytes=operational,
        authorizing_available_bytes=operational,
        belief_bound_bytes=belief_bound,
        native_source=native_source,
        probe_name=probe_name,
        probe_available=probe_compatible,
        probe_executed=probe_executed,
        disagreement_ratio=ratio,
        selected_reason=reason,
        administrator_bound_bytes=administrator_bound,
    )


def needs_empirical_fallback(
    *,
    family: str | None,
    credible_family: bool,
    reports: Sequence[object],
    evidence: StorageCapacityEvidence,
) -> bool:
    """Whether the proprietary fallback should run before selection.

    Local filesystems whose native size is credible do not require a 25 GiB
    write merely because a quota tool is absent. Families that require
    evidence (FUSE, NFS, ...) do, unless a compatible probe already produced
    an available-bytes figure. Identification without a capacity number is
    not settlement.
    """
    if evidence.status is StorageEvidenceStatus.CONTRADICTED:
        return True
    settled = any(
        getattr(item, "executed", False)
        and is_resolved(getattr(item, "available_bytes", NOT_PROVIDED))
        for item in reports
    )
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return not credible_family
    return bool(family and not credible_family and not settled)
