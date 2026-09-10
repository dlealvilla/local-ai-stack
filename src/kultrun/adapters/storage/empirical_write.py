"""Real writes that actually consume space. Chunked, flushed, bounded."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from kultrun.storage.failures import classify_oserror
from kultrun.storage.ports import (
    EmpiricalWriteBudget,
    EmpiricalWriteResult,
)


class RealWritePort:
    """os.write of real bytes. Not truncate, not sparse, not fallocate-only."""

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> EmpiricalWriteResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        chunk = bytearray(min(budget.chunk_bytes, max(1, size)))
        try:
            with path.open("wb") as handle:
                while written < size:
                    if cancelled is not None and cancelled():
                        return EmpiricalWriteResult(
                            written_bytes=written, detail="cancelled"
                        )
                    step = min(len(chunk), size - written)
                    handle.write(chunk[:step])
                    written += step
                    if written == size or written % (len(chunk) * 8) == 0:
                        handle.flush()
                        os.fsync(handle.fileno())
            return EmpiricalWriteResult(written_bytes=written)
        except OSError as error:
            return EmpiricalWriteResult(
                written_bytes=written,
                failure_code=classify_oserror(error),
                failure_errno=error.errno,
                detail=str(error),
            )

    def remove(self, path: Path) -> bool:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return not path.exists()
        return not path.exists()
