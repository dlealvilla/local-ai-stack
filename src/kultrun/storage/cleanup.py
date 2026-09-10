"""Step 0: inventory owned state, clean only what dual ownership permits.

Full storage rediscovery is mandatory after this returns. This module does
not itself rediscover capacity; the caller must.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from kultrun.host.contracts import HostId
from kultrun.storage.contracts import CleanupReport
from kultrun.storage.ownership import OwnershipService


def step0_cleanup(
    ownership: OwnershipService,
    host_id: HostId,
    *,
    active_roots: Iterable[Path] = (),
    allowed_roots: Sequence[Path] | None = None,
    extra_roots: Sequence[Path] = (),
) -> CleanupReport:
    """Find managed roots, reconcile, and remove only safe disposable state."""
    ownership.reconcile(allowed_roots=allowed_roots)
    return ownership.cleanup_disposable(
        host_id,
        active_roots=active_roots,
        allowed_roots=allowed_roots,
        extra_roots=extra_roots,
    )
