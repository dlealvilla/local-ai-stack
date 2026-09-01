"""Atomic JSON-file reservation persistence adapter.

AI_DEPLOYMENT_PHASE9_RESOURCE_RESERVATIONS_V1
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

from core.resource_reservations import (
    ReservationRecord,
)


class JsonFileReservationStore:
    """Simple durable reservation store for the Phase 9 single-host MVP."""

    FORMAT_VERSION = 1

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> list[ReservationRecord]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if payload.get("format_version") != self.FORMAT_VERSION:
            raise ValueError(
                "unsupported reservation store format version: "
                f"{payload.get('format_version')!r}"
            )

        reservations = payload.get("reservations")

        if not isinstance(reservations, list):
            raise ValueError(
                "reservation store 'reservations' must be a list"
            )

        return [
            ReservationRecord.from_dict(value)
            for value in reservations
        ]

    def save(
        self,
        reservations: Iterable[ReservationRecord],
    ) -> None:
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "format_version": self.FORMAT_VERSION,
            "reservations": [
                reservation.to_dict()
                for reservation in reservations
            ],
        }

        temporary = self.path.with_name(
            f".{self.path.name}.tmp-{os.getpid()}"
        )

        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temporary, self.path)

            try:
                directory_fd = os.open(
                    self.path.parent,
                    os.O_RDONLY,
                )
            except OSError:
                return

            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)

        finally:
            if temporary.exists():
                temporary.unlink()
