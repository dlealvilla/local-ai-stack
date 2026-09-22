"""Capacity contracts (MACHI 4).

These records separate reported, proven, and SAFE planning values.
They are not admission, not placement, and not an optimizer.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from machi.kernel.clock import require_utc
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract, contract, meaning
from machi.kernel.unresolved import Maybe

_TOKEN_MAX = 80
_REASON_MAX = 240
_MAX_DEVICES = 64
_MAX_DOMAINS = 64
_MAX_TIERS = 16
_MAX_SETTINGS = 24


class EvidenceStrength(StrEnum):
    """How much trust a selected number deserves. Not a score to average."""

    REPORTED = "reported"
    OBSERVED = "observed"
    AUTHORITATIVE = "authoritative"
    SPECIALIST = "specialist"
    EMPIRICALLY_PROVEN = "empirically_proven"
    ADMINISTRATOR_BOUNDED = "administrator_bounded"
    UNRESOLVED = "unresolved"


class SonarFailure(StrEnum):
    """Why a Sonar write stopped. Hard bounds stay distinct."""

    NONE = "none"
    EDQUOT = "edquot"
    ENOSPC = "enospc"
    PERMISSION = "permission"
    READ_ONLY = "read_only"
    IO_ERROR = "io_error"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"
    UNEXPECTED = "unexpected"


class SonarStatus(StrEnum):
    """What the bounded write proved. Not a speed benchmark."""

    NOT_ATTEMPTED = "not_attempted"
    CORROBORATED = "corroborated"
    CONTRADICTED = "contradicted"
    STOPPED_FOR_RESERVE = "stopped_for_reserve"
    UNRESOLVED = "unresolved"


class SonarWritePolicy(StrEnum):
    """Whether this evaluation may create a probe file."""

    DISABLED = "disabled"
    BOUNDED = "bounded"


class CapacitySettingProvenance(StrEnum):
    """Who selected a Capacity setting."""

    PRODUCT_DEFAULT = "product_default"
    ADMINISTRATOR = "administrator"


class CapacitySettingSupport(StrEnum):
    """Whether the setting is usable now."""

    SUPPORTED = "supported"


@contract(kind="capacity.setting", version=1)
@dataclass(frozen=True, slots=True)
class CapacitySetting(Contract):
    """One inspectable Capacity knob."""

    name: str = meaning("dotted setting name")
    value: str = meaning("current value as text")
    provenance: CapacitySettingProvenance = meaning("who selected this value")
    reason: str = meaning("why this value is in force")
    allowed_values: str = meaning("compact allowed-value description")
    support_state: CapacitySettingSupport = meaning("whether this setting is usable")
    mutability: str = meaning("runtime or restart_required")
    invalidation: str = meaning("what must be recomputed if this changes")

    def __post_init__(self) -> None:
        _bounded(self.name, what="setting name", maximum=_TOKEN_MAX)
        _bounded(self.value, what="setting value", maximum=_REASON_MAX)
        _bounded(self.reason, what="setting reason", maximum=_REASON_MAX)
        _bounded(self.allowed_values, what="allowed values", maximum=_REASON_MAX)
        if self.mutability not in {"runtime", "restart_required"}:
            raise ValidationError("setting mutability is not supported")
        _bounded(self.invalidation, what="invalidation", maximum=_TOKEN_MAX)


@contract(kind="capacity.settings", version=1)
@dataclass(frozen=True, slots=True)
class CapacitySettings(Contract):
    """Typed Tier-2 Capacity policy. Reserves are explicit."""

    memory_reserve_bytes: int = meaning("bytes held back from the memory hard ceiling")
    accelerator_reserve_bytes: int = meaning(
        "bytes held back from each discrete accelerator total"
    )
    storage_reserve_bytes: int = meaning(
        "bytes held back from a storage hard bound, including Sonar"
    )
    sonar_writes: SonarWritePolicy = meaning(
        "disabled by default; bounded writes require an explicit invocation"
    )
    sonar_max_tier_bytes: int = meaning(
        "largest Sonar tier this evaluation may attempt"
    )
    admin_fallback: str = meaning("allow or deny a last-resort administrator bound")
    settings: tuple[CapacitySetting, ...] = meaning("inspectable setting records")

    def __post_init__(self) -> None:
        for name, value in (
            ("memory_reserve_bytes", self.memory_reserve_bytes),
            ("accelerator_reserve_bytes", self.accelerator_reserve_bytes),
            ("storage_reserve_bytes", self.storage_reserve_bytes),
            ("sonar_max_tier_bytes", self.sonar_max_tier_bytes),
        ):
            if value < 0:
                raise ValidationError(
                    "capacity reserve or tier must be a non-negative integer",
                    field=name,
                )
        if self.admin_fallback not in {"allow", "deny"}:
            raise ValidationError("admin fallback must be allow or deny")
        if len(self.settings) > _MAX_SETTINGS:
            raise ValidationError("too many capacity settings")


@contract(kind="capacity.memory", version=1)
@dataclass(frozen=True, slots=True)
class MemoryCapacity(Contract):
    """System RAM planning ceiling. Not accelerator memory and not disk."""

    physical_bytes: Maybe[int] = meaning(
        "reported physical RAM; not a planning ceiling"
    )
    execution_limit_bytes: Maybe[int] = meaning(
        "authoritative cgroup or container limit when known"
    )
    hard_ceiling_bytes: Maybe[int] = meaning("minimum of the hard bounds that exist")
    reserve_bytes: int = meaning("configured headroom subtracted from the hard ceiling")
    safe_bytes: Maybe[int] = meaning(
        "planning ceiling after reserve; Unresolved when unknown"
    )
    strength: EvidenceStrength = meaning("trust in safe_bytes")
    reason: str = meaning("how the ceiling was chosen")

    def __post_init__(self) -> None:
        if self.reserve_bytes < 0:
            raise ValidationError("memory reserve must not be negative")
        _bounded(self.reason, what="memory reason", maximum=_REASON_MAX)


@contract(kind="capacity.accelerator", version=1)
@dataclass(frozen=True, slots=True)
class AcceleratorCapacity(Contract):
    """One device. Several devices are not one pooled VRAM number."""

    identity: str = meaning("provider-local device identity from Discover")
    ordinal: int = meaning("position in the accelerator observation")
    topology: str = meaning("discrete, unified, or unresolved")
    physical_bytes: Maybe[int] = meaning("dedicated total when Discover reported one")
    current_used_bytes: Maybe[int] = meaning(
        "current occupancy; Unresolved when this tier cannot prove it"
    )
    reserve_bytes: int = meaning("headroom subtracted from a discrete total")
    safe_bytes: Maybe[int] = meaning(
        "per-device planning ceiling; not a sum across devices"
    )
    strength: EvidenceStrength = meaning("trust in safe_bytes")
    reason: str = meaning("how this device ceiling was chosen")

    def __post_init__(self) -> None:
        if self.ordinal < 0 or self.reserve_bytes < 0:
            raise ValidationError("accelerator capacity fields must not be negative")
        _bounded(self.identity, what="accelerator identity", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="accelerator reason", maximum=_REASON_MAX)


@contract(kind="capacity.specialist_bound", version=1)
@dataclass(frozen=True, slots=True)
class SpecialistBound(Contract):
    """A caller's real remaining entitlement, when a specialist actually read it."""

    backing_store_id: str = meaning("2.4 backing identity this bound applies to")
    remaining_bytes: int = meaning("hard remaining bytes the specialist reported")
    source: str = meaning("which specialist produced the bound")

    def __post_init__(self) -> None:
        _bounded(self.backing_store_id, what="backing id", maximum=_TOKEN_MAX)
        _bounded(self.source, what="specialist source", maximum=_TOKEN_MAX)
        if self.remaining_bytes < 0:
            raise ValidationError("specialist remaining bytes must not be negative")


