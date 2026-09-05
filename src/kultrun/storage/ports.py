"""The reservation seam.

A probe genuinely reserves space and reports what happened. It owns no
ladder, no budget arithmetic and no interpretation — those belong to
`storage/sanity.py`, so that swapping the reservation primitive for a
different platform does not re-open the decision logic.

`capacity` depends on the normalized evidence this produces and never on a
reservation primitive. That is the boundary that keeps a filesystem
mutation out from behind a capacity read.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.storage.contracts import ProbeOutcome


@dataclass(frozen=True, slots=True)
class ReservationBudget:
    """What one attempt is allowed to spend.

    Passed in rather than owned by the probe, because a probe that decides
    its own limits cannot be bounded by the thing that called it.
    """

    #: Reservation is extended in units of this size, so the probe can be
    #: stopped between them. A single 64 GiB call would be uninterruptible:
    #: the previous implementation made exactly that call and could not
    #: abandon it, which is how an interrupted run orphaned 42,990 MiB.
    chunk_bytes: int
    #: Wall clock after which the attempt gives up mid-ladder.
    deadline: dt.datetime
    #: Cumulative bytes the whole ladder may still reserve.
    remaining_work_bytes: int


@dataclass(frozen=True, slots=True)
class ReservationResult:
    """What one attempt established."""

    outcome: ProbeOutcome
    reserved_bytes: int
    detail: str | None = None


@runtime_checkable
class StorageSanityProbe(Protocol):
    """Something that can genuinely reserve space and then release it."""

    @property
    def method(self) -> Name:
        """How it reserves, recorded in the evidence."""
        ...

    def reserve(
        self, path: Path, target_bytes: int, budget: ReservationBudget
    ) -> ReservationResult:
        """Try to genuinely reserve `target_bytes` at `path`.

        Must extend the reservation in units of `budget.chunk_bytes` and
        stop between units when the deadline or the work allowance is
        exhausted, reporting `ABANDONED` with what it did reserve.

        Must not raise for an ordinary failure: a full filesystem, a quota,
        an unsupported primitive and a permission error are all results.
        Must not leave the artifact behind — and must not report success at
        cleanup on the basis of free space having changed.

        **Must genuinely reserve.** A sparse file, a `truncate` or a
        seek-and-write would succeed instantly at almost any size and prove
        nothing; on a mount advertising half a petabyte it would cheerfully
        "verify" a petabyte. That substitution is the one that looks like it
        worked.
        """
        ...
