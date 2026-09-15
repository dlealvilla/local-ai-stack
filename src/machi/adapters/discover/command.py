"""Bounded subprocess observation helper for Discover adapters.

Observation only. Never ``shell=True``. Missing executables are
unavailable, not a measured empty result. Paths from stderr are not
retained as product evidence.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from machi.kernel.errors import ValidationError

CommandRunner = Callable[[Sequence[str], float], "CommandOutcome"]


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    """Result of one non-mutating command invocation."""

    found: bool
    timed_out: bool
    returncode: int | None
    stdout: str
    stderr: str


def run_command(argv: Sequence[str], timeout: float) -> CommandOutcome:
    """Run ``argv`` with a timeout. Does not invoke a shell."""
    if not argv:
        raise ValidationError("command argv is required")
    if timeout <= 0:
        raise ValidationError("command timeout must be positive", timeout=timeout)
    executable = argv[0]
    if shutil.which(executable) is None:
        return CommandOutcome(
            found=False,
            timed_out=False,
            returncode=None,
            stdout="",
            stderr="",
        )
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _command_text(exc.stdout)
        stderr = _command_text(exc.stderr)
        return CommandOutcome(
            found=True,
            timed_out=True,
            returncode=None,
            stdout=stdout,
            stderr=stderr,
        )
    except OSError:
        return CommandOutcome(
            found=False,
            timed_out=False,
            returncode=None,
            stdout="",
            stderr="",
        )
    return CommandOutcome(
        found=True,
        timed_out=False,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _command_text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, str):
        return value
    return ""


def bounded_detail(text: str, *, maximum: int = 160) -> str:
    """Compact a provider reason. Drop path-bearing text rather than leak it."""
    compact = " ".join(text.split())
    if not compact:
        return ""
    if "/" in compact or "\\" in compact:
        return "provider command failed"
    if len(compact) > maximum:
        return compact[:maximum]
    return compact
