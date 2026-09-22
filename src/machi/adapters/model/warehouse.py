"""Owned warehouse. Staging is not a stored artifact."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from machi.adapters.model.local import sha256_file
from machi.kernel.errors import ValidationError
from machi.kernel.schema import to_dict
from machi.model.contracts import ArtifactLifecycle, ModelArtifact, ModelFileRecord

_MANIFEST = ".machi-model.json"


def warehouse_root(state_root: Path) -> Path:
    return state_root / "models" / "warehouse"


def staging_root(state_root: Path) -> Path:
    return state_root / "models" / "staging"


def cache_root(state_root: Path) -> Path:
    return state_root / "models" / "cache"


def load_artifact(state_root: Path, artifact_id: str) -> ModelArtifact | None:
    path = warehouse_root(state_root) / artifact_id / _MANIFEST
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("purpose") != "model_artifact":
        return None
    from machi.kernel.schema import from_dict

    record = from_dict(payload, extra="ignore")
    if not isinstance(record, ModelArtifact):
        return None
    return record


def verify_stored(state_root: Path, artifact: ModelArtifact) -> bool:
    """Re-read hashes once. A mismatch is corrupt, not a silent repair."""
    if artifact.lifecycle is not ArtifactLifecycle.STORED:
        return False
    root = warehouse_root(state_root) / artifact.artifact_id
    for item in artifact.files:
        path = root / item.relative_path
        if not path.is_file() or path.is_symlink():
            return False
        if path.stat().st_size != item.size_bytes:
            return False
        if sha256_file(path) != item.sha256:
            return False
    return True


def promote(
    state_root: Path,
    artifact: ModelArtifact,
    staged_files: Path,
) -> Path:
    """Rename a verified staging directory into the warehouse."""
    final = warehouse_root(state_root) / artifact.artifact_id
    if final.exists():
        raise ValidationError("warehouse artifact already exists")
    final.parent.mkdir(parents=True, exist_ok=True)
    payload = to_dict(artifact)
    payload["purpose"] = "model_artifact"
    manifest = staged_files / _MANIFEST
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    staged_files.rename(final)
    return final


def prepare_staging(state_root: Path, artifact_id: str) -> Path:
    """Replace an incomplete staging directory. Never touch the warehouse."""
    staging = staging_root(state_root) / artifact_id
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    return staging


def file_records(
    root: Path,
    relative_paths: tuple[str, ...],
) -> tuple[ModelFileRecord, ...]:
    records: list[ModelFileRecord] = []
    for relative in relative_paths:
        path = root / relative
        records.append(
            ModelFileRecord(
                relative_path=relative,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return tuple(records)


def list_stored(state_root: Path) -> tuple[str, ...]:
    root = warehouse_root(state_root)
    if not root.is_dir():
        return ()
    found: list[str] = []
    for child in sorted(root.iterdir()):
        if (child / _MANIFEST).is_file():
            found.append(child.name)
    return tuple(found)
