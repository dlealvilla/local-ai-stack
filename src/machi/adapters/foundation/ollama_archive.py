"""Owned Ollama archive realization. No model bytes and no shell."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from machi.foundation.contracts import FailureCode, SupportState
from machi.foundation.ollama import OllamaRuntimeRecipe, runtime_environment_id
from machi.kernel.errors import ValidationError

_OWNER = "machi"
_ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
_CHUNK = 1024 * 1024
_MAX_MEMBERS = 10_000
_MAX_NAME = 240
_MAX_MEMBER = 2 * 1024 * 1024 * 1024
_CLOUD_CONFIG = '{"disable_ollama_cloud": true}\n'
_CONFIG_BYTES = len(_CLOUD_CONFIG.encode()) * 2
_MANIFEST_BUDGET = 4096
_REQUIRED_BINARY = "bin/ollama"
_STDERR_LIMIT = 4096


class RegistryCorruptError(Exception):
    """The environment index is not a list of id strings."""


@dataclass(frozen=True, slots=True)
class InstallFaults:
    """Test seams. Production calls leave these unset."""

    fail_promote: bool = False
    fail_parent_fsync: bool = False
    registry_fault: str | None = None
    extra_bytes: bytes = b""
    steps: list[str] | None = None


@dataclass(frozen=True, slots=True)
class InstalledPrefix:
    """One owned tree. Empty models directory means nothing was pulled."""

    environment_id: str
    prefix: Path
    footprint_bytes: int
    install_seconds: float


@dataclass(frozen=True, slots=True)
class PrefixRefusal:
    """The archive was not installed, or promotion needs reconciliation."""

    failure: FailureCode
    support: SupportState
    reason: str
    environment_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecompressorEvidence:
    """Tooling provenance. Not a model-qualification input."""

    name: str
    version: str


class SystemZstdDecompressor:
    """Stream an existing zstd tool. Does not install one."""

    def __init__(
        self, executable: str | None = None, timeout_seconds: float = 5.0
    ) -> None:
        self._executable = executable
        self.timeout_seconds = timeout_seconds

    def preflight(self) -> DecompressorEvidence | PrefixRefusal:
        path = self._executable or shutil.which("zstd")
        if not path:
            return PrefixRefusal(
                FailureCode.PREREQUISITE_BLOCKED,
                SupportState.BLOCKED_BY_PREREQUISITE,
                "zstd decompressor is not available",
            )
        try:
            finished = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return PrefixRefusal(
                FailureCode.PREREQUISITE_BLOCKED,
                SupportState.BLOCKED_BY_PREREQUISITE,
                "zstd decompressor did not respond",
            )
        if finished.returncode != 0:
            return PrefixRefusal(
                FailureCode.PREREQUISITE_BLOCKED,
                SupportState.BLOCKED_BY_PREREQUISITE,
                "zstd decompressor is not usable",
            )
        version = (finished.stdout or finished.stderr).strip().splitlines()
        text = version[0][:80] if version else "unknown"
        self._executable = path
        return DecompressorEvidence("zstd", text)

    def open_stream(self, source: Path) -> subprocess.Popen[bytes]:
        path = self._executable or shutil.which("zstd")
        if not path:
            raise ValidationError("zstd decompressor is not available")
        return subprocess.Popen(
            [path, "-d", "-c", str(source)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def observe_runtime_identity(executable: Path) -> tuple[str, str]:
    """Hash the executable and, when present, the adjacent library tree."""
    if not executable.is_file() or executable.is_symlink():
        return "unresolved", "absent"
    library = _library_dir(executable)
    files = [executable]
    if library is not None:
        files.extend(_regular_files(library))
    if len(files) > _MAX_MEMBERS:
        return _hash_files([executable]), "partial_executable"
    if library is None or len(files) == 1:
        return _hash_files(files), "partial_executable"
    return _hash_files(files), "runtime_closure"


@dataclass(frozen=True, slots=True)
class RegistryInspection:
    """Index state. A corrupt file is not treated as an empty index."""

    corrupt: bool
    reason: str
    unregistered: tuple[str, ...]


def individual_member_refusal(size: int) -> str | None:
    """Per-member ceiling. Aggregate size is not judged here."""
    if size < 0 or size > _MAX_MEMBER:
        return "archive member size exceeds the extraction bound"
    return None


def generated_metadata_budget() -> int:
    """Manifest and cloud-config bytes we ourselves write. Not the registry."""
    return _CONFIG_BYTES + _MANIFEST_BUDGET


def projected_registry_temp_bytes(current: list[str], environment_id: str) -> int:
    """Bytes of the temp file written beside the existing index."""
    identifiers = list(current)
    if environment_id not in identifiers:
        identifiers.append(environment_id)
    return len(_registry_payload(identifiers))


def provisioning_peak(
    *,
    staged_bytes: int,
    declared_bytes: int,
    metadata_bytes: int,
    registry_temp_bytes: int,
) -> int:
    """Owned bytes present together before the staged archive is removed."""
    return staged_bytes + declared_bytes + metadata_bytes + registry_temp_bytes


def inspect_environment_index(state_root: Path) -> RegistryInspection:
    """Read the index without raising. Corruption stays visible."""
    base = state_root / "foundation" / "environments"
    if not base.is_dir():
        return RegistryInspection(False, "none", ())
    try:
        registered = set(_read_registry(base / "registry.json"))
    except RegistryCorruptError:
        return RegistryInspection(True, "environment index is corrupt", ())
    found: list[str] = []
    for child in sorted(base.iterdir()):
        manifest = child / "manifest.json"
        if not child.is_dir() or not _owned_manifest(manifest, child.name):
            continue
        if child.name not in registered:
            found.append(child.name)
    return RegistryInspection(False, "none", tuple(found))


def unregistered_owned_generations(state_root: Path) -> tuple[str, ...]:
    """Owned generations whose valid index does not cite them."""
    return inspect_environment_index(state_root).unregistered


def realize_prefix(
    state_root: Path,
    archive_path: Path,
    recipe: OllamaRuntimeRecipe,
    *,
    safe_bytes: int | None,
    decompressor: SystemZstdDecompressor | None = None,
    faults: InstallFaults | None = None,
) -> InstalledPrefix | PrefixRefusal:
    """Stage, verify, and promote one prefix. Missing SAFE bytes refuse."""
    import time

    if safe_bytes is None:
        return PrefixRefusal(
            FailureCode.INSUFFICIENT_CAPACITY,
            SupportState.INSUFFICIENT_CAPACITY,
            "safe storage bound was not provided",
        )
    if safe_bytes < 1:
        return PrefixRefusal(
            FailureCode.INSUFFICIENT_CAPACITY,
            SupportState.INSUFFICIENT_CAPACITY,
            "extraction bound must be positive",
        )
    if not archive_path.is_file():
        return PrefixRefusal(
            FailureCode.PACKAGE_DOWNLOAD_FAILED,
            SupportState.PROVISIONING_FAILED,
            "local runtime archive is missing",
        )
    observed = archive_path.stat().st_size
    if observed != recipe.artifact_bytes:
        return PrefixRefusal(
            FailureCode.PACKAGE_DOWNLOAD_FAILED,
            SupportState.PROVISIONING_FAILED,
            "artifact length does not match the frozen recipe",
        )
    if safe_bytes < recipe.artifact_bytes:
        return PrefixRefusal(
            FailureCode.INSUFFICIENT_CAPACITY,
            SupportState.INSUFFICIENT_CAPACITY,
            "safe storage does not cover the staged artifact",
        )
    tool = decompressor or SystemZstdDecompressor()
    faults = faults or InstallFaults()
    staging = _staging_dir(state_root)
    try:
        staging.mkdir(parents=True)
        (staging / ".machi-stage").write_text(_OWNER, encoding="utf-8")
        staged = staging / "artifact.bin"
        try:
            digest, copied = _copy_and_hash(
                archive_path,
                staged,
                recipe.artifact_bytes,
                faults.extra_bytes,
            )
        except ArchiveLengthError as exc:
            return PrefixRefusal(
                FailureCode.PACKAGE_DOWNLOAD_FAILED,
                SupportState.PROVISIONING_FAILED,
                str(exc),
            )
        if copied != recipe.artifact_bytes:
            return PrefixRefusal(
                FailureCode.PACKAGE_DOWNLOAD_FAILED,
                SupportState.PROVISIONING_FAILED,
                "artifact length does not match the frozen recipe",
            )
        if digest != recipe.artifact_sha256:
            return PrefixRefusal(
                FailureCode.PACKAGE_DOWNLOAD_FAILED,
                SupportState.PROVISIONING_FAILED,
                "artifact checksum does not match the pinned recipe",
            )
        environment_id = runtime_environment_id(recipe)
        final = _owned_root(state_root, environment_id)
        try:
            current_ids = _read_registry(
                state_root / "foundation" / "environments" / "registry.json"
            )
        except RegistryCorruptError:
            return PrefixRefusal(
                FailureCode.VERIFICATION_FAILED,
                SupportState.RECONCILE_REQUIRED,
                "environment index is corrupt",
            )
        if final.exists():
            return _reuse_or_refuse(final, final / "ollama", recipe)
        zstd = _is_zstd(staged)
        evidence: DecompressorEvidence | None = None
        if zstd:
            checked = tool.preflight()
            if isinstance(checked, PrefixRefusal):
                return checked
            evidence = checked
        declared = _preflight(staged, zstd, tool)
        staged_size = staged.stat().st_size
        registry_temp = projected_registry_temp_bytes(current_ids, environment_id)
        peak = provisioning_peak(
            staged_bytes=staged_size,
            declared_bytes=declared,
            metadata_bytes=generated_metadata_budget(),
            registry_temp_bytes=registry_temp,
        )
        if peak > safe_bytes:
            return PrefixRefusal(
                FailureCode.INSUFFICIENT_CAPACITY,
                SupportState.INSUFFICIENT_CAPACITY,
                "safe storage does not cover the provisioning peak",
            )
        started = time.monotonic()
        generation = staging / "generation"
        extracted = generation / "ollama"
        written = _extract(extracted, staged, zstd, tool, declared)
        _write_cloud_config(extracted)
        _write_manifest(
            generation,
            environment_id,
            recipe,
            written,
            evidence,
        )
        footprint = _tree_bytes(generation)
        occupied = staged_size + footprint + registry_temp
        if occupied > safe_bytes or written > declared:
            raise ValidationError("safe storage does not cover the provisioning peak")
        _fsync_tree(generation)
        if faults.fail_promote:
            raise ValidationError("promotion failed")
        final.parent.mkdir(parents=True, exist_ok=True)
        generation.replace(final)
        _mark(faults, "rename")
        try:
            if faults.fail_parent_fsync:
                raise OSError("parent fsync failed")
            _fsync_directory(final.parent)
        except OSError:
            return PrefixRefusal(
                FailureCode.PROMOTED_UNREGISTERED,
                SupportState.RECONCILE_REQUIRED,
                "generation promoted but the parent directory was not made durable",
                environment_id,
            )
        _mark(faults, "parent_fsync")
        try:
            _register(state_root, environment_id, faults.registry_fault)
            _mark(faults, "registry")
        except RegistryCorruptError:
            return PrefixRefusal(
                FailureCode.VERIFICATION_FAILED,
                SupportState.RECONCILE_REQUIRED,
                "environment index is corrupt",
                environment_id,
            )
        except OSError:
            return PrefixRefusal(
                FailureCode.PROMOTED_UNREGISTERED,
                SupportState.RECONCILE_REQUIRED,
                "generation promoted but the environment index was not updated",
                environment_id,
            )
        return InstalledPrefix(
            environment_id=environment_id,
            prefix=final / "ollama",
            footprint_bytes=footprint,
            install_seconds=time.monotonic() - started,
        )
    except (ValidationError, tarfile.TarError, OSError) as exc:
        reason = str(exc) if str(exc) else "prefix extraction failed"
        return PrefixRefusal(
            FailureCode.PACKAGE_INSTALL_FAILED,
            SupportState.PROVISIONING_FAILED,
            reason[:240],
        )
    finally:
        _discard_staging(staging, state_root)


def _preflight(
    staged: Path,
    zstd: bool,
    tool: SystemZstdDecompressor,
) -> int:
    declared = 0
    count = 0
    handle, process = _open_tar(staged, zstd, tool)
    try:
        for member in handle:
            count += 1
            _reject_member(member)
            if member.isfile():
                declared += member.size
            if count > _MAX_MEMBERS:
                raise ValidationError("archive member count exceeds the limit")
    finally:
        _close_tar(handle, process)
    return declared


def _extract(
    prefix: Path,
    staged: Path,
    zstd: bool,
    tool: SystemZstdDecompressor,
    declared: int,
) -> int:
    prefix.mkdir(parents=True)
    written = 0
    count = 0
    handle, process = _open_tar(staged, zstd, tool)
    try:
        for member in handle:
            count += 1
            _reject_member(member)
            if count > _MAX_MEMBERS:
                raise ValidationError("archive member count exceeds the limit")
            relative = _relative_name(member.name)
            destination = _destination(prefix, relative)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            source = handle.extractfile(member)
            if source is None:
                raise ValidationError("archive member is unreadable")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as outbound:
                remaining = member.size
                while remaining > 0:
                    chunk = source.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    written += len(chunk)
                    if written > declared:
                        raise ValidationError(
                            "archive extracted size exceeds the extraction bound"
                        )
                    outbound.write(chunk)
            mode = 0o755 if relative.as_posix() == _REQUIRED_BINARY else 0o644
            destination.chmod(mode)
    finally:
        _close_tar(handle, process)
    binary = prefix / "bin" / "ollama"
    library = prefix / "lib" / "ollama"
    if not binary.is_file() or not library.is_dir():
        raise ValidationError("archive is missing the prefix-relative runtime layout")
    (prefix / "models").mkdir(exist_ok=True)
    (prefix / "logs").mkdir(exist_ok=True)
    return written


def _open_tar(
    staged: Path,
    zstd: bool,
    tool: SystemZstdDecompressor,
) -> tuple[tarfile.TarFile, _TimedChild | None]:
    if not zstd:
        return tarfile.open(staged, "r|"), None
    process = tool.open_stream(staged)
    if process.stdout is None:
        process.kill()
        raise ValidationError("zstd decompressor produced no stream")
    child = _TimedChild(process, tool.timeout_seconds)
    return tarfile.open(fileobj=process.stdout, mode="r|"), child


class _TimedChild:
    """Kills a decompressor when its deadline passes, even if a pipe stays open."""

    def __init__(
        self, process: subprocess.Popen[bytes], timeout_seconds: float
    ) -> None:
        self.process = process
        self.timeout_seconds = timeout_seconds
        self.timed_out = False
        self._timer = threading.Timer(timeout_seconds, self._expire)
        self._timer.daemon = True
        self._timer.start()

    def _expire(self) -> None:
        self.timed_out = True
        with contextlib.suppress(OSError):
            self.process.kill()

    def cancel(self) -> None:
        self._timer.cancel()


def _close_tar(handle: tarfile.TarFile, child: _TimedChild | None) -> None:
    handle.close()
    if child is None:
        return
    process = child.process
    if process.stdout is not None:
        process.stdout.close()
    child.cancel()
    stderr = _read_stderr_bounded(process)
    try:
        code = process.wait(timeout=child.timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        raise ValidationError("zstd decompressor timed out") from None
    if child.timed_out:
        raise ValidationError("zstd decompressor timed out")
    if code != 0:
        detail = stderr.decode("utf-8", errors="replace").strip()[:160]
        message = "zstd decompressor exited without success"
        if detail:
            message = f"{message}: {detail}"
        raise ValidationError(message)


def _read_stderr_bounded(process: subprocess.Popen[bytes]) -> bytes:
    """Drain stderr on another thread so a stuck pipe cannot hide the deadline."""
    if process.stderr is None:
        return b""
    kept: list[bytes] = []

    def _read() -> None:
        buffer = bytearray()
        assert process.stderr is not None
        while True:
            piece = process.stderr.read(1024)
            if not piece:
                break
            room = _STDERR_LIMIT - len(buffer)
            if room > 0:
                buffer.extend(piece[:room])
        kept.append(bytes(buffer))

    thread = threading.Thread(target=_read, daemon=True)
    thread.start()
    thread.join(1)
    return kept[0] if kept else b""


def _reject_member(member: tarfile.TarInfo) -> None:
    if len(member.name) > _MAX_NAME:
        raise ValidationError("archive member name exceeds the limit")
    _relative_name(member.name)
    if member.issym() or member.islnk():
        raise ValidationError("archive links are refused")
    if not member.isdir() and not member.isfile():
        raise ValidationError("archive special members are refused")
    if member.isfile():
        reason = individual_member_refusal(member.size)
        if reason is not None:
            raise ValidationError(reason)


def _relative_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError("archive member escapes the prefix")
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        raise ValidationError("archive member escapes the prefix")
    return PurePosixPath(*parts)


def _destination(prefix: Path, relative: PurePosixPath) -> Path:
    root = prefix.resolve()
    destination = (prefix / Path(*relative.parts)).resolve()
    if destination != root and root not in destination.parents:
        raise ValidationError("archive member escapes the prefix")
    return destination


def _is_zstd(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(len(_ZSTD_MAGIC)) == _ZSTD_MAGIC


class ArchiveLengthError(Exception):
    """The copied artifact is not the frozen length."""


def _copy_and_hash(
    source: Path, dest: Path, limit: int, extra: bytes = b""
) -> tuple[str, int]:
    """Copy at most the authorized length. Extra source bytes are a refusal."""
    digest = hashlib.sha256()
    copied = 0
    pending = extra
    with source.open("rb") as inbound, dest.open("wb") as outbound:
        while True:
            chunk = inbound.read(_CHUNK)
            if not chunk and pending:
                chunk = pending
                pending = b""
            if not chunk:
                break
            if copied + len(chunk) > limit:
                raise ArchiveLengthError("archive copy exceeded the authorized length")
            digest.update(chunk)
            outbound.write(chunk)
            copied += len(chunk)
    return digest.hexdigest(), copied


def _library_dir(executable: Path) -> Path | None:
    candidates = (
        executable.parent.parent / "lib" / "ollama",
        executable.parent / "lib" / "ollama",
    )
    for candidate in candidates:
        if candidate.is_dir() and not candidate.is_symlink():
            return candidate
    return None


def _regular_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in sorted(filenames):
            file = Path(dirpath) / name
            if file.is_symlink() or not file.is_file():
                continue
            found.append(file)
    return found


def _hash_files(files: list[Path]) -> str:
    digest = hashlib.sha256()
    common = Path(os.path.commonpath([str(file.resolve().parent) for file in files]))
    for file in files:
        relative = file.resolve().relative_to(common).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        with file.open("rb") as handle:
            while True:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    return digest.hexdigest()


def _write_cloud_config(prefix: Path) -> None:
    payload = _CLOUD_CONFIG
    for relative in ("config/server.json", ".ollama/server.json"):
        path = prefix / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def _write_manifest(
    generation: Path,
    environment_id: str,
    recipe: OllamaRuntimeRecipe,
    footprint: int,
    evidence: DecompressorEvidence | None,
) -> None:
    payload = {
        "environment_id": environment_id,
        "recipe_id": recipe.recipe_id,
        "version": recipe.version,
        "artifact_sha256": recipe.artifact_sha256,
        "owner": _OWNER,
        "owned": True,
        "relative_prefix": f"foundation/environments/{environment_id}/ollama",
        "measured_bytes": footprint,
        "models_reserved": True,
        "decompressor": evidence.name if evidence else "none",
        "decompressor_version": evidence.version if evidence else "none",
    }
    path = generation / "manifest.json"
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if len(text.encode()) > _MANIFEST_BUDGET:
        raise ValidationError("generation manifest exceeds its budget")
    path.write_text(text, encoding="utf-8")


def _register(state_root: Path, environment_id: str, fault: str | None) -> None:
    directory = state_root / "foundation" / "environments"
    directory.mkdir(parents=True, exist_ok=True)
    registry = directory / "registry.json"
    current = _read_registry(registry)
    if environment_id not in current:
        current.append(environment_id)
    payload = _registry_payload(current).decode()
    temporary = directory / f".registry-{os.getpid()}.tmp"
    try:
        if fault == "temp":
            raise OSError("registry temp failed")
        with temporary.open("w", encoding="utf-8") as handle:
            if fault == "write":
                raise OSError("registry write failed")
            handle.write(payload)
            handle.flush()
            if fault == "fsync":
                raise OSError("registry fsync failed")
            os.fsync(handle.fileno())
        if fault == "replace":
            raise OSError("registry replace failed")
        temporary.replace(registry)
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def _registry_payload(identifiers: list[str]) -> bytes:
    return (json.dumps(identifiers, indent=2) + "\n").encode()


def _read_registry(path: Path) -> list[str]:
    if not path.is_file():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RegistryCorruptError("environment index is corrupt") from exc
    wrong_shape = not isinstance(loaded, list) or any(
        not isinstance(item, str) for item in loaded
    )
    if wrong_shape:
        raise RegistryCorruptError("environment index is corrupt")
    return list(loaded)


def _owned_manifest(path: Path, directory_name: str) -> bool:
    """Parsed ownership. A matching substring is not proof."""
    if not path.is_file():
        return False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if not isinstance(loaded, dict):
        return False
    return (
        loaded.get("owner") == _OWNER
        and loaded.get("owned") is True
        and loaded.get("environment_id") == directory_name
    )


def _mark(faults: InstallFaults, step: str) -> None:
    if faults.steps is not None:
        faults.steps.append(step)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_tree(root: Path) -> None:
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            file = Path(dirpath) / name
            if file.is_symlink():
                continue
            descriptor = os.open(file, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        descriptor = os.open(dirpath, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _tree_bytes(root: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            file = Path(dirpath) / name
            if file.is_symlink():
                continue
            total += file.stat().st_size
    return total


def _staging_dir(state_root: Path) -> Path:
    base = (state_root / "foundation" / "staging").resolve()
    name = "stage_" + hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    staging = (base / name).resolve()
    if staging.parent != base:
        raise ValidationError("staging path escaped owned storage")
    return staging


def _owned_root(state_root: Path, environment_id: str) -> Path:
    base = (state_root / "foundation" / "environments").resolve()
    root = (base / environment_id).resolve()
    if root.parent != base or environment_id.startswith("."):
        raise ValidationError("environment path escaped owned storage")
    return root


def _reuse_or_refuse(
    root: Path, prefix: Path, recipe: OllamaRuntimeRecipe
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
    return InstalledPrefix(identity, prefix, measured, 0.0)


def _discard_staging(staging: Path, state_root: Path) -> None:
    if not staging.exists():
        return
    base = (state_root / "foundation" / "staging").resolve()
    resolved = staging.resolve()
    if resolved.parent != base:
        return
    marker = staging / ".machi-stage"
    if not marker.is_file() or marker.read_text(encoding="utf-8") != _OWNER:
        return
    shutil.rmtree(staging)
    if base.is_dir() and not any(base.iterdir()):
        base.rmdir()
