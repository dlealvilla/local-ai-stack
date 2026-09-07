"""Resolve a logical executable inside one execution environment.

Runtime names a component. Executors map that name onto their environment.
This module is executor-owned; Runtime must not import it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from kultrun.kernel.errors import ValidationError

#: Component names a runtime may emit instead of a host filesystem path.
INTERPRETER_COMPONENTS = frozenset({"python", "python3"})


def is_interpreter_component(executable: str) -> bool:
    """True when the executable is a logical interpreter, not a host path."""
    if os.sep in executable or (os.altsep and os.altsep in executable):
        return False
    return Path(executable).name in INTERPRETER_COMPONENTS


def native_interpreter() -> str:
    """The interpreter running this Kultrun process."""
    return sys.executable


def container_command(executable: str) -> str:
    """Map a logical or host-shaped executable onto a container argv[0].

    A host-absolute interpreter path is treated as the python component.
    Other host paths cannot be consumed coherently and fail closed.
    """
    name = Path(executable).name
    if name in INTERPRETER_COMPONENTS:
        return "python"
    if os.sep in executable or (os.altsep and os.altsep in executable):
        raise ValidationError(
            "host path is not a container command",
            executable=executable,
        )
    if not executable.strip():
        raise ValidationError("executable must not be empty")
    return executable


def host_pythonpath_entries(entries: tuple[str, ...]) -> tuple[str, ...]:
    """Drop PYTHONPATH. It is a host import path, not a container fact."""
    kept: list[str] = []
    for entry in entries:
        name, _, _value = entry.partition("=")
        if name == "PYTHONPATH":
            continue
        kept.append(entry)
    return tuple(kept)
