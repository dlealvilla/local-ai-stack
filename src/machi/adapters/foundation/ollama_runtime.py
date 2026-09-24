"""Owned Ollama prefix and daemon lifecycle. No model pull and no inference."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

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
from machi.kernel.errors import ValidationError

_OWNER = "machi"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_REQUIRED_BINARY = "bin/ollama"
_REQUIRED_LIBRARY = "lib/ollama"


@dataclass(frozen=True, slots=True)
class InstalledPrefix:
    """One owned tree. Empty models directory means nothing was pulled."""

    environment_id: str
    prefix: Path
    footprint_bytes: int
    install_seconds: float


@dataclass(frozen=True, slots=True)
class PrefixRefusal:
    """The archive was not installed. Host directories stay untouched."""

    failure: FailureCode
    support: SupportState
    reason: str


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
        archive: bytes,
        recipe: OllamaRuntimeRecipe,
        *,
        safe_bytes: int | None = None,
    ) -> InstalledPrefix | PrefixRefusal:
        """Extract a checksummed archive under the state root, or refuse."""
        digest = hashlib.sha256(archive).hexdigest()
        if digest != recipe.artifact_sha256:
            return PrefixRefusal(
                FailureCode.PACKAGE_DOWNLOAD_FAILED,
                SupportState.PROVISIONING_FAILED,
                "artifact checksum does not match the pinned recipe",
            )
        environment_id = _environment_id(recipe)
        root = _owned_root(state_root, environment_id)
        prefix = root / "ollama"
        if root.exists():
            return _reuse_or_refuse(root, prefix, recipe)
        started = time.monotonic()
        root.mkdir(parents=True)
        try:
            _extract(prefix, archive)
            _write_cloud_config(prefix)
            footprint = _tree_bytes(prefix)
            if safe_bytes is not None and footprint > safe_bytes:
                raise ValidationError("safe storage does not cover the prefix")
            _write_manifest(state_root, root, environment_id, recipe, footprint)
        except (ValidationError, tarfile.TarError, OSError) as exc:
            _discard(root)
            reason = str(exc) if str(exc) else "prefix extraction failed"
            return PrefixRefusal(
                FailureCode.PACKAGE_INSTALL_FAILED,
                SupportState.PROVISIONING_FAILED,
                reason[:240],
            )
        return InstalledPrefix(
            environment_id=environment_id,
            prefix=prefix,
            footprint_bytes=footprint,
            install_seconds=time.monotonic() - started,
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
        return assess_existing(
            observation,
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


def _environment_id(recipe: OllamaRuntimeRecipe) -> str:
    digest = hashlib.sha256(
        f"{recipe.recipe_id}\n{recipe.artifact_sha256}".encode()
    ).hexdigest()
    return "renv_" + digest[:16]


def _owned_root(state_root: Path, environment_id: str) -> Path:
    base = (state_root / "foundation" / "environments").resolve()
    root = (base / environment_id).resolve()
    if root.parent != base:
        raise ValidationError("environment path escaped owned storage")
    if environment_id.startswith("."):
        raise ValidationError("environment id is not owned")
    return root


def _reuse_or_refuse(
    root: Path,
    prefix: Path,
    recipe: OllamaRuntimeRecipe,
) -> InstalledPrefix | PrefixRefusal:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return PrefixRefusal(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "existing prefix has no ownership manifest",
        )
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return PrefixRefusal(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "existing prefix manifest is unreadable",
        )
    if not isinstance(loaded, dict) or loaded.get("owned") is not True:
        return PrefixRefusal(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "existing prefix is not owned",
        )
    if loaded.get("artifact_sha256") != recipe.artifact_sha256:
        return PrefixRefusal(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "existing prefix checksum does not match this recipe",
        )
    identity = loaded.get("environment_id")
    measured = loaded.get("measured_bytes")
    if not isinstance(identity, str) or not isinstance(measured, int):
        return PrefixRefusal(
            FailureCode.VERIFICATION_FAILED,
            SupportState.VERIFICATION_FAILED,
            "existing prefix manifest is incomplete",
        )
    return InstalledPrefix(
        environment_id=identity,
        prefix=prefix,
        footprint_bytes=measured,
        install_seconds=0,
    )


def _extract(prefix: Path, archive: bytes) -> None:
    payload = _inflate(archive)
    prefix.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as handle:
        for member in handle.getmembers():
            destination = _member_destination(prefix, member)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValidationError("archive links are refused")
            source = handle.extractfile(member)
            if source is None:
                raise ValidationError("archive member is unreadable")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read())
            if member.name == _REQUIRED_BINARY:
                destination.chmod(0o755)
    binary = prefix / "bin" / "ollama"
    library = prefix / "lib" / "ollama"
    if not binary.is_file() or not library.is_dir():
        raise ValidationError("archive is missing the prefix-relative runtime layout")
    (prefix / "models").mkdir(exist_ok=True)
    (prefix / "logs").mkdir(exist_ok=True)


def _inflate(archive: bytes) -> bytes:
    """Unpack the official zstd asset with the zstd tool. Plain tar is already bytes."""
    if not archive.startswith(_ZSTD_MAGIC):
        return archive
    try:
        completed = subprocess.run(
            ["zstd", "-d", "-c"],
            input=archive,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ValidationError(
            "zstd is required to unpack the official archive"
        ) from exc
    if completed.returncode != 0 or not completed.stdout:
        raise ValidationError("zstd could not unpack the official archive")
    return bytes(completed.stdout)


def _member_destination(prefix: Path, member: tarfile.TarInfo) -> Path:
    name = member.name
    if name.startswith(("/", "\\")):
        raise ValidationError("archive member is absolute")
    parts = Path(name).parts
    if ".." in parts or not parts:
        raise ValidationError("archive member escapes the prefix")
    root = prefix.resolve()
    destination = (prefix / name).resolve()
    if destination != root and root not in destination.parents:
        raise ValidationError("archive member escapes the prefix")
    return destination


def _write_cloud_config(prefix: Path) -> None:
    payload = json.dumps({"disable_ollama_cloud": True}, indent=2) + "\n"
    for relative in ("config/server.json", ".ollama/server.json"):
        path = prefix / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def _write_manifest(
    state_root: Path,
    root: Path,
    environment_id: str,
    recipe: OllamaRuntimeRecipe,
    footprint: int,
) -> None:
    payload = {
        "environment_id": environment_id,
        "recipe_id": recipe.recipe_id,
        "artifact_sha256": recipe.artifact_sha256,
        "owner": _OWNER,
        "owned": True,
        "relative_prefix": f"foundation/environments/{environment_id}/ollama",
        "measured_bytes": footprint,
        "models_reserved": True,
    }
    (root / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    registry = state_root / "foundation" / "environments" / "registry.json"
    current: list[str] = []
    if registry.is_file():
        loaded = json.loads(registry.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            current = [str(item) for item in loaded]
    if environment_id not in current:
        current.append(environment_id)
    registry.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


def _tree_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            file = Path(dirpath) / name
            if file.is_symlink():
                continue
            total += file.stat().st_size
    return total


def _store_has_files(models: Path) -> bool:
    if not models.exists():
        return False
    return any(filenames for _dirpath, _dirnames, filenames in os.walk(models))


def _discard(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def _failed(reason: str) -> OllamaAssessment:
    return OllamaAssessment(
        FailureCode.VERIFICATION_FAILED,
        SupportState.VERIFICATION_FAILED,
        reason,
    )
