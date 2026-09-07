"""Structured argv runner for a container engine CLI.

`shell` is never True. Output is bounded. Failures are values.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence

from kultrun.execution.engine import EngineCommandResult

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_OUTPUT_LIMIT_BYTES = 256 * 1024


def which(command: str) -> str | None:
    """Where a command is, or None. Never raises."""
    return shutil.which(command)


def run(
    argv: Sequence[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
) -> EngineCommandResult:
    """Run a fixed argument vector. Never concatenates a shell string."""
    if not argv:
        return EngineCommandResult(
            found=False,
            completed=False,
            returncode=-1,
            stdout="",
            stderr="",
            detail="engine argv was empty",
        )
    executable = argv[0]
    resolved = executable if "/" in executable else which(executable)
    if resolved is None:
        return EngineCommandResult(
            found=False,
            completed=False,
            returncode=-1,
            stdout="",
            stderr="",
            detail=f"{executable} not on PATH",
        )
    command = [resolved, *list(argv[1:])]
    try:
        finished = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return EngineCommandResult(
            found=True,
            completed=False,
            returncode=-1,
            stdout="",
            stderr="",
            detail=f"{executable} exceeded {timeout:g}s and was abandoned",
        )
    except OSError as error:
        return EngineCommandResult(
            found=True,
            completed=False,
            returncode=-1,
            stdout="",
            stderr="",
            detail=f"{executable}: {error}",
        )
    stdout = _bound(finished.stdout, output_limit_bytes)
    stderr = _bound(finished.stderr, output_limit_bytes)
    if finished.returncode != 0:
        return EngineCommandResult(
            found=True,
            completed=False,
            returncode=finished.returncode,
            stdout=stdout,
            stderr=stderr,
            detail=_normalized_detail(executable, finished.returncode, stderr),
        )
    return EngineCommandResult(
        found=True,
        completed=True,
        returncode=finished.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _bound(raw: bytes, limit: int) -> str:
    return raw[:limit].decode("utf-8", errors="replace")


def _normalized_detail(executable: str, returncode: int, stderr: str) -> str:
    snippet = " ".join(stderr.strip().split())[:200]
    if snippet:
        return f"{executable} exited {returncode}: {snippet}"
    return f"{executable} exited {returncode}"
