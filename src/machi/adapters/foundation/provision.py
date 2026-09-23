"""Provision a managed vLLM generation through NativeProcessRunner."""

from __future__ import annotations

import datetime as dt
import json
import os
import secrets
from collections.abc import Callable
from pathlib import Path

from machi.adapters.foundation.process import NativeProcessRunner, ProcessRunner
from machi.adapters.foundation.uv_tool import UV_VERSION
from machi.foundation.contracts import (
    AcceleratorBackend,
    FailureCode,
    FeatureState,
    FoundationCandidate,
    FoundationRequirement,
    FoundationSelection,
    FoundationSet,
    FoundationSettings,
    ManagedGeneration,
    ProvisionMode,
    RuntimeCapability,
    SupportState,
    VerificationEvidence,
)
from machi.foundation.policy import (
    MINIMUM_MEMORY_BYTES,
    PERSISTENT_BYTES,
    TRANSIENT_BYTES,
)
from machi.foundation.select import selection_from_candidate
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.kernel.unresolved import NOT_MEASURED, NOT_PROVIDED, Maybe, is_resolved

_MANIFEST = ".machi-foundation.json"


class ManagedVllmProvisioner:
    """Create or reuse one generation. Does not download a model or serve."""

    def __init__(
        self,
        runner: ProcessRunner | None = None,
        *,
        clock: Clock | None = None,
        uv_executable: str | Callable[[Path], str] = "uv",
    ) -> None:
        self._runner = runner or NativeProcessRunner()
        self._clock = clock or SystemClock()
        self._uv = uv_executable

    def apply(
        self,
        *,
        state_root: Path,
        candidate: FoundationCandidate,
        settings: FoundationSettings,
        capacity_evidence_id: str,
    ) -> FoundationSet:
        requirement = FoundationRequirement(
            persistent_bytes=PERSISTENT_BYTES,
            transient_bytes=TRANSIENT_BYTES,
            minimum_memory_bytes=MINIMUM_MEMORY_BYTES,
        )
        when = self._clock.now()
        selection_id = f"fsel_{secrets.token_hex(8)}"
        if candidate.failure is not FailureCode.NONE:
            return FoundationSet(
                selection=selection_from_candidate(
                    candidate,
                    selection_id=selection_id,
                    capacity_evidence_id=capacity_evidence_id,
                ),
                candidate=candidate,
                requirement=requirement,
                generation=NOT_PROVIDED,
                verification=NOT_PROVIDED,
                capability=NOT_PROVIDED,
                settings=settings,
                observed_at=when,
            )
        reused = self._reuse(state_root, candidate, settings)
        if reused is not None:
            generation, verification = reused
            reused_capability = _capability(candidate)
            return FoundationSet(
                selection=selection_from_candidate(
                    candidate,
                    selection_id=selection_id,
                    capacity_evidence_id=capacity_evidence_id,
                    generation_id=generation.generation_id,
                    ready=True,
                ),
                candidate=candidate,
                requirement=requirement,
                generation=generation,
                verification=verification,
                capability=reused_capability,
                settings=settings,
                observed_at=when,
            )
        if settings.provision_mode is not ProvisionMode.PROVISION:
            return FoundationSet(
                selection=selection_from_candidate(
                    candidate,
                    selection_id=selection_id,
                    capacity_evidence_id=capacity_evidence_id,
                ),
                candidate=candidate,
                requirement=requirement,
                generation=NOT_PROVIDED,
                verification=NOT_PROVIDED,
                capability=NOT_PROVIDED,
                settings=settings,
                observed_at=when,
            )
        if (
            candidate.backend is AcceleratorBackend.ROCM
            and candidate.native_status == "realize"
        ):
            return self._failed(
                candidate,
                requirement,
                settings,
                capacity_evidence_id,
                selection_id,
                when,
                FailureCode.PREREQUISITE_BLOCKED,
                "managed userspace is not realized",
            )
        generation_id = f"fgen_{secrets.token_hex(8)}"
        root = state_root / "foundation" / "generations" / generation_id
        root.mkdir(parents=True, exist_ok=False)
        cache = state_root / "foundation" / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        venv = root / "venv"
        python = venv / "bin" / "python"
        resolver = self._uv
        if callable(resolver):
            try:
                uv = resolver(state_root)
            except ValidationError:
                return self._failed(
                    candidate,
                    requirement,
                    settings,
                    capacity_evidence_id,
                    selection_id,
                    when,
                    FailureCode.PYTHON_PROVISION_FAILED,
                    "managed tool bootstrap failed",
                )
        else:
            uv = resolver
        env = _provision_env(cache, candidate.native_library_prefix)
        created = self._runner.run(
            [uv, "venv", "--python", candidate.python_version, str(venv), "--seed"],
            cwd=str(root),
            timeout=settings.timeout_seconds,
            env=env,
        )
        if created.timed_out:
            return self._failed(
                candidate,
                requirement,
                settings,
                capacity_evidence_id,
                selection_id,
                when,
                FailureCode.TIMEOUT,
                "managed Python provisioning timed out",
            )
        if created.returncode != 0:
            return self._failed(
                candidate,
                requirement,
                settings,
                capacity_evidence_id,
                selection_id,
                when,
                FailureCode.PYTHON_PROVISION_FAILED,
                "managed Python environment was not created",
            )
        installed = self._runner.run(
            self._install_argv(uv, candidate, python),
            cwd=str(root),
            timeout=settings.timeout_seconds,
            env=env,
        )
        if installed.timed_out:
            return self._failed(
                candidate,
                requirement,
                settings,
                capacity_evidence_id,
                selection_id,
                when,
                FailureCode.TIMEOUT,
                "package install timed out",
            )
        if installed.returncode != 0:
            return self._failed(
                candidate,
                requirement,
                settings,
                capacity_evidence_id,
                selection_id,
                when,
                FailureCode.PACKAGE_INSTALL_FAILED,
                "vLLM package install failed",
            )
        generation = ManagedGeneration(
            generation_id=generation_id,
            candidate_id=candidate.candidate_id,
            python_path=str(python),
            vllm_version=candidate.vllm_version,
            created_at=when,
        )
        verification = self._verify(candidate, python, settings.timeout_seconds, env)
        self._write_manifest(root, generation, cache, candidate, verification)
        capability: RuntimeCapability | None = None
        ready = verification.passed
        if ready:
            capability = _capability(candidate)
        support_failure = candidate.failure if ready else verification.failure
        selection = selection_from_candidate(
            candidate,
            selection_id=selection_id,
            capacity_evidence_id=capacity_evidence_id,
            generation_id=generation_id,
            ready=ready,
        )
        if not ready:
            selection = _replace_selection(selection, support_failure)
        return FoundationSet(
            selection=selection,
            candidate=candidate,
            requirement=requirement,
            generation=generation,
            verification=verification,
            capability=capability if capability is not None else NOT_PROVIDED,
            settings=settings,
            observed_at=when,
        )

    def _reuse(
        self,
        state_root: Path,
        candidate: FoundationCandidate,
        settings: FoundationSettings,
    ) -> tuple[ManagedGeneration, VerificationEvidence] | None:
        base = state_root / "foundation" / "generations"
        if not base.is_dir():
            return None
        for child in base.iterdir():
            manifest = child / _MANIFEST
            if not manifest.is_file():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if payload.get("candidate_id") != candidate.candidate_id:
                continue
            python = Path(str(payload["python_path"]))
            env = _provision_env(
                state_root / "foundation" / "cache",
                candidate.native_library_prefix,
            )
            verification = self._verify(
                candidate, python, settings.timeout_seconds, env
            )
            if not verification.passed:
                continue
            generation = ManagedGeneration(
                generation_id=str(payload["generation_id"]),
                candidate_id=candidate.candidate_id,
                python_path=str(python),
                vllm_version=candidate.vllm_version,
                created_at=self._clock.now(),
            )
            return generation, verification
        return None

    def _install_argv(
        self,
        uv: str,
        candidate: FoundationCandidate,
        python: Path,
    ) -> list[str]:
        base = [uv, "pip", "install", "--python", str(python), candidate.package_spec]
        if candidate.backend is AcceleratorBackend.CUDA:
            return [*base, "--torch-backend=auto"]
        return [*base, "--extra-index-url", candidate.package_source]

    def _verify(
        self,
        candidate: FoundationCandidate,
        python: Path,
        timeout: int,
        env: dict[str, str],
    ) -> VerificationEvidence:
        pin = candidate.vllm_version
        backend = candidate.backend
        if not is_resolved(backend):
            return VerificationEvidence(
                passed=False,
                observed_version=NOT_MEASURED,
                effective_python=NOT_MEASURED,
                effective_torch=NOT_MEASURED,
                effective_backend_runtime=NOT_MEASURED,
                failure=FailureCode.VERIFICATION_FAILED,
                reason="verification has no accelerator backend",
            )
        backend_name = backend.value
        code = (
            "import vllm\n"
            f"if not vllm.__version__.startswith({pin!r}):\n"
            "    raise SystemExit(1)\n"
            "import vllm.entrypoints.openai.api_server\n"
            "import sys\n"
            "import torch\n"
            f"if {backend_name!r} == 'cuda' and not torch.version.cuda:\n"
            "    print('MACHI_BACKEND_MISMATCH')\n"
            "    raise SystemExit(2)\n"
            f"if {backend_name!r} == 'rocm' and not torch.version.hip:\n"
            "    print('MACHI_BACKEND_MISMATCH')\n"
            "    raise SystemExit(2)\n"
            "runtime = torch.version.hip or torch.version.cuda or ''\n"
            "print(vllm.__version__)\n"
            "print(torch.__version__)\n"
            "print(runtime)\n"
            "print(sys.version.split()[0])\n"
        )
        result = self._runner.run(
            [str(python), "-c", code],
            cwd=str(python.parent),
            timeout=timeout,
            env=env,
        )
        if result.timed_out:
            return VerificationEvidence(
                passed=False,
                observed_version=NOT_MEASURED,
                effective_python=NOT_MEASURED,
                effective_torch=NOT_MEASURED,
                effective_backend_runtime=NOT_MEASURED,
                failure=FailureCode.TIMEOUT,
                reason="verification timed out",
            )
        if "MACHI_BACKEND_MISMATCH" in result.stdout:
            return VerificationEvidence(
                passed=False,
                observed_version=NOT_MEASURED,
                effective_python=NOT_MEASURED,
                effective_torch=NOT_MEASURED,
                effective_backend_runtime=NOT_MEASURED,
                failure=FailureCode.DRIVER_OR_BACKEND_INCOMPATIBLE,
                reason="installed backend does not match the selected provider",
            )
        if result.returncode != 0:
            return VerificationEvidence(
                passed=False,
                observed_version=NOT_MEASURED,
                effective_python=NOT_MEASURED,
                effective_torch=NOT_MEASURED,
                effective_backend_runtime=NOT_MEASURED,
                failure=FailureCode.VERIFICATION_FAILED,
                reason="import, version, or entrypoint check failed",
            )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        observed = lines[0][:32] if lines else ""
        return VerificationEvidence(
            passed=True,
            observed_version=observed,
            effective_python=_line(lines, 3),
            effective_torch=_line(lines, 1),
            effective_backend_runtime=_line(lines, 2),
            failure=FailureCode.NONE,
            reason="import, version, backend, and entrypoint checks passed",
        )

    def _write_manifest(
        self,
        root: Path,
        generation: ManagedGeneration,
        cache: Path,
        candidate: FoundationCandidate,
        verification: VerificationEvidence,
    ) -> None:
        payload = to_dict(generation)
        payload["purpose"] = "managed_vllm_foundation"
        payload["tool_name"] = "uv"
        payload["tool_version"] = UV_VERSION
        payload["measured_persistent_bytes"] = _tree_bytes(root)
        payload["measured_cache_bytes"] = _tree_bytes(cache)
        payload["wheel_variant"] = candidate.variant
        payload["observed_rocm"] = _text(candidate.observed_rocm)
        payload["accelerator_architecture"] = _text(candidate.accelerator_architecture)
        payload["native_status"] = candidate.native_status
        payload["native_library_prefix"] = candidate.native_library_prefix
        payload["effective_python"] = _text(verification.effective_python)
        payload["effective_torch"] = _text(verification.effective_torch)
        payload["effective_backend_runtime"] = _text(
            verification.effective_backend_runtime
        )
        text = json.dumps(payload, indent=2) + "\n"
        (root / _MANIFEST).write_text(text, encoding="utf-8")

    def _failed(
        self,
        candidate: FoundationCandidate,
        requirement: FoundationRequirement,
        settings: FoundationSettings,
        capacity_evidence_id: str,
        selection_id: str,
        when: dt.datetime,
        failure: FailureCode,
        reason: str,
    ) -> FoundationSet:
        refused = FoundationCandidate(
            candidate_id=candidate.candidate_id,
            family=candidate.family,
            engine=candidate.engine,
            executor=candidate.executor,
            backend=candidate.backend,
            python_version=candidate.python_version,
            vllm_version=candidate.vllm_version,
            package_spec=candidate.package_spec,
            package_source=candidate.package_source,
            variant=candidate.variant,
            required_rocm=candidate.required_rocm,
            observed_rocm=candidate.observed_rocm,
            observed_glibc=candidate.observed_glibc,
            accelerator_architecture=candidate.accelerator_architecture,
            native_libraries=candidate.native_libraries,
            native_status=candidate.native_status,
            native_library_prefix=candidate.native_library_prefix,
            support=SupportState.PROVISIONING_FAILED,
            failure=failure,
            reason=reason,
        )
        return FoundationSet(
            selection=selection_from_candidate(
                refused,
                selection_id=selection_id,
                capacity_evidence_id=capacity_evidence_id,
            ),
            candidate=refused,
            requirement=requirement,
            generation=NOT_PROVIDED,
            verification=NOT_PROVIDED,
            capability=NOT_PROVIDED,
            settings=settings,
            observed_at=when,
        )


