"""Which build is this, and was it built from anything traceable?

The Machi build tool writes ``BUILD.json`` into the package and the wheel
carries it. Absence is meaningful: a source checkout reports ``origin =
source`` rather than pretending to be an artifact.

The artifact filename is not here — it is not known when the manifest is
written. It lives in the build-side record.

``source_commit`` is ``None`` rather than ``Unresolved`` when running from
a checkout: it is structurally not applicable, derived from origin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import Final

MANIFEST_NAME: Final = "BUILD.json"
DISTRIBUTION: Final = "machi"
_UNKNOWN_VERSION: Final = "unknown"


class BuildOrigin(StrEnum):
    """Where the running code came from."""

    ARTIFACT = "artifact"
    SOURCE = "source"


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    """Enough to tie an observation to the source state that produced it."""

    version: str
    origin: BuildOrigin
    source_commit: str | None = None
    build_id: str | None = None
    built_at: str | None = None
    clean_source: bool | None = None

    @property
    def is_artifact(self) -> bool:
        return self.origin is BuildOrigin.ARTIFACT

    @property
    def acceptable_as_evidence(self) -> bool:
        """Whether a real-host result from this build may be accepted."""
        return self.is_artifact and self.clean_source is True

    def describe(self) -> str:
        """One line, greppable."""
        if not self.is_artifact:
            return f"machi {self.version} (source checkout, not a build artifact)"
        commit = self.source_commit or "unknown-commit"
        suffix = "" if self.clean_source else " [WIP: built from a dirty tree]"
        return f"machi {self.version} build {self.build_id} from {commit}{suffix}"


def identity(package_root: Path | None = None) -> BuildIdentity:
    """Read the identity of the running build. Never raises."""
    root = package_root or Path(__file__).resolve().parent.parent
    manifest = _read_manifest(root / MANIFEST_NAME)
    version = _installed_version() or _text(manifest, "version") or _UNKNOWN_VERSION

    if manifest is None:
        return BuildIdentity(version=version, origin=BuildOrigin.SOURCE)

    clean = manifest.get("clean_source")
    return BuildIdentity(
        version=version,
        origin=BuildOrigin.ARTIFACT,
        source_commit=_text(manifest, "source_commit"),
        build_id=_text(manifest, "build_id"),
        built_at=_text(manifest, "built_at"),
        clean_source=clean if isinstance(clean, bool) else None,
    )


def _read_manifest(path: Path) -> dict[str, object] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _installed_version() -> str | None:
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None


def _text(manifest: dict[str, object] | None, key: str) -> str | None:
    if manifest is None:
        return None
    value = manifest.get(key)
    return value if isinstance(value, str) and value else None
