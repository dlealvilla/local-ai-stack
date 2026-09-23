"""Run a bounded process. Foundation providers build the argument list.

Long-running spawn, poll, and terminate live on the same runner. Serve
uses them for one managed process. Callers still build the argument list.
"""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ProcessResult:
    """One finished process. stdout is bounded by the caller."""

    returncode: int
    stdout: str
    timed_out: bool


class ProcessRunner(Protocol):
    """The execution seam. Foundation does not call a shell itself."""

    def run(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult: ...


@dataclass(frozen=True, slots=True)
class SpawnedProcess:
    """One managed process. The stamp distinguishes a reused pid."""

    pid: int
    process_stamp: str
    identity_token: str
    argv_fingerprint: str


@dataclass(frozen=True, slots=True)
class ProcessView:
    """Whether that exact process is still the one we spawned."""

    alive: bool
    identity_ok: bool
    returncode: int | None


class NativeProcessRunner:
    """subprocess without a shell. Not a container runtime."""

    def __init__(self) -> None:
        self._children: dict[int, subprocess.Popen[bytes]] = {}

    def spawn(
        self,
        argv: list[str],
        *,
        cwd: str,
        env: Mapping[str, str] | None,
        stdout_path: Path,
        stderr_path: Path,
    ) -> SpawnedProcess:
        """Start one process in its own session. The caller owns the argv."""
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
        token = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
        merged = dict(os.environ if env is None else env)
        merged["MACHI_SERVE_IDENTITY"] = token
        stdout_handle = stdout_path.open("ab")
        stderr_handle = stderr_path.open("ab")
        try:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=merged,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(argv[0]) from exc
        finally:
            stdout_handle.close()
            stderr_handle.close()
        self._children[process.pid] = process
        stamp = _start_stamp(process.pid) or token
        return SpawnedProcess(
            pid=process.pid,
            process_stamp=stamp,
            identity_token=token,
            argv_fingerprint=_argv_fingerprint(argv),
        )

    def view(self, spawned: SpawnedProcess) -> ProcessView:
        """Read liveness. A different start stamp is not our process."""
        code = _returncode(self._children.get(spawned.pid), spawned.pid)
        if code is not None:
            return ProcessView(alive=False, identity_ok=True, returncode=code)
        alive = _alive(spawned.pid)
        if not alive:
            return ProcessView(
                alive=False,
                identity_ok=True,
                returncode=_returncode(self._children.get(spawned.pid), spawned.pid),
            )
        if _start_stamp(spawned.pid) != spawned.process_stamp:
            return ProcessView(alive=True, identity_ok=False, returncode=None)
        token = _identity_token(spawned.pid)
        if token is not None and token != spawned.identity_token:
            return ProcessView(alive=True, identity_ok=False, returncode=None)
        return ProcessView(alive=True, identity_ok=True, returncode=None)

    def terminate(
        self, spawned: SpawnedProcess, *, grace_seconds: float
    ) -> ProcessView:
        """Stop one identified process. A mismatched pid is left untouched."""
        current = self.view(spawned)
        if not current.identity_ok:
            return current
        if not current.alive:
            return current
        _signal_group(spawned.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline and _alive(spawned.pid):
            time.sleep(0.05)
        if _alive(spawned.pid):
            _signal_group(spawned.pid, signal.SIGKILL)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and _alive(spawned.pid):
                time.sleep(0.05)
        return self.view(spawned)

    def run(
        self,
        argv: list[str],
        *,
        cwd: str,
        timeout: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        try:
            finished = subprocess.run(
                argv,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
                text=True,
                check=False,
                env=dict(env) if env is not None else None,
            )
        except FileNotFoundError:
            return ProcessResult(returncode=127, stdout="", timed_out=False)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            return ProcessResult(returncode=124, stdout=stdout[:400], timed_out=True)
        text = finished.stdout or ""
        return ProcessResult(
            returncode=finished.returncode,
            stdout=text[:400],
            timed_out=False,
        )


def read_bounded(path: Path, *, limit: int) -> str:
    """Last bytes of a log. A longer file is marked truncated."""
    if limit < 1 or not path.is_file():
        return ""
    data = path.read_bytes()
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace")
    tail = data[-limit:].decode("utf-8", errors="replace")
    return "[truncated]\n" + tail


def _argv_fingerprint(argv: list[str]) -> str:
    return hashlib.sha256("\n".join(argv).encode()).hexdigest()[:32]


def _alive(pid: int) -> bool:
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _start_stamp(pid: int) -> str:
    finished = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
    )
    return finished.stdout.strip()[:80]


def _identity_token(pid: int) -> str | None:
    path = Path(f"/proc/{pid}/environ")
    if not path.is_file():
        return None
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    prefix = b"MACHI_SERVE_IDENTITY="
    for item in raw.split(b"\0"):
        if item.startswith(prefix):
            return item[len(prefix) :].decode("utf-8", errors="replace")
    return None


def _returncode(process: subprocess.Popen[bytes] | None, pid: int) -> int | None:
    if process is not None:
        code = process.poll()
        if code is None:
            try:
                code = process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                return None
        return code
    try:
        waited, status = os.waitpid(pid, os.WNOHANG)
    except ChildProcessError:
        return None
    if waited == 0:
        return None
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return None


def _signal_group(pid: int, sig: int) -> None:
    if pid <= 1:
        return
    try:
        os.killpg(pid, sig)
    except OSError:
        try:
            os.kill(pid, sig)
        except OSError:
            return
