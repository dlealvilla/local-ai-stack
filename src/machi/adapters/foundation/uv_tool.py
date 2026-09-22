"""Install a pinned uv binary under the owned state root.

This is bootstrap tooling for the managed environment. It is not the
vLLM runtime, and it is not system Python.
"""

from __future__ import annotations

import hashlib
import io
import platform
import stat
import tarfile
import urllib.request
from pathlib import Path

from machi.kernel.errors import ValidationError

UV_VERSION = "0.12.17"
_BASE = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}"
_ASSETS: dict[str, tuple[str, str]] = {
    "x86_64": (
        "uv-x86_64-unknown-linux-gnu.tar.gz",
        "fa82fd8dde8e8eefdecada6aa0889666556cfceb690d06e0c3bca49eb3070a63",
    ),
    "aarch64": (
        "uv-aarch64-unknown-linux-gnu.tar.gz",
        "d636d1b678e9e7f367ecb22b46bd1cabbed234d6bc3b4d96365d2b507f72f86c",
    ),
}


class ManagedUv:
    """Resolve a Machi-owned uv executable, downloading it once if needed."""

    def resolve(self, state_root: Path) -> str:
        machine = platform.machine().lower()
        if machine in {"amd64", "x86_64"}:
            key = "x86_64"
        elif machine in {"arm64", "aarch64"}:
            key = "aarch64"
        else:
            raise ValidationError("uv bootstrap does not support this machine")
        filename, digest = _ASSETS[key]
        tools = state_root / "foundation" / "tools"
        dest = tools / "uv"
        if dest.is_file() and _executable(dest):
            return str(dest)
        tools.mkdir(parents=True, exist_ok=True)
        payload = _download(f"{_BASE}/{filename}")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest:
            raise ValidationError("uv archive checksum did not match the pin")
        binary = _uv_member(payload)
        dest.write_bytes(binary)
        dest.chmod(dest.stat().st_mode | stat.S_IXUSR)
        return str(dest)


def _executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def _download(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            body = response.read()
        if not isinstance(body, bytes):
            raise ValidationError("uv archive download was not bytes")
        return body
    except OSError as exc:
        raise ValidationError("uv archive could not be downloaded") from exc


def _uv_member(payload: bytes) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                name = Path(member.name)
                if name.name != "uv" or not member.isfile():
                    continue
                if ".." in name.parts:
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                return extracted.read()
    except tarfile.TarError as exc:
        raise ValidationError("uv archive could not be read") from exc
    raise ValidationError("uv archive did not contain the uv binary")
