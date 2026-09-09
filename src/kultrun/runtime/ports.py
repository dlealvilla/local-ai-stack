"""The runtime seam.

Named `InferenceRuntime` in `docs/ARCHITECTURE.md`. Stage 1.3 implements
the port with a reference process adapter that is not an LLM runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.ids import Name
from kultrun.runtime.contracts import (
    RuntimeInstallation,
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeProvisioningPlan,
    RuntimeReadiness,
    RuntimeSupportDescriptor,
    RuntimeVerificationCheck,
    RuntimeVerificationProbe,
)
from kultrun.runtime.memory import RuntimeExtraResult


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
        expected_served_model: str | None = None,
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


@dataclass(frozen=True, slots=True)
class IntegrityOutcome:
    """Installation-path checks before a probe runs. Not a persisted contract."""

    succeeded: bool
    reason_code: str | None = None
    message: str | None = None
    checks: tuple[RuntimeVerificationCheck, ...] = ()


@dataclass(frozen=True, slots=True)
class ProbeExecutionResult:
    """What the executor-neutral probe runner observed. Data only."""

    timed_out: bool = False
    executor_unavailable: bool = False
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    executed: bool = True


@dataclass(frozen=True, slots=True)
class VerifierOutcome:
    """Interpreted probe evidence. Not a persisted contract."""

    succeeded: bool
    reason_codes: tuple[str, ...] = ()
    message: str | None = None
    checks: tuple[RuntimeVerificationCheck, ...] = ()
    python_version: str | None = None
    runtime_package_version: str | None = None
    backend: str | None = None
    backend_version: str | None = None
    cuda_available: bool | None = None
    cuda_runtime_version: str | None = None
    device_count: int | None = None
    devices: tuple[str, ...] = ()
    accelerator_operation: str | None = None
    evidence_digest: str | None = None
    summary: str = ""
    diagnostic_summary: str = ""
    probe_exit_code: int | None = None


@runtime_checkable
class RuntimeVerifier(Protocol):
    """Interprets runtime verification. Does not exec or provision."""

    @property
    def identity(self) -> Name:
        """Stable verifier name."""
        ...

    @property
    def schema_version(self) -> str:
        """Verifier schema token recorded on the profile."""
        ...

    def inspect_integrity(
        self, installation: RuntimeInstallation, *, state_root: Path
    ) -> IntegrityOutcome:
        """Runtime-specific install checks. Must not start a process."""
        ...

    def probe_spec(self, installation: RuntimeInstallation) -> RuntimeVerificationProbe:
        """Structured probe recipe. Composition copies this into an ExecutorSpec."""
        ...

    def interpret(
        self,
        installation: RuntimeInstallation,
        result: ProbeExecutionResult,
        *,
        host: HostCapabilities,
    ) -> VerifierOutcome:
        """Normalize probe evidence. Must not exec or provision."""
        ...


@runtime_checkable
class VerificationProbeRunner(Protocol):
    """Runs a verification probe. Product implementations live outside runtime."""

    def run(
        self,
        spec: RuntimeVerificationProbe,
        *,
        host_id: HostId,
    ) -> ProbeExecutionResult:
        """Execute one bounded probe. Must not interpret runtime evidence."""
        ...


@dataclass(frozen=True, slots=True)
class InterpretedRuntimeMemory:
    """Adapter-normalized vLLM memory facts. Not a persisted profile."""

    model_load_bytes: int | None
    available_kv_bytes: int | None
    usable: bool
    reason: str | None = None
    extra: RuntimeExtraResult | None = None


@runtime_checkable
class RuntimeMemoryInterpreter(Protocol):
    """Runtime-specific log interpretation. Must not start a process."""

    @property
    def identity(self) -> Name:
        """Stable interpreter identity."""
        ...

    def interpret(
        self,
        *,
        stdout: str,
        stderr: str,
        probe_budget_bytes: int,
    ) -> InterpretedRuntimeMemory:
        """Parse captured output into memory facts. Must not exec."""
        ...
