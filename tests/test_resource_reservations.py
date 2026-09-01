"""Tests for Phase 9 resource reservations."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.resource_reservations.json_file import (
    JsonFileReservationStore,
)
from core.resource_reservations import (
    ReservationConflictError,
    ReservationDeniedError,
    ResourceReservationLedger,
)


class ResourceReservationLedgerTests(unittest.TestCase):
    def test_successful_reservation_accounts_capacity(self) -> None:
        ledger = ResourceReservationLedger(
            {
                "system_ram_bytes": 1000,
                "dedicated_vram_bytes": 500,
            }
        )

        reservation = ledger.reserve(
            "model-a",
            {
                "system_ram_bytes": 400,
                "dedicated_vram_bytes": 200,
            },
        )

        self.assertEqual(
            reservation.workload_id,
            "model-a",
        )

        self.assertEqual(
            ledger.total_reserved(),
            {
                "system_ram_bytes": 400,
                "dedicated_vram_bytes": 200,
            },
        )

        self.assertEqual(
            ledger.available_resources(),
            {
                "dedicated_vram_bytes": 300,
                "system_ram_bytes": 600,
            },
        )

    def test_overcommit_is_denied_without_mutation(self) -> None:
        ledger = ResourceReservationLedger(
            {"dedicated_vram_bytes": 100}
        )

        ledger.reserve(
            "model-a",
            {"dedicated_vram_bytes": 80},
        )

        with self.assertRaises(
            ReservationDeniedError
        ) as raised:
            ledger.reserve(
                "model-b",
                {"dedicated_vram_bytes": 30},
            )

        self.assertFalse(
            raised.exception.decision.allowed
        )

        self.assertEqual(
            raised.exception.decision.deficits,
            {"dedicated_vram_bytes": 10},
        )

        self.assertIsNone(
            ledger.reservation_for_workload("model-b")
        )

    def test_unknown_pool_fails_closed(self) -> None:
        ledger = ResourceReservationLedger(
            {"system_ram_bytes": 100}
        )

        decision = ledger.evaluate(
            {"future_accelerator_bytes": 1}
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(
            decision.deficits,
            {"future_accelerator_bytes": 1},
        )

    def test_duplicate_workload_is_rejected(self) -> None:
        ledger = ResourceReservationLedger(
            {"system_ram_bytes": 100}
        )

        ledger.reserve(
            "model-a",
            {"system_ram_bytes": 10},
        )

        with self.assertRaises(
            ReservationConflictError
        ):
            ledger.reserve(
                "model-a",
                {"system_ram_bytes": 10},
            )

    def test_release_restores_capacity(self) -> None:
        ledger = ResourceReservationLedger(
            {"system_ram_bytes": 100}
        )

        reservation = ledger.reserve(
            "model-a",
            {"system_ram_bytes": 60},
        )

        removed = ledger.release(
            reservation.reservation_id
        )

        self.assertIsNotNone(removed)
        self.assertEqual(
            ledger.available_resources(),
            {"system_ram_bytes": 100},
        )

    def test_json_store_survives_ledger_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reservations.json"

            store = JsonFileReservationStore(path)

            first = ResourceReservationLedger(
                {"system_ram_bytes": 100},
                store=store,
            )

            first.reserve(
                "model-a",
                {"system_ram_bytes": 25},
                metadata={"model_id": "example/model"},
            )

            second = ResourceReservationLedger(
                {"system_ram_bytes": 100},
                store=JsonFileReservationStore(path),
            )

            restored = second.reservation_for_workload(
                "model-a"
            )

            self.assertIsNotNone(restored)
            self.assertEqual(
                restored.resources,
                {"system_ram_bytes": 25},
            )
            self.assertEqual(
                restored.metadata["model_id"],
                "example/model",
            )

    def test_reconcile_releases_only_stale_workloads(self) -> None:
        ledger = ResourceReservationLedger(
            {"system_ram_bytes": 100}
        )

        ledger.reserve(
            "model-a",
            {"system_ram_bytes": 25},
        )
        ledger.reserve(
            "model-b",
            {"system_ram_bytes": 25},
        )

        released = ledger.reconcile(
            {"model-b"}
        )

        self.assertEqual(
            [value.workload_id for value in released],
            ["model-a"],
        )

        self.assertIsNone(
            ledger.reservation_for_workload("model-a")
        )
        self.assertIsNotNone(
            ledger.reservation_for_workload("model-b")
        )

    def test_capacity_refresh_does_not_destroy_reservations(self) -> None:
        ledger = ResourceReservationLedger(
            {"system_ram_bytes": 100}
        )

        ledger.reserve(
            "model-a",
            {"system_ram_bytes": 60},
        )

        ledger.set_capacities(
            {"system_ram_bytes": 50}
        )

        snapshot = ledger.snapshot()

        self.assertEqual(
            snapshot.reserved["system_ram_bytes"],
            60,
        )
        self.assertEqual(
            snapshot.available["system_ram_bytes"],
            -10,
        )

        decision = ledger.evaluate(
            {"system_ram_bytes": 1}
        )

        self.assertFalse(decision.allowed)


if __name__ == "__main__":
    unittest.main()
