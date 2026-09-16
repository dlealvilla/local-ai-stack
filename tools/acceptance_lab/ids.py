"""Stable development identifiers. Distinct from Machi product IDs."""

from __future__ import annotations

import hashlib
import re

_PREFIX = re.compile(r"^[a-z]{2,8}$")


def stable_id(prefix: str, *parts: str) -> str:
    """Return ``prefix_`` plus 16 hex chars of SHA-256 over joined parts."""
    if not _PREFIX.fullmatch(prefix):
        raise ValueError(f"invalid id prefix: {prefix}")
    material = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:16]
    return f"{prefix}_{digest}"
