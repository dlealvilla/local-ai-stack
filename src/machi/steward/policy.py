"""Default Steward policy. Typed, inspectable, and biased to preservation."""

from __future__ import annotations

from machi.steward.contracts import (
    ObsoletePolicy,
    StewardSetting,
    StewardSettingProvenance,
    StewardSettings,
    StewardSettingSupportState,
)


def default_steward_settings(
    *,
    obsolete_policy: ObsoletePolicy = ObsoletePolicy.CANDIDATE,
    provenance: StewardSettingProvenance = StewardSettingProvenance.PRODUCT_DEFAULT,
) -> StewardSettings:
    """Product defaults. Unknown, conflict, and legacy state are kept."""
    reason = (
        "obsolete verified objects are reclaim candidates and are not deleted"
        if obsolete_policy is ObsoletePolicy.CANDIDATE
        else "obsolete verified objects wait for an explicit policy decision"
    )
    rows = (
        _setting(
            "ownership.unknown",
            "preserve",
            provenance,
            "unknown ownership is not Machi-owned and is not reclaimable",
            "preserve",
        ),
        _setting(
            "ownership.conflicted",
            "preserve",
            provenance,
            "disagreement fails closed and is surfaced",
            "preserve",
        ),
        _setting(
            "ownership.legacy",
            "preserve",
            provenance,
            "unlabelled or legacy evidence is reported and not adopted",
            "preserve",
        ),
        _setting(
            "protection.active",
            "protect",
            provenance,
            "the current generation stays protected",
            "protect",
        ),
        _setting(
            "reclaim.obsolete",
            obsolete_policy.value,
            provenance,
            reason,
            "candidate,ask",
        ),
        _setting(
            "scan.scope",
            "registered_roots",
            provenance,
            "only caller-supplied roots are inspected",
            "registered_roots",
        ),
        _setting(
            "destructive.authorization",
            "false",
            provenance,
            "Tier 2 does not delete",
            "false",
        ),
    )
    return StewardSettings(
        unknown_ownership="preserve",
        conflicted_ownership="preserve",
        legacy_unlabelled="preserve",
        active_resource="protect",
        obsolete_policy=obsolete_policy,
        scan_scope="registered_roots",
        destructive_authorization=False,
        settings=rows,
    )


def _setting(
    name: str,
    value: str,
    provenance: StewardSettingProvenance,
    reason: str,
    allowed: str,
) -> StewardSetting:
    return StewardSetting(
        name=name,
        value=value,
        provenance=provenance,
        reason=reason,
        allowed_values=allowed,
        support_state=StewardSettingSupportState.SUPPORTED,
        mutability="runtime",
        invalidation="reassess",
    )
