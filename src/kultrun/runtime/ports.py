"""The runtime seam.

Named `InferenceRuntime` in `docs/ARCHITECTURE.md`. Stage 1.3 implements
the port with a reference process adapter that is not an LLM runtime.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeProvisioningPlan,
)


@runtime_checkable
class InferenceRuntime(Protocol):
    """Translates a profile into a structured launch recipe."""

    @property
    def identity(self) -> Name:
        """Stable runtime name."""
        ...

    def profile(self) -> RuntimeProfile:
        """What this adapter can do."""
        ...

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        """Produce the recipe. Must not start a process."""
        ...


@runtime_checkable
class RuntimeProvisioner(Protocol):
    """Places a runtime environment. Does not verify it."""

    @property
    def identity(self) -> Name:
        """Adapter identity this provisioner installs."""
        ...

    def supports(self, plan: RuntimeProvisioningPlan) -> bool:
        """Whether this provisioner can execute the plan."""
        ...

    def provision(self, plan: RuntimeProvisioningPlan) -> RuntimeInstallation:
        """Install or reuse. Status INSTALLED is not VERIFIED."""
        ...


@runtime_checkable
class RuntimeVerifier(Protocol):
    """Proves an installation is operational. Does not select models."""

    @property
    def identity(self) -> Name:
        """Adapter identity this verifier understands."""
        ...

    def verify(
        self, installation: RuntimeInstallation, host: HostCapabilities
    ) -> RuntimeCapabilityProfile:
        """Produce a capability profile. May be FAILED."""
        ...
