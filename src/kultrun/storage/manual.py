"""Last-resort administrator capacity. Not a parallel planning authority.

Manual capacity is evidence used only after native, specialist, and Sonar
cannot establish authorizing capacity. It does not bypass ResourceManager,
does not shrink during deployment replanning, and does not override a
smaller hard or empirical bound.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kultrun.evidence.contracts import Provenance
from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.storage.characterize import StorageCharacterizationService
from kultrun.storage.contracts import (
    AdministratorCapacityBound,
    StorageCapacityEvidence,
)
from kultrun.storage.index import StorageEvidenceIndex
from kultrun.storage.limits import POLICY_VERSION
from kultrun.storage.topology import pools_from_host

PRODUCER = Name("storage.administrator")


@dataclass(frozen=True, slots=True)
class AdministratorCapacityResult:
    """Operator-visible result of supplying a last-resort bound."""

    accepted: bool
    reason: str
    bound: AdministratorCapacityBound | None
    evidence: StorageCapacityEvidence | None

    def payload(self) -> dict[str, object]:
        authorizing = None
        status = None
        source = None
        if self.evidence is not None:
            value = self.evidence.authorizing_available_bytes
            authorizing = value if isinstance(value, int) else None
            status = self.evidence.status.value
            source = (
                self.evidence.native_source
                if is_resolved(self.evidence.native_source)
                else None
            )
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "mount_point": self.bound.mount_point if self.bound is not None else None,
            "available_bytes": (
                self.bound.available_bytes if self.bound is not None else None
            ),
            "authorizing_available_bytes": authorizing,
            "status": status,
            "native_source": source,
            "last_resort": True,
            "mutations": True,
        }


class AdministratorCapacityService:
    """Persist a last-resort bound and re-characterize for the pipeline."""

    def __init__(
        self,
        characterization: StorageCharacterizationService,
        index: StorageEvidenceIndex,
        clock: Clock,
        state_root: Path,
        *,
        allow_empirical: bool,
    ) -> None:
        self._characterization = characterization
        self._index = index
        self._clock = clock
        self._state_root = Path(state_root)
        self._allow_empirical = allow_empirical

    def inspect(
        self, host: HostCapabilities, mount_point: str | None = None
    ) -> dict[str, object]:
        """Read stored last-resort bounds. Does not probe or characterize."""
        matching = self._index.matching_administrator_bytes(host)
        evidence = self._index.for_host(host)
        rows: list[dict[str, object]] = []
        for mount, available in matching.items():
            if mount_point is not None and mount != mount_point:
                continue
            item = evidence.get(mount)
            authorizing = (
                item.authorizing_available_bytes
                if item is not None
                and isinstance(item.authorizing_available_bytes, int)
                else None
            )
            rows.append(
                {
                    "mount_point": mount,
                    "available_bytes": available,
                    "authorizing_available_bytes": authorizing,
                    "status": item.status.value if item is not None else None,
                    "native_source": (
                        item.native_source
                        if item is not None and is_resolved(item.native_source)
                        else None
                    ),
                    "identity_matched": True,
                }
            )
        return {
            "bounds": rows,
            "count": len(rows),
            "last_resort": True,
            "mutations": False,
        }

    def set(
        self, host: HostCapabilities, mount_point: str, available_bytes: int
    ) -> AdministratorCapacityResult:
        """Record a last-resort bound only when automatic capacity is unresolved."""
        if available_bytes <= 0:
            raise ValidationError(
                "administrator capacity must be a positive byte count",
                parameter="bytes",
            )
        pool = next(
            (item for item in pools_from_host(host) if item.mount_point == mount_point),
            None,
        )
        if pool is None:
            raise NotFoundError(
                "no such candidate storage pool",
                mount_point=mount_point,
            )
        without = dict(self._index.matching_administrator_bytes(host))
        without.pop(mount_point, None)
        first = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=self._allow_empirical,
            probe_workspace=self._state_root,
            administrator_bounds=without,
        )
        automatic = first.evidence.get(mount_point)
        if automatic is not None and is_resolved(automatic.authorizing_available_bytes):
            self._index.record_expensive(first.evidence, first.empirical_evidence)
            raise PreconditionFailedError(
                "automatic storage capacity is already established; "
                "manual capacity is last-resort evidence only",
                reason="capacity_already_established",
                mount_point=mount_point,
            )
        bound = AdministratorCapacityBound(
            host_id=host.host_id,
            mount_point=mount_point,
            quota_identity=pool.quota_identity,
            pool_fingerprint=pool.fingerprint,
            available_bytes=available_bytes,
            observed_at=self._clock.now(),
            provenance=Provenance(
                producer=PRODUCER,
                producer_version=NOT_PROVIDED,
                observed_at=self._clock.now(),
                policy_version=POLICY_VERSION,
            ),
        )
        self._index.put_administrator_bound(bound)
        second = self._characterization.characterize(
            host,
            run_cleanup=True,
            run_empirical=self._allow_empirical,
            probe_workspace=self._state_root,
            administrator_bounds=self._index.matching_administrator_bytes(host),
        )
        self._index.record_expensive(second.evidence, second.empirical_evidence)
        evidence = second.evidence.get(mount_point)
        return AdministratorCapacityResult(
            accepted=True,
            reason="administrator-provided bound; weaker than hard evidence",
            bound=bound,
            evidence=evidence,
        )
