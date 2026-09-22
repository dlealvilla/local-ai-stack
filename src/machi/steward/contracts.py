"""Steward contracts (MACHI 3).

These records classify ownership, lifecycle, protection, occupancy, and
reclaimability. They are not Capacity envelopes and they do not authorize
deletion. ``destructive_authorization`` is always false at Tier 2.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

_TOKEN_MAX = 64
_REASON_MAX = 240
_PATH_MAX = 512
_ID_MAX = 80
_MAX_RESOURCES = 64
_MAX_SETTINGS = 16
_MAX_BACKING = 64


class OwnershipStatus(StrEnum):
    """Whether dual proof says this root belongs to Machi."""

    VERIFIED_MACHI_OWNED = "verified_machi_owned"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"
    NOT_MACHI_OWNED = "not_machi_owned"
    LEGACY_UNVERIFIED = "legacy_unverified"


class LifecycleStatus(StrEnum):
    """Generation state of a verified Machi resource. Not an ownership proof."""

    ACTIVE = "active"
    STANDBY = "standby"
    OBSOLETE = "obsolete"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class ProtectionStatus(StrEnum):
    """Retention separate from lifecycle. Obsolete may still be protected."""

    ACTIVE_PROTECTED = "active_protected"
    ROLLBACK_PROTECTED = "rollback_protected"
    EVIDENCE_RETAINED = "evidence_retained"
    POLICY_RETAINED = "policy_retained"
    UNPROTECTED = "unprotected"
    UNKNOWN = "unknown"


class Reclaimability(StrEnum):
    """Whether current rules would allow a later cleanup. Not a delete."""

    RECLAIMABLE = "reclaimable"
    NOT_RECLAIMABLE = "not_reclaimable"
    REQUIRES_POLICY_DECISION = "requires_policy_decision"
    UNKNOWN = "unknown"


class ResourceCategory(StrEnum):
    """What kind of managed object this is. Extensible; only roots exist now."""

    INSTALLATION_ROOT = "installation_root"
    UNKNOWN = "unknown"


class GenerationHint(StrEnum):
    """Caller-supplied generation. Never inferred from a path name."""

    CURRENT = "current"
    OBSOLETE = "obsolete"
    ABANDONED = "abandoned"
    ROLLBACK = "rollback"


class ProtectionHint(StrEnum):
    """Caller-supplied protection. Active resources stay protected."""

    DEFAULT = "default"
    ROLLBACK = "rollback"
    EVIDENCE = "evidence"
    POLICY = "policy"
    UNPROTECTED = "unprotected"


class ObsoletePolicy(StrEnum):
    """What an obsolete, unprotected, verified object becomes."""

    CANDIDATE = "candidate"
    ASK = "ask"


class StewardSettingProvenance(StrEnum):
    """Who selected a Steward setting."""

    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR = "administrator"


class StewardSettingSupportState(StrEnum):
    """Whether the setting is usable now."""

    SUPPORTED = "supported"


class MarkerFact(StrEnum):
    """What the local marker file showed. Not a delete decision."""

    ABSENT = "absent"
    VALID = "valid"
    MALFORMED = "malformed"
    UNSUPPORTED = "unsupported"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    WRONG_PRODUCT = "wrong_product"
    NOT_A_FILE = "not_a_file"


class RegistryFact(StrEnum):
    """What the control-plane registry showed for the marker id."""

    ABSENT = "absent"
    NOT_CONSULTED = "not_consulted"
    MATCH = "match"
    MISMATCH = "mismatch"
    MALFORMED = "malformed"


class InstallFact(StrEnum):
    """What the InstallRecord showed for the same marker id."""

    ABSENT = "absent"
    NOT_CONSULTED = "not_consulted"
    MATCH = "match"
    MISMATCH = "mismatch"


@contract(kind="steward.setting", version=1)
@dataclass(frozen=True, slots=True)
class StewardSetting(Contract):
    """One inspectable Steward setting for later command-center aggregation."""

    name: str = meaning("dotted setting name")
    value: str = meaning("current value as text")
    provenance: StewardSettingProvenance = meaning("who selected this value")
    reason: str = meaning("why this value is in force")
    allowed_values: str = meaning("compact allowed-value description")
    support_state: StewardSettingSupportState = meaning(
        "whether this setting is usable"
    )
    mutability: str = meaning("runtime or restart_required")
    invalidation: str = meaning("what must re-run if this setting changes")

    def __post_init__(self) -> None:
        _require_bounded(self.name, what="setting name", maximum=_TOKEN_MAX)
        _require_bounded(self.value, what="setting value", maximum=_REASON_MAX)
        _require_bounded(self.reason, what="setting reason", maximum=_REASON_MAX)
        _require_bounded(
            self.allowed_values, what="allowed values", maximum=_REASON_MAX
        )
        if self.mutability not in {"runtime", "restart_required"}:
            raise ValidationError(
                "setting mutability is not supported",
                mutability=self.mutability,
            )
        _require_bounded(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="steward.settings", version=1)
@dataclass(frozen=True, slots=True)
class StewardSettings(Contract):
    """Typed Tier-2 Steward policy. Preservation is the default."""

    unknown_ownership: str = meaning("preserve; unknown is not Machi-owned")
    conflicted_ownership: str = meaning("preserve and surface the conflict")
    legacy_unlabelled: str = meaning("preserve and report; do not adopt")
    active_resource: str = meaning("protect the current generation")
    obsolete_policy: ObsoletePolicy = meaning(
        "obsolete unprotected objects are candidates or need a decision"
    )
    scan_scope: str = meaning("only caller-supplied roots; no mount crawl")
    destructive_authorization: bool = meaning(
        "Tier 2 never authorizes deletion; always false"
    )
    settings: tuple[StewardSetting, ...] = meaning("inspectable setting records")

    def __post_init__(self) -> None:
        if self.unknown_ownership != "preserve":
            raise ValidationError("unknown ownership must be preserved")
        if self.conflicted_ownership != "preserve":
            raise ValidationError("conflicted ownership must be preserved")
        if self.legacy_unlabelled != "preserve":
            raise ValidationError("legacy unlabelled state must be preserved")
        if self.active_resource != "protect":
            raise ValidationError("active resources must be protected")
        if self.scan_scope != "registered_roots":
            raise ValidationError("Steward scan scope is registered roots only")
        if self.destructive_authorization:
            raise ValidationError("Tier-2 Steward must not authorize destruction")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many Steward settings")


@contract(kind="steward.resource", version=1)
@dataclass(frozen=True, slots=True)
class StewardResource(Contract):
    """One known root after ownership and occupancy classification."""

    resource_id: str = meaning("marker id or root fingerprint; not a customer filename")
    path: str = meaning("managed root path; operational document, not an event field")
    ownership: OwnershipStatus = meaning("dual-proof result")
    lifecycle: LifecycleStatus = meaning("generation state; unknown unless verified")
    protection: ProtectionStatus = meaning("retention; independent of lifecycle")
    reclaimability: Reclaimability = meaning("candidate or not; not a delete")
    category: ResourceCategory = meaning("installation root or unknown")
    generation: GenerationHint = meaning("caller-supplied generation hint")
    install_id: Maybe[str] = meaning("InstallId when the record matched")
    size_bytes: Maybe[int] = meaning(
        "measured bytes of this verified root; Unresolved otherwise"
    )
    mount_id: Maybe[str] = meaning("2.4 mount id when an observation was supplied")
    backing_store_id: Maybe[str] = meaning(
        "2.4 backing identity when an observation was supplied"
    )
    storage_class: Maybe[str] = meaning("2.4 storage class when supplied")
    provenance: str = meaning("which evidence produced this classification")
    reason: str = meaning("short classification reason")
    destructive_authorization: bool = meaning("always false at Tier 2")

    def __post_init__(self) -> None:
        _require_bounded(self.resource_id, what="resource id", maximum=_ID_MAX)
        _require_bounded(self.path, what="path", maximum=_PATH_MAX)
        _require_bounded(self.provenance, what="provenance", maximum=_REASON_MAX)
        _require_bounded(self.reason, what="reason", maximum=_REASON_MAX)
        if self.destructive_authorization:
            raise ValidationError("a Steward resource must not authorize destruction")
        if _is_measured(self.size_bytes) and self.ownership is not (
            OwnershipStatus.VERIFIED_MACHI_OWNED
        ):
            raise ValidationError("only verified Machi roots may carry measured bytes")


@contract(kind="steward.occupancy_totals", version=1)
@dataclass(frozen=True, slots=True)
class OccupancyTotals(Contract):
    """Bytes already in use, split so Capacity can subtract them later."""

    active_bytes: Maybe[int] = meaning("verified active or standby protected bytes")
    protected_bytes: Maybe[int] = meaning("verified bytes that must be kept")
    reclaimable_bytes: Maybe[int] = meaning("verified candidate bytes; not deleted")
    unknown_bytes: Maybe[int] = meaning(
        "Unresolved when an unclassified root was not measured"
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("active_bytes", self.active_bytes),
            ("protected_bytes", self.protected_bytes),
            ("reclaimable_bytes", self.reclaimable_bytes),
            ("unknown_bytes", self.unknown_bytes),
        ):
            if isinstance(value, int) and value < 0:
                raise ValidationError(
                    "occupancy bytes must not be negative",
                    field=name,
                )


@contract(kind="steward.backing_occupancy", version=1)
@dataclass(frozen=True, slots=True)
class BackingOccupancy(Contract):
    """Occupancy grouped by 2.4 backing identity. Not a second capacity."""

    backing_store_id: Maybe[str] = meaning("shared backing id, or Unresolved")
    resource_count: int = meaning("how many managed roots share this identity")
    size_bytes: Maybe[int] = meaning("sum of measured bytes; Unresolved if any is")

    def __post_init__(self) -> None:
        if self.resource_count < 1:
            raise ValidationError("backing occupancy needs at least one resource")
        if isinstance(self.size_bytes, int) and self.size_bytes < 0:
            raise ValidationError("backing occupancy bytes must not be negative")


@contract(kind="steward.occupancy_map", version=1)
@dataclass(frozen=True, slots=True)
class OccupancyMap(Contract):
    """Tier-2 projection. The registry remains the ownership authority."""

    resources: tuple[StewardResource, ...] = meaning("classified known roots")
    totals: OccupancyTotals = meaning("aggregated occupancy for Capacity")
    backing: tuple[BackingOccupancy, ...] = meaning("occupancy by backing store")
    settings: StewardSettings = meaning("typed policy used for this projection")
    destructive_authorization: bool = meaning("always false; Steward does not delete")
    observed_at: dt.datetime = meaning("when this projection was built; UTC")
    provider: str = meaning("adapter identifier, for example native")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        if self.destructive_authorization:
            raise ValidationError("Tier-2 OccupancyMap must not authorize destruction")
        if len(self.resources) > _MAX_RESOURCES:
            raise ValidationError("too many Steward resources")
        if len(self.backing) > _MAX_BACKING:
            raise ValidationError("too many backing occupancy rows")
        seen: set[str] = set()
        for resource in self.resources:
            if resource.resource_id in seen:
                raise ValidationError(
                    "Steward counted the same managed object twice",
                    resource_id=resource.resource_id,
                )
            seen.add(resource.resource_id)


def _is_measured(value: Maybe[int]) -> bool:
    """True when bytes were actually measured, including a real zero."""
    return isinstance(value, int)


def _require_bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(
            f"{what} must be a non-empty bounded string",
            maximum=maximum,
        )
