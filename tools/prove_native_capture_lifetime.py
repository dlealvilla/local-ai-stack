"""Prove NativeProcessExecutor lets the launching interpreter exit.

Development proof, not a product command. Used after an isolated wheel
install so the next host consumes the same capture-lifetime behaviour.

    python tools/prove_native_capture_lifetime.py
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CHILD = r"""
import os
import signal
import sys
import time
from pathlib import Path

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
progress = Path(os.environ["KULTRUN_PROGRESS"])
ready_file = Path(os.environ["KULTRUN_READY_FILE"])
ready_after = int(os.environ.get("KULTRUN_READY_AFTER", "262144"))
chunk = b"O" * 2048
err = b"E" * 2048
written = 0
while written < ready_after:
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(err)
    sys.stderr.buffer.flush()
    written += 2048
    progress.write_text(str(written), encoding="utf-8")
ready_file.write_text("READY", encoding="utf-8")
print("READY", flush=True)
print("READY-ERR", file=sys.stderr, flush=True)
while True:
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(err)
    sys.stderr.buffer.flush()
    written += 2048
    if written % (2048 * 16) == 0:
        progress.write_text(str(written), encoding="utf-8")
    time.sleep(0.01)
"""

LAUNCHER = r"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from kultrun.adapters.execution.native_process import NativeProcessExecutor
from kultrun.execution.contracts import ExecutorSpec
from kultrun.host.contracts import HostId

def main() -> None:
    executor = NativeProcessExecutor()
    spec = ExecutorSpec(
        executable=sys.executable,
        arguments=("-c", os.environ["KULTRUN_CHILD"]),
        environment=(
            f"KULTRUN_PROGRESS={os.environ['KULTRUN_PROGRESS']}",
            f"KULTRUN_READY_FILE={os.environ['KULTRUN_READY_FILE']}",
            f"KULTRUN_READY_AFTER={os.environ.get('KULTRUN_READY_AFTER', '262144')}",
        ),
        output_limit_bytes=4096,
    )
    handle = executor.start(HostId.generate(), spec)
    ready_path = Path(os.environ["KULTRUN_READY_FILE"])
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        handle = executor.observe(handle)
        if ready_path.exists():
            print(
                f"PARENT_SUCCESS pid={os.getpid()} child={handle.pid}",
                flush=True,
            )
            raise SystemExit(0)
        if handle.observed_state.value in {"exited", "failed"}:
            print(handle.stdout, file=sys.stderr)
            print(handle.stderr, file=sys.stderr)
            raise SystemExit(2)
        time.sleep(0.05)
    raise SystemExit(3)

if __name__ == "__main__":
    main()
"""


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def main() -> int:
    import kultrun

    package = Path(kultrun.__file__).resolve()
    work = Path(tempfile.mkdtemp(prefix="kultrun-capture-proof-"))
    progress = work / "progress"
    ready_file = work / "ready"
    launcher = work / "launcher.py"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(package.parent.parent)
    env["KULTRUN_CHILD"] = CHILD
    env["KULTRUN_PROGRESS"] = str(progress)
    env["KULTRUN_READY_FILE"] = str(ready_file)
    env["KULTRUN_READY_AFTER"] = "262144"
    started = time.monotonic()
    finished = subprocess.run(
        [sys.executable, str(launcher)],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=25,
        check=False,
    )
    ready_to_exit = time.monotonic() - started
    if finished.returncode != 0:
        print(finished.stdout)
        print(finished.stderr, file=sys.stderr)
        return finished.returncode or 2
    child = int(finished.stdout.strip().rsplit("child=", 1)[1])
    try:
        if not _pid_alive(child):
            print("child died when parent exited", file=sys.stderr)
            return 4
        before = int(progress.read_text(encoding="utf-8"))
        time.sleep(2.0)
        if not _pid_alive(child):
            print("child died while writing after parent exit", file=sys.stderr)
            return 5
        after = int(progress.read_text(encoding="utf-8"))
        if after - before < 64 * 1024:
            print(
                f"child did not keep writing: {before} -> {after}",
                file=sys.stderr,
            )
            return 6
        payload = {
            "parent_exit_code": finished.returncode,
            "parent_stdout": finished.stdout.strip(),
            "child_pid": child,
            "ready_to_parent_exit_seconds": round(ready_to_exit, 3),
            "bytes_after_parent_exit": after - before,
            "kultrun_file": str(package),
            "result": "PASS",
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(child, signal.SIGKILL)


if __name__ == "__main__":
    raise SystemExit(main())
