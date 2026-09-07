"""Fixture vLLM path. Architecture and T2 evidence; not a production runtime."""

from __future__ import annotations

from pathlib import Path

from kultrun.adapters.runtime.serving import ReferenceServingRuntime
from kultrun.host.contracts import AcceleratorVendor, HostCapabilities
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.runtime.contracts import (
    CapabilityProfileId,
    InstallationStatus,
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimeInstallationId,
    RuntimeLaunchRequest,
    RuntimeLaunchSpec,
    RuntimeProfile,
    RuntimeProvisioningPlan,
    SupportTier,
    VerificationStatus,
)
from kultrun.runtime.fingerprint import verification_fingerprint

IDENTITY = Name("fixture-vllm")
FAMILY = Name("vllm")
EXECUTOR = Name("native-process")
FIXTURE_VERSION = "fixture-1.6.0"
PINNED_SUPPORT = "0.10.2"


class FixtureVllmRuntime:
    """Launch recipe is the reference serving workload. Not real vLLM."""

    def __init__(self) -> None:
        self._serving = ReferenceServingRuntime()

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="Fixture vLLM (architecture / T2)",
            executor_kind=EXECUTOR,
            capabilities=("fixture", "loopback-health", "readiness"),
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        inner = self._serving.launch_spec(request)
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable=inner.executable,
            arguments=inner.arguments,
            environment=inner.environment,
            working_directory=inner.working_directory,
            output_limit_bytes=inner.output_limit_bytes,
            grace_period_seconds=inner.grace_period_seconds,
            device_indexes=inner.device_indexes,
        )


class FixtureVllmProvisioner:
    """Writes a marker directory. Does not install vLLM."""

    def __init__(self, state_root: Path, clock: Clock | None = None) -> None:
        self._root = Path(state_root)
        self._clock = clock or SystemClock()

    @property
    def identity(self) -> Name:
        return IDENTITY

    def supports(self, plan: RuntimeProvisioningPlan) -> bool:
        return plan.runtime_provider == IDENTITY

    def provision(self, plan: RuntimeProvisioningPlan) -> RuntimeInstallation:
        location = self._root / "runtimes" / "fixture-vllm" / FIXTURE_VERSION
        location.mkdir(parents=True, exist_ok=True)
        marker = location / "INSTALLED"
        marker.write_text(FIXTURE_VERSION, encoding="utf-8")
        return RuntimeInstallation(
            installation_id=RuntimeInstallationId.generate(),
            runtime_provider=IDENTITY,
            runtime_family=FAMILY,
            runtime_version=FIXTURE_VERSION,
            executor_kind=plan.executor_kind,
            host_id=plan.host_id,
            status=InstallationStatus.INSTALLED,
            location=str(location),
            installed_at=self._clock.now().isoformat(),
            provenance=("fixture-marker", f"support-table:{PINNED_SUPPORT}"),
            provisioning_plan_id=plan.plan_id.value,
        )


class FixtureVllmVerifier:
    """Operational proof for the fixture path. Support metadata is versioned."""

    def __init__(self, *, succeed: bool = True) -> None:
        self._succeed = succeed

    @property
    def identity(self) -> Name:
        return IDENTITY

    def verify(
        self, installation: RuntimeInstallation, host: HostCapabilities
    ) -> RuntimeCapabilityProfile:
        fingerprint = verification_fingerprint(installation, host)
        nvidia = tuple(
            item.index
            for item in host.accelerators
            if item.vendor is AcceleratorVendor.NVIDIA
        )
        if installation.status is not InstallationStatus.INSTALLED or not self._succeed:
            return RuntimeCapabilityProfile(
                profile_id=CapabilityProfileId.generate(),
                installation_id=installation.installation_id,
                runtime_provider=IDENTITY,
                runtime_family=FAMILY,
                runtime_version=installation.runtime_version,
                executor_kind=installation.executor_kind,
                host_id=installation.host_id,
                host_fingerprint=host.fingerprint,
                status=VerificationStatus.FAILED,
                support_tier=SupportTier.FIXTURE,
                verification_method="fixture-marker",
                verification_fingerprint=fingerprint,
                supported_architectures=(),
                failure_reason="runtime_verification_failed",
                evidence=("fixture verification did not succeed",),
            )
        return RuntimeCapabilityProfile(
            profile_id=CapabilityProfileId.generate(),
            installation_id=installation.installation_id,
            runtime_provider=IDENTITY,
            runtime_family=FAMILY,
            runtime_version=installation.runtime_version,
            executor_kind=installation.executor_kind,
            host_id=installation.host_id,
            host_fingerprint=host.fingerprint,
            status=VerificationStatus.VERIFIED,
            support_tier=SupportTier.FIXTURE,
            verified_at=installation.installed_at
            if installation.installed_at is not NOT_PROVIDED
            else NOT_PROVIDED,
            verification_method="fixture-marker+support-table",
            verification_confidence="high",
            verification_fingerprint=fingerprint,
            supported_architectures=(
                "llama",
                "qwen",
                "qwen2",
                "qwen2.5",
                "mistral",
                "phi",
                "gemma",
            ),
            supported_formats=("safetensors",),
            supported_quantizations=("awq", "fp16", "f16", "bf16", "gptq-int4"),
            supported_modalities=("text",),
            supported_accelerator_types=("nvidia",),
            usable_devices=nvidia,
            verified_accelerator_access=bool(nvidia),
            verified_engine_initialization=True,
            verified_readiness=True,
            known_limitations=(
                "fixture path; not production vLLM",
                "support metadata is versioned, not inferred from one workload",
            ),
            evidence=(
                "installation marker present",
                "validation workload=fixture-ok",
            ),
            capability_schema_version=f"vllm-support:{PINNED_SUPPORT}",
        )
