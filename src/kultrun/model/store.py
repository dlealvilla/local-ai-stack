"""Kultrun-owned model artifact paths. Callers never choose destinations."""

from __future__ import annotations

import fcntl
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kultrun.kernel.errors import ValidationError
from kultrun.model.contracts import ArtifactId

MODELS_DIR = "models"
STAGING_DIR = "staging"
ARTIFACTS_DIR = "artifacts"
LOCKS_DIR = "locks"
MANIFEST_NAME = "MANIFEST.json"
_SAFE_NAME = re.compile(r"^[0-9a-f]{16,64}$")
_LOCK_NAME = re.compile(r"^[0-9a-f]{64}$")


class ModelArtifactStore:
    """Layout under ``{state_root}/models/``. Paths are never caller-supplied."""

    def __init__(self, state_root: Path) -> None:
        self._root = (Path(state_root) / MODELS_DIR).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / STAGING_DIR).mkdir(parents=True, exist_ok=True)
        (self._root / ARTIFACTS_DIR).mkdir(parents=True, exist_ok=True)
        (self._root / LOCKS_DIR).mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def staging_dir(self, identity_key: str) -> Path:
        if not _LOCK_NAME.fullmatch(identity_key):
            raise ValidationError("staging identity is not a safe filename")
        return self._child(self._root / STAGING_DIR, identity_key)

    def artifact_dir(self, artifact_id: ArtifactId) -> Path:
        parsed = ArtifactId.parse(artifact_id.value)
        token = parsed.value.split("_", 1)[1]
        if not _SAFE_NAME.fullmatch(token):
            raise ValidationError("artifact identity is not usable as a path")
        return self._child(self._root / ARTIFACTS_DIR, parsed.value)

    def manifest_path(self, artifact_id: ArtifactId) -> Path:
        return self.artifact_dir(artifact_id) / MANIFEST_NAME

    def relative_location(self, artifact_id: ArtifactId) -> str:
        return f"{ARTIFACTS_DIR}/{artifact_id.value}"

    def contains(self, path: Path) -> bool:
        """True when path is inside this model store after resolution."""
        resolved = path.resolve()
        root = self._root.resolve()
        return resolved == root or root in resolved.parents

    def _child(self, parent: Path, name: str) -> Path:
        if "/" in name or "\\" in name or name in {".", ".."}:
            raise ValidationError("path escapes the model store", name=name)
        parent = parent.resolve()
        if not self.contains(parent):
            raise ValidationError("path escapes the model store", path=str(parent))
        target = (parent / name).resolve()
        if target.parent != parent:
            raise ValidationError("path escapes the model store", path=str(target))
        return target

    @contextmanager
    def lock(self, identity_key: str) -> Iterator[None]:
        """Exclusive lock for one exact artifact identity. Not a scheduler."""
        if not _LOCK_NAME.fullmatch(identity_key):
            raise ValidationError("lock identity is not a safe filename")
        path = self._child(self._root / LOCKS_DIR, f"{identity_key}.lock")
        handle = path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
