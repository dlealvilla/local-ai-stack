"""The runtime seam.

Named `InferenceRuntime` in `docs/ARCHITECTURE.md`. Stage 1.3 implements
the port with a reference process adapter that is not an LLM runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeProvisioningPlan,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
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

    def support(self) -> RuntimeSupportDescriptor:
        """Declared static support. Not proof that anything is installed."""
        ...

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        """Produce the recipe. Must not start a process."""
        ...

    def inspect_readiness(
        self,
        *,
        stdout: str,
        stderr: str,
        execution_alive: bool,
        bound_address: str | None = None,
        bound_port: int | None = None,
    ) -> RuntimeReadiness:
        """Runtime-owned READY probe. Must not signal or kill a process."""
        ...


@dataclass(frozen=True, slots=True)
class InstallerOutcome:
    """What a provisioner adapter did in staging. Not a persisted contract."""

    succeeded: bool
    python_executable: str | None = None
    python_version: str | None = None
    installer_version: str | None = None
    resolved_runtime_version: str | None = None
    report_relative_path: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    provenance: tuple[str, ...] = ()


@runtime_checkable
class RuntimeProvisioner(Protocol):
    """Installs an exact plan into a staging directory. Does not verify."""

    @property
    def identity(self) -> Name:
        """Stable provisioner name."""
        ...

    @property
    def installer_mechanism(self) -> str:
        """Isolation strategy recorded on the plan."""
        ...

    @property
    def requires_host_python(self) -> bool:
        """Whether a host Python 3.12 interpreter is a hard prerequisite."""
        ...

    def install(
        self,
        plan: RuntimeProvisioningPlan,
        staging_dir: Path,
        *,
        python_executable: str | None,
    ) -> InstallerOutcome:
        """Write into staging_dir only. Must not promote or verify the engine."""
        ...
