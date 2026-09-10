"""Persist plans and installations. Orchestrates staging and promotion.

Does not import execution, model, resource, inference, or adapters.
Does not verify a runtime engine or import vLLM.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.runtime.contracts import (
    CompatibilityClass,
    InstallationStatus,
    RuntimeCandidate,
    RuntimeInstallation,
    RuntimeInstallationId,
    RuntimePolicy,
    RuntimeProvisioningPlan,
    RuntimeProvisioningPlanId,
    RuntimeSupportDescriptor,
)
from kultrun.runtime.lock import ProvisioningLock
from kultrun.runtime.plan import (
    build_plan,
    find_candidate,
    fingerprint_installation_id,
    is_provisionable,
)
from kultrun.runtime.ports import RuntimeProvisioner
from kultrun.runtime.python import locate_python
from kultrun.runtime.resolve import ExecutorCapabilityView, resolve

REPORT_NAME = "installer-report.json"
METADATA_NAME = "installation-metadata.json"


class ProvisioningService:
    """Candidate → plan → installation. INSTALLED is not VERIFIED."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        provisioner: RuntimeProvisioner,
        state_root: Path,
        lock: ProvisioningLock,
    ) -> None:
        self._store = store
        self._clock = clock
        self._provisioner = provisioner
        self._state_root = Path(state_root).resolve()
        self._lock = lock
        self._runtimes = self._state_root / "runtimes"

    def reconcile(self) -> None:
        """An interrupted INSTALLING record is never a success."""
        with self._lock.hold():
            for item in self._store.records(RuntimeInstallation):
                if item.status is InstallationStatus.INSTALLING:
                    failed = replace(
                        item,
                        status=InstallationStatus.FAILED,
                        completed_at=self._clock.now(),
                        last_failure_code="interrupted",
                        last_failure_message=(
                            "provisioning was interrupted; not installed"
                        ),
                    )
                    self._store.put(failed.installation_id.value, failed)
                    self._cleanup_staging_for(item.installation_id, item.attempt_count)

    def plans(self) -> tuple[RuntimeProvisioningPlan, ...]:
        return self._store.records(RuntimeProvisioningPlan)

    def installations(self) -> tuple[RuntimeInstallation, ...]:
        return self._store.records(RuntimeInstallation)

    def get_plan(self, plan_id: RuntimeProvisioningPlanId) -> RuntimeProvisioningPlan:
        record = self._store.get(RuntimeProvisioningPlan, plan_id.value)
        if record is None:
            raise NotFoundError("no such provisioning plan", plan_id=plan_id.value)
        return record

    def get_installation(
        self, installation_id: RuntimeInstallationId
    ) -> RuntimeInstallation:
        record = self._store.get(RuntimeInstallation, installation_id.value)
        if record is None:
            raise NotFoundError(
                "no such runtime installation",
                installation_id=installation_id.value,
            )
        return record

    def create_plan(
        self,
        candidate_id: str,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        policy: RuntimePolicy,
        *,
        components: Mapping[str, str] | None = None,
    ) -> RuntimeProvisioningPlan:
        """Persist an exact install plan. Does not mutate the host Python."""
        with self._lock.hold():
            candidate = self._require_provisionable(
                candidate_id, host, executors, descriptors, components
            )
            python = self._python_or_fail()
            plan = build_plan(
                candidate,
                host,
                mechanism=self._provisioner.installer_mechanism,
                python_executable=python,
                created_at=self._clock.now(),
            )
            existing = self._store.get(RuntimeProvisioningPlan, plan.plan_id.value)
            if existing is not None:
                return existing
            self._store.put(plan.plan_id.value, plan)
            return plan

    def provision(
        self,
        plan_id: RuntimeProvisioningPlanId,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        *,
        components: Mapping[str, str] | None = None,
        retry: bool = False,
        policy: RuntimePolicy | None = None,
    ) -> RuntimeInstallation:
        """Install the plan into an isolated environment. Not verification."""
        with self._lock.hold():
            plan = self.get_plan(plan_id)
            self._assert_fresh(
                plan,
                host,
                executors,
                descriptors,
                components,
                policy or RuntimePolicy(),
            )
            python = self._python_or_fail()
            installation_id = fingerprint_installation_id(plan.plan_id.value)
            existing = self._store.get(RuntimeInstallation, installation_id.value)
            if existing is not None:
                if (
                    existing.status is InstallationStatus.INSTALLED
                    and existing.plan_id == plan.plan_id
                ):
                    return existing
                if existing.status is InstallationStatus.INSTALLING:
                    raise ConflictError(
                        "this plan is already provisioning",
                        installation_id=installation_id.value,
                    )
                if existing.status is InstallationStatus.FAILED and not retry:
                    return existing
            now = self._clock.now()
            attempt = 1 if existing is None else existing.attempt_count + 1
            record = RuntimeInstallation(
                installation_id=installation_id,
                plan_id=plan.plan_id,
                candidate_id=plan.candidate_id,
                runtime=plan.runtime,
                runtime_family=plan.runtime_family,
                runtime_provider=plan.runtime_provider,
                runtime_version=plan.runtime_version,
                executor=plan.executor,
                host_id=plan.host_id,
                host_fingerprint=plan.host_fingerprint,
                status=InstallationStatus.INSTALLING,
                installation_root=plan.installation_root,
                installer=plan.installer,
                package_source=plan.components[0].source if plan.components else "pypi",
                created_at=existing.created_at if existing is not None else now,
                started_at=now,
                attempt_count=attempt,
            )
            self._store.put(record.installation_id.value, record)
            staging = self._staging_dir(installation_id, attempt)
            final = self._final_dir(plan)
            try:
                self._prepare_staging(staging)
                outcome = self._provisioner.install(
                    plan, staging, python_executable=python
                )
                if not outcome.succeeded:
                    return self._fail(
                        record,
                        staging,
                        code=outcome.failure_code or "installer_failed",
                        message=outcome.failure_message or "installer failed",
                    )
                if outcome.resolved_runtime_version != plan.runtime_version:
                    return self._fail(
                        record,
                        staging,
                        code="version_mismatch",
                        message=(
                            "installed package metadata "
                            f"{outcome.resolved_runtime_version!r} != "
                            f"{plan.runtime_version!r}"
                        ),
                    )
                report_path, report_sha = self._capture_report(staging, plan)
                self._write_metadata(staging, record)
                self._promote(staging, final)
            except (OSError, TimeoutError) as error:
                from kultrun.storage.failures import classify_oserror

                classified = classify_oserror(error)
                return self._fail(
                    record,
                    staging,
                    code=classified.value,
                    message=str(error),
                )
            python_executable = _relocated_after_promote(
                outcome.python_executable, staging, final
            )
            installer_version = _relocated_after_promote(
                outcome.installer_version, staging, final
            )
            finished = replace(
                record,
                status=InstallationStatus.INSTALLED,
                python_executable=python_executable or NOT_PROVIDED,
                python_version=outcome.python_version or NOT_PROVIDED,
                installer_version=installer_version or NOT_PROVIDED,
                provenance_manifest_path=report_path or NOT_PROVIDED,
                provenance_manifest_sha256=report_sha or NOT_PROVIDED,
                resolved_runtime_version=(
                    outcome.resolved_runtime_version or NOT_PROVIDED
                ),
                completed_at=self._clock.now(),
                last_failure_code=NOT_PROVIDED,
                last_failure_message=NOT_PROVIDED,
            )
            self._store.put(finished.installation_id.value, finished)
            return finished

    def _require_provisionable(
        self,
        candidate_id: str,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        components: Mapping[str, str] | None,
    ) -> RuntimeCandidate:
        resolution = resolve(
            host, executors, descriptors, RuntimePolicy(), components=components
        )
        candidate = find_candidate(resolution, candidate_id)
        if candidate is None:
            raise NotFoundError("no such runtime candidate", candidate_id=candidate_id)
        if candidate.compatibility is CompatibilityClass.UNSUPPORTED:
            raise PreconditionFailedError(
                "unsupported runtime candidate cannot be planned",
                candidate_id=candidate_id,
            )
        if candidate.compatibility is CompatibilityClass.UNRESOLVED:
            raise PreconditionFailedError(
                "unresolved runtime candidate cannot be planned",
                candidate_id=candidate_id,
            )
        if not is_provisionable(candidate):
            raise PreconditionFailedError(
                "runtime candidate is not provisionable",
                candidate_id=candidate_id,
                compatibility=candidate.compatibility.value,
            )
        return candidate

    def _assert_fresh(
        self,
        plan: RuntimeProvisioningPlan,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        descriptors: Sequence[RuntimeSupportDescriptor],
        components: Mapping[str, str] | None,
        policy: RuntimePolicy,
    ) -> None:
        fingerprint = host.fingerprint
        if fingerprint != plan.host_fingerprint:
            raise PreconditionFailedError(
                "host fingerprint no longer matches this plan",
                plan_id=plan.plan_id.value,
            )
        if host.host_id != plan.host_id:
            raise PreconditionFailedError(
                "host identity no longer matches this plan",
                plan_id=plan.plan_id.value,
            )
        if not _executor_available(executors, plan.executor.value):
            raise PreconditionFailedError(
                "executor is no longer available",
                executor=plan.executor.value,
            )
        resolution = resolve(
            host, executors, descriptors, policy, components=components
        )
        current = find_candidate(resolution, plan.candidate_id.value)
        if current is None:
            raise PreconditionFailedError(
                "runtime candidate no longer resolves",
                candidate_id=plan.candidate_id.value,
            )
        if current.compatibility in {
            CompatibilityClass.UNSUPPORTED,
            CompatibilityClass.UNRESOLVED,
        }:
            raise PreconditionFailedError(
                "runtime candidate is no longer provisionable",
                compatibility=current.compatibility.value,
            )
        if not is_provisionable(current):
            raise PreconditionFailedError(
                "runtime candidate is no longer provisionable",
                candidate_id=plan.candidate_id.value,
            )
        version = current.version if isinstance(current.version, str) else ""
        if version != plan.runtime_version:
            raise PreconditionFailedError(
                "planned version no longer matches resolved candidate",
                planned=plan.runtime_version,
                resolved=version or "unresolved",
            )

    def _python_or_fail(self) -> str | None:
        if not self._provisioner.requires_host_python:
            return None
        found = locate_python()
        if found is None:
            raise PreconditionFailedError(
                "python 3.12 is not available; Kultrun will not install Python",
                python_version="3.12",
            )
        return found

    def _staging_dir(
        self, installation_id: RuntimeInstallationId, attempt: int
    ) -> Path:
        return self._runtimes / ".staging" / f"{installation_id.value}-{attempt}"

    def _final_dir(self, plan: RuntimeProvisioningPlan) -> Path:
        return self._state_root / plan.installation_root

    def _prepare_staging(self, staging: Path) -> None:
        if staging.exists():
            self._cleanup(staging)
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "manifest").mkdir(exist_ok=True)

    def _promote(self, staging: Path, final: Path) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            self._cleanup(final)
        staging.replace(final)

    def _capture_report(
        self, staging: Path, plan: RuntimeProvisioningPlan
    ) -> tuple[str | None, str | None]:
        report = staging / "manifest" / REPORT_NAME
        if not report.is_file():
            return None, None
        digest = hashlib.sha256(report.read_bytes()).hexdigest()
        relative = f"{plan.installation_root}/manifest/{REPORT_NAME}"
        return relative, digest

    def _write_metadata(self, staging: Path, record: RuntimeInstallation) -> None:
        payload = {
            "installation_id": record.installation_id.value,
            "plan_id": record.plan_id.value,
            "runtime": record.runtime.value,
            "runtime_version": record.runtime_version,
            "verified": False,
        }
        (staging / METADATA_NAME).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )

    def _fail(
        self,
        record: RuntimeInstallation,
        staging: Path,
        *,
        code: str,
        message: str,
    ) -> RuntimeInstallation:
        self._cleanup(staging)
        failed = replace(
            record,
            status=InstallationStatus.FAILED,
            completed_at=self._clock.now(),
            last_failure_code=code,
            last_failure_message=message,
        )
        self._store.put(failed.installation_id.value, failed)
        return failed

    def _cleanup_staging_for(
        self, installation_id: RuntimeInstallationId, attempt: int
    ) -> None:
        self._cleanup(self._staging_dir(installation_id, attempt))

    def _cleanup(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            path.resolve().relative_to(self._runtimes.resolve())
        except ValueError as error:
            raise ValidationError(
                "refusing to delete a path outside the runtimes root",
                path=str(path),
            ) from error
        shutil.rmtree(path, ignore_errors=True)


def _relocated_after_promote(
    value: str | None, staging: Path, final: Path
) -> str | None:
    """Rewrite staging paths onto the promoted installation root.

    The provisioner runs against the staging directory. After atomic
    promotion the staging path no longer exists; the receipt must name
    the surviving interpreter, not the deleted one.
    """
    if value is None:
        return None
    prefix = str(staging)
    if value == prefix or value.startswith(prefix + "/"):
        return str(final) + value[len(prefix) :]
    return value.replace(prefix, str(final))


def _executor_available(executors: Sequence[ExecutorCapabilityView], name: str) -> bool:
    for profile in executors:
        if profile.executor.value == name:
            token = getattr(profile.availability, "value", profile.availability)
            return str(token).strip().lower() == "available"
    return False
