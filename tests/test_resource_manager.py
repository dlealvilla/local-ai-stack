from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.resource_manager.json_state import (
    JsonFileWorkloadStateStore,
)
from adapters.resource_reservations.json_file import (
    JsonFileReservationStore,
)
from core.resource_manager import (
    ResourceManager,
    RuntimeStartError,
    RuntimeStopError,
    UnknownModelError,
    WorkloadConflictError,
)
from core.resource_reservations import (
    ReservationDeniedError,
    ResourceReservationLedger,
)


class FakePlanningProvider:
    def __init__(
        self,
        *,
        capacities=None,
        models=None,
    ):
        self.capacities = capacities or {
            "accelerator:0:memory": 100,
        }

        self.models = models or {
            "model-a": 40,
            "model-b": 70,
        }

    def build_view(self):
        resolutions = {
            model_id: {
                "model_id": model_id,
                "resolved": True,
                "basis":
                    "provisional_estimate",
                "requirements": {
                    "accelerator:0:memory":
                        amount,
                },
            }
            for model_id, amount
            in self.models.items()
        }

        return {
            "capacities":
                dict(self.capacities),
            "requirement_resolutions_by_model":
                resolutions,
            "requirements_by_model": {
                model_id: dict(
                    resolution["requirements"]
                )
                for model_id, resolution
                in resolutions.items()
            },
        }


class FakeRuntime:
    def __init__(self):
        self.started = []
        self.stopped = []
        self.fail_start = False
        self.fail_stop = False

    def start(
        self,
        *,
        workload_id,
        model_id,
        metadata,
    ):
        if self.fail_start:
            raise RuntimeError(
                "synthetic start failure"
            )

        self.started.append(
            (workload_id, model_id)
        )

        return {
            "runtime_handle":
                f"handle:{workload_id}",
        }

    def stop(
        self,
        *,
        workload_id,
        model_id,
        runtime_state,
    ):
        if self.fail_stop:
            raise RuntimeError(
                "synthetic stop failure"
            )

        self.stopped.append(
            (workload_id, model_id)
        )


