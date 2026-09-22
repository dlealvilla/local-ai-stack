"""Run a bounded process. Foundation providers build the argument list."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
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


class NativeProcessRunner:
    """subprocess without a shell. Not a container runtime."""

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
