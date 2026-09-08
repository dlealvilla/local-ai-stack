"""Locate a host Python interpreter. Does not install one."""

from __future__ import annotations

import shutil
import sys


def locate_python(requirement: str = "3.12") -> str | None:
    """Return a host interpreter matching major.minor, or None.

    Never installs Python. A missing interpreter is a provisioning
    prerequisite failure, not a prompt to use apt or pyenv.
    Managed interpreter acquisition is K-66.
    """
    wanted = _parse(requirement)
    if wanted is None:
        return None
    if sys.version_info[:2] == wanted:
        return sys.executable
    for name in (f"python{requirement}", f"python{wanted[0]}.{wanted[1]}"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _parse(requirement: str) -> tuple[int, int] | None:
    parts = requirement.strip().split(".")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None
