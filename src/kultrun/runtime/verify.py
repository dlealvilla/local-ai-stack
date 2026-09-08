"""Verify an exact RuntimeInstallation. Does not provision, select, or infer.

Does not import execution, model, resource, inference, or adapters.
Probe execution is injected through VerificationProbeRunner.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import TypeVar

from kultrun.host.contracts import HostCapabilities
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import NotFoundError
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe, is_resolved
from kultrun.runtime.basis import (
    build_verification_basis,
    effective_status,
    executor_is_available,
    fingerprint_profile_id,
)
from kultrun.runtime.contracts import (
    InstallationStatus,
    RuntimeCapabilityProfile,
    RuntimeInstallation,
    RuntimeInstallationId,
    RuntimeVerificationBasis,
    RuntimeVerificationCheck,
    VerificationReasonCode,
    VerificationStatus,
)
from kultrun.runtime.lock import VerificationLock
from kultrun.runtime.ports import (
    IntegrityOutcome,
    ProbeExecutionResult,
    RuntimeVerifier,
    VerificationProbeRunner,
    VerifierOutcome,
)
from kultrun.runtime.resolve import ExecutorCapabilityView

_DIAGNOSTIC_LIMIT = 512
T = TypeVar("T")


class VerificationService:
    """Installation → probe → RuntimeCapabilityProfile. Installed is not verified."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        verifier: RuntimeVerifier,
        runner: VerificationProbeRunner,
        state_root: Path,
        lock: VerificationLock,
    ) -> None:
        self._store = store
        self._clock = clock
        self._verifier = verifier
        self._runner = runner
        self._state_root = Path(state_root).resolve()
        self._lock = lock

    def reconcile(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> None:
        """Re-evaluate stored VERIFIED against the current basis. No probe."""
        with self._lock.hold():
            for item in self._store.records(RuntimeCapabilityProfile):
                installation = self._store.get(
                    RuntimeInstallation, item.installation_id.value
                )
                if installation is None:
                    continue
                current = build_verification_basis(installation, host, executors)
                status = effective_status(
                    item.status,
                    item.verification_basis_fingerprint,
                    current.fingerprint,
                )
                if status is item.status:
                    continue
                self._store.put(
                    item.profile_id.value,
                    replace(
                        item,
                        status=status,
                        reason_codes=(
                            *item.reason_codes,
                            VerificationReasonCode.VERIFICATION_BASIS_CHANGED,
                        )
                        if (
                            status is VerificationStatus.STALE
                            and VerificationReasonCode.VERIFICATION_BASIS_CHANGED
                            not in item.reason_codes
                        )
                        else item.reason_codes,
                    ),
                )

    def profiles(
        self,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> tuple[RuntimeCapabilityProfile, ...]:
        """Current profiles with effective staleness. GET must not probe."""
        refreshed: list[RuntimeCapabilityProfile] = []
        for item in self._store.records(RuntimeCapabilityProfile):
            installation = self._store.get(
                RuntimeInstallation, item.installation_id.value
            )
            if installation is None:
                refreshed.append(item)
                continue
            refreshed.append(self._present(item, installation, host, executors))
        return tuple(refreshed)

    def profile_for(
        self,
        installation_id: RuntimeInstallationId,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> RuntimeCapabilityProfile | None:
        """One profile, or None when the installation has never been verified."""
        profile_id = fingerprint_profile_id(installation_id.value)
        item = self._store.get(RuntimeCapabilityProfile, profile_id.value)
        if item is None:
            return None
        installation = self._store.get(RuntimeInstallation, installation_id.value)
        if installation is None:
            return item
        return self._present(item, installation, host, executors)

    def verify(
        self,
        installation_id: RuntimeInstallationId,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> RuntimeCapabilityProfile:
        """Probe the exact installation unless a fresh VERIFIED profile exists."""
        with self._lock.hold():
            installation = self._store.get(
                RuntimeInstallation, installation_id.value
            )
            if installation is None:
                raise NotFoundError(
                    "no such runtime installation",
                    installation_id=installation_id.value,
                )
            existing = self._store.get(
                RuntimeCapabilityProfile,
                fingerprint_profile_id(installation_id.value).value,
            )
            basis = build_verification_basis(installation, host, executors)
            if existing is not None:
                presented = self._apply_effective(existing, basis)
                if presented.status is VerificationStatus.VERIFIED:
                    return presented

            failed = self._integrity_failure(installation, host, executors, basis)
            if failed is not None:
                return self._persist_from_integrity(
                    installation, existing, basis, failed
                )

            spec = self._verifier.probe_spec(installation)
            python = self._python_path(installation)
            if python is not None:
                spec = replace(spec, executable=str(python))
            result = self._runner.run(spec, host_id=host.host_id)
            outcome = self._verifier.interpret(installation, result, host=host)
            return self._persist_outcome(
                installation, existing, basis, result, outcome
            )

    def _present(
        self,
        item: RuntimeCapabilityProfile,
        installation: RuntimeInstallation,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
    ) -> RuntimeCapabilityProfile:
        basis = build_verification_basis(installation, host, executors)
        return self._apply_effective(item, basis)

    def _apply_effective(
        self,
        item: RuntimeCapabilityProfile,
        basis: RuntimeVerificationBasis,
    ) -> RuntimeCapabilityProfile:
        status = effective_status(
            item.status, item.verification_basis_fingerprint, basis.fingerprint
        )
        if status is item.status:
            return item
        updated = replace(
            item,
            status=status,
            reason_codes=(
                *item.reason_codes,
                VerificationReasonCode.VERIFICATION_BASIS_CHANGED,
            )
            if (
                status is VerificationStatus.STALE
                and VerificationReasonCode.VERIFICATION_BASIS_CHANGED
                not in item.reason_codes
            )
            else item.reason_codes,
        )
        self._store.put(updated.profile_id.value, updated)
        return updated

    def _integrity_failure(
        self,
        installation: RuntimeInstallation,
        host: HostCapabilities,
        executors: Sequence[ExecutorCapabilityView],
        basis: RuntimeVerificationBasis,
    ) -> IntegrityOutcome | None:
        del host, basis
        if installation.status is not InstallationStatus.INSTALLED:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.INSTALLATION_NOT_INSTALLED.value,
                message="installation is not in the installed state",
                checks=(
                    RuntimeVerificationCheck(
                        name="installation_status",
                        outcome="fail",
                        detail=installation.status.value,
                    ),
                ),
            )
        root = self._final_root(installation)
        if not root.is_dir():
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.INSTALLATION_PATH_MISSING.value,
                message="final installation root is missing",
                checks=(
                    RuntimeVerificationCheck(
                        name="installation_root",
                        outcome="fail",
                        detail=installation.installation_root,
                    ),
                ),
            )
        python = self._python_path(installation)
        if python is None or not python.is_file():
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.PYTHON_EXECUTABLE_MISSING.value,
                message="isolated runtime Python is missing",
                checks=(
                    RuntimeVerificationCheck(
                        name="python_executable",
                        outcome="fail",
                        detail="missing",
                    ),
                ),
            )
        try:
            python.relative_to(root)
        except ValueError:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.PYTHON_EXECUTABLE_MISSING.value,
                message="Python executable is not inside the installation",
                checks=(
                    RuntimeVerificationCheck(
                        name="python_executable",
                        outcome="fail",
                        detail="outside installation root",
                    ),
                ),
            )
        if not executor_is_available(executors, installation.executor.value):
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.EXECUTOR_UNAVAILABLE.value,
                message="executor is not available on the current host",
                checks=(
                    RuntimeVerificationCheck(
                        name="executor",
                        outcome="fail",
                        detail=installation.executor.value,
                    ),
                ),
            )
        specific = self._verifier.inspect_integrity(
            installation, state_root=self._state_root
        )
        if not specific.succeeded:
            return specific
        return None

    def _persist_from_integrity(
        self,
        installation: RuntimeInstallation,
        existing: RuntimeCapabilityProfile | None,
        basis: RuntimeVerificationBasis,
        integrity: IntegrityOutcome,
    ) -> RuntimeCapabilityProfile:
        now = self._clock.now()
        attempts = (existing.attempt_count if existing is not None else 0) + 1
        created = existing.created_at if existing is not None else now
        code = integrity.reason_code or VerificationReasonCode.PYTHON_PROBE_FAILED.value
        profile = self._blank(
            installation,
            existing,
            basis,
            created=created,
            attempted_at=now,
            attempt_count=attempts,
            status=VerificationStatus.FAILED,
            checks=integrity.checks,
            reason_codes=_codes(code),
            message=integrity.message,
            diagnostic=integrity.message or "",
        )
        self._store.put(profile.profile_id.value, profile)
        return profile

    def _persist_outcome(
        self,
        installation: RuntimeInstallation,
        existing: RuntimeCapabilityProfile | None,
        basis: RuntimeVerificationBasis,
        result: ProbeExecutionResult,
        outcome: VerifierOutcome,
    ) -> RuntimeCapabilityProfile:
        now = self._clock.now()
        attempts = (existing.attempt_count if existing is not None else 0)
        if result.executed:
            attempts += 1
        created = existing.created_at if existing is not None else now
        status = (
            VerificationStatus.VERIFIED
            if outcome.succeeded
            else VerificationStatus.FAILED
        )
        codes = tuple(
            VerificationReasonCode(code) for code in outcome.reason_codes
        )
        python_exec = (
            installation.python_executable
            if is_resolved(installation.python_executable)
            else NOT_PROVIDED
        )
        profile = self._blank(
            installation,
            existing,
            basis,
            created=created,
            attempted_at=now,
            attempt_count=attempts,
            status=status,
            checks=outcome.checks,
            reason_codes=codes,
            message=outcome.message,
            diagnostic=_clip(
                outcome.diagnostic_summary or result.stderr or result.stdout
            ),
            python_executable=python_exec,
            python_version=_maybe(outcome.python_version),
            runtime_package_version=_maybe(outcome.runtime_package_version),
            backend=_maybe(outcome.backend),
            backend_version=_maybe(outcome.backend_version),
            backend_accelerator_available=_maybe(outcome.cuda_available),
            backend_accelerator_runtime_version=_maybe(
                outcome.cuda_runtime_version
            ),
            device_count=_maybe(outcome.device_count),
            devices=outcome.devices,
            accelerator_operation=_maybe(outcome.accelerator_operation),
            evidence_digest=_maybe(outcome.evidence_digest),
            probe_exit_code=_maybe(
                outcome.probe_exit_code
                if outcome.probe_exit_code is not None
                else result.exit_code
            ),
            verified_at=now if outcome.succeeded else (
                existing.verified_at if existing is not None else None
            ),
        )
        self._store.put(profile.profile_id.value, profile)
        return profile

    def _blank(
        self,
        installation: RuntimeInstallation,
        existing: RuntimeCapabilityProfile | None,
        basis: RuntimeVerificationBasis,
        *,
        created: dt.datetime,
        attempted_at: dt.datetime,
        attempt_count: int,
        status: VerificationStatus,
        checks: tuple[RuntimeVerificationCheck, ...],
        reason_codes: tuple[VerificationReasonCode, ...],
        message: str | None,
        diagnostic: str,
        python_executable: Maybe[str] = NOT_PROVIDED,
        python_version: Maybe[str] = NOT_PROVIDED,
        runtime_package_version: Maybe[str] = NOT_PROVIDED,
        backend: Maybe[str] = NOT_PROVIDED,
        backend_version: Maybe[str] = NOT_PROVIDED,
        backend_accelerator_available: Maybe[bool] = NOT_PROVIDED,
        backend_accelerator_runtime_version: Maybe[str] = NOT_PROVIDED,
        device_count: Maybe[int] = NOT_PROVIDED,
        devices: tuple[str, ...] = (),
        accelerator_operation: Maybe[str] = NOT_PROVIDED,
        evidence_digest: Maybe[str] = NOT_PROVIDED,
        probe_exit_code: Maybe[int] = NOT_PROVIDED,
        verified_at: dt.datetime | None = None,
    ) -> RuntimeCapabilityProfile:
        del existing
        failure_code: Maybe[str] = NOT_PROVIDED
        failure_message: Maybe[str] = NOT_PROVIDED
        if status is VerificationStatus.FAILED:
            failure_code = (
                reason_codes[0].value if reason_codes else "probe_exit_nonzero"
            )
            failure_message = message or diagnostic or "verification failed"
        return RuntimeCapabilityProfile(
            profile_id=fingerprint_profile_id(installation.installation_id.value),
            installation_id=installation.installation_id,
            plan_id=installation.plan_id,
            candidate_id=installation.candidate_id,
            runtime=installation.runtime,
            runtime_family=installation.runtime_family,
            runtime_provider=installation.runtime_provider,
            runtime_version=installation.runtime_version,
            executor=installation.executor,
            executor_type=basis.executor_type,
            host_id=basis.host_id,
            status=status,
            verification_basis_fingerprint=basis.fingerprint,
            verifier_provider=self._verifier.identity,
            verifier_schema=self._verifier.schema_version,
            created_at=created,
            last_attempted_at=attempted_at,
            attempt_count=attempt_count,
            verification_basis=basis,
            verified_at=verified_at,
            python_executable=python_executable,
            python_version=python_version,
            runtime_package_version=runtime_package_version,
            backend=backend,
            backend_version=backend_version,
            backend_accelerator_available=backend_accelerator_available,
            backend_accelerator_runtime_version=backend_accelerator_runtime_version,
            device_count=device_count,
            devices=devices,
            accelerator_operation=accelerator_operation,
            checks=checks,
            reason_codes=reason_codes,
            diagnostic_summary=diagnostic,
            evidence_digest=evidence_digest,
            last_failure_code=failure_code,
            last_failure_message=failure_message,
            probe_exit_code=probe_exit_code,
        )

    def _final_root(self, installation: RuntimeInstallation) -> Path:
        return (self._state_root / installation.installation_root).resolve()

    def _python_path(self, installation: RuntimeInstallation) -> Path | None:
        """The recorded venv interpreter path, not the host interpreter it shims.

        A venv ``python`` is typically a symlink to the host interpreter.
        Following that leaf symlink would treat a legitimate isolated
        environment as ``python_executable_missing``. K-66 still does not
        provision a managed interpreter; this only locates the shim.
        """
        raw = installation.python_executable
        if not is_resolved(raw):
            return None
        path = Path(raw)
        if not path.is_absolute():
            path = self._state_root / path
        return path.parent.resolve() / path.name


def _maybe(value: T | None) -> Maybe[T]:
    return NOT_PROVIDED if value is None else value


def _codes(code: str) -> tuple[VerificationReasonCode, ...]:
    try:
        return (VerificationReasonCode(code),)
    except ValueError:
        return (VerificationReasonCode.PYTHON_PROBE_FAILED,)


def _clip(text: str) -> str:
    value = text.strip()
    if len(value) <= _DIAGNOSTIC_LIMIT:
        return value
    return value[: _DIAGNOSTIC_LIMIT - 1] + "…"
