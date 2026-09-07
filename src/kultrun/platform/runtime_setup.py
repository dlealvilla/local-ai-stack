"""Host-driven runtime planning, provision and verification."""

from __future__ import annotations

from collections.abc import Sequence

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.errors import NotFoundError, PreconditionFailedError
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import (
    CompatibilityClass,
    ProvisioningPlanId,
    RuntimeCandidate,
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimePolicy,
    RuntimeProvisioningPlan,
    SupportTier,
    VerificationStatus,
)
from kultrun.runtime.ports import RuntimeProvisioner, RuntimeVerifier
from kultrun.runtime.resolver import RuntimeResolver
from kultrun.runtime.store import RuntimeEvidenceStore


class RuntimeSetupService:
    """Phase 1: choose and prove an execution environment. No model."""

    def __init__(
        self,
        resolver: RuntimeResolver,
        evidence: RuntimeEvidenceStore,
        provisioners: Sequence[RuntimeProvisioner],
        verifiers: Sequence[RuntimeVerifier],
    ) -> None:
        self._resolver = resolver
        self._evidence = evidence
        self._provisioners = {item.identity: item for item in provisioners}
        self._verifiers = {item.identity: item for item in verifiers}

    @property
    def evidence(self) -> RuntimeEvidenceStore:
        return self._evidence

    def candidates(
        self, host: HostCapabilities, policy: RuntimePolicy | None = None
    ) -> tuple[RuntimeCandidate, ...]:
        return self._resolver.candidates(host, policy)

    def select(
        self, host: HostCapabilities, policy: RuntimePolicy | None = None
    ) -> RuntimeCandidate:
        chosen = self._resolver.select(host, policy)
        if chosen is None:
            requested = policy.requested_runtime if policy is not None else None
            if requested is not None and is_resolved(requested):
                raise PreconditionFailedError(
                    "requested runtime is not a compatible path on this host",
                    reason="runtime_incompatible",
                    runtime=str(requested),
                )
            raise PreconditionFailedError(
                "no compatible runtime path is available",
                reason="no_runtime_candidate",
            )
        return chosen

    def plan_for(self, candidate: RuntimeCandidate) -> RuntimeProvisioningPlan:
        if candidate.compatibility is not CompatibilityClass.COMPATIBLE:
            raise PreconditionFailedError(
                "cannot provision an incompatible runtime candidate",
                reason="runtime_incompatible",
                runtime=candidate.runtime_provider.value,
            )
        version = (
            "fixture-1.6.0"
            if candidate.support_tier is SupportTier.FIXTURE
            else "0.10.2"
        )
        strategy = (
            "fixture-marker"
            if candidate.support_tier is SupportTier.FIXTURE
            else "isolated-venv"
        )
        return RuntimeProvisioningPlan(
            plan_id=ProvisioningPlanId.generate(),
            candidate_id=candidate.candidate_id,
            runtime_provider=candidate.runtime_provider,
            runtime_family=candidate.runtime_family,
            intended_version=version,
            executor_kind=candidate.executor_kind,
            host_id=candidate.host_id,
            required_components=candidate.required_components,
            installation_strategy=strategy,
            expected_backend=candidate.required_backend,
            verification_method=(
                "fixture-marker+support-table"
                if candidate.support_tier is SupportTier.FIXTURE
                else "isolated-import+accelerator-visibility"
            ),
        )

    def provision(self, plan: RuntimeProvisioningPlan) -> RuntimeInstallation:
        provisioner = self._provisioners.get(plan.runtime_provider)
        if provisioner is None:
            raise NotFoundError(
                "no provisioner for this runtime",
                runtime=plan.runtime_provider.value,
            )
        installation = provisioner.provision(plan)
        self._evidence.put_installation(installation)
        return installation

    def verify(
        self, installation_id: str, host: HostCapabilities
    ) -> RuntimeCapabilityProfile:
        installation = self._evidence.get_installation(installation_id)
        if installation is None:
            raise NotFoundError(
                "no such runtime installation", installation_id=installation_id
            )
        verifier = self._verifiers.get(installation.runtime_provider)
        if verifier is None:
            raise NotFoundError(
                "no verifier for this runtime",
                runtime=installation.runtime_provider.value,
            )
        profile = verifier.verify(installation, host)
        self._evidence.put_profile(profile)
        return profile

    def provision_and_verify(
        self, host: HostCapabilities, policy: RuntimePolicy | None = None
    ) -> RuntimeCapabilityProfile:
        candidate = self.select(host, policy)
        plan = self.plan_for(candidate)
        installation = self.provision(plan)
        return self.verify(installation.installation_id.value, host)

    def profiles(self, host: HostCapabilities) -> tuple[RuntimeCapabilityProfile, ...]:
        return self._evidence.refresh_staleness(host)

    def verified(self, host: HostCapabilities) -> tuple[RuntimeCapabilityProfile, ...]:
        return self._evidence.verified_executable(host)

    def require_current_profile(
        self, profile_id: str, host: HostCapabilities
    ) -> RuntimeCapabilityProfile:
        self._evidence.refresh_staleness(host)
        profile = self._evidence.get_profile(profile_id)
        if profile is None:
            raise NotFoundError(
                "no such runtime capability profile", profile_id=profile_id
            )
        if profile.status is not VerificationStatus.VERIFIED:
            raise PreconditionFailedError(
                "runtime capability profile is not currently verified",
                reason="runtime_revalidation_required",
                profile_id=profile_id,
                status=profile.status.value,
            )
        return profile
