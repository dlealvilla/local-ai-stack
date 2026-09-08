"""Deterministic fixture verifier. Not real vLLM and never uses the network."""

from __future__ import annotations

import json
from pathlib import Path

from kultrun.host.contracts import HostCapabilities, HostId
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.basis import evidence_digest
from kultrun.runtime.contracts import (
    RuntimeInstallation,
    RuntimeVerificationCheck,
    RuntimeVerificationProbe,
    VerificationReasonCode,
)
from kultrun.runtime.pins import VLLM_VERSION
from kultrun.runtime.ports import (
    IntegrityOutcome,
    ProbeExecutionResult,
    VerifierOutcome,
)

IDENTITY = Name("fixture")

SCENARIO_HEALTHY = "healthy"
SCENARIO_PACKAGE_MISSING = "package_missing"
SCENARIO_VERSION_MISMATCH = "version_mismatch"
SCENARIO_IMPORT_FAILURE = "import_failure"
SCENARIO_BACKEND_UNAVAILABLE = "backend_unavailable"
SCENARIO_GPU_MISSING = "gpu_missing"
SCENARIO_OPERATION_FAILED = "operation_failed"
SCENARIO_TIMEOUT = "timeout"
SCENARIO_INVALID_EVIDENCE = "invalid_evidence"

_HEALTHY_PAYLOAD = {
    "python_version": "3.12.3",
    "vllm_version": VLLM_VERSION,
    "vllm_import": "pass",
    "backend": "torch",
    "backend_version": "2.9.0",
    "backend_import": "pass",
    "cuda_available": True,
    "cuda_runtime_version": "12.8",
    "device_count": 1,
    "devices": ["NVIDIA L40S"],
    "accelerator_operation": "pass",
}


class FixtureRuntimeVerifier:
    """Simulates verification outcomes. Offline only."""

    def __init__(self, scenario: str = SCENARIO_HEALTHY) -> None:
        self._scenario = scenario

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def schema_version(self) -> str:
        return "1"

    def inspect_integrity(
        self, installation: RuntimeInstallation, *, state_root: Path
    ) -> IntegrityOutcome:
        del state_root
        if self._scenario == SCENARIO_PACKAGE_MISSING:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.RUNTIME_PACKAGE_MISSING.value,
                message="fixture runtime package is missing",
                checks=(
                    RuntimeVerificationCheck(
                        name="runtime_package",
                        outcome="fail",
                        detail=installation.runtime.value,
                    ),
                ),
            )
        return IntegrityOutcome(succeeded=True)

    def probe_spec(self, installation: RuntimeInstallation) -> RuntimeVerificationProbe:
        python = (
            installation.python_executable
            if is_resolved(installation.python_executable)
            else "/nonexistent/python"
        )
        return RuntimeVerificationProbe(
            executable=python,
            arguments=("-c", "print('fixture-probe')"),
            environment=("PYTHONPATH=", "PYTHONNOUSERSITE=1"),
            timeout_seconds=5.0,
            output_limit_bytes=4096,
        )

    def interpret(
        self,
        installation: RuntimeInstallation,
        result: ProbeExecutionResult,
        *,
        host: HostCapabilities,
    ) -> VerifierOutcome:
        del installation
        if result.timed_out or self._scenario == SCENARIO_TIMEOUT:
            return _failed(
                VerificationReasonCode.PROBE_TIMEOUT,
                "probe timed out",
                result,
                host,
            )
        if result.executor_unavailable:
            return _failed(
                VerificationReasonCode.EXECUTOR_UNAVAILABLE,
                "executor unavailable",
                result,
                host,
            )
        if self._scenario == SCENARIO_INVALID_EVIDENCE or not _json_ok(result.stdout):
            return _failed(
                VerificationReasonCode.PROBE_OUTPUT_INVALID,
                "probe output was not valid evidence",
                result,
                host,
            )
        if self._scenario == SCENARIO_VERSION_MISMATCH:
            return _failed(
                VerificationReasonCode.RUNTIME_VERSION_MISMATCH,
                "runtime package version is not 0.28.0",
                result,
                host,
                payload=_payload_with(vllm_version="9.9.9"),
            )
        if self._scenario == SCENARIO_IMPORT_FAILURE:
            return _failed(
                VerificationReasonCode.RUNTIME_IMPORT_FAILED,
                "import vllm failed",
                result,
                host,
            )
        if self._scenario == SCENARIO_BACKEND_UNAVAILABLE:
            return _failed(
                VerificationReasonCode.BACKEND_ACCELERATOR_UNAVAILABLE,
                "CUDA is not available in the runtime",
                result,
                host,
            )
        if self._scenario == SCENARIO_GPU_MISSING:
            return _failed(
                VerificationReasonCode.ACCELERATOR_NOT_VISIBLE,
                "no GPU devices were visible",
                result,
                host,
            )
        if self._scenario == SCENARIO_OPERATION_FAILED:
            return _failed(
                VerificationReasonCode.ACCELERATOR_OPERATION_FAILED,
                "tiny accelerator operation failed",
                result,
                host,
            )
        payload = _payload_with(devices=_device_names(host))
        encoded = json.dumps(payload, sort_keys=True)
        return VerifierOutcome(
            succeeded=True,
            checks=_healthy_checks(),
            python_version=str(payload["python_version"]),
            runtime_package_version=str(payload["vllm_version"]),
            backend=str(payload["backend"]),
            backend_version=str(payload["backend_version"]),
            cuda_available=True,
            cuda_runtime_version=str(payload["cuda_runtime_version"]),
            device_count=int(str(payload["device_count"])),
            devices=_as_names(payload["devices"]),
            accelerator_operation="pass",
            evidence_digest=evidence_digest(encoded),
            summary="fixture verification passed",
            probe_exit_code=0,
        )


