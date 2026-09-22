"""POSIX lock so two processes cannot both pass the capacity check."""

from __future__ import annotations

import fcntl
from pathlib import Path
from types import TracebackType
from typing import TextIO


class FileAdmissionLock:
    """Held for the whole admit or release. Not a reservation."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._handle: TextIO | None = None

    def __enter__(self) -> object:
        self._root.mkdir(parents=True, exist_ok=True)
        handle = (self._root / ".admit.lock").open("a", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        self._handle = handle
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        handle = self._handle
        if handle is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
            self._handle = None
