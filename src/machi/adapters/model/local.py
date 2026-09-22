"""Copy a local tree into staging. External paths stay unowned."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from machi.kernel.errors import ValidationError

_MAX_FILES = 512
_MAX_DEPTH = 8


def list_local_files(root: Path) -> tuple[tuple[str, int], ...]:
    """Regular files only. Symlinks and special files fail closed."""
    base = root.resolve()
    found: list[tuple[str, int]] = []
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        current = Path(dirpath)
        depth = len(current.relative_to(base).parts)
        if depth > _MAX_DEPTH:
            raise ValidationError("local import exceeded the depth bound")
        dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
        for name in filenames:
            path = current / name
            _reject_unsafe(path, base)
            relative = path.relative_to(base).as_posix()
            found.append((relative, path.stat().st_size))
            if len(found) > _MAX_FILES:
                raise ValidationError("local import exceeded the file bound")
    return tuple(found)


def copy_files(root: Path, destination: Path, relative_paths: tuple[str, ...]) -> None:
    """Copy planned files. The destination must already exist."""
    base = root.resolve()
    for relative in relative_paths:
        source = (base / relative).resolve()
        if not str(source).startswith(str(base) + os.sep) and source != base:
            raise ValidationError("local import path escaped the source root")
        _reject_unsafe(base / relative, base)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_hashed(base / relative, target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_hashed(source: Path, target: Path) -> None:
    digest = hashlib.sha256()
    with source.open("rb") as incoming, target.open("wb") as outgoing:
        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
            digest.update(chunk)
            outgoing.write(chunk)


def _reject_unsafe(path: Path, root: Path) -> None:
    if path.is_symlink():
        raise ValidationError("local import rejected a symlink")
    try:
        info = path.lstat()
    except OSError as exc:
        raise ValidationError("local import could not stat a file") from exc
    mode = info.st_mode
    special = stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode) or stat.S_ISCHR(mode)
    if special or stat.S_ISBLK(mode):
        raise ValidationError("local import rejected a special file")
    if info.st_nlink > 1:
        raise ValidationError("local import rejected a hard link")
    if not stat.S_ISREG(mode):
        raise ValidationError("local import rejected a non-regular file")
    resolved = path.resolve()
    if not str(resolved).startswith(str(root.resolve()) + os.sep):
        raise ValidationError("local import path escaped the source root")