class FixtureProbeRunner:
    """Returns canned probe output. Never starts a process."""

    def __init__(self, scenario: str = SCENARIO_HEALTHY) -> None:
        self._scenario = scenario
        self.run_count = 0
        self.last_spec: RuntimeVerificationProbe | None = None

    def run(
        self,
        spec: RuntimeVerificationProbe,
        *,
        host_id: HostId,
    ) -> ProbeExecutionResult:
        del host_id
        self.last_spec = spec
        self.run_count += 1
        if self._scenario == SCENARIO_TIMEOUT:
            return ProbeExecutionResult(timed_out=True, executed=True)
        if self._scenario == SCENARIO_INVALID_EVIDENCE:
            return ProbeExecutionResult(
                exit_code=0,
                stdout="not-json",
                executed=True,
            )
        payload = dict(_HEALTHY_PAYLOAD)
        return ProbeExecutionResult(
            exit_code=0,
            stdout=json.dumps(payload, sort_keys=True),
            executed=True,
        )


def _as_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item) for item in value)


def _json_ok(text: str) -> bool:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(value, dict)


def _payload_with(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = dict(_HEALTHY_PAYLOAD)
    payload.update(overrides)
    return payload


def _device_names(host: HostCapabilities) -> list[str]:
    if not host.accelerators:
        return ["NVIDIA L40S"]
    return [
        item.model_name if is_resolved(item.model_name) else "unknown"
        for item in host.accelerators
    ]


def _healthy_checks() -> tuple[RuntimeVerificationCheck, ...]:
    return (
        RuntimeVerificationCheck(name="installation_integrity", outcome="pass"),
        RuntimeVerificationCheck(name="python_environment", outcome="pass"),
        RuntimeVerificationCheck(name="runtime_package", outcome="pass"),
        RuntimeVerificationCheck(name="runtime_import", outcome="pass"),
        RuntimeVerificationCheck(name="backend_import", outcome="pass"),
        RuntimeVerificationCheck(name="accelerator_visibility", outcome="pass"),
        RuntimeVerificationCheck(name="accelerator_operation", outcome="pass"),
    )


def _failed(
    code: VerificationReasonCode,
    message: str,
    result: ProbeExecutionResult,
    host: HostCapabilities,
    payload: dict[str, object] | None = None,
) -> VerifierOutcome:
    del host
    encoded = json.dumps(payload, sort_keys=True) if payload is not None else ""
    return VerifierOutcome(
        succeeded=False,
        reason_codes=(code.value,),
        message=message,
        checks=(
            RuntimeVerificationCheck(name=code.value, outcome="fail", detail=message),
        ),
        evidence_digest=evidence_digest(encoded) if encoded else None,
        summary=message,
        diagnostic_summary=_clip_stderr(result),
        probe_exit_code=result.exit_code,
    )


def _clip_stderr(result: ProbeExecutionResult) -> str:
    text = (result.stderr or result.stdout).strip()
    return text[:512]
