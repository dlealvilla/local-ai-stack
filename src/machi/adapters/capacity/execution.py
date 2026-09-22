"""Read an execution memory ceiling. Unlimited is unresolved, not a huge integer."""

from __future__ import annotations

import sys
from pathlib import Path

from machi.kernel.unresolved import NOT_PROVIDED, Maybe, Unresolved, UnresolvedReason

_V2 = Path("/sys/fs/cgroup/memory.max")
_V1 = Path("/sys/fs/cgroup/memory/memory.limit_in_bytes")
_UNLIMITED_V1 = 2**60


def read_execution_limit(
    *,
    v2_path: Path | None = None,
    v1_path: Path | None = None,
) -> Maybe[int]:
    """Return a cgroup hard limit, or Unresolved when the platform has none."""
    if sys.platform != "linux" and v2_path is None and v1_path is None:
        return Unresolved(
            UnresolvedReason.UNSUPPORTED,
            "execution memory limits are not read on this platform",
        )
    v2 = v2_path if v2_path is not None else _V2
    if v2.is_file():
        return _parse(v2.read_text(encoding="utf-8"))
    v1 = v1_path if v1_path is not None else _V1
    if v1.is_file():
        return _parse(v1.read_text(encoding="utf-8"))
    return Unresolved(NOT_PROVIDED.reason, "no cgroup memory limit was visible")


def _parse(text: str) -> Maybe[int]:
    token = text.strip()
    if token == "max":
        return Unresolved(NOT_PROVIDED.reason, "cgroup memory limit is unlimited")
    try:
        value = int(token)
    except ValueError:
        return Unresolved(UnresolvedReason.INCONCLUSIVE,
            "cgroup memory limit was not an integer")
    if value <= 0 or value >= _UNLIMITED_V1:
        return Unresolved(NOT_PROVIDED.reason,
            "cgroup memory limit is not a finite ceiling")
    return value
