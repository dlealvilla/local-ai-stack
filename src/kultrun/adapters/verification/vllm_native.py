"""vLLM 0.28.0 native-process verifier. Does not provision or load a model."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kultrun.host.contracts import AcceleratorVendor, HostCapabilities
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.runtime.basis import evidence_digest
from kultrun.runtime.contracts import (
    RuntimeInstallation,
    RuntimeVerificationCheck,
    RuntimeVerificationProbe,
    VerificationReasonCode,
)
from kultrun.runtime.pins import (
    NATIVE_EXECUTOR,
    PROBE_OUTPUT_LIMIT_BYTES,
    PROBE_TIMEOUT_SECONDS,
    VLLM_PACKAGE,
    VLLM_VERSION,
)
from kultrun.runtime.ports import (
    IntegrityOutcome,
    ProbeExecutionResult,
    VerifierOutcome,
)

IDENTITY = Name("vllm-native")

# Executed inside the isolated runtime Python via argv. Not imported here.
PROBE_SOURCE = (
    "import json,sys\n"
    "p={'python_version':'{}.{}.{}'.format(*sys.version_info[:3]),"
    "'vllm_version':None,'vllm_import':'fail','backend':None,"
    "'backend_version':None,'backend_import':'fail','cuda_available':False,"
    "'cuda_runtime_version':None,'device_count':0,'devices':[],"
    "'accelerator_operation':'skip'}\n"
    "try:\n"
    " import importlib.metadata as m\n"
    " p['vllm_version']=m.version('vllm')\n"
    "except Exception as e:\n"
    " p['metadata_error']=str(e)[:200]\n"
    "try:\n"
    " import vllm\n"
    " p['vllm_import']='pass'\n"
    " v=getattr(vllm,'__version__',None)\n"
    " p['vllm_module_version']=str(v) if v else None\n"
    "except Exception as e:\n"
    " p['vllm_import']='fail';p['vllm_import_error']=str(e)[:200]\n"
    " print(json.dumps(p,sort_keys=True));sys.exit(2)\n"
    "try:\n"
    " import torch\n"
    " p['backend']='torch';p['backend_version']=getattr(torch,'__version__',None)\n"
    " p['backend_import']='pass'\n"
    " p['cuda_available']=bool(torch.cuda.is_available())\n"
    " if p['cuda_available']:\n"
    "  p['device_count']=int(torch.cuda.device_count())\n"
    "  p['devices']=[torch.cuda.get_device_name(i) for i in range(p['device_count'])]\n"
    "  p['cuda_runtime_version']=str(getattr(torch.version,'cuda',None))\n"
    "  try:\n"
    "   t=torch.zeros(1,device='cuda');t=t+1;torch.cuda.synchronize()\n"
    "   p['accelerator_operation']='pass'\n"
    "  except Exception as e:\n"
    "   p['accelerator_operation']='fail'\n"
    "   p['accelerator_operation_error']=str(e)[:200]\n"
    "except Exception as e:\n"
    " p['backend_import']='fail';p['backend_error']=str(e)[:200]\n"
    " print(json.dumps(p,sort_keys=True));sys.exit(3)\n"
    "print(json.dumps(p,sort_keys=True))\n"
)


class VllmNativeVerifier:
    """Proves the pinned vLLM native install can import and touch CUDA."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def schema_version(self) -> str:
        return "1"

    def inspect_integrity(
        self, installation: RuntimeInstallation, *, state_root: Path
    ) -> IntegrityOutcome:
        if installation.runtime.value != VLLM_PACKAGE:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.RUNTIME_PACKAGE_MISSING.value,
                message="installation is not the vLLM native runtime",
                checks=(
                    RuntimeVerificationCheck(
                        name="runtime_family",
                        outcome="fail",
                        detail=installation.runtime.value,
                    ),
                ),
            )
        if installation.executor.value != NATIVE_EXECUTOR:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.EXECUTOR_UNAVAILABLE.value,
                message="vLLM native verifier requires native-process",
                checks=(
                    RuntimeVerificationCheck(
                        name="executor",
                        outcome="fail",
                        detail=installation.executor.value,
                    ),
                ),
            )
        if installation.runtime_version != VLLM_VERSION:
            return IntegrityOutcome(
                succeeded=False,
                reason_code=VerificationReasonCode.RUNTIME_VERSION_MISMATCH.value,
                message="installation version is not the Stage 1.6D pin",
                checks=(
                    RuntimeVerificationCheck(
                        name="runtime_version",
                        outcome="fail",
                        detail=installation.runtime_version,
                    ),
                ),
            )
        manifest = installation.provenance_manifest_path
        if is_resolved(manifest):
            path = Path(manifest)
            if not path.is_absolute():
                path = Path(state_root) / path
            if not path.is_file():
                return IntegrityOutcome(
                    succeeded=False,
                    reason_code=VerificationReasonCode.INSTALLATION_PATH_MISSING.value,
                    message="installer provenance manifest is missing",
                    checks=(
                        RuntimeVerificationCheck(
                            name="provenance_manifest",
                            outcome="fail",
                            detail=str(manifest),
                        ),
                    ),
                )
        return IntegrityOutcome(succeeded=True)

    def probe_spec(self, installation: RuntimeInstallation) -> RuntimeVerificationProbe:
        python = (
            installation.python_executable
            if is_resolved(installation.python_executable)
            else ""
        )
        return RuntimeVerificationProbe(
            executable=python,
            arguments=("-c", PROBE_SOURCE),
            environment=("PYTHONPATH=", "PYTHONNOUSERSITE=1"),
            timeout_seconds=PROBE_TIMEOUT_SECONDS,
            output_limit_bytes=PROBE_OUTPUT_LIMIT_BYTES,
        )

    def interpret(
        self,
        installation: RuntimeInstallation,
        result: ProbeExecutionResult,
        *,
        host: HostCapabilities,
    ) -> VerifierOutcome:
        del installation
        if result.timed_out:
            return _fail(
                VerificationReasonCode.PROBE_TIMEOUT,
                "verification probe timed out",
                result,
            )
        if result.executor_unavailable:
            return _fail(
                VerificationReasonCode.EXECUTOR_UNAVAILABLE,
                "executor could not run the probe",
                result,
            )
        payload = _parse(result.stdout)
        if payload is None:
            code = (
                VerificationReasonCode.PROBE_EXIT_NONZERO
                if result.exit_code not in (0, None)
                else VerificationReasonCode.PROBE_OUTPUT_INVALID
            )
            return _fail(code, "probe output was not valid JSON evidence", result)
        digest = evidence_digest(json.dumps(payload, sort_keys=True, default=str))
        checks: list[RuntimeVerificationCheck] = []
        python_version = _as_str(payload.get("python_version"))
        if not python_version or not python_version.startswith("3.12"):
            return _fail(
                VerificationReasonCode.PYTHON_PROBE_FAILED,
                "runtime Python version is not 3.12",
                result,
                payload=payload,
                digest=digest,
            )
        checks.append(
            RuntimeVerificationCheck(
                name="python_environment", outcome="pass", detail=python_version
            )
        )
        package = _as_str(payload.get("vllm_version"))
        if not package:
            return _fail(
                VerificationReasonCode.RUNTIME_PACKAGE_MISSING,
                "vllm package metadata is missing",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
            )
        if package != VLLM_VERSION:
            return _fail(
                VerificationReasonCode.RUNTIME_VERSION_MISMATCH,
                f"vllm package version is {package}, expected {VLLM_VERSION}",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
            )
        checks.append(
            RuntimeVerificationCheck(
                name="runtime_package", outcome="pass", detail=package
            )
        )
        if payload.get("vllm_import") != "pass":
            return _fail(
                VerificationReasonCode.RUNTIME_IMPORT_FAILED,
                _as_str(payload.get("vllm_import_error")) or "import vllm failed",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
            )
        checks.append(RuntimeVerificationCheck(name="runtime_import", outcome="pass"))
        if payload.get("backend_import") != "pass":
            return _fail(
                VerificationReasonCode.BACKEND_IMPORT_FAILED,
                _as_str(payload.get("backend_error")) or "backend import failed",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
            )
        backend = _as_str(payload.get("backend"))
        backend_version = _as_str(payload.get("backend_version"))
        checks.append(
            RuntimeVerificationCheck(
                name="backend_import",
                outcome="pass",
                detail=backend or "backend",
            )
        )
        cuda = bool(payload.get("cuda_available"))
        if not cuda:
            return _fail(
                VerificationReasonCode.BACKEND_ACCELERATOR_UNAVAILABLE,
                "CUDA is not available in the runtime",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
                backend=backend,
                backend_version=backend_version,
            )
        checks.append(
            RuntimeVerificationCheck(
                name="cuda_available", outcome="pass", detail="yes"
            )
        )
        count = int(payload.get("device_count") or 0)
        names = tuple(str(item) for item in (payload.get("devices") or []))
        if count < 1 or not names:
            return _fail(
                VerificationReasonCode.ACCELERATOR_NOT_VISIBLE,
                "no GPU devices were visible inside the runtime",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
                backend=backend,
                backend_version=backend_version,
                cuda=True,
            )
        if not _devices_match(host, names):
            return _fail(
                VerificationReasonCode.ACCELERATOR_IDENTITY_MISMATCH,
                "observed GPU identity does not match current host facts",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
                backend=backend,
                backend_version=backend_version,
                cuda=True,
                devices=names,
                device_count=count,
            )
        checks.append(
            RuntimeVerificationCheck(
                name="accelerator_visibility",
                outcome="pass",
                detail=f"{count} {', '.join(names)}",
            )
        )
        operation = _as_str(payload.get("accelerator_operation")) or "skip"
        if operation != "pass":
            return _fail(
                VerificationReasonCode.ACCELERATOR_OPERATION_FAILED,
                _as_str(payload.get("accelerator_operation_error"))
                or "tiny accelerator operation failed",
                result,
                payload=payload,
                digest=digest,
                python_version=python_version,
                package=package,
                backend=backend,
                backend_version=backend_version,
                cuda=True,
                devices=names,
                device_count=count,
            )
        checks.append(
            RuntimeVerificationCheck(name="accelerator_operation", outcome="pass")
        )
        return VerifierOutcome(
            succeeded=True,
            checks=tuple(checks),
            python_version=python_version,
            runtime_package_version=package,
            backend=backend,
            backend_version=backend_version,
            cuda_available=True,
            cuda_runtime_version=_as_str(payload.get("cuda_runtime_version")),
            device_count=count,
            devices=names,
            accelerator_operation="pass",
            evidence_digest=digest,
            summary="vLLM native verification passed",
            probe_exit_code=result.exit_code,
        )


