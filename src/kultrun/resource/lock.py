"""Exclusive admission lock. Not a scheduler."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

LOCK_NAME = "admission.lock"


class AdmissionLock:
    """One lock for competing admit/release on this installation."""

    def __init__(self, state_root: Path) -> None:
        root = Path(state_root).resolve() / "resources"
        root.mkdir(parents=True, exist_ok=True)
        self._path = root / LOCK_NAME

    @contextmanager
    def hold(self) -> Iterator[None]:
        handle = self._path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
