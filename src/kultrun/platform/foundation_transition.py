"""Foundation rebootstrap orchestration contract. Does not launch llama.cpp.

Inspects a requested family change against live instances. A different
family requires stop + reservation release before the new foundation may
become the active serving foundation. Same-family model switch stays on
the existing lighter lifecycle.
"""

from __future__ import annotations

from kultrun.host.contracts import HostCapabilities
from kultrun.inference.service import InstanceService
from kultrun.kernel.errors import ConflictError, PreconditionFailedError
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import (
    FoundationTransition,
    FoundationTransitionKind,
    RuntimeCandidate,
    RuntimeCapabilityProfile,
    VerificationStatus,
)
from kultrun.runtime.plan import is_provisionable
from kultrun.runtime.selection import FoundationSelectionService
from kultrun.runtime.transition import classify_transition


class FoundationTransitionService:
    """Classify and gate foundation switches. Does not exec a new runtime."""

    def __init__(
        self,
        foundation: FoundationSelectionService,
        instances: InstanceService,
    ) -> None:
        self._foundation = foundation
        self._instances = instances

    def inspect(
        self,
        host: HostCapabilities,
        *,
        to_family: str | None,
        to_candidate_id: str | None = None,
        production_executable: bool = False,
    ) -> FoundationTransition:
        stored = self._foundation.stored(host)
        from_id = (
            stored.selected_candidate_id
            if stored is not None and isinstance(stored.selected_candidate_id, str)
            else None
        )
        from_family = self._family_of_selected(host)
        return classify_transition(
            host.host_id,
            from_family=from_family,
            to_family=to_family,
            from_candidate_id=from_id,
            to_candidate_id=to_candidate_id,
            production_executable=production_executable,
        )

    def assert_can_activate(self, host: HostCapabilities, to_family: str) -> None:
        """Refuse a second live product foundation. Does not stop or launch."""
        live = self._instances.live_product_families(host.host_id)
        if live and to_family not in live:
            raise ConflictError(
                "foundation rebootstrap requires the active foundation to stop",
                reason="foundation_rebootstrap_required",
                active_families=tuple(sorted(live)),
                requested=to_family,
            )

    def require_production_executable(self, transition: FoundationTransition) -> None:
        if (
            transition.transition_kind
            is FoundationTransitionKind.FOUNDATION_REBOOTSTRAP
            and not transition.production_executable
        ):
            raise PreconditionFailedError(
                "requested foundation is not a verified executable runtime",
                reason="foundation_not_executable",
                requested=(
                    transition.to_family if is_resolved(transition.to_family) else None
                ),
            )

    def _family_of_selected(self, host: HostCapabilities) -> str | None:
        stored = self._foundation.stored(host)
        if stored is None or not isinstance(stored.selected_candidate_id, str):
            live = self._instances.live_product_families(host.host_id)
            if len(live) == 1:
                return next(iter(live))
            return None
        installation = self._foundation.installation_for(stored.selected_candidate_id)
        if installation is not None:
            return installation.runtime.value
        return None


def production_executable_for(
    candidate: RuntimeCandidate | None,
    profile: RuntimeCapabilityProfile | None,
) -> bool:
    """Verified + provisionable. FUTURE and unverified paths are not executable."""
    if candidate is None or profile is None:
        return False
    if not is_provisionable(candidate):
        return False
    return profile.status is VerificationStatus.VERIFIED
