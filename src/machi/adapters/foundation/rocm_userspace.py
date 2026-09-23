"""Realize or verify the rocm700 userspace. No kernel and no global loader."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machi.foundation.policy import ROCM700_LIBS
from machi.foundation.recipe import HostRuntimeFacts, rocm700_userspace, version_line
from machi.kernel.errors import ValidationError

# Published ROCm 7.0 user/kernel matrix. 6.1 is not in this set.
_ACCEPTED_DRIVER_LINES = frozenset({(6, 2), (6, 3), (6, 4), (30, 10)})
_GREEN = "green"
_UNKNOWN_LICENSES = frozenset({"", "unknown", "unlicensed"})
_OWNER = "machi"


@dataclass(frozen=True, slots=True)
class ComponentRecord:
    """One redistributed userspace component. Size stays unset until measured."""

    name: str
    version: str
    soname: str
    provenance: str
    license_name: str
    classification: str
    reason: str
    required: bool = True
    size_bytes: int | None = None
    integrity: str | None = None


@dataclass(frozen=True, slots=True)
class AmdHostDevices:
    """Host prerequisites the provider must not install."""

    kernel_module: bool
    gpu_device: bool
    kfd: bool
    dri: bool


@dataclass(frozen=True, slots=True)
class UserspacePlan:
    """managed, verified, or refused. OCI is not a disposition."""

    disposition: str
    reason: str
    failure: str


@dataclass(frozen=True, slots=True)
class RealizedEnvironment:
    """Owned prefix. The future image builder reads this manifest."""

    environment_id: str
    prefix: Path
    measured_bytes: int
    manifest_path: Path


def driver_compatible(driver_line: str | None) -> bool:
    """True only for an accepted amdgpu major.minor line."""
    if driver_line is None:
        return False
    return version_line(driver_line) in _ACCEPTED_DRIVER_LINES


def minimum_components() -> tuple[ComponentRecord, ...]:
    """Sonames the pinned wheel loads. Sizes are unmeasured."""
    specs = (
        ("hip-runtime", "7.0", "libamdhip64.so.7", "MIT", "CLR hip runtime"),
        ("hiprtc", "7.0", "libhiprtc.so.7", "MIT", "libtorch_hip needs hiprtc"),
        ("rocblas", "7.0", "librocblas.so.5", "MIT", "libtorch_hip needs rocBLAS"),
        ("rocsolver", "7.0", "librocsolver.so.0", "BSD-3-Clause", "libtorch_hip"),
        ("miopen", "7.0", "libMIOpen.so.1", "MIT", "libtorch_hip needs MIOpen"),
        ("hipblas", "7.0", "libhipblas.so.3", "MIT", "vLLM and torch need hipBLAS"),
        ("hipfft", "7.0", "libhipfft.so.0", "MIT", "libtorch_hip needs hipFFT"),
        ("hiprand", "7.0", "libhiprand.so.1", "MIT", "libtorch_hip needs hipRAND"),
        ("hipsparse", "7.0", "libhipsparse.so.4", "MIT", "torch links hipSPARSE"),
        ("hipsolver", "7.0", "libhipsolver.so.1", "MIT", "torch links hipSOLVER"),
        (
            "hipsparselt",
            "7.0",
            "libhipsparselt.so.0",
            "MIT",
            "libtorch_hip needs hipSPARSELt",
        ),
        (
            "hipblaslt",
            "7.0",
            "libhipblaslt.so.1",
            "MIT",
            "vLLM and torch need hipBLASLt",
        ),
        ("rccl", "7.0", "librccl.so.1", "BSD-3-Clause", "libtorch_hip needs RCCL"),
        ("roctx", "7.0", "libroctx64.so.4", "MIT", "libtorch_python needs rocTX"),
        ("openmpi", "abi-40", "libmpi.so.40", "BSD-3-Clause", "torch global deps"),
        (
            "openmpi-cxx",
            "abi-40",
            "libmpi_cxx.so.40",
            "BSD-3-Clause",
            "torch python extension",
        ),
    )
    if tuple(item[2] for item in specs) != ROCM700_LIBS:
        raise ValidationError("userspace sonames drifted from the recipe")
    return tuple(
        ComponentRecord(
            name=name,
            version=version,
            soname=soname,
            provenance="vllm 0.18.0+rocm700 wheel linkage",
            license_name=license_name,
            classification=_GREEN,
            reason=reason,
        )
        for name, version, soname, license_name, reason in specs
    )


def measured_bytes(components: tuple[ComponentRecord, ...]) -> int | None:
    """None when any required size is still unknown."""
    total = 0
    for item in components:
        if not item.required:
            continue
        if item.size_bytes is None:
            return None
        total += item.size_bytes
    return total


def assess(host: HostRuntimeFacts, devices: AmdHostDevices) -> UserspacePlan:
    """Decide managed, verified, or refused. Does not install."""
    if not (
        devices.kernel_module and devices.gpu_device and devices.kfd and devices.dri
    ):
        return UserspacePlan(
            "refused",
            "host kernel, gpu, kfd, or dri is absent",
            "prerequisite_blocked",
        )
    if not driver_compatible(host.driver_line):
        return UserspacePlan(
            "refused",
            "amdgpu line is outside the rocm700 compatibility set",
            "driver_or_backend_incompatible",
        )
    kind, detail = rocm700_userspace(host, python_version="3.12")
    if kind == "refuse":
        reason = detail[1] if detail is not None else "userspace refused"
        failure = detail[0] if detail is not None else "driver_or_backend_incompatible"
        return UserspacePlan("refused", reason, failure)
    if kind == "verified":
        return UserspacePlan(
            "verified",
            "existing userspace matches the rocm700 recipe",
            "none",
        )
    return UserspacePlan(
        "managed",
        "host can realize the rocm700 recipe under owned storage",
        "none",
    )


def realize(
    state_root: Path,
    host: HostRuntimeFacts,
    devices: AmdHostDevices,
    components: tuple[ComponentRecord, ...],
    *,
    recipe_id: str,
    safe_bytes: int | None,
    writer: Callable[[Path, tuple[ComponentRecord, ...]], None],
) -> RealizedEnvironment | UserspacePlan:
    """Write an owned prefix or return a refusal. Never touches a global install."""
    plan = assess(host, devices)
    if plan.disposition != "managed":
        return plan
    blocked = _license_block(components)
    if blocked is not None:
        return blocked
    size = measured_bytes(components)
    if size is None:
        return UserspacePlan(
            "refused",
            "prefix footprint is unmeasured",
            "insufficient_capacity",
        )
    if safe_bytes is None or safe_bytes < size:
        return UserspacePlan(
            "refused",
            "safe storage does not cover the measured prefix",
            "insufficient_capacity",
        )
    environment_id = _environment_id(recipe_id, components)
    root = _owned_root(state_root, environment_id)
    if root.exists():
        raise ValidationError("environment already exists")
    root.mkdir(parents=True)
    try:
        writer(root, components)
        integrity = _hash_tree(root)
        _write_manifest(
            state_root,
            root,
            environment_id,
            recipe_id,
            components,
            integrity,
            size,
        )
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    return RealizedEnvironment(
        environment_id=environment_id,
        prefix=root,
        measured_bytes=size,
        manifest_path=root / "manifest.json",
    )


def remove_owned_environment(state_root: Path, environment_id: str) -> None:
    """Delete one owned environment. Leave every sibling in place."""
    root = _owned_root(state_root, environment_id)
    manifest = _read_manifest(root)
    if manifest.get("owned") is not True or manifest.get("owner") != _OWNER:
        raise ValidationError("refusing to delete an environment Machi does not own")
    shutil.rmtree(root)
    _drop_registry(state_root, environment_id)


def generation_process_env(prefix: Path) -> dict[str, str]:
    """Loader path for one generation. Does not change the process environment."""
    return {"LD_LIBRARY_PATH": str(prefix / "lib")}


def unrelated_process_env() -> dict[str, str]:
    """An unrelated process sees no managed prefix."""
    return {}


def _license_block(
    components: tuple[ComponentRecord, ...],
) -> UserspacePlan | None:
    for item in components:
        if not item.required:
            continue
        license_name = item.license_name.strip().lower()
        if item.classification != _GREEN or license_name in _UNKNOWN_LICENSES:
            return UserspacePlan(
                "refused",
                f"{item.name} needs license review",
                "package_resolution_failed",
            )
    return None


def _environment_id(
    recipe_id: str, components: tuple[ComponentRecord, ...]
) -> str:
    parts = [recipe_id]
    for item in components:
        parts.append(f"{item.name}:{item.version}:{item.soname}")
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return "renv_" + digest[:16]


def _owned_root(state_root: Path, environment_id: str) -> Path:
    base = (state_root / "foundation" / "environments").resolve()
    root = (base / environment_id).resolve()
    if root.parent != base:
        raise ValidationError("environment path escaped owned storage")
    return root


def _write_manifest(
    state_root: Path,
    root: Path,
    environment_id: str,
    recipe_id: str,
    components: tuple[ComponentRecord, ...],
    integrity: dict[str, str],
    size: int,
) -> None:
    payload = {
        "environment_id": environment_id,
        "recipe_id": recipe_id,
        "owner": _OWNER,
        "owned": True,
        "relative_prefix": f"foundation/environments/{environment_id}",
        "version": "7.0",
        "measured_bytes": size,
        "future_image_input": True,
        "loader": "process-local",
        "components": [
            {
                "name": item.name,
                "version": item.version,
                "soname": item.soname,
                "provenance": item.provenance,
                "license": item.license_name,
                "classification": item.classification,
                "reason": item.reason,
                "required": item.required,
                "size_bytes": item.size_bytes,
                "integrity": integrity.get(item.soname),
            }
            for item in components
        ],
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


def _read_manifest(root: Path) -> dict[str, object]:
    path = root / "manifest.json"
    if not path.is_file():
        raise ValidationError("owned environment manifest is missing")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValidationError("owned environment manifest is unreadable")
    return loaded


def _drop_registry(state_root: Path, environment_id: str) -> None:
    registry = state_root / "foundation" / "environments" / "registry.json"
    if not registry.is_file():
        return
    loaded = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        return
    kept = [str(item) for item in loaded if str(item) != environment_id]
    registry.write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")


def _hash_tree(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    lib = root / "lib"
    if not lib.is_dir():
        return found
    for path in sorted(lib.iterdir()):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        found[path.name] = digest
    return found