def _capability(candidate: FoundationCandidate) -> RuntimeCapability:
    backend = candidate.backend
    if not is_resolved(backend):
        raise ValidationError("capability requires a resolved backend")
    return RuntimeCapability(
        engine=candidate.engine,
        version=candidate.vllm_version,
        backend=backend,
        import_state=FeatureState.VERIFIED,
        entrypoint_state=FeatureState.VERIFIED,
        server_launch=FeatureState.UNSUPPORTED,
        streaming=FeatureState.DECLARED_BY_VERSION,
        structured_output=FeatureState.UNRESOLVED,
        lora=FeatureState.UNRESOLVED,
        metrics=FeatureState.UNRESOLVED,
    )


def _line(lines: list[str], index: int) -> Maybe[str]:
    if len(lines) <= index or not lines[index]:
        return NOT_MEASURED
    return lines[index][:32]


def _text(value: Maybe[str]) -> str:
    if is_resolved(value) and isinstance(value, str):
        return value
    return "unresolved"


def _provision_env(cache: Path, library_prefix: str) -> dict[str, str]:
    kept = (
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "NO_PROXY",
        "no_proxy",
        "ALL_PROXY",
    )
    env = {key: os.environ[key] for key in kept if key in os.environ}
    env["UV_CACHE_DIR"] = str(cache)
    env["UV_LINK_MODE"] = "copy"
    if library_prefix != "none":
        env["LD_LIBRARY_PATH"] = library_prefix
    return env


def _tree_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            file = Path(dirpath) / name
            if file.is_symlink():
                continue
            try:
                total += file.stat().st_size
            except OSError:
                continue
    return total


def _replace_selection(
    selection: FoundationSelection,
    failure: FailureCode,
) -> FoundationSelection:
    verified = {
        FailureCode.VERIFICATION_FAILED,
        FailureCode.TIMEOUT,
        FailureCode.DRIVER_OR_BACKEND_INCOMPATIBLE,
    }
    support = (
        SupportState.VERIFICATION_FAILED
        if failure in verified
        else SupportState.PROVISIONING_FAILED
    )
    return FoundationSelection(
        selection_id=selection.selection_id,
        family=selection.family,
        engine=selection.engine,
        executor=selection.executor,
        backend=selection.backend,
        support=support,
        failure=failure,
        candidate_id=selection.candidate_id,
        generation_id=selection.generation_id,
        capacity_evidence_id=selection.capacity_evidence_id,
        reason=selection.reason,
    )
