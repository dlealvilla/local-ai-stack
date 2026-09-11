"""Build an exact RuntimeProvisioningPlan from a current RuntimeCandidate.

Does not install. Does not verify. Does not import execution or adapters.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.errors import PreconditionFailedError
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.runtime.contracts import (
    CompatibilityClass,
    ProvisioningComponent,
    ResolutionReasonCode,
    RuntimeCandidate,
    RuntimeCandidateId,
    RuntimeInstallationId,
    RuntimeProvisioningPlan,
    RuntimeProvisioningPlanId,
    RuntimeResolution,
    RuntimeSupportTier,
)
from kultrun.runtime.pins import (
    NATIVE_EXECUTOR,
    PIP_INSTALLER,
    PLAN_SCHEMA,
    PYPI_SOURCE,
    PYTHON_VERSION,
    TARGET_SEMANTICS,
    VLLM_PACKAGE,
    VLLM_VERSION,
)
from kultrun.storage.footprint import runtime_provisioning_requirement

_SOLVABLE = {
    ResolutionReasonCode.REQUIRED_COMPONENT_MISSING,
}

_SOLVABLE_MISSING = {VLLM_PACKAGE}


def is_provisionable(candidate: RuntimeCandidate) -> bool:
    """True when 1.6C can install this path. Unsupported/unresolved never are.

    FUTURE families are declared, not installable. A name in the catalogue
    is not production feasibility.
    """
    if candidate.support_tier is RuntimeSupportTier.FUTURE:
        return False
    if candidate.compatibility in {
        CompatibilityClass.UNSUPPORTED,
        CompatibilityClass.UNRESOLVED,
    }:
        return False
    if candidate.executor.value != NATIVE_EXECUTOR:
        return False
    leftover = set(candidate.reason_codes) - _SOLVABLE
    if leftover:
        return False
    leftover_missing = [
        item
        for item in candidate.missing_prerequisites
        if item not in _SOLVABLE_MISSING
    ]
    return not leftover_missing


def find_candidate(
    resolution: RuntimeResolution, candidate_id: str
) -> RuntimeCandidate | None:
    """Search every classification group. Absence is not a boolean miss."""
    for group in (
        resolution.candidates,
        resolution.unsupported,
        resolution.unresolved,
    ):
        for item in group:
            if item.candidate_id.value == candidate_id:
                return item
    return None


def fingerprint_plan(
    *,
    candidate_id: str,
    runtime: str,
    version: str,
    executor: str,
    host_id: str,
    host_fingerprint: str,
    python_version: str,
    installer: str,
    components: str,
    mechanism: str,
) -> tuple[RuntimeProvisioningPlanId, str]:
    """Stable plan id and full fingerprint for the same intended install."""
    material = "|".join(
        (
            PLAN_SCHEMA,
            candidate_id,
            runtime,
            version,
            executor,
            host_id,
            host_fingerprint,
            python_version,
            installer,
            mechanism,
            components,
            TARGET_SEMANTICS.format(runtime=runtime, version=version),
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return RuntimeProvisioningPlanId(f"rplan_{digest[:16]}"), digest


def fingerprint_installation_id(plan_id: str) -> RuntimeInstallationId:
    """One installation identity per plan. Retry reuses it."""
    digest = hashlib.sha256(f"runtime.installation@1|{plan_id}".encode()).hexdigest()
    return RuntimeInstallationId(f"rinst_{digest[:16]}")


def build_plan(
    candidate: RuntimeCandidate,
    host: HostCapabilities,
    *,
    mechanism: str,
    python_executable: str | None,
    created_at: dt.datetime,
    destination_mount: Maybe[str] = NOT_PROVIDED,
) -> RuntimeProvisioningPlan:
    """Exact intended install. Refuses unsupported and unverified claims."""
    if not is_provisionable(candidate):
        raise PreconditionFailedError(
            "runtime candidate is not provisionable",
            candidate_id=candidate.candidate_id.value,
            compatibility=candidate.compatibility.value,
            reason_codes=tuple(code.value for code in candidate.reason_codes),
        )
    if candidate.runtime.value != VLLM_PACKAGE:
        raise PreconditionFailedError(
            "only vLLM native provisioning is implemented",
            runtime=candidate.runtime.value,
        )
    version = candidate.version if isinstance(candidate.version, str) else ""
    if version != VLLM_VERSION:
        raise PreconditionFailedError(
            "candidate version is not the Stage 1.6C pin",
            expected=VLLM_VERSION,
            got=version or "unresolved",
        )
    fingerprint = host.fingerprint if is_resolved(host.fingerprint) else ""
    if not fingerprint:
        raise PreconditionFailedError("host fingerprint is unresolved")
    if fingerprint != (
        candidate.host_fingerprint
        if isinstance(candidate.host_fingerprint, str)
        else ""
    ):
        raise PreconditionFailedError(
            "candidate host fingerprint does not match current host"
        )
    component = ProvisioningComponent(
        category="python-package",
        name=Name(VLLM_PACKAGE),
        version=VLLM_VERSION,
        source=PYPI_SOURCE,
        installer=PIP_INSTALLER,
    )
    plan_id, digest = fingerprint_plan(
        candidate_id=candidate.candidate_id.value,
        runtime=candidate.runtime.value,
        version=version,
        executor=candidate.executor.value,
        host_id=host.host_id.value,
        host_fingerprint=fingerprint,
        python_version=PYTHON_VERSION,
        installer=PIP_INSTALLER,
        components=f"{VLLM_PACKAGE}=={VLLM_VERSION}",
        mechanism=mechanism,
    )
    installation_id = fingerprint_installation_id(plan_id.value)
    root = f"runtimes/{candidate.runtime.value}/{version}/{installation_id.value}"
    mount: Maybe[str] = (
        destination_mount if isinstance(destination_mount, str) else NOT_PROVIDED
    )
    requirement = runtime_provisioning_requirement(mount_point=mount)
    return RuntimeProvisioningPlan(
        plan_id=plan_id,
        candidate_id=RuntimeCandidateId.parse(candidate.candidate_id.value),
        runtime=candidate.runtime,
        runtime_family=candidate.runtime_family,
        runtime_provider=candidate.runtime_provider,
        runtime_version=version,
        executor=candidate.executor,
        host_id=host.host_id,
        host_fingerprint=fingerprint,
        python_version=PYTHON_VERSION,
        python_executable=python_executable or NOT_PROVIDED,
        installation_root=root,
        installer=PIP_INSTALLER,
        installer_mechanism=mechanism,
        components=(component,),
        required_prerequisites=(f"python{PYTHON_VERSION}", NATIVE_EXECUTOR),
        unresolved_prerequisites=(),
        created_at=created_at,
        plan_fingerprint=digest,
        provenance=(
            f"candidate={candidate.candidate_id.value}",
            f"schema={PLAN_SCHEMA}",
            f"pin={VLLM_PACKAGE}=={VLLM_VERSION}",
        ),
        storage_mount=requirement.mount_point,
        persistent_bytes=requirement.persistent_bytes,
        peak_transient_bytes=requirement.peak_transient_bytes,
        cache_bytes=requirement.cache_bytes,
        required_peak_free_bytes=requirement.required_peak_free_bytes,
    )
