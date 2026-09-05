"""Running a read-only external tool, with a timeout and no surprises.

Shared by the providers because all three read from external commands, and
the failure discipline has to be identical: a tool that hangs is abandoned,
a tool that is absent is a fact rather than an exception, and nothing here
modifies the host.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

#: Long enough for a slow vendor tool on a loaded machine, short enough that
#: discovery cannot hang startup. A provider that exceeds it reports
#: unavailable rather than blocking.
DEFAULT_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    """What a command did, including not existing."""

    found: bool
    completed: bool
    stdout: str
    detail: str | None = None

    @property
    def usable(self) -> bool:
        return self.found and self.completed


def which(command: str) -> str | None:
    """Where a command is, or None. Never raises."""
    return shutil.which(command)


def run(
    argv: list[str], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> CommandResult:
    """Run a read-only command and return what happened.

    Every failure mode becomes a value: absent, timed out, non-zero. None of
    them raises, because a discovery provider that raises turns one missing
    tool into a failed startup.
    """
    if which(argv[0]) is None:
        return CommandResult(
            found=False, completed=False, stdout="", detail=f"{argv[0]} not on PATH"
        )
    try:
        finished = subprocess.run(  # fixed argv, never a shell
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(
            found=True,
            completed=False,
            stdout="",
            detail=f"{argv[0]} exceeded {timeout:g}s and was abandoned",
        )
    except OSError as error:
        return CommandResult(
            found=True, completed=False, stdout="", detail=f"{argv[0]}: {error}"
        )
    if finished.returncode != 0:
        return CommandResult(
            found=True,
            completed=False,
            stdout=finished.stdout,
            detail=(
                f"{argv[0]} exited {finished.returncode}: "
                f"{finished.stderr.strip()[:200]}"
            ),
        )
    return CommandResult(found=True, completed=True, stdout=finished.stdout)
