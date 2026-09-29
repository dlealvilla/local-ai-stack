"""Packaged Admin and Command Center files. Node is build-time only."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent / "static"


def packaged_static(product: str) -> Path | None:
    """Return a built UI directory shipped inside the wheel, when present."""
    if product not in {"admin", "command-center"}:
        return None
    candidate = _ROOT / product
    if (candidate / "index.html").is_file():
        return candidate
    return None
