"""Build a Machi wheel that knows where it came from.

Isolated from the Kultrun prototype builder. The root ``pyproject.toml``
produces a Kultrun distribution; this tool stages ``pyproject.machi.toml``
and ``src/machi`` only, so the artifact cannot ship Kultrun runtime code.

    python tools/build_machi.py

Writes ``BUILD.json`` into the staged package, builds the wheel, hashes it,
and records ``dist/machi/machi-manifest.json``. The source tree is left as it
was found.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
PACKAGE = REPOSITORY / "src" / "machi"
CONFIG = REPOSITORY / "pyproject.machi.toml"
DIST = REPOSITORY / "dist" / "machi"
BUILD_MANIFEST = DIST / "machi-manifest.json"


@dataclass(frozen=True)
class MachiBuild:
    source_commit: str
    build_id: str
    artifact: str
    sha256: str
    built_at: str
    version: str
    clean_source: bool
    size_bytes: int


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
    return git("rev-parse", "HEAD"), not git("status", "--porcelain")


def project_version() -> str:
    text = CONFIG.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit("pyproject.machi.toml declares no version")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_ui(target: Path) -> None:
    """Copy Vite production builds into the wheel. Node is not a runtime."""
    mapping = {
        "admin": REPOSITORY / "ui" / "admin" / "dist",
        "command-center": REPOSITORY / "ui" / "command-center" / "dist",
        "workspace": REPOSITORY / "ui" / "workspace" / "dist",
    }
    for name, source in mapping.items():
        if not (source / "index.html").is_file():
            raise SystemExit(f"missing production UI build: {source}")
        shutil.copytree(source, target / name)


def build(*, keep_dist: bool = False) -> MachiBuild:
    commit, clean = source_state()
    version = project_version()
    built_at = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    build_id = f"{version}+{commit[:12]}" + ("" if clean else ".wip")

    if not keep_dist and DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": version,
        "source_commit": commit,
        "build_id": build_id,
        "built_at": built_at,
        "clean_source": clean,
        "distribution": "machi",
    }

    staging = Path(tempfile.mkdtemp(prefix="machi-build-"))
    try:
        shutil.copytree(PACKAGE, staging / "src" / "machi")
        _stage_ui(staging / "src" / "machi" / "adapters" / "rukan" / "static")
        shutil.copyfile(CONFIG, staging / "pyproject.toml")
        (staging / "src" / "machi" / "BUILD.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        finished = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", str(DIST)],
            cwd=staging,
            capture_output=True,
            text=True,
            check=False,
        )
        if finished.returncode != 0:
            sys.stderr.write(finished.stdout + finished.stderr)
            raise SystemExit("machi wheel build failed")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    wheels = sorted(DIST.glob("machi-*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no Machi wheel was produced")
    wheel = wheels[-1]
    record = MachiBuild(
        source_commit=commit,
        build_id=build_id,
        artifact=wheel.name,
        sha256=sha256(wheel),
        built_at=built_at,
        version=version,
        clean_source=clean,
        size_bytes=wheel.stat().st_size,
    )
    BUILD_MANIFEST.write_text(
        json.dumps(asdict(record), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-dist",
        action="store_true",
        help="keep previously built Machi wheels in dist/machi/",
    )
    options = parser.parse_args()
    record = build(keep_dist=options.keep_dist)
    print(f"artifact   {record.artifact}")
    print(f"sha256     {record.sha256}")
    print(f"size       {record.size_bytes}")
    print(f"build id   {record.build_id}")
    print(f"commit     {record.source_commit}")
    print(f"clean      {record.clean_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
