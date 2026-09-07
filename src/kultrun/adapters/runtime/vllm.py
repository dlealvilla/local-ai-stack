"""Replaceable vLLM adapter. Isolated from the Kultrun core environment."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from kultrun.host.contracts import AcceleratorVendor, HostCapabilities
from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
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

IDENTITY = Name("vllm")
FAMILY = Name("vllm")
EXECUTOR = Name("native-process")
PINNED_VERSION = "0.10.2"


class VllmInferenceRuntime:
    """Translates a launch request into vLLM argv. Does not exec."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def profile(self) -> RuntimeProfile:
        return RuntimeProfile(
            runtime=self.identity,
            display_name="vLLM",
            executor_kind=EXECUTOR,
            capabilities=("openai-compatible", "generation"),
            required_components=(Name("vllm"),),
        )

    def launch_spec(
        self, request: RuntimeLaunchRequest | None = None
    ) -> RuntimeLaunchSpec:
        del request
        return RuntimeLaunchSpec(
            runtime=self.identity,
            profile=self.identity,
            executable="vllm",
            arguments=("serve", "--help"),
            environment=(),
        )


class VllmProvisioner:
    """Install pinned vLLM into a Kultrun-managed virtualenv."""

    def __init__(self, state_root: Path, clock: Clock | None = None) -> None:
        self._root = Path(state_root)
        self._clock = clock or SystemClock()

    @property
    def identity(self) -> Name:
        return IDENTITY

    def supports(self, plan: RuntimeProvisioningPlan) -> bool:
        return plan.runtime_provider == IDENTITY

    def provision(self, plan: RuntimeProvisioningPlan) -> RuntimeInstallation:
        location = self._root / "runtimes" / "vllm" / PINNED_VERSION
        location.mkdir(parents=True, exist_ok=True)
        python = location / "bin" / "python"
        try:
            if not python.exists():
                subprocess.run(
                    [sys.executable, "-m", "venv", str(location)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            subprocess.run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "--disable-pip-version-check",
                    f"vllm=={PINNED_VERSION}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError):
            return RuntimeInstallation(
                installation_id=RuntimeInstallationId.generate(),
                runtime_provider=IDENTITY,
                runtime_family=FAMILY,
                runtime_version=PINNED_VERSION,
                executor_kind=plan.executor_kind,
                host_id=plan.host_id,
                status=InstallationStatus.FAILED,
                location=str(location),
                provenance=("isolated-venv",),
                failure_reason="runtime_provision_failed",
                provisioning_plan_id=plan.plan_id.value,
            )
        return RuntimeInstallation(
            installation_id=RuntimeInstallationId.generate(),
            runtime_provider=IDENTITY,
            runtime_family=FAMILY,
            runtime_version=PINNED_VERSION,
            executor_kind=plan.executor_kind,
            host_id=plan.host_id,
            status=InstallationStatus.INSTALLED,
            location=str(location),
            installed_at=self._clock.now().isoformat(),
            provenance=("isolated-venv", f"vllm=={PINNED_VERSION}"),
            provisioning_plan_id=plan.plan_id.value,
        )


class VllmVerifier:
    """Import and accelerator visibility in the isolated environment."""

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
        if installation.status is not InstallationStatus.INSTALLED:
            return _failed(installation, host, fingerprint, "runtime_not_installed")
        python = Path(str(installation.location)) / "bin" / "python"
        try:
            result = subprocess.run(
                [
                    str(python),
                    "-c",
                    "import vllm; print(vllm.__version__)",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            version = result.stdout.strip() or installation.runtime_version
        except (OSError, subprocess.CalledProcessError):
            return _failed(
                installation, host, fingerprint, "runtime_import_failed"
            )
        if not nvidia:
            return _failed(
                installation, host, fingerprint, "expected_accelerator_not_visible"
            )
        return RuntimeCapabilityProfile(
            profile_id=CapabilityProfileId.generate(),
            installation_id=installation.installation_id,
            runtime_provider=IDENTITY,
            runtime_family=FAMILY,
            runtime_version=version,
            executor_kind=installation.executor_kind,
            host_id=installation.host_id,
            host_fingerprint=host.fingerprint,
            status=VerificationStatus.VERIFIED,
            support_tier=SupportTier.PRODUCT,
            verified_at=installation.installed_at,
            verification_method="isolated-import+accelerator-visibility",
            verification_confidence="medium",
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
            verified_accelerator_access=True,
            verified_engine_initialization=False,
            verified_readiness=False,
            known_limitations=(
                "engine initialization and tiny-model readiness are T5 evidence",
            ),
            evidence=("import vllm succeeded", f"version {version}"),
            capability_schema_version=f"vllm-support:{PINNED_VERSION}",
        )


def _failed(
    installation: RuntimeInstallation,
    host: HostCapabilities,
    fingerprint: str,
    reason: str,
) -> RuntimeCapabilityProfile:
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
        support_tier=SupportTier.PRODUCT,
        verification_method="isolated-import+accelerator-visibility",
        verification_fingerprint=fingerprint,
        supported_architectures=(),
        failure_reason=reason,
        evidence=(reason,),
    )