@contract(kind="capacity.admin_bound", version=1)
@dataclass(frozen=True, slots=True)
class AdministratorBound(Contract):
    """Last-resort ceiling. It cannot raise a smaller hard proof."""

    domain_id: str = meaning("storage domain this bound applies to")
    bound_bytes: int = meaning("administrator ceiling in bytes")
    reason: str = meaning("why the administrator supplied this bound")

    def __post_init__(self) -> None:
        _bounded(self.domain_id, what="domain id", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="admin reason", maximum=_REASON_MAX)
        if self.bound_bytes < 0:
            raise ValidationError("administrator bound must not be negative")


@contract(kind="capacity.sonar_evidence", version=1)
@dataclass(frozen=True, slots=True)
class SonarEvidence(Contract):
    """Bounded write result. Success does not raise the reported ceiling."""

    status: SonarStatus = meaning(
        "not attempted, corroborated, contradicted, or stopped"
    )
    proven_lower_bytes: Maybe[int] = meaning("highest tier actually committed")
    contradictory_upper_bytes: Maybe[int] = meaning(
        "first tier that failed with EDQUOT or ENOSPC"
    )
    failure: SonarFailure = meaning("classified write failure, or none")
    tiers_attempted: tuple[int, ...] = meaning("tier sizes attempted, in order")
    cleanup_completed: Maybe[bool] = meaning("whether the owned probe file was removed")
    reason: str = meaning("short sonar outcome")

    def __post_init__(self) -> None:
        if len(self.tiers_attempted) > _MAX_TIERS:
            raise ValidationError("too many sonar tiers")
        for tier in self.tiers_attempted:
            if tier < 1:
                raise ValidationError("sonar tier must be positive", tier=tier)
        _bounded(self.reason, what="sonar reason", maximum=_REASON_MAX)


