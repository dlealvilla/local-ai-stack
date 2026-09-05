"""Which build is this, and was it built from anything traceable?

A deployed instance must be able to answer *"which exact build produced this
output?"* — otherwise a real-host observation cannot be tied to a source
state, and the build → deploy → observe → fix loop has no way to tell a
fixed defect from a stale artifact.

The build tool writes `BUILD.json` into the package and the wheel carries
it. This module reads it.

**Absence is meaningful, not an error.** Running from a source checkout
produces `origin = SOURCE`, and that is reported rather than smoothed over.
`docs/DEVELOPMENT_WORKFLOW.md` makes an installed artifact binding for
real-host acceptance from the workflow-adoption checkpoint forward, so a run
that quietly executed a checkout would invalidate its own evidence. Better
for the product to say so.

The artifact *filename* is deliberately not here. It is not known at the
moment the manifest is written into the package, and a field that is
structurally always empty in the one command whose job is to be trusted is
worse than no field. It lives in the build-side record instead, where it is
genuinely known.

`source_commit` is `None` rather than `Unresolved` when running from a
checkout. It is not an unmeasured value; it is structurally not applicable,
derived from `origin`, which is the invariant in `docs/ARCHITECTURE.md`
Part II §6 — not-applicable is derived, never a third null state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from importlib import metadata
from pathlib import Path
from typing import Final

#: Written into the package by `tools/build_prototype.py` at build time and
#: shipped inside the wheel. Absent in a source checkout, deliberately.
MANIFEST_NAME: Final = "BUILD.json"

#: The distribution name, for reading the version the installer recorded.
DISTRIBUTION: Final = "kultrun"

_UNKNOWN_VERSION: Final = "unknown"


class BuildOrigin(StrEnum):
    """Where the running code came from."""

    #: Installed from a built artifact carrying a manifest.
    ARTIFACT = "artifact"
    #: Executing from a source tree. Valid for development, and never valid
    #: as real-host acceptance evidence.
    SOURCE = "source"


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    """Enough to tie an observation to the source state that produced it."""

    version: str
    origin: BuildOrigin
    source_commit: str | None = None
    build_id: str | None = None
    built_at: str | None = None
    #: Whether the source tree was clean when the artifact was built. A
    #: `False` here marks the artifact experimental: its behaviour cannot be
    #: reproduced from any commit, so it may not carry a final acceptance.
    clean_source: bool | None = None

    @property
    def is_artifact(self) -> bool:
        return self.origin is BuildOrigin.ARTIFACT

    @property
    def acceptable_as_evidence(self) -> bool:
        """Whether a real-host result from this build may be accepted.

        Requires an artifact built from a clean source tree. Everything else
        is a development iteration, which is expected and useful — but a
        result no commit can reproduce is not evidence.
        """
        return self.is_artifact and self.clean_source is True

    def describe(self) -> str:
        """One line, for a log or a command that must be greppable."""
        if not self.is_artifact:
            return f"kultrun {self.version} (source checkout, not a build artifact)"
        commit = self.source_commit or "unknown-commit"
        suffix = "" if self.clean_source else " [WIP: built from a dirty tree]"
        return f"kultrun {self.version} build {self.build_id} from {commit}{suffix}"


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
    """The shipped manifest, or None when there is not a usable one.

    An unreadable manifest is treated as absent rather than fatal. A build
    that cannot describe itself must still run — the platform reports
    `SOURCE`, which is wrong in a visible way rather than a crash on start.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _installed_version() -> str | None:
    """The version the installer recorded, when installed as a distribution.

    Deliberately not a constant in source. A literal would drift from
    `pyproject.toml`, and the drift would be invisible in exactly the
    situation this module exists to make visible.

    Distinct from `main.PLATFORM_VERSION`, which versions persisted platform
    state and changes when state semantics change, not when a build happens.
    """
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None


def _text(manifest: dict[str, object] | None, key: str) -> str | None:
    if manifest is None:
        return None
    value = manifest.get(key)
    return value if isinstance(value, str) and value else None
