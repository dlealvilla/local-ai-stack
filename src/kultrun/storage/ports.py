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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.storage.contracts import ProbeOutcome, StorageFailureCode
from kultrun.storage.limits import (
    DEFAULT_MAX_EMPIRICAL_PROBE_BYTES,
    DEFAULT_PROBE_CHUNK_BYTES,
    DEFAULT_PROBE_TIMEOUT_SECONDS,
)


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


@dataclass(frozen=True, slots=True)
class StorageEnvironment:
    """Facts a probe uses to decide whether it applies. Not a capacity claim."""

    os_name: str
    architecture: str
    mount_point: str
    filesystem_type: Maybe[str]
    device: Maybe[str]


@dataclass(frozen=True, slots=True)
class CapacityProbeResult:
    """What one technology-specific probe measured. Not an admission."""

    available_bytes: Maybe[int] = NOT_PROVIDED
    hard_maximum_bytes: Maybe[int] = NOT_PROVIDED
    executed: bool = False
    available: bool = False
    detail: str = ""


@runtime_checkable
class StorageCapacityProbe(Protocol):
    """Replaceable technology-specific capacity probe.

    Generic storage core asks `supports` then, when true, **must** call
    `probe`. Adapters own vendor and OS details.
    """

    @property
    def name(self) -> str:
        """Stable probe identity, recorded in evidence."""
        ...

    @property
    def technology(self) -> str:
        """Technology this probe addresses, e.g. 'linux-quota', 'moosefs'."""
        ...

    def supports(self, environment: StorageEnvironment) -> bool:
        """True when this probe is the compatible method for the environment."""
        ...

    def probe(self, environment: StorageEnvironment) -> CapacityProbeResult:
        """Measure available writable capacity. Must not raise for ordinary miss."""
        ...


@dataclass(frozen=True, slots=True)
class EmpiricalWriteBudget:
    """What one empirical write attempt may spend."""

    chunk_bytes: int = DEFAULT_PROBE_CHUNK_BYTES
    deadline: dt.datetime | None = None
    max_bytes: int = DEFAULT_MAX_EMPIRICAL_PROBE_BYTES
    timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class EmpiricalWriteResult:
    """What one real-write attempt established."""

    written_bytes: int
    failure_code: StorageFailureCode | None = None
    failure_errno: int | None = None
    detail: str | None = None


@runtime_checkable
class EmpiricalWritePort(Protocol):
    """Actually consume space. Sparse/truncate/fallocate-only is not enough."""

    def write_exactly(
        self,
        path: Path,
        size: int,
        budget: EmpiricalWriteBudget,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> EmpiricalWriteResult:
        """Write `size` real bytes to `path`, flushing periodically.

        Must not allocate a single in-memory buffer of `size`. Must stop
        on cancellation, deadline, EDQUOT, ENOSPC, and permission errors
        without raising those as surprises.
        """
        ...

    def remove(self, path: Path) -> bool:
        """Remove the probe file. True when the path is confirmed gone."""
        ...
