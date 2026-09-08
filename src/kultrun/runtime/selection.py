"""Bounded foundation selection. Recommendation is not verification.

Does not import execution, model, resource, inference, planning, or
subprocess. Does not rank with weights. Does not silently execute a
different foundation than the one selected.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.runtime.contracts import (
    FoundationConfidence,
    FoundationSelection,
    FoundationSelectionId,
    FoundationSelectionMode,
    InstallationStatus,
    RuntimeCandidate,
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeResolution,
    RuntimeSupportDescriptor,
    VerificationStatus,
)
from kultrun.runtime.lock import SelectionLock
from kultrun.runtime.pins import SELECTION_SCHEMA
from kultrun.runtime.plan import find_candidate, is_provisionable
from kultrun.runtime.provision import ProvisioningService
from kultrun.runtime.resolve import ExecutorCapabilityView, resolve
from kultrun.runtime.verify import VerificationService

STALE_DOMAINS: tuple[str, ...] = (
    "eligible_model_view",
    "current_model_validity",
    "model_requirement",
    "capacity",
    "resource_request",
    "deployment_plan",
)

ROLE_RECOMMENDED = "recommended_to_provision"
ROLE_OTHER = "other_provisionable"
ROLE_BLOCKED = "blocked"


def fingerprint_selection_id(host_id: str) -> FoundationSelectionId:
    """One current selection identity per host."""
    digest = hashlib.sha256(f"{SELECTION_SCHEMA}|{host_id}".encode()).hexdigest()
    return FoundationSelectionId(f"fsel_{digest[:16]}")


@dataclass(frozen=True, slots=True)
class ClassifiedRuntimeCandidate:
    """Derived classification of one RuntimeCandidate. Not a new identity."""

    candidate_id: str
    confidence: FoundationConfidence
    role: str
    selected: bool
    reason: str
    installation_id: str | None
    profile_id: str | None
    profile_status: str | None


@dataclass(frozen=True, slots=True)
class FoundationOverview:
    """Current recommendation, selection, and confidence. Not persisted."""

    selection: FoundationSelection
    resolution: RuntimeResolution
    candidates: tuple[ClassifiedRuntimeCandidate, ...]
    provisionable_ids: tuple[str, ...]
    blocked_ids: tuple[str, ...]
    verified_executable_ids: tuple[str, ...]
    selected_installation_id: str | None
    selected_profile_status: str | None

    def payload(self) -> dict[str, object]:
        """API-shaped view. GET callers must not treat this as a mutation."""
        recommended = self.selection.recommended_candidate_id
        selected = self.selection.selected_candidate_id
        return {
            "selection": self.selection,
            "selection_mode": self.selection.selection_mode.value,
            "resolver_mode": self.resolution.policy.mode.value,
            "recommended_candidate_id": (
                recommended if isinstance(recommended, str) else None
            ),
            "selected_candidate_id": selected if isinstance(selected, str) else None,
            "recommended_to_provision": [
                item.candidate_id
                for item in self.candidates
                if item.role == ROLE_RECOMMENDED
            ],
            "other_provisionable": [
                item.candidate_id
                for item in self.candidates
                if item.role == ROLE_OTHER
            ],
            "blocked": list(self.blocked_ids),
            "verified_executable": list(self.verified_executable_ids),
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "confidence": item.confidence.value,
                    "role": item.role,
                    "selected": item.selected,
                    "reason": item.reason,
                    "installation_id": item.installation_id,
                    "profile_id": item.profile_id,
                    "profile_status": item.profile_status,
                }
                for item in self.candidates
            ],
            "selected_installation_id": self.selected_installation_id,
            "selected_profile_status": self.selected_profile_status,
            "downstream_stale": self.selection.downstream_stale,
            "stale_domains": list(self.selection.stale_domains),
            "mutations": False,
            "provision": False,
            "verify": False,
        }


class FoundationSelectionService:
    """Recommend, persist AUTO|MANUAL, realize and verify the selected path."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        provisioning: ProvisioningService,
        verification: VerificationService,
        lock: SelectionLock,
    ) -> None:
        self._store = store
        self._clock = clock
        self._provisioning = provisioning
        self._verification = verification
        self._lock = lock

    def stored(self, host: HostCapabilities) -> FoundationSelection | None:
        """Persisted selection, if any. Does not resolve or probe."""
        return self._load(host.host_id.value)

    def view(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
    ) -> FoundationOverview:
        """Classify the current set. GET must not persist or probe."""
        with self._lock.hold():
            return self._view(host, executors, descriptors, policy, components)

    def select_auto(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
    ) -> FoundationOverview:
        """Follow the current recommendation. Does not provision or verify."""
        with self._lock.hold():
            overview = self._view(host, executors, descriptors, policy, components)
            self._persist(
                host,
                FoundationSelectionMode.AUTO,
                overview.selection.recommended_candidate_id,
                overview.selection.recommended_candidate_id,
            )
            return self._view(host, executors, descriptors, policy, components)

    def select_manual(
        self,
        candidate_id: str,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
    ) -> FoundationOverview:
        """Hold a provisionable candidate. Not proof it is executable."""
        if not candidate_id.strip():
            raise ValidationError(
                "a candidate id is required", parameter="candidate_id"
            )
        with self._lock.hold():
            overview = self._view(host, executors, descriptors, policy, components)
            candidate = find_candidate(overview.resolution, candidate_id)
            if candidate is None:
                raise NotFoundError(
                    "no such runtime candidate", candidate_id=candidate_id
                )
            if not is_provisionable(candidate):
                raise PreconditionFailedError(
                    "blocked foundation cannot be selected",
                    candidate_id=candidate_id,
                )
            self._persist(
                host,
                FoundationSelectionMode.MANUAL,
                overview.selection.recommended_candidate_id,
                candidate.candidate_id.value,
            )
            return self._view(host, executors, descriptors, policy, components)

    def realize_selected(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
        retry: bool = False,
    ) -> RuntimeInstallation:
        """Plan and provision the selected candidate only. Does not verify."""
        with self._lock.hold():
            overview = self._view(host, executors, descriptors, policy, components)
            selected = overview.selection.selected_candidate_id
            if not isinstance(selected, str):
                raise PreconditionFailedError("no selected foundation to realize")
            candidate = find_candidate(overview.resolution, selected)
            if candidate is None:
                raise NotFoundError(
                    "no such runtime candidate", candidate_id=selected
                )
            if not is_provisionable(candidate):
                raise PreconditionFailedError(
                    "selected foundation is not provisionable",
                    candidate_id=selected,
                )
            resolved_policy = policy or RuntimePolicy()
            plan = self._provisioning.create_plan(
                selected,
                host,
                executors,
                descriptors,
                resolved_policy,
                components=components,
            )
            return self._provisioning.provision(
                plan.plan_id,
                host,
                executors,
                descriptors,
                components=components,
                retry=retry,
                policy=resolved_policy,
            )

    def verify_selected(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None = None,
        *,
        components: Mapping[str, str] | None = None,
    ) -> RuntimeCapabilityProfile:
        """Verify the selected installation only. Does not switch foundation."""
        with self._lock.hold():
            overview = self._view(host, executors, descriptors, policy, components)
            selected = overview.selection.selected_candidate_id
            if not isinstance(selected, str):
                raise PreconditionFailedError("no selected foundation to verify")
            installation = self._installation_for(selected)
            if installation is None:
                raise PreconditionFailedError(
                    "selected foundation has no installation to verify",
                    candidate_id=selected,
                )
            return self._verification.verify(
                installation.installation_id, host, executors
            )

    def _view(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy | None,
        components: Mapping[str, str] | None,
    ) -> FoundationOverview:
        resolved_policy = policy or RuntimePolicy()
        resolution = resolve(
            host, executors, descriptors, resolved_policy, components=components
        )
        recommended = self._recommend(resolution)
        stored = self._load(host.host_id.value)
        selection = self._effective(host, stored, recommended)
        rows = self._classify(resolution, selection, host, executors)
        provisionable = tuple(
            item.candidate_id
            for item in rows
            if item.confidence is not FoundationConfidence.BLOCKED
        )
        blocked = tuple(
            item.candidate_id
            for item in rows
            if item.confidence is FoundationConfidence.BLOCKED
        )
        verified = tuple(
            item.candidate_id
            for item in rows
            if item.confidence is FoundationConfidence.VERIFIED_EXECUTABLE
        )
        chosen = (
            selection.selected_candidate_id
            if isinstance(selection.selected_candidate_id, str)
            else None
        )
        selected_row = next(
            (item for item in rows if item.candidate_id == chosen), None
        )
        return FoundationOverview(
            selection=selection,
            resolution=resolution,
            candidates=rows,
            provisionable_ids=provisionable,
            blocked_ids=blocked,
            verified_executable_ids=verified,
            selected_installation_id=(
                selected_row.installation_id if selected_row else None
            ),
            selected_profile_status=(
                selected_row.profile_status if selected_row else None
            ),
        )

    def _recommend(self, resolution: RuntimeResolution) -> str | None:
        provisionable = [
            item for item in resolution.candidates if is_provisionable(item)
        ]
        if not provisionable:
            return None
        preferred = resolution.preferred_candidate_id
        if isinstance(preferred, str) and any(
            item.candidate_id.value == preferred for item in provisionable
        ):
            return preferred
        return provisionable[0].candidate_id.value

    def _effective(
        self,
        host: HostCapabilities,
        stored: FoundationSelection | None,
        recommended: str | None,
    ) -> FoundationSelection:
        rec: Maybe[str] = recommended if recommended is not None else NOT_PROVIDED
        if stored is None:
            now = self._clock.now()
            return FoundationSelection(
                selection_id=fingerprint_selection_id(host.host_id.value),
                host_id=host.host_id,
                selection_mode=FoundationSelectionMode.AUTO,
                recommended_candidate_id=rec,
                selected_candidate_id=rec,
                created_at=now,
                selected_at=now,
                generation=0,
            )
        selected = stored.selected_candidate_id
        stale = stored.downstream_stale
        domains = stored.stale_domains
        if stored.selection_mode is FoundationSelectionMode.AUTO:
            selected = rec
            if stored.selected_candidate_id != rec:
                stale = True
                domains = STALE_DOMAINS
        return replace(
            stored,
            recommended_candidate_id=rec,
            selected_candidate_id=selected,
            downstream_stale=stale,
            stale_domains=domains,
        )

    def _classify(
        self,
        resolution: RuntimeResolution,
        selection: FoundationSelection,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> tuple[ClassifiedRuntimeCandidate, ...]:
        recommended = selection.recommended_candidate_id
        selected = selection.selected_candidate_id
        rows: list[ClassifiedRuntimeCandidate] = []
        for candidate in (
            *resolution.candidates,
            *resolution.unresolved,
            *resolution.unsupported,
        ):
            installation = self._installation_for(candidate.candidate_id.value)
            profile = None
            if installation is not None:
                profile = self._verification.profile_for(
                    installation.installation_id, host, executors
                )
            confidence = _confidence(candidate, profile)
            ident = candidate.candidate_id.value
            if confidence is FoundationConfidence.BLOCKED:
                role = ROLE_BLOCKED
            elif ident == recommended:
                role = ROLE_RECOMMENDED
            else:
                role = ROLE_OTHER
            rows.append(
                ClassifiedRuntimeCandidate(
                    candidate_id=ident,
                    confidence=confidence,
                    role=role,
                    selected=ident == selected,
                    reason=candidate.reason,
                    installation_id=(
                        installation.installation_id.value
                        if installation is not None
                        else None
                    ),
                    profile_id=(
                        profile.profile_id.value if profile is not None else None
                    ),
                    profile_status=(
                        profile.status.value if profile is not None else None
                    ),
                )
            )
        return tuple(rows)

    def _persist(
        self,
        host: HostCapabilities,
        mode: FoundationSelectionMode,
        recommended: Maybe[str],
        selected: Maybe[str],
    ) -> FoundationSelection:
        stored = self._load(host.host_id.value)
        now = self._clock.now()
        previous = stored.selected_candidate_id if stored is not None else None
        changed = previous != selected
        if stored is None:
            record = FoundationSelection(
                selection_id=fingerprint_selection_id(host.host_id.value),
                host_id=host.host_id,
                selection_mode=mode,
                recommended_candidate_id=recommended,
                selected_candidate_id=selected,
                created_at=now,
                selected_at=now,
                generation=1,
                downstream_stale=changed,
                stale_domains=STALE_DOMAINS if changed else (),
            )
        else:
            record = replace(
                stored,
                selection_mode=mode,
                recommended_candidate_id=recommended,
                selected_candidate_id=selected,
                selected_at=now if changed else stored.selected_at,
                generation=(
                    stored.generation + 1 if changed else stored.generation
                ),
                downstream_stale=True if changed else stored.downstream_stale,
                stale_domains=(
                    STALE_DOMAINS if changed else stored.stale_domains
                ),
            )
        self._store.put(record.selection_id.value, record)
        return record

    def _load(self, host_id: str) -> FoundationSelection | None:
        return self._store.get(
            FoundationSelection, fingerprint_selection_id(host_id).value
        )

    def _installation_for(self, candidate_id: str) -> RuntimeInstallation | None:
        matches = [
            item
            for item in self._provisioning.installations()
            if item.candidate_id.value == candidate_id
        ]
        if not matches:
            return None
        installed = [
            item for item in matches if item.status is InstallationStatus.INSTALLED
        ]
        return installed[-1] if installed else matches[-1]


def _confidence(
    candidate: RuntimeCandidate, profile: RuntimeCapabilityProfile | None
) -> FoundationConfidence:
    if profile is not None and profile.status is VerificationStatus.VERIFIED:
        return FoundationConfidence.VERIFIED_EXECUTABLE
    if is_provisionable(candidate):
        return FoundationConfidence.PROVISIONABLE
    return FoundationConfidence.BLOCKED
