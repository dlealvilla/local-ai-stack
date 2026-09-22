"""Pure Steward classification. No filesystem access and no deletion."""

from __future__ import annotations

from dataclasses import dataclass

from machi.steward.contracts import (
    GenerationHint,
    InstallFact,
    LifecycleStatus,
    MarkerFact,
    ObsoletePolicy,
    OwnershipStatus,
    ProtectionHint,
    ProtectionStatus,
    Reclaimability,
    RegistryFact,
    ResourceCategory,
    StewardSettings,
)

_CONFLICT_MARKERS = frozenset(
    {
        MarkerFact.MALFORMED,
        MarkerFact.UNSUPPORTED,
        MarkerFact.FINGERPRINT_MISMATCH,
        MarkerFact.WRONG_PRODUCT,
        MarkerFact.NOT_A_FILE,
    }
)
_RECLAIM_LIFECYCLES = frozenset({LifecycleStatus.OBSOLETE, LifecycleStatus.ABANDONED})


@dataclass(frozen=True, slots=True)
class OwnershipFacts:
    """Evidence already read by an adapter. Not itself a product contract."""

    marker: MarkerFact
    registry: RegistryFact
    install_record: InstallFact
    legacy_marker: bool
    marker_id: str | None = None
    install_id: str | None = None


@dataclass(frozen=True, slots=True)
class Classification:
    """Domain result before occupancy bytes and mount association."""

    ownership: OwnershipStatus
    lifecycle: LifecycleStatus
    protection: ProtectionStatus
    reclaimability: Reclaimability
    category: ResourceCategory
    reason: str
    provenance: str


def classify_ownership(
    facts: OwnershipFacts,
    *,
    generation: GenerationHint,
    protection: ProtectionHint,
    settings: StewardSettings,
) -> Classification:
    """Apply dual proof. Unknown and conflict are never reclaimable."""
    ownership, reason = _ownership(facts)
    if ownership is not OwnershipStatus.VERIFIED_MACHI_OWNED:
        return Classification(
            ownership=ownership,
            lifecycle=LifecycleStatus.UNKNOWN,
            protection=ProtectionStatus.UNKNOWN,
            reclaimability=Reclaimability.NOT_RECLAIMABLE,
            category=ResourceCategory.UNKNOWN,
            reason=reason,
            provenance=_provenance(facts),
        )
    lifecycle = _lifecycle(facts, generation)
    kept = _protection(lifecycle, protection)
    reclaim = _reclaim(lifecycle, kept, settings)
    return Classification(
        ownership=ownership,
        lifecycle=lifecycle,
        protection=kept,
        reclaimability=reclaim,
        category=ResourceCategory.INSTALLATION_ROOT,
        reason=reason,
        provenance=_provenance(facts),
    )


def _ownership(facts: OwnershipFacts) -> tuple[OwnershipStatus, str]:
    if facts.legacy_marker and facts.marker is not MarkerFact.VALID:
        if facts.marker is MarkerFact.ABSENT:
            return (
                OwnershipStatus.LEGACY_UNVERIFIED,
                "legacy ownership evidence is present and is not Machi proof",
            )
        return (
            OwnershipStatus.CONFLICTED,
            "legacy evidence disagrees with the local Machi marker",
        )
    if facts.legacy_marker and facts.marker is MarkerFact.VALID:
        return (
            OwnershipStatus.CONFLICTED,
            "Machi and legacy ownership evidence both exist",
        )
    if facts.marker in _CONFLICT_MARKERS:
        return (
            OwnershipStatus.CONFLICTED,
            f"local marker is {facts.marker.value}; refusing to treat it as proof",
        )
    if facts.marker is MarkerFact.ABSENT:
        return (
            OwnershipStatus.NOT_MACHI_OWNED,
            "no Machi ownership marker is present",
        )
    if facts.registry in {RegistryFact.ABSENT, RegistryFact.NOT_CONSULTED}:
        return (
            OwnershipStatus.UNKNOWN,
            "local marker is present and registry agreement is missing",
        )
    if facts.registry is not RegistryFact.MATCH:
        return (
            OwnershipStatus.CONFLICTED,
            "registry record does not agree with the local marker",
        )
    if facts.install_record is InstallFact.MISMATCH:
        return (
            OwnershipStatus.CONFLICTED,
            "InstallId does not agree with the ownership evidence",
        )
    return (
        OwnershipStatus.VERIFIED_MACHI_OWNED,
        "local marker and registry record agree",
    )


def _lifecycle(facts: OwnershipFacts, generation: GenerationHint) -> LifecycleStatus:
    if (
        facts.install_record is not InstallFact.MATCH
        and generation is GenerationHint.CURRENT
    ):
        return LifecycleStatus.UNKNOWN
    if generation is GenerationHint.CURRENT:
        return LifecycleStatus.ACTIVE
    if generation is GenerationHint.OBSOLETE:
        return LifecycleStatus.OBSOLETE
    if generation is GenerationHint.ABANDONED:
        return LifecycleStatus.ABANDONED
    return LifecycleStatus.STANDBY


def _protection(lifecycle: LifecycleStatus, hint: ProtectionHint) -> ProtectionStatus:
    if lifecycle is LifecycleStatus.UNKNOWN:
        return ProtectionStatus.UNKNOWN
    if lifecycle is LifecycleStatus.ACTIVE:
        return ProtectionStatus.ACTIVE_PROTECTED
    if lifecycle is LifecycleStatus.STANDBY or hint is ProtectionHint.ROLLBACK:
        return ProtectionStatus.ROLLBACK_PROTECTED
    if hint is ProtectionHint.EVIDENCE:
        return ProtectionStatus.EVIDENCE_RETAINED
    if hint is ProtectionHint.POLICY:
        return ProtectionStatus.POLICY_RETAINED
    return ProtectionStatus.UNPROTECTED


def _reclaim(
    lifecycle: LifecycleStatus,
    protection: ProtectionStatus,
    settings: StewardSettings,
) -> Reclaimability:
    if lifecycle not in _RECLAIM_LIFECYCLES:
        return Reclaimability.NOT_RECLAIMABLE
    if protection is not ProtectionStatus.UNPROTECTED:
        return Reclaimability.NOT_RECLAIMABLE
    if settings.obsolete_policy is ObsoletePolicy.ASK:
        return Reclaimability.REQUIRES_POLICY_DECISION
    return Reclaimability.RECLAIMABLE


def _provenance(facts: OwnershipFacts) -> str:
    return (
        f"marker={facts.marker.value};registry={facts.registry.value};"
        f"install={facts.install_record.value};legacy={facts.legacy_marker}"
    )