class ResourceManagerTests(unittest.TestCase):
    def make_manager(
        self,
        *,
        planning=None,
        runtime=None,
        reservation_store=None,
        state_store=None,
    ):
        ledger = ResourceReservationLedger(
            {},
            store=reservation_store,
        )

        return ResourceManager(
            ledger=ledger,
            planning_provider=
                planning
                or FakePlanningProvider(),
            runtime=runtime
                or FakeRuntime(),
            state_store=state_store,
        )

    def test_preview_does_not_reserve(self):
        manager = self.make_manager()

        preview = manager.preview_start(
            "model-a"
        )

        self.assertTrue(
            preview["admission"]["allowed"]
        )

        self.assertEqual(
            manager.snapshot()
                ["resources"]
                ["reservations"],
            [],
        )

    def test_start_reserves_and_tracks_running_workload(self):
        runtime = FakeRuntime()

        manager = self.make_manager(
            runtime=runtime
        )

        workload = manager.start_model(
            "model-a",
            workload_id="workload-a",
        )

        self.assertEqual(
            workload.status,
            "running",
        )

        self.assertEqual(
            len(
                manager.snapshot()
                ["resources"]
                ["reservations"]
            ),
            1,
        )

        self.assertEqual(
            runtime.started,
            [
                (
                    "workload-a",
                    "model-a",
                )
            ],
        )

    def test_second_workload_is_denied_when_capacity_exhausted(self):
        manager = self.make_manager()

        manager.start_model(
            "model-a",
            workload_id="workload-a",
        )

        with self.assertRaises(
            ReservationDeniedError
        ):
            manager.start_model(
                "model-b",
                workload_id="workload-b",
            )

        self.assertIsNone(
            manager.workload(
                "workload-b"
            )
        )

    def test_start_runtime_failure_rolls_back_reservation(self):
        runtime = FakeRuntime()
        runtime.fail_start = True

        manager = self.make_manager(
            runtime=runtime
        )

        with self.assertRaises(
            RuntimeStartError
        ):
            manager.start_model(
                "model-a",
                workload_id="workload-a",
            )

        self.assertIsNone(
            manager.workload(
                "workload-a"
            )
        )

        self.assertEqual(
            manager.snapshot()
                ["resources"]
                ["reservations"],
            [],
        )

    def test_stop_releases_reservation(self):
        runtime = FakeRuntime()

        manager = self.make_manager(
            runtime=runtime
        )

        manager.start_model(
            "model-a",
            workload_id="workload-a",
        )

        stopped = manager.stop_workload(
            "workload-a"
        )

        self.assertEqual(
            stopped.status,
            "stopped",
        )

        self.assertIsNone(
            manager.workload(
                "workload-a"
            )
        )

        self.assertEqual(
            manager.snapshot()
                ["resources"]
                ["reservations"],
            [],
        )

    def test_stop_failure_keeps_workload_and_reservation(self):
        runtime = FakeRuntime()

        manager = self.make_manager(
            runtime=runtime
        )

        manager.start_model(
            "model-a",
            workload_id="workload-a",
        )

        runtime.fail_stop = True

        with self.assertRaises(
            RuntimeStopError
        ):
            manager.stop_workload(
                "workload-a"
            )

        self.assertEqual(
            manager.workload(
                "workload-a"
            ).status,
            "running",
        )

        self.assertEqual(
            len(
                manager.snapshot()
                ["resources"]
                ["reservations"]
            ),
            1,
        )

    def test_unknown_model_fails_before_reservation(self):
        manager = self.make_manager()

        with self.assertRaises(
            UnknownModelError
        ):
            manager.start_model(
                "unknown-model",
                workload_id="workload-x",
            )

        self.assertEqual(
            manager.snapshot()
                ["resources"]
                ["reservations"],
            [],
        )

    def test_duplicate_workload_id_is_rejected(self):
        manager = self.make_manager()

        manager.start_model(
            "model-a",
            workload_id="same",
        )

        with self.assertRaises(
            WorkloadConflictError
        ):
            manager.start_model(
                "model-a",
                workload_id="same",
            )

    def test_capacity_refresh_changes_future_admission(self):
        planning = FakePlanningProvider(
            capacities={
                "accelerator:0:memory":
                    100,
            }
        )

        manager = self.make_manager(
            planning=planning
        )

        self.assertTrue(
            manager.preview_start(
                "model-a"
            )["admission"]["allowed"]
        )

        planning.capacities = {
            "accelerator:0:memory":
                20,
        }

        self.assertFalse(
            manager.preview_start(
                "model-a"
            )["admission"]["allowed"]
        )

    def test_durable_state_and_reservation_survive_recreation(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)

            reservation_path = (
                directory
                / "reservations.json"
            )

            workload_path = (
                directory
                / "workloads.json"
            )

            planning = FakePlanningProvider()
            runtime = FakeRuntime()

            first = self.make_manager(
                planning=planning,
                runtime=runtime,
                reservation_store=
                    JsonFileReservationStore(
                        reservation_path
                    ),
                state_store=
                    JsonFileWorkloadStateStore(
                        workload_path
                    ),
            )

            first.start_model(
                "model-a",
                workload_id="persisted",
            )

            second = self.make_manager(
                planning=planning,
                runtime=runtime,
                reservation_store=
                    JsonFileReservationStore(
                        reservation_path
                    ),
                state_store=
                    JsonFileWorkloadStateStore(
                        workload_path
                    ),
            )

            restored = second.workload(
                "persisted"
            )

            self.assertIsNotNone(
                restored
            )

            self.assertEqual(
                restored.status,
                "running",
            )

            self.assertEqual(
                len(
                    second.snapshot()
                    ["resources"]
                    ["reservations"]
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
