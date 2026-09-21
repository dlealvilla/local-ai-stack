"""Generic invocation-failure classification.

PyYAML is one instance of a missing interpreter module. Diagnosis keys
on ``ModuleNotFoundError``, not on a yaml-specific architecture.
"""

from __future__ import annotations

import re

_MISSING_MODULE = re.compile(
    r"ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]"
)
_PERMISSION = re.compile(
    r"permission denied|EACCES|PermissionError",
    re.IGNORECASE,
)

_MODULE_MAX = 64


def missing_module_name(text: str) -> str | None:
    """Return the imported module name, or None when the failure is other."""
    match = _MISSING_MODULE.search(text)
    if match is None:
        return None
    name = match.group(1).strip()
    if not name or len(name) > _MODULE_MAX:
        return None
    if "/" in name or "\\" in name or " " in name:
        return None
    return name


def looks_like_permission_denied(text: str) -> bool:
    """True when stderr or exception text indicates a permission failure."""
    return bool(_PERMISSION.search(text))
