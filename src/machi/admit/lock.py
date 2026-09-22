"""In-process admission lock. A file lock lives in the adapter."""

from __future__ import annotations

import threading
from types import TracebackType
from typing import Protocol


class AdmissionLock(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


class LocalLock:
    """Serializes admit and release inside one process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> object:
        self._lock.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._lock.release()
