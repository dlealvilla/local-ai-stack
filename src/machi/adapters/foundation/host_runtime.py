"""Read the ROCm userland the pinned recipe needs. No package install."""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from machi.adapters.foundation.process import NativeProcessRunner
from machi.discover.contracts import AcceleratorObservation
from machi.foundation.policy import ROCM700_LIBS
from machi.foundation.recipe import HostRuntimeFacts

_MODEL_ARCH = (
    ("MI350", "gfx950"),
    ("MI300", "gfx942"),
    ("MI250", "gfx90a"),
)


def observe_host_runtime(
    accelerators: AcceleratorObservation | None = None,
    *,
    runner: NativeProcessRunner | None = None,
    version_text: str | None = None,
    library_roots: tuple[Path, ...] | None = None,
    glibc_text: str | None = None,
    rocminfo_text: str | None = None,
) -> HostRuntimeFacts:
    """Observe ROCm, glibc, gfx, and recipe sonames. Missing facts stay unset."""
    if sys.platform != "linux" and version_text is None and library_roots is None:
        return HostRuntimeFacts()
    rocm = version_text if version_text is not None else _read_rocm_version()
    glibc = glibc_text if glibc_text is not None else _glibc_version()
    architecture = _architecture(accelerators, rocminfo_text, runner)
    roots = library_roots if library_roots is not None else _library_roots()
    present, prefix = _libraries(roots)
    return HostRuntimeFacts(
        rocm_version=rocm,
        glibc_version=glibc,
        accelerator_architecture=architecture,
        present_libraries=present,
        library_prefix=prefix,
    )


def _read_rocm_version() -> str | None:
    paths = [Path("/opt/rocm/.info/version")]
    opt = Path("/opt")
    if opt.is_dir():
        paths.extend(sorted(opt.glob("rocm*/.info/version")))
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return text.splitlines()[0].strip()
    return None


def _glibc_version() -> str | None:
    try:
        libc = ctypes.CDLL(None)
        reader = libc.gnu_get_libc_version
        reader.restype = ctypes.c_char_p
        raw = reader()
    except (AttributeError, OSError):
        return None
    if not raw:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace").strip()
    return str(raw).strip()


def _architecture(
    accelerators: AcceleratorObservation | None,
    rocminfo_text: str | None,
    runner: NativeProcessRunner | None,
) -> str | None:
    text = rocminfo_text
    if text is None and sys.platform == "linux":
        text = _rocminfo(runner or NativeProcessRunner())
    found = _gfx_token(text or "")
    if found is not None:
        return found
    if accelerators is None:
        return None
    for device in accelerators.devices:
        if not device.model_name:
            continue
        for needle, arch in _MODEL_ARCH:
            if needle in device.model_name:
                return arch
    return None


def _rocminfo(runner: NativeProcessRunner) -> str:
    result = runner.run(["rocminfo"], cwd="/", timeout=20)
    if result.timed_out or result.returncode != 0:
        return ""
    return result.stdout


def _gfx_token(text: str) -> str | None:
    for token in text.replace(":", " ").split():
        if token.startswith("gfx") and token[3:].isalnum():
            return token
    return None


def _library_roots() -> tuple[Path, ...]:
    roots = [
        Path("/opt/rocm/lib"),
        Path("/usr/lib"),
        Path("/usr/lib64"),
        Path("/lib"),
        Path("/lib64"),
    ]
    opt = Path("/opt")
    if opt.is_dir():
        roots.extend(sorted(opt.glob("rocm*/lib")))
    return tuple(roots)


def _libraries(roots: tuple[Path, ...]) -> tuple[frozenset[str], str]:
    present: set[str] = set()
    prefixes: list[str] = []
    for soname in ROCM700_LIBS:
        directory = _find_soname(roots, soname)
        if directory is None:
            continue
        present.add(soname)
        if directory not in prefixes and not _default_linker_dir(directory):
            prefixes.append(directory)
    prefix = ":".join(prefixes) if prefixes else "none"
    return frozenset(present), prefix


def _find_soname(roots: tuple[Path, ...], soname: str) -> str | None:
    for root in roots:
        if not root.is_dir():
            continue
        direct = root / soname
        if direct.is_file():
            return str(root)
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for child in children:
            if child.name == soname or child.name.startswith(soname + "."):
                return str(root)
    return None


def _default_linker_dir(directory: str) -> bool:
    return directory in {"/usr/lib", "/usr/lib64", "/lib", "/lib64"}
