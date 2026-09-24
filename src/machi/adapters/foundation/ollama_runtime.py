"""Owned Ollama prefix and daemon lifecycle. No model pull and no inference."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from machi.adapters.foundation.ollama_archive import (
    InstalledPrefix,
    InstallFaults,
    PrefixRefusal,
    SystemZstdDecompressor,
    observe_runtime_identity,
    realize_prefix,
    unregistered_owned_generations,
)
from machi.adapters.foundation.process import NativeProcessRunner, SpawnedProcess
from machi.foundation.contracts import FailureCode, SupportState
from machi.foundation.ollama import (
    ExistingOllamaObservation,
    OllamaAssessment,
    OllamaRuntimeRecipe,
    assess_existing,
    assess_managed,
    pinned_recipe,
    private_endpoint,
)
from machi.kernel.clock import Clock, SystemClock

__all__ = [
    "InstallFaults",
    "InstalledPrefix",
    "OllamaRuntime",
    "PrefixRefusal",
    "SystemZstdDecompressor",
    "daemon_environment",
    "unregistered_owned_generations",
]


class UrllibVersionClient:
    """Read the local version endpoint. No other route is requested."""

    def api_version(self, endpoint: str, *, timeout: float) -> str | None:
        if private_endpoint(endpoint) is None:
            return None
        request = urllib.request.Request(
            endpoint.rstrip("/") + "/api/version",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict):
            return None
        version = payload.get("version")
        if not isinstance(version, str):
            return None
        return version


class OllamaRuntime:
    """Install and supervise one owned daemon. Serving a model is later."""

    def __init__(
        self,
        *,
        runner: NativeProcessRunner | None = None,
        client: UrllibVersionClient | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._runner = runner or NativeProcessRunner()
        self._client = client or UrllibVersionClient()
        self._clock = clock or SystemClock()
        self._spawned: SpawnedProcess | None = None
        self._prefix: Path | None = None
        self._port: int | None = None
        self._recipe: OllamaRuntimeRecipe | None = None
        self._fingerprint = ""
        self._capacity = ""
        self._footprint: int | None = None
        self._install_seconds: float | None = None

    def install(
        self,
        state_root: Path,
        archive_path: Path,
        recipe: OllamaRuntimeRecipe,
        *,
        safe_bytes: int | None = None,
        decompressor: SystemZstdDecompressor | None = None,
        faults: InstallFaults | None = None,
    ) -> InstalledPrefix | PrefixRefusal:
        """Stage a local archive, verify it, then promote an owned prefix."""
        return realize_prefix(
            state_root,
            archive_path,
            recipe,
            safe_bytes=safe_bytes,
            decompressor=decompressor,
            faults=faults,
        )

    def verify_existing(
        self,
        observation: ExistingOllamaObservation,
        *,
        execution_environment_fingerprint: str,
        capacity_evidence_id: str,
        recipe: OllamaRuntimeRecipe | None = None,
    ) -> OllamaAssessment:
        """Record an already-running daemon. This does not stop or repair it."""
        identity, strength = observe_runtime_identity(Path(observation.executable_path))
        observed = ExistingOllamaObservation(
            identified_by=observation.identified_by,
            executable_path=observation.executable_path,
            version_text=observation.version_text,
            endpoint=observation.endpoint,
            api_version=observation.api_version,
            cloud_disabled=observation.cloud_disabled,
            auto_update=observation.auto_update,
            runtime_identity_sha256=None if identity == "unresolved" else identity,
            identity_strength=strength,
        )
        return assess_existing(
            observed,
            recipe or pinned_recipe(),
            execution_environment_fingerprint=execution_environment_fingerprint,
            capacity_evidence_id=capacity_evidence_id,
            observed_at=self._clock.now(),
            verify_seconds=None,
        )

    def start(
        self,
        prefix: Path,
        *,
        port: int,
        recipe: OllamaRuntimeRecipe,
        execution_environment_fingerprint: str,
        capacity_evidence_id: str,
        footprint_bytes: int,
        install_seconds: float,
        timeout_seconds: float = 5,
    ) -> OllamaAssessment:
        """Start ``ollama serve`` from the owned prefix and read its version."""
        if self._spawned is not None:
            return _failed("owned daemon is already started")
        if _store_has_files(prefix / "models"):
            return _failed("model store is not empty")
        if port < 1 or port > 65535:
            return _failed("daemon port is outside 1..65535")
        endpoint = f"http://127.0.0.1:{port}"
        env = daemon_environment(prefix, port)
        if env.get("OLLAMA_NO_CLOUD") != "1":
            return _failed("cloud disable flag is missing")
        binary = str(prefix / "bin" / "ollama")
        probed = self._runner.run(
            [binary, "--version"], cwd=str(prefix), timeout=10, env=env
        )
        if probed.timed_out or probed.returncode != 0 or not probed.stdout.strip():
            return _failed("executable version was not reported")
        logs = prefix / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        try:
            spawned = self._runner.spawn(
                [binary, "serve"],
                cwd=str(prefix),
                env=env,
                stdout_path=logs / "daemon.stdout",
                stderr_path=logs / "daemon.stderr",
            )
        except FileNotFoundError:
            return _failed("owned executable is missing")
        self._spawned = spawned
        self._prefix = prefix
        self._port = port
        self._recipe = recipe
        self._fingerprint = execution_environment_fingerprint
        self._capacity = capacity_evidence_id
        self._footprint = footprint_bytes
        self._install_seconds = install_seconds
        version, verify_seconds = self._poll_version(endpoint, timeout_seconds)
        assessment = assess_managed(
            recipe=recipe,
            version_text=probed.stdout.strip(),
            api_version=version,
            endpoint=endpoint,
            cloud_disabled=True,
            artifact_sha256=recipe.artifact_sha256,
            execution_environment_fingerprint=execution_environment_fingerprint,
            capacity_evidence_id=capacity_evidence_id,
            observed_at=self._clock.now(),
            startup_seconds=time.monotonic() - started,
            verify_seconds=verify_seconds,
            footprint_bytes=footprint_bytes,
            install_seconds=install_seconds,
            lifecycle="started",
        )
        if assessment.substrate is None:
            self.stop()
        return assessment

    def stop(self) -> str:
        """Stop the daemon this object started. An unknown pid is left alone."""
        spawned = self._spawned
        self._spawned = None
        if spawned is None:
            return "stopped"
        self._runner.terminate(spawned, grace_seconds=2)
        return "stopped"

    def restart(
        self,
        *,
        timeout_seconds: float = 5,
    ) -> OllamaAssessment:
        """Stop and start the same owned prefix. This does not load a model."""
        prefix = self._prefix
        port = self._port
        recipe = self._recipe
        if prefix is None or port is None or recipe is None:
            return _failed("owned daemon has no prefix to restart")
        footprint = self._footprint or 0
        install_seconds = self._install_seconds or 0
        fingerprint = self._fingerprint
        capacity = self._capacity
        self.stop()
        return self.start(
            prefix,
            port=port,
            recipe=recipe,
            execution_environment_fingerprint=fingerprint,
            capacity_evidence_id=capacity,
            footprint_bytes=footprint,
            install_seconds=install_seconds,
            timeout_seconds=timeout_seconds,
        )

    def _poll_version(
        self, endpoint: str, timeout_seconds: float
    ) -> tuple[str | None, float | None]:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            started = time.monotonic()
            version = self._client.api_version(endpoint, timeout=0.2)
            elapsed = time.monotonic() - started
            if version is not None:
                return version, elapsed
            time.sleep(0.05)
        return None, None


def daemon_environment(prefix: Path, port: int) -> dict[str, str]:
    """Process-local bind, model dir, and cloud switch. No inherited cloud key."""
    env: dict[str, str] = {}
    for key in ("PATH", "TMPDIR", "LANG", "LC_ALL"):
        if key in os.environ:
            env[key] = os.environ[key]
    root = str(prefix)
    env["HOME"] = root
    env["OLLAMA_HOST"] = f"127.0.0.1:{port}"
    env["OLLAMA_MODELS"] = str(prefix / "models")
    env["OLLAMA_NO_CLOUD"] = "1"
    return env


def _store_has_files(models: Path) -> bool:
    if not models.exists():
        return False
    return any(filenames for _dirpath, _dirnames, filenames in os.walk(models))


def _failed(reason: str) -> OllamaAssessment:
    return OllamaAssessment(
        FailureCode.VERIFICATION_FAILED,
        SupportState.VERIFICATION_FAILED,
        reason,
    )
