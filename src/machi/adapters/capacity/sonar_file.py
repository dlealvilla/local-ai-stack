"""Owned Sonar file. Exclusive create, real bytes, no sparse holes, no other paths."""

from __future__ import annotations

import errno
import os
import secrets
from pathlib import Path

from machi.capacity.contracts import SonarFailure
from machi.capacity.sonar import SonarMedia, SonarWriteResult

_PREFIX = ".machi-capacity-sonar-"
_CHUNK = 64 * 1024


class FileSonarMedia(SonarMedia):
    """One probe file inside a directory the caller already owns."""

    def __init__(self, directory: Path) -> None:
        self._path = directory / f"{_PREFIX}{secrets.token_hex(6)}"
        self._fd: int | None = None
        self._committed = 0

    @property
    def path(self) -> Path:
        """Probe path. Events must not copy this into a payload."""
        return self._path

    def extend_to(self, nbytes: int) -> SonarWriteResult:
        if nbytes < self._committed:
            return SonarWriteResult(SonarFailure.UNEXPECTED, self._committed)
        try:
            if self._fd is None:
                self._fd = os.open(
                    self._path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            remaining = nbytes - self._committed
            while remaining:
                chunk = b"\0" * min(_CHUNK, remaining)
                written = os.write(self._fd, chunk)
                if written <= 0:
                    return SonarWriteResult(SonarFailure.UNEXPECTED, self._committed)
                self._committed += written
                remaining -= written
            os.fsync(self._fd)
        except OSError as exc:
            return SonarWriteResult(_classify(exc), self._committed)
        return SonarWriteResult(SonarFailure.NONE, self._committed)

    def cleanup(self) -> bool:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if not self._path.name.startswith(_PREFIX):
            return False
        try:
            self._path.unlink(missing_ok=True)
        except OSError:
            return self._path.exists() is False
        return not self._path.exists()


def _classify(exc: OSError) -> SonarFailure:
    if exc.errno == getattr(errno, "EDQUOT", None):
        return SonarFailure.EDQUOT
    if exc.errno == errno.ENOSPC:
        return SonarFailure.ENOSPC
    if exc.errno == errno.EROFS:
        return SonarFailure.READ_ONLY
    if exc.errno in {errno.EACCES, errno.EPERM}:
        return SonarFailure.PERMISSION
    if exc.errno == errno.EINTR:
        return SonarFailure.INTERRUPTED
    return SonarFailure.IO_ERROR
