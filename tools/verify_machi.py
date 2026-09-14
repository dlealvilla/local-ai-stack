"""Install a Machi wheel into a throwaway environment and prove kernel.alive.

python tools/verify_machi.py dist/machi/machi-0.1.0-py3-none-any.whl
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def isolated_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def run(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    finished = subprocess.run(
        command, capture_output=True, text=True, check=False, env=env
    )
    if finished.returncode != 0:
        sys.stderr.write(finished.stdout + finished.stderr)
        raise SystemExit(f"command failed: {' '.join(command)}")
    return finished


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    options = parser.parse_args()
    wheel = options.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"no wheel at {wheel}")

    root = Path(tempfile.mkdtemp(prefix="machi-verify-"))
    venv_dir = root / "venv"
    journal = root / "journal"
    venv.create(venv_dir, with_pip=True, symlinks=True)
    python = venv_dir / "bin/python"
    machi = venv_dir / "bin/machi"
    env = isolated_env()
    run([str(python), "-m", "pip", "install", "--upgrade", "pip"], env=env)
    run([str(python), "-m", "pip", "install", str(wheel)], env=env)
    check = run(
        [
            str(python),
            "-c",
            "import machi, importlib.util as u; "
            "assert u.find_spec('kultrun') is None; "
            "print('machi_ok'); print('kultrun_absent')",
        ],
        env=env,
    )
    print(check.stdout, end="")
    print(run([str(machi), "version"], env=env).stdout, end="")
    prove = run([str(machi), "kernel", "prove", "--journal-dir", str(journal)], env=env)
    print(prove.stdout, end="")
    if '"event_type": "kernel.alive"' not in prove.stdout:
        raise SystemExit("first prove did not emit kernel.alive")
    if '"privacy": "public_ops"' not in prove.stdout:
        raise SystemExit("kernel.alive was not public_ops")
    run([str(machi), "kernel", "prove", "--journal-dir", str(journal)], env=env)
    listed = run(
        [str(machi), "kernel", "events", "--journal-dir", str(journal)], env=env
    )
    print(listed.stdout, end="")
    if "records  2" not in listed.stdout:
        raise SystemExit("expected two kernel.alive records after a second prove")
    print("verify_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
