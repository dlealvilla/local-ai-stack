"""Real writes that actually consume space. Chunked, flushed, bounded."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from kultrun.storage.failures import classify_oserror
from kultrun.storage.payload import fill_payload
from kultrun.storage.ports import EmpiricalWriteBudget, EmpiricalWriteResult


class RealWritePort:
    """os.write of real bytes. Grows an existing file; never sparse/truncate."""

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> EmpiricalWriteResult:
        path.parent.mkdir(parents=True, exist_ok=True)
        current = path.stat().st_size if path.exists() else 0
        if current >= size:
            return EmpiricalWriteResult(written_bytes=0, detail="already at target")
        added = 0
        chunk = bytearray(min(budget.chunk_bytes, max(1, size - current)))
        try:
            mode = "r+b" if path.exists() else "wb"
            with path.open(mode) as handle:
                handle.seek(0, os.SEEK_END)
                offset = current
                while offset < size:
                    if cancelled is not None and cancelled():
                        return EmpiricalWriteResult(
                            written_bytes=added, detail="cancelled"
                        )
                    step = min(len(chunk), size - offset)
                    view = chunk[:step]
                    fill_payload(view, offset)
                    handle.write(view)
                    offset += step
                    added += step
                    handle.flush()
                    os.fsync(handle.fileno())
            return EmpiricalWriteResult(written_bytes=added)
        except OSError as error:
            return EmpiricalWriteResult(
                written_bytes=added,
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
