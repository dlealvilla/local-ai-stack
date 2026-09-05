"""Build a prototype wheel that knows where it came from.

Development tooling, not a release system. `docs/DEVELOPMENT_WORKFLOW.md`
makes an installed artifact binding for real-host acceptance, and that only
works if an artifact can be tied back to a source state — otherwise a remote
observation cannot be told apart from a stale deployment.

    python tools/build_prototype.py

Writes `BUILD.json` into the package, builds the wheel so the manifest ships
inside it, removes the manifest again, hashes the artifact and records a
manifest beside it in `dist/`.

**The source tree is left as it was found.** The manifest is removed in a
`finally`, because a stray `BUILD.json` would make the next build claim a
commit it was not built from — and a wrong build identity is worse than
none, since the whole point is to trust what a deployed instance says.

A dirty tree is allowed and produces an artifact marked `clean_source:
false`, which the product reports as WIP and refuses to call acceptable
evidence. Iterating against a real host without committing first is normal;
*accepting* a result that no commit can reproduce is not.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
PACKAGE = REPOSITORY / "src" / "kultrun"
MANIFEST_IN_PACKAGE = PACKAGE / "BUILD.json"
DIST = REPOSITORY / "dist"
BUILD_MANIFEST = DIST / "prototype-manifest.json"


@dataclass(frozen=True)
class PrototypeBuild:
    """What was built, and from what. The deployment token's source half."""

    source_commit: str
    build_id: str
    artifact: str
    sha256: str
    built_at: str
    version: str
    clean_source: bool


def git(*arguments: str) -> str:
    finished = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    )
    return finished.stdout.strip()


def source_state() -> tuple[str, bool]:
    """The current commit, and whether the tree matches it."""
    return git("rev-parse", "HEAD"), not git("status", "--porcelain")


def project_version() -> str:
    """The declared version, read rather than duplicated."""
    text = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("pyproject.toml declares no version")


def build(*, keep_dist: bool = False) -> PrototypeBuild:
    commit, clean = source_state()
    version = project_version()
    built_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    build_id = f"{version}+{commit[:12]}" + ("" if clean else ".wip")

    if not keep_dist and DIST.exists():
        # Otherwise an old wheel sits beside the new one and the wrong file
        # gets shipped, which is the failure this whole tool exists to stop.
        shutil.rmtree(DIST)

    manifest = {
        "version": version,
        "source_commit": commit,
        "build_id": build_id,
        "built_at": built_at,
        "clean_source": clean,
    }

    try:
        MANIFEST_IN_PACKAGE.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        finished = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(DIST)],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )
        if finished.returncode != 0:
            sys.stderr.write(finished.stdout + finished.stderr)
            raise SystemExit("wheel build failed")
    finally:
        MANIFEST_IN_PACKAGE.unlink(missing_ok=True)

    wheels = sorted(DIST.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel was produced")
    wheel = wheels[-1]

    record = PrototypeBuild(
        source_commit=commit,
        build_id=build_id,
        artifact=wheel.name,
        sha256=sha256(wheel),
        built_at=built_at,
        version=version,
        clean_source=clean,
    )
    BUILD_MANIFEST.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-dist",
        action="store_true",
        help="keep previously built wheels in dist/",
    )
    options = parser.parse_args()

    record = build(keep_dist=options.keep_dist)
    print(f"artifact   {record.artifact}")
    print(f"sha256     {record.sha256}")
    print(f"build id   {record.build_id}")
    print(f"commit     {record.source_commit}")
    print(f"built at   {record.built_at}")
    if not record.clean_source:
        print(
            "\nWIP: built from a dirty tree. Usable for iteration; not "
            "acceptable as acceptance evidence."
        )
    print(f"\nmanifest   {BUILD_MANIFEST.relative_to(REPOSITORY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
