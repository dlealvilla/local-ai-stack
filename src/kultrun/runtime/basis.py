"""Material verification basis. Not host sameness and not capacity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.contracts import (
    RuntimeCapabilityProfileId,
    RuntimeInstallation,
    RuntimeVerificationBasis,
    VerificationStatus,
)
from kultrun.runtime.pins import BASIS_SCHEMA
from kultrun.runtime.resolve import ExecutorCapabilityView


def evidence_digest(payload: str) -> str:
    """SHA-256 of structured probe text."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprint_profile_id(installation_id: str) -> RuntimeCapabilityProfileId:
    """One current profile identity per installation."""
    digest = hashlib.sha256(
        f"runtime.capability_profile@1|{installation_id}".encode()
    ).hexdigest()
    return RuntimeCapabilityProfileId(f"rcap_{digest[:16]}")


def effective_status(
    status: VerificationStatus, stored_fingerprint: str, current_fingerprint: str
) -> VerificationStatus:
    """VERIFIED survives only while the material basis is unchanged."""
    if (
        status is VerificationStatus.VERIFIED
        and stored_fingerprint != current_fingerprint
    ):
        return VerificationStatus.STALE
    return status


def match_executor(
    executors: Sequence[ExecutorCapabilityView], name: str
) -> ExecutorCapabilityView | None:
    """The current capability view for this executor identity, if any."""
    for profile in executors:
        if profile.executor.value == name:
            return profile
    return None


def executor_is_available(
    executors: Sequence[ExecutorCapabilityView], name: str
) -> bool:
    profile = match_executor(executors, name)
    if profile is None:
        return False
    token = getattr(profile.availability, "value", profile.availability)
    return str(token).strip().lower() == "available"


def build_verification_basis(
    installation: RuntimeInstallation,
    host: HostCapabilities,
    executors: Sequence[ExecutorCapabilityView],
) -> RuntimeVerificationBasis:
    """Facts that materially affect confidence in a previous verification."""
    python = (
        installation.python_executable
        if is_resolved(installation.python_executable)
        else ""
    )
    python_version = (
        installation.python_version
        if is_resolved(installation.python_version)
        else ""
    )
    matched = match_executor(executors, installation.executor.value)
    if matched is None:
        executor_type = "unknown"
    else:
        token = getattr(matched.executor_type, "value", matched.executor_type)
        executor_type = str(token)
    available = executor_is_available(executors, installation.executor.value)
    accelerators = tuple(host.accelerators)
    primary = accelerators[0] if accelerators else None
    vendor = primary.vendor.value if primary is not None else "none"
    if primary is not None and is_resolved(primary.model_name):
        model = primary.model_name
    else:
        model = "none"
    driver = "none"
    if primary is not None and is_resolved(primary.driver_version):
        driver = str(primary.driver_version)
    payload = {
        "schema": BASIS_SCHEMA,
        "host_id": host.host_id.value,
        "installation_id": installation.installation_id.value,
        "installation_root": installation.installation_root,
        "runtime": installation.runtime.value,
        "runtime_version": installation.runtime_version,
        "python_executable": python,
        "python_version": python_version,
        "executor": installation.executor.value,
        "executor_type": executor_type,
        "executor_available": available,
        "os_family": host.operating_environment.os_name,
        "architecture": host.operating_environment.architecture.value,
        "accelerators": [
            {
                "index": item.index,
                "vendor": item.vendor.value,
                "model": item.model_name,
                "driver": (
                    str(item.driver_version)
                    if is_resolved(item.driver_version)
                    else "none"
                ),
            }
            for item in accelerators
        ],
        "accelerator_count": len(accelerators),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return RuntimeVerificationBasis(
        host_id=host.host_id,
        installation_id=installation.installation_id,
        installation_root=installation.installation_root,
        runtime=installation.runtime,
        runtime_version=installation.runtime_version,
        python_executable=python,
        python_version=python_version,
        executor=installation.executor,
        executor_type=executor_type,
        executor_available=available,
        os_family=host.operating_environment.os_name,
        architecture=host.operating_environment.architecture.value,
        accelerator_vendor=vendor,
        accelerator_model=model,
        accelerator_count=len(accelerators),
        driver_version=driver,
        fingerprint=digest,
    )
