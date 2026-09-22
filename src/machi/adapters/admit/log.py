"""Read and create admission records through the existing file store."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from machi.adapters.persistence.file_store import FileStore
from machi.admit.contracts import ReservationRelease, ResourceReservation
from machi.kernel.errors import ValidationError
from machi.kernel.schema import Contract


class StoreReservationLog:
    """Exclusive creates. A bad file is counted, not repaired."""

    def __init__(self, store: FileStore) -> None:
        self._store = store

    def create(self, key: str, record: Contract) -> tuple[Contract, bool]:
        result = self._store.create(key, record)
        return result.record, result.created

    def reservations(self) -> tuple[tuple[ResourceReservation, ...], int]:
        directory = self._store.root / ResourceReservation.kind
        found: list[ResourceReservation] = []
        malformed = _read(self._store, directory, ResourceReservation, found)
        return tuple(found), malformed

    def releases(self) -> tuple[ReservationRelease, ...]:
        directory = self._store.root / ReservationRelease.kind
        found: list[ReservationRelease] = []
        _read(self._store, directory, ReservationRelease, found)
        return tuple(found)


RecordT = TypeVar("RecordT", ResourceReservation, ReservationRelease)


def _read(
    store: FileStore,
    directory: Path,
    contract_type: type[RecordT],
    found: list[RecordT],
) -> int:
    if not directory.is_dir():
        return 0
    malformed = 0
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            found.append(store.get(contract_type, path.stem))
        except (ValidationError, OSError):
            malformed += 1
    return malformed
