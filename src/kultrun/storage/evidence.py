"""Normalize and arbitrate storage-capacity evidence.

Compares available-to-available on one domain. A 50 GB quota total is
never compared against 6 GB currently free. The 10% rule is:

    abs(native_available - probe_available) / max(native_available, probe_available)

A heuristic disbelief ceiling may be recorded as a belief bound. It never
becomes authorizing SAFE — Capacity withholds SAFE from operational evidence,
and unverified FUSE/network pools keep SAFE unresolved. Specialist remaining
bytes always beat generic native; the 10% ratio is diagnostic only.
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
from kultrun.storage.limits import (
    DISAGREEMENT_RATIO,
    NATIVE_ANOMALY_TRIGGER_BYTES,
    NATIVE_CLASS_PROBE_NAMES,
    POLICY_VERSION,
)

PRODUCER = Name("storage.sonar")


def disagreement_ratio(native: int, probe: int) -> float:
    """Symmetric relative difference. Both operands must be available bytes."""
    if native < 0 or probe < 0:
        raise ValueError("available bytes cannot be negative")
    largest = max(native, probe)
    if largest == 0:
        return 0.0
    return abs(native - probe) / largest


def native_may_authorize(
    native_trusted: bool, native: Maybe[int], probe: Maybe[int]
) -> bool:
    """Whether generic native/declared bytes may become authorizing capacity.

    Specialists that already produced domain bytes settle the pool even when
    native is huge. A trusted-local figure above the anomaly trigger without
    those bytes is not an entitlement.
    """
    if not native_trusted:
        return False
    if is_resolved(probe):
        return True
    return not (is_resolved(native) and native > NATIVE_ANOMALY_TRIGGER_BYTES)


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

    trusted = native_may_authorize(native_trusted, native, probe)

    if is_resolved(native) and is_resolved(probe):
        ratio = disagreement_ratio(native, probe)
        selected = cap_by_hard(probe, hard_maximum)
        if ratio <= DISAGREEMENT_RATIO:
            status = StorageEvidenceStatus.CORROBORATED
            reason = "specialist available used; native corroborates within 10%"
            confidence = Confidence.HIGH
        else:
            status = StorageEvidenceStatus.CONTRADICTED
            reason = (
                "specialist available used; native disagreed by more than 10%; "
                "hard entitlement still caps"
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
        if trusted:
            status = StorageEvidenceStatus.AUTHORITATIVE
            reason = "native/declared available; no independent probe figure"
            confidence = Confidence.MEDIUM
        else:
            selected = NOT_PROVIDED
            status = StorageEvidenceStatus.UNRESOLVED
            if native_trusted:
                reason = (
                    "native/declared figure is above the anomaly trigger "
                    f"({NATIVE_ANOMALY_TRIGGER_BYTES} bytes) without specialist "
                    "domain bytes; authorizing SAFE stays unresolved"
                )
            else:
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
    """Whether Sonar should run before this characterization can authorize.

    Specialist domain bytes settle the pool for this stage; Sonar
    corroboration of a settled specialist is a later stage. Identification
    without a capacity number is not settlement. Unresolved native — including
    a trusted-local figure above the anomaly trigger — does require Sonar.
    """
    del family
    settled = any(
        getattr(item, "executed", False)
        and is_resolved(getattr(item, "available_bytes", NOT_PROVIDED))
        and getattr(item, "probe_name", "") not in NATIVE_CLASS_PROBE_NAMES
        for item in reports
    )
    if settled:
        return False
    if evidence.status is StorageEvidenceStatus.UNRESOLVED:
        return True
    if evidence.status is StorageEvidenceStatus.CONTRADICTED:
        return True
    return not credible_family
