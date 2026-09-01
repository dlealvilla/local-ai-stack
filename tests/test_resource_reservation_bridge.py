from __future__ import annotations

import unittest

from core.resource_reservation_bridge import (
    ResourceReservationBridgeError,
    reservation_capacities_from_resource_safety,
    resolve_model_reservation_requirement,
)
from core.resource_reservations import (
    ResourceReservationLedger,
)


def safety_fixture():
    return {
        "resource_pools": [
            {
                "pool_id": "memory:system_ram",
                "memory_type": "system_ram",
                "safety": {
                    "resolved": True,
                    "safe_available_before_reservations_bytes":
                        1000,
                },
            },
            {
                "pool_id": "accelerator:0:memory",
                "memory_type": "dedicated_vram",
                "safety": {
                    "resolved": True,
                    "safe_available_before_reservations_bytes":
                        500,
                },
            },
        ],
        "unresolved_pool_ids": [],
    }


class ResourceReservationBridgeTests(unittest.TestCase):
    def test_exact_phase8_safe_capacity_contract(self):
        result = (
            reservation_capacities_from_resource_safety(
                safety_fixture()
            )
        )

        self.assertEqual(
            result,
            {
                "memory:system_ram": 1000,
                "accelerator:0:memory": 500,
            },
        )

    def test_unresolved_pool_is_excluded(self):
        safety = safety_fixture()
        safety["unresolved_pool_ids"] = [
            "accelerator:0:memory"
        ]

        result = (
            reservation_capacities_from_resource_safety(
                safety
            )
        )

        self.assertEqual(
            result,
            {
                "memory:system_ram": 1000,
            },
        )

    def test_missing_exact_safe_field_fails_closed(self):
        safety = safety_fixture()

        del safety["resource_pools"][0]["safety"][
            "safe_available_before_reservations_bytes"
        ]

        with self.assertRaises(
            ResourceReservationBridgeError
        ):
            reservation_capacities_from_resource_safety(
                safety
            )

    def test_exact_runtime_requirement_wins(self):
        model = {
            "model_id": "model-a",
            "model_resource_requirements": {
                "runtime_requirements_ready": True,
                "target_requirements": {
                    "system_ram_bytes": 100,
                    "dedicated_vram_bytes": 200,
                    "unified_memory_bytes": None,
                },
            },
            "dimensions": {
                "memory": {
                    "provisional_estimate": {
                        "resolved": True,
                        "estimated_runtime_target_bytes": 999,
                    }
                }
            },
        }

        result = resolve_model_reservation_requirement(
            model,
            resource_safety=safety_fixture(),
        )

        self.assertEqual(
            result["basis"],
            "exact_target_requirements",
        )

        self.assertEqual(
            result["requirements"],
            {
                "memory:system_ram": 100,
                "accelerator:0:memory": 200,
            },
        )

    def test_resolved_provisional_estimate_is_used(self):
        model = {
            "model_id": "model-a",
            "model_resource_requirements": {
                "runtime_requirements_ready": False,
                "target_requirements": {
                    "system_ram_bytes": None,
                    "dedicated_vram_bytes": None,
                    "unified_memory_bytes": None,
                },
            },
            "dimensions": {
                "memory": {
                    "confidence": "low",
                    "provisional_estimate": {
                        "resolved": True,
                        "confidence": "low",
                        "estimated_runtime_target_bytes": 250,
                        "method": "working_estimate",
                        "reason": "test",
                    },
                }
            },
        }

        result = resolve_model_reservation_requirement(
            model,
            resource_safety=safety_fixture(),
        )

        self.assertEqual(
            result["basis"],
            "provisional_estimate",
        )

        self.assertEqual(
            result["requirements"],
            {
                "accelerator:0:memory": 250,
            },
        )

    def test_unresolved_provisional_estimate_fails_closed(self):
        model = {
            "model_id": "model-a",
            "model_resource_requirements": {
                "runtime_requirements_ready": False,
            },
            "dimensions": {
                "memory": {
                    "provisional_estimate": {
                        "resolved": False,
                        "estimated_runtime_target_bytes": None,
                    }
                }
            },
        }

        with self.assertRaises(
            ResourceReservationBridgeError
        ):
            resolve_model_reservation_requirement(
                model,
                resource_safety=safety_fixture(),
            )

    def test_multiple_gpu_pools_do_not_get_guessed(self):
        safety = safety_fixture()

        safety["resource_pools"].append(
            {
                "pool_id": "accelerator:1:memory",
                "memory_type": "dedicated_vram",
                "safety": {
                    "resolved": True,
                    "safe_available_before_reservations_bytes":
                        500,
                },
            }
        )

        model = {
            "model_id": "model-a",
            "model_resource_requirements": {
                "runtime_requirements_ready": False,
            },
            "dimensions": {
                "memory": {
                    "provisional_estimate": {
                        "resolved": True,
                        "estimated_runtime_target_bytes": 100,
                    }
                }
            },
        }

        with self.assertRaises(
            ResourceReservationBridgeError
        ):
            resolve_model_reservation_requirement(
                model,
                resource_safety=safety,
            )

    def test_bridge_result_is_consumable_by_ledger(self):
        capacities = (
            reservation_capacities_from_resource_safety(
                safety_fixture()
            )
        )

        ledger = ResourceReservationLedger(
            capacities
        )

        decision = ledger.evaluate(
            {
                "accelerator:0:memory": 250,
            }
        )

        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
