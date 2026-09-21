"""Resolve the interpreter a vendor CLI actually uses.

The amd-smi failure was ``#!/usr/bin/env python3`` selecting an
interpreter that lacked yaml. Remediation must target that interpreter
or fail closed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machi.kernel.unresolved import Unresolved, UnresolvedReason
from machi.prerequisites.contracts import InterpreterResolution

Which = Callable[[str], str | None]
ReadShebang = Callable[[str], str]


@dataclass(frozen=True, slots=True)
class InterpreterIdentity:
    """Unique interpreter used by a CLI, or a closed failure to identify one."""

    resolution: InterpreterResolution
    path: str | Unresolved
    basename: str


_UNRESOLVED = Unresolved(
    UnresolvedReason.INCONCLUSIVE,
    "CLI interpreter could not be uniquely identified",
)


def resolve_cli_interpreter(
    executable_path: str,
    *,
    which: Which,
    read_shebang: ReadShebang,
) -> InterpreterIdentity:
    """Identify the interpreter from the executable shebang, or fail closed."""
    try:
        shebang = read_shebang(executable_path).strip()
    except OSError:
        return InterpreterIdentity(
            resolution=InterpreterResolution.AMBIGUOUS,
            path=_UNRESOLVED,
            basename="",
        )
    if not shebang.startswith("#!"):
        return InterpreterIdentity(
            resolution=InterpreterResolution.AMBIGUOUS,
            path=_UNRESOLVED,
            basename="",
        )
    parts = shebang[2:].strip().split()
    if not parts:
        return InterpreterIdentity(
            resolution=InterpreterResolution.AMBIGUOUS,
            path=_UNRESOLVED,
            basename="",
        )
    program = parts[0]
    if Path(program).name == "env":
        args = parts[1:]
        if args and args[0] == "-S":
            args = args[1:]
        if not args:
            return InterpreterIdentity(
                resolution=InterpreterResolution.AMBIGUOUS,
                path=_UNRESOLVED,
                basename="",
            )
        candidate = args[0]
        if not _looks_like_python(candidate):
            return InterpreterIdentity(
                resolution=InterpreterResolution.NOT_PYTHON,
                path=_UNRESOLVED,
                basename="",
            )
        resolved = which(Path(candidate).name)
        if not resolved:
            return InterpreterIdentity(
                resolution=InterpreterResolution.AMBIGUOUS,
                path=_UNRESOLVED,
                basename="",
            )
        return InterpreterIdentity(
            resolution=InterpreterResolution.ENV_WHICH,
            path=resolved,
            basename=Path(resolved).name,
        )
    if not _looks_like_python(program):
        return InterpreterIdentity(
            resolution=InterpreterResolution.NOT_PYTHON,
            path=_UNRESOLVED,
            basename="",
        )
    return InterpreterIdentity(
        resolution=InterpreterResolution.SHEBANG_ABSOLUTE,
        path=program,
        basename=Path(program).name,
    )


def read_shebang_line(path: str) -> str:
    """Read the first line of a file. Used as the default shebang reader."""
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        return handle.readline(256)


def _looks_like_python(program: str) -> bool:
    name = Path(program).name.lower()
    return name == "python" or name.startswith("python3")
