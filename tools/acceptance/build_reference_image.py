"""Build the Stage 1.6A reference-serving acceptance image.

Development tooling. Not a product image-building subsystem.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPOSITORY / "tests" / "fixtures" / "containers" / "reference-serving"
DIST = REPOSITORY / "dist"
TAG = "kultrun-reference-serving:stage-16a"


def latest_wheel() -> Path:
    wheels = sorted(DIST.glob("*.whl"), key=lambda path: path.stat().st_mtime)
    if not wheels:
        raise SystemExit("no wheel in dist/; run tools/build_prototype.py first")
    return wheels[-1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    wheel = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else latest_wheel()
    if not wheel.is_file():
        print(f"missing wheel: {wheel}", file=sys.stderr)
        return 1
    context = Path("/tmp/kultrun-reference-image")
    if context.exists():
        shutil.rmtree(context)
    context.mkdir(parents=True)
    shutil.copy2(FIXTURE / "Dockerfile", context / "Dockerfile")
    # Stable context name; Dockerfile renames to a PEP 427 filename for pip.
    shutil.copy2(wheel, context / "kultrun.whl")
    built = subprocess.run(
        ["docker", "build", "-t", TAG, str(context)],
        check=False,
    )
    if built.returncode != 0:
        return built.returncode
    inspected = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}} {{json .RepoDigests}}",
            TAG,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    image_id = (inspected.stdout or "").strip()
    evidence = {
        "tag": TAG,
        "wheel": wheel.name,
        "wheel_sha256": sha256(wheel),
        "image_inspect": image_id,
        "dockerfile": str(FIXTURE / "Dockerfile"),
        "production_image": False,
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
