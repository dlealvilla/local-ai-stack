"""Store seam for holds and releases. The domain does not scan disks."""

from __future__ import annotations

from typing import Protocol

from machi.admit.contracts import ReservationRelease, ResourceReservation
from machi.kernel.schema import Contract


class ReservationLog(Protocol):
    """Exclusive creates plus a read of what is already stored."""

    def create(self, key: str, record: Contract) -> tuple[Contract, bool]:
        """Return the stored record and whether this call created it."""
        ...

    def reservations(self) -> tuple[tuple[ResourceReservation, ...], int]:
        """Valid holds, and how many records could not be read."""
        ...

    def releases(self) -> tuple[ReservationRelease, ...]:
        """Release records. A second identical release converges."""
        ...
