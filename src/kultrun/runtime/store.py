"""Persist runtime installations and capability profiles."""

from __future__ import annotations

from dataclasses import replace

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.persistence import Store
from kultrun.runtime.contracts import (
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    VerificationStatus,
)
from kultrun.runtime.fingerprint import verification_fingerprint


class RuntimeEvidenceStore:
    """Installations and profiles, independent of model artifacts."""

    def __init__(self, store: Store) -> None:
        self._store = store

    def put_installation(self, installation: RuntimeInstallation) -> None:
        self._store.put(installation.installation_id.value, installation)

    def get_installation(
        self, installation_id: str
    ) -> RuntimeInstallation | None:
        return self._store.get(RuntimeInstallation, installation_id)

    def installations(self) -> tuple[RuntimeInstallation, ...]:
        return tuple(self._store.records(RuntimeInstallation))

    def put_profile(self, profile: RuntimeCapabilityProfile) -> None:
        self._store.put(profile.profile_id.value, profile)

    def get_profile(self, profile_id: str) -> RuntimeCapabilityProfile | None:
        return self._store.get(RuntimeCapabilityProfile, profile_id)

    def profiles(self) -> tuple[RuntimeCapabilityProfile, ...]:
        return tuple(self._store.records(RuntimeCapabilityProfile))

    def latest_for_installation(
        self, installation_id: str
    ) -> RuntimeCapabilityProfile | None:
        matches = [
            item
            for item in self.profiles()
            if item.installation_id.value == installation_id
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: item.verified_at or "")

    def refresh_staleness(
        self, host: HostCapabilities
    ) -> tuple[RuntimeCapabilityProfile, ...]:
        """Mark profiles STALE when verification identity changed."""
        updated: list[RuntimeCapabilityProfile] = []
        for profile in self.profiles():
            installation = self.get_installation(profile.installation_id.value)
            if installation is None:
                stale = replace(
                    profile,
                    status=VerificationStatus.STALE,
                    failure_reason="runtime_installation_missing",
                )
                self.put_profile(stale)
                updated.append(stale)
                continue
            current = verification_fingerprint(installation, host)
            if (
                profile.status is VerificationStatus.VERIFIED
                and current != profile.verification_fingerprint
            ):
                stale = replace(
                    profile,
                    status=VerificationStatus.STALE,
                    failure_reason="runtime_environment_changed",
                )
                self.put_profile(stale)
                updated.append(stale)
                continue
            updated.append(profile)
        return tuple(updated)

    def verified_executable(
        self, host: HostCapabilities
    ) -> tuple[RuntimeCapabilityProfile, ...]:
        """Profiles that may authorize executable-model selection."""
        self.refresh_staleness(host)
        return tuple(
            item
            for item in self.profiles()
            if item.status is VerificationStatus.VERIFIED
            and item.support_tier.value in {"product", "fixture"}
        )
