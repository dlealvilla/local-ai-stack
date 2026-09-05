"""Genuine space reservation, in bounded units.

`os.posix_fallocate` asks the filesystem to actually reserve the space. That
choice is the single most important thing carried forward from the previous
implementation: `truncate`, or seeking and writing one byte, produces a
**sparse** file that succeeds instantly at almost any size and proves
nothing. On the reference host's mount, advertising half a petabyte, a
sparse probe would cheerfully "verify" a petabyte.

Two corrections to how the previous implementation used it.

**Chunked.** It made a single call for the whole target, so the probe was
uninterruptible: no deadline, shutdown or operator could stop it mid-call.
Here the reservation is extended one chunk at a time and every budget is
checked between chunks.

**Cleanup is not assumed.** The artifact is removed in `finally` *and* the
path is confirmed gone. The previous implementation's `finally` was written
correctly and never ran, because the probe executed on a daemon thread that
shutdown did not await, orphaning a 42,990 MiB file. Cleanup is also never
inferred from free space: deleting that file returned only about 1.1 GB to
`df` immediately, because the volume reclaimed asynchronously.
"""

from __future__ import annotations

import contextlib
import errno
import os
import uuid
from pathlib import Path
from typing import Final

from kultrun.kernel.clock import Clock, SystemClock
from kultrun.kernel.ids import Name
from kultrun.storage.contracts import ProbeOutcome
from kultrun.storage.ports import ReservationBudget, ReservationResult

METHOD: Final = Name("posix-fallocate")

#: Only these mean "the pool cannot hold this". Everything else is an
#: absence of method or of permission, and must never become a capacity
#: bound — "unsupported" is not evidence that storage is too small.
_CAPACITY_ERRORS: Final = {
    errno.ENOSPC: ProbeOutcome.NO_SPACE,
    errno.EDQUOT: ProbeOutcome.QUOTA_EXCEEDED,
}
_OTHER_ERRORS: Final = {
    errno.EFBIG: ProbeOutcome.FILE_TOO_LARGE,
    errno.EOPNOTSUPP: ProbeOutcome.UNSUPPORTED,
    errno.ENOTSUP: ProbeOutcome.UNSUPPORTED,
    errno.EINVAL: ProbeOutcome.UNSUPPORTED,
}


class PosixFallocateProbe:
    """Reserves space with `posix_fallocate`, one chunk at a time."""

    method = METHOD

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def reserve(
        self, path: Path, target_bytes: int, budget: ReservationBudget
    ) -> ReservationResult:
        """Extend a reservation to `target_bytes`, or report why not."""
        if not hasattr(os, "posix_fallocate"):
            return ReservationResult(
                outcome=ProbeOutcome.UNSUPPORTED,
                reserved_bytes=0,
                detail="this platform offers no posix_fallocate; no genuine "
                "reservation is possible and a sparse file would prove nothing",
            )

        allowed = min(target_bytes, budget.remaining_work_bytes)
        if allowed < target_bytes:
            return ReservationResult(
                outcome=ProbeOutcome.ABANDONED,
                reserved_bytes=0,
                detail=(
                    f"the work allowance leaves {budget.remaining_work_bytes} "
                    f"bytes, short of the {target_bytes} this rung needs"
                ),
            )

        # A unique name per attempt, created exclusively, so an existing file
        # can never be opened let alone overwritten.
        unique = path.with_name(f"{path.stem}-{uuid.uuid4().hex[:12]}{path.suffix}")
        try:
            unique.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return ReservationResult(
                outcome=ProbeOutcome.ERROR,
                reserved_bytes=0,
                detail=f"cannot create the probe directory: {error}",
            )

        descriptor: int | None = None
        reserved = 0
        try:
            descriptor = os.open(
                unique, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            while reserved < target_bytes:
                if self._clock.now() >= budget.deadline:
                    return ReservationResult(
                        outcome=ProbeOutcome.ABANDONED,
                        reserved_bytes=reserved,
                        detail=(
                            f"the time budget expired with {reserved} of "
                            f"{target_bytes} bytes reserved"
                        ),
                    )
                chunk = min(budget.chunk_bytes, target_bytes - reserved)
                os.posix_fallocate(descriptor, reserved, chunk)
                reserved += chunk
            return ReservationResult(
                outcome=ProbeOutcome.VERIFIED, reserved_bytes=reserved
            )
        except OSError as error:
            code = error.errno or 0
            outcome = _CAPACITY_ERRORS.get(code) or _OTHER_ERRORS.get(
                code, ProbeOutcome.ERROR
            )
            return ReservationResult(
                outcome=outcome,
                reserved_bytes=reserved,
                detail=f"errno {error.errno}: {error.strerror}",
            )
        finally:
            if descriptor is not None:
                with contextlib.suppress(OSError):
                    os.close(descriptor)
            # Removed here, and the caller separately confirms the path is
            # gone. Neither step trusts a free-space delta.
            with contextlib.suppress(OSError):
                unique.unlink(missing_ok=True)


def build(clock: Clock | None = None) -> PosixFallocateProbe:
    """Factory for the adapter registry."""
    return PosixFallocateProbe(clock)
