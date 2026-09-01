import unittest

from core.resource_manager import (
    ResourceManager,
)
from core.resource_reservations import (
    ResourceReservationLedger,
)


POOL = "accelerator:0:memory"


class FakePlanningProvider:
    def __init__(
        self,
        *,
        capacity,
        requirement,
    ):
        self.capacity = int(capacity)
        self.requirement = int(requirement)

    def build_view(self):
        return {
            "capacities": {
                POOL:
                    self.capacity,
            },

            "requirements_by_model": {
                "model-a": {
                    POOL:
                        self.requirement,
                },
            },

            "requirement_resolutions_by_model": {
                "model-a": {
                    "model_id":
                        "model-a",

                    "resolved":
                        True,

                    "basis":
                        "test",

                    "requirements": {
                        POOL:
                            self.requirement,
                    },
                },
            },
        }


class FakeRuntime:
    pass


class CapacityAccountingTests(
    unittest.TestCase
):
    def make_manager(
        self,
        *,
        capacity=100,
        requirement=80,
    ):
        ledger = (
            ResourceReservationLedger(
                {}
            )
        )

        provider = (
            FakePlanningProvider(
                capacity=capacity,
                requirement=requirement,
            )
        )

        manager = ResourceManager(
            ledger=ledger,
            planning_provider=provider,
            runtime=FakeRuntime(),
        )

        return (
            manager,
            ledger,
            provider,
        )

    def test_no_reservations_use_live_observed_capacity(
        self,
    ):
        manager, ledger, _ = (
            self.make_manager()
        )

        preview = manager.preview_start(
            "model-a"
        )

        self.assertTrue(
            preview["admission"]["allowed"]
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            100,
        )

    def test_managed_runtime_consumption_not_double_subtracted(
        self,
    ):
        manager, ledger, provider = (
            self.make_manager()
        )

        manager.preview_start(
            "model-a"
        )

        ledger.reserve(
            workload_id="first",
            resources={
                POOL: 80,
            },
        )

        # Managed workload physically consumes 80.
        # Live safe availability therefore falls from 100 to 20.
        provider.capacity = 20

        preview = manager.preview_start(
            "model-a"
        )

        admission = preview[
            "admission"
        ]

        self.assertFalse(
            admission["allowed"]
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            100,
        )

        self.assertEqual(
            admission["available"][POOL],
            20,
        )

        self.assertEqual(
            admission["deficits"][POOL],
            60,
        )

    def test_unconsumed_reservation_cannot_inflate_total(
        self,
    ):
        manager, ledger, provider = (
            self.make_manager()
        )

        manager.preview_start(
            "model-a"
        )

        ledger.reserve(
            workload_id="first",
            resources={
                POOL: 80,
            },
        )

        # Reservation exists but physical availability has not
        # changed yet.
        provider.capacity = 100

        preview = manager.preview_start(
            "model-a"
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            100,
        )

        self.assertEqual(
            preview["admission"]["available"][POOL],
            20,
        )

    def test_external_pressure_reduces_accounting_total(
        self,
    ):
        manager, ledger, provider = (
            self.make_manager()
        )

        manager.preview_start(
            "model-a"
        )

        ledger.reserve(
            workload_id="first",
            resources={
                POOL: 80,
            },
        )

        # Managed reservation=80, but only 10 now appears free.
        # Total safely inferable capacity is therefore 90.
        provider.capacity = 10

        preview = manager.preview_start(
            "model-a"
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            90,
        )

        self.assertEqual(
            preview["admission"]["available"][POOL],
            10,
        )

    def test_capacity_can_recover_after_reservations_clear(
        self,
    ):
        manager, ledger, provider = (
            self.make_manager()
        )

        manager.preview_start(
            "model-a"
        )

        reservation = ledger.reserve(
            workload_id="first",
            resources={
                POOL: 80,
            },
        )

        provider.capacity = 10

        manager.preview_start(
            "model-a"
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            90,
        )

        ledger.release(
            reservation.reservation_id
        )

        provider.capacity = 100

        manager.preview_start(
            "model-a"
        )

        self.assertEqual(
            ledger.snapshot().capacities[POOL],
            100,
        )


if __name__ == "__main__":
    unittest.main()
