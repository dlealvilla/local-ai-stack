"""Install a Machi wheel into a throwaway environment and prove M0 plus 1.2.1.

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
    env.pop("MACHI_STATE_ROOT", None)
    env.pop("KULTRUN_STATE_ROOT", None)
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
    kernel_journal = root / "kernel-journal"
    root_a = root / "root-a"
    root_b = root / "root-b"
    env_root = root / "root-env"
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
    prove = run(
        [str(machi), "kernel", "prove", "--journal-dir", str(kernel_journal)],
        env=env,
    )
    print(prove.stdout, end="")
    if '"event_type": "kernel.alive"' not in prove.stdout:
        raise SystemExit("first prove did not emit kernel.alive")
    if '"privacy": "public_ops"' not in prove.stdout:
        raise SystemExit("kernel.alive was not public_ops")
    run([str(machi), "kernel", "prove", "--journal-dir", str(kernel_journal)], env=env)
    listed = run(
        [str(machi), "kernel", "events", "--journal-dir", str(kernel_journal)], env=env
    )
    print(listed.stdout, end="")
    if "records  2" not in listed.stdout:
        raise SystemExit("expected two kernel.alive records after a second prove")

    bind_a = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_a)], env=env
    )
    print(bind_a.stdout, end="")
    if '"event_type": "install.state_root.bound"' not in bind_a.stdout:
        raise SystemExit("bind-root did not emit install.state_root.bound")
    if '"privacy": "restricted"' not in bind_a.stdout:
        raise SystemExit("state-root event was not restricted")
    event_at = bind_a.stdout.find('"kind": "event_record"')
    if event_at < 0:
        raise SystemExit("bind-root did not print an EventRecord")
    if str(root_a) in bind_a.stdout[event_at:]:
        raise SystemExit("absolute state root leaked into the event document")
    if not (root_a / "journal" / "events.jsonl").is_file():
        raise SystemExit("bound root did not persist a Kernel journal")

    reentry = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_a)], env=env
    )
    print(reentry.stdout, end="")
    if '"existed": true' not in reentry.stdout:
        raise SystemExit("same-root re-entry did not report existed=true")
    if '"created": false' not in reentry.stdout:
        raise SystemExit("same-root re-entry did not report created=false")

    bind_b = run(
        [str(machi), "install", "bind-root", "--state-root", str(root_b)], env=env
    )
    print(bind_b.stdout, end="")
    if not root_b.is_dir():
        raise SystemExit("second root was not created")
    env_bind = env.copy()
    env_bind["MACHI_STATE_ROOT"] = str(env_root)
    env_bind.pop("KULTRUN_STATE_ROOT", None)
    bound_env = run([str(machi), "install", "bind-root"], env=env_bind)
    print(bound_env.stdout, end="")
    if '"selection_source": "environment"' not in bound_env.stdout:
        raise SystemExit("MACHI_STATE_ROOT did not win as environment source")
    if not env_root.is_dir():
        raise SystemExit("environment override did not create its root")

    print("verify_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