@contract(kind="capacity.storage_domain", version=1)
@dataclass(frozen=True, slots=True)
class StorageDomainCapacity(Contract):
    """One backing pool. Mounts that share it are not added together."""

    domain_id: str = meaning("backing id, or one mount id when backing is unresolved")
    backing_resolved: bool = meaning("false when this domain must not be merged")
    reported_available_bytes: Maybe[int] = meaning(
        "filesystem-reported available bytes"
    )
    specialist_remaining_bytes: Maybe[int] = meaning(
        "specialist hard remaining, if read"
    )
    hard_bound_bytes: Maybe[int] = meaning("smallest trusted hard ceiling")
    reserve_bytes: int = meaning("storage headroom")
    safe_bytes: Maybe[int] = meaning("planning bytes now; not potential-after-reclaim")
    protected_occupancy_bytes: Maybe[int] = meaning(
        "Steward protected bytes on this backing; not subtracted again from available"
    )
    reclaimable_bytes: Maybe[int] = meaning("candidate bytes; not current free space")
    potential_after_reclaim_bytes: Maybe[int] = meaning(
        "safe_bytes plus reclaimable candidates; not current free space"
    )
    usable: bool = meaning("false for read-only or pseudo domains")
    strength: EvidenceStrength = meaning("trust in safe_bytes")
    sonar: SonarEvidence = meaning("empirical write evidence, or not attempted")
    reason: str = meaning("how the storage ceiling was chosen")

    def __post_init__(self) -> None:
        if self.reserve_bytes < 0:
            raise ValidationError("storage reserve must not be negative")
        _bounded(self.domain_id, what="domain id", maximum=_TOKEN_MAX)
        _bounded(self.reason, what="storage reason", maximum=_REASON_MAX)


@contract(kind="capacity.envelope", version=1)
@dataclass(frozen=True, slots=True)
class CapacityEnvelope(Contract):
    """SAFE planning facts for one evidence generation. Not an admission."""

    evidence_id: str = meaning("identity of this snapshot; plans must cite it")
    input_token: str = meaning("fingerprint of the inputs; a mismatch means stale")
    memory: MemoryCapacity = meaning("system RAM planning ceiling")
    accelerators: tuple[AcceleratorCapacity, ...] = meaning("per-device ceilings")
    storage_domains: tuple[StorageDomainCapacity, ...] = meaning("per-backing storage")
    settings: CapacitySettings = meaning("policy used for this snapshot")
    observed_at: dt.datetime = meaning("when this envelope was derived; UTC")
    provider: str = meaning("adapter identifier, for example native")

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observed_at", require_utc(self.observed_at, what="observed_at")
        )
        _bounded(self.evidence_id, what="evidence id", maximum=_TOKEN_MAX)
        _bounded(self.input_token, what="input token", maximum=80)
        _bounded(self.provider, what="provider", maximum=_TOKEN_MAX)
        if len(self.accelerators) > _MAX_DEVICES:
            raise ValidationError("too many accelerator capacity rows")
        if len(self.storage_domains) > _MAX_DOMAINS:
            raise ValidationError("too many storage domains")
        identities = [item.identity for item in self.accelerators]
        if len(set(identities)) != len(identities):
            raise ValidationError("accelerator capacity rows must be unique")
        domains = [item.domain_id for item in self.storage_domains]
        if len(set(domains)) != len(domains):
            raise ValidationError("storage domains must be unique")


def _bounded(value: str, *, what: str, maximum: int) -> None:
    if not value or len(value) > maximum:
        raise ValidationError(f"{what} must be a non-empty bounded string",
            maximum=maximum)
