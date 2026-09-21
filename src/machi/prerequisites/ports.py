"""Replaceable PrerequisiteReadiness adapter port (MACHI 2.5.1).

Domain owns the cycle. Adapters inspect a concrete target and may
perform only allowlisted mutations when the service asks.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from machi.prerequisites.contracts import (
    PrerequisiteDiagnosis,
    PrerequisiteInspection,
    PrerequisitePlan,
    PrerequisitePolicy,
    PrerequisiteSetting,
    RemediationResult,
    VerificationResult,
)


@runtime_checkable
class PrerequisiteAdapter(Protocol):
    """Something that can inspect and optionally remediate one target."""

    adapter_id: str

    def extra_settings(self) -> tuple[PrerequisiteSetting, ...]:
        """Typed settings a later command center can aggregate."""
        ...

    def inspect(self) -> PrerequisiteInspection:
        """Read the target. Must not mutate the host."""
        ...

    def diagnose(self, inspection: PrerequisiteInspection) -> PrerequisiteDiagnosis:
        """Classify an inspection. Must not mutate the host."""
        ...

    def plan(
        self,
        inspection: PrerequisiteInspection,
        diagnosis: PrerequisiteDiagnosis,
        policy: PrerequisitePolicy,
    ) -> PrerequisitePlan:
        """Produce an exact plan. Must not mutate the host."""
        ...

    def remediate(
        self,
        plan: PrerequisitePlan,
        policy: PrerequisitePolicy,
        inspection: PrerequisiteInspection,
    ) -> RemediationResult:
        """Perform only allowlisted actions when policy is remediate."""
        ...

    def verify(self, inspection: PrerequisiteInspection) -> VerificationResult:
        """Classify a post-mutation (or no-op) inspection. Must not mutate."""
        ...