def _parse(text: str) -> dict[str, Any] | None:
    blob = text.strip()
    if not blob:
        return None
    try:
        value = json.loads(blob.splitlines()[-1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _devices_match(host: HostCapabilities, observed: tuple[str, ...]) -> bool:
    expected = [
        item
        for item in host.accelerators
        if item.vendor is AcceleratorVendor.NVIDIA
    ]
    if not expected:
        return False
    lowered = tuple(name.lower() for name in observed)
    raw_model = expected[0].model_name
    host_model = raw_model.lower() if is_resolved(raw_model) else ""
    if not any("nvidia" in name or host_model in name for name in lowered):
        return False
    return any(host_model in name or name in host_model for name in lowered) or any(
        "nvidia" in name for name in lowered
    )


def _fail(
    code: VerificationReasonCode,
    message: str,
    result: ProbeExecutionResult,
    *,
    payload: dict[str, Any] | None = None,
    digest: str | None = None,
    python_version: str | None = None,
    package: str | None = None,
    backend: str | None = None,
    backend_version: str | None = None,
    cuda: bool | None = None,
    devices: tuple[str, ...] = (),
    device_count: int | None = None,
) -> VerifierOutcome:
    del payload
    diagnostic = (result.stderr or result.stdout).strip()[:512]
    return VerifierOutcome(
        succeeded=False,
        reason_codes=(code.value,),
        message=message,
        checks=(
            RuntimeVerificationCheck(
                name=code.value, outcome="fail", detail=message
            ),
        ),
        python_version=python_version,
        runtime_package_version=package,
        backend=backend,
        backend_version=backend_version,
        cuda_available=cuda,
        device_count=device_count,
        devices=devices,
        evidence_digest=digest,
        summary=message,
        diagnostic_summary=diagnostic,
        probe_exit_code=result.exit_code,
    )
