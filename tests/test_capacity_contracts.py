"""C1 parity tests for the normalized capacity contracts.

The oracle is the existing source, not hand-written arithmetic. Memory
figures come from the real `build_resource_capacity` and
`build_resource_safety`; the storage budget comes from the real
`calculate_platform_storage_budget`. A test asserting a number this
module calculated itself would prove nothing about parity.

Observed values come from the authoritative RunPod host so C2 can compare
real-host output directly.
"""

from __future__ import annotations

import unittest
from unittest import mock

from core.capacity_contracts import (
    CAPACITY_CONTRACTS_SCHEMA_VERSION,
    PLATFORM_DATA_STORAGE_POOL_ID,
    build_capacity_envelope,
    build_host_capability_profile,
)
from core.resource_capacity import build_resource_capacity
from core.resource_reservation_bridge import (
    reservation_capacities_from_resource_safety,
)
from core.resource_reservations import ResourceReservationLedger
from core.resource_safety import build_resource_safety
from core.storage_budget import (
    calculate_platform_storage_budget,
)


# Observed on the authoritative host (NVIDIA RTX PRO 4500 Blackwell
# Server Edition, RunPod network volume).
HOST_RAM_TOTAL = 811_121_754_112
HOST_RAM_AVAILABLE = 664_193_302_528

HOST_VRAM_TOTAL = 34_207_694_848
HOST_VRAM_FREE = 33_688_649_728
HOST_VRAM_USED = HOST_VRAM_TOTAL - HOST_VRAM_FREE

# Golden values produced by the existing resource-safety implementation
# for the observation above. C2 compares real-host output against these.
#
# Live RAM availability drifts between reads, so a real-host comparison
# must derive both figures from a single capacity snapshot rather than
# calling the builders independently.
GOLDEN_RAM_PROTECTED = 81_112_175_411
GOLDEN_RAM_SAFE = 583_081_127_117
GOLDEN_VRAM_PROTECTED = 3_420_769_484
GOLDEN_VRAM_SAFE = 30_267_880_244

# The filesystem advertises ~238 TB while the platform has no verified
# capacity at all. Preserving that contradiction is the point.
REPORTED_FS_TOTAL = 959_597_695_598_592
REPORTED_FS_FREE = 238_077_691_035_648

GIB = 1024 ** 3


def snapshot(*, accelerators=None, ram_available=HOST_RAM_AVAILABLE):
    """A capacity snapshot in the shape `build_resource_capacity` consumes."""

    if accelerators is None:
        accelerators = [
            {
                "index": 0,
                "vendor": "nvidia",
                "name": "NVIDIA RTX PRO 4500 Blackwell Server Edition",
                "memory": {
                    "total_bytes": HOST_VRAM_TOTAL,
                    "used_bytes": HOST_VRAM_USED,
                    "free_bytes": HOST_VRAM_FREE,
                },
            },
        ]

    used = None

    if ram_available is not None:
        used = HOST_RAM_TOTAL - ram_available

    return {
        "schema_version": 1,
        "generated_at": "2026-09-02T11:46:14.879961+00:00",
        "host": {
            "operating_system": "Linux",
            "architecture": "x86_64",
            "cpu_model": "AMD EPYC 9354 32-Core Processor",
            "cpu_cores": 128,
        },
        "memory": {
            "total_bytes": HOST_RAM_TOTAL,
            "used_bytes": used,
            "available_bytes": ram_available,
            "availability_source": "/proc/meminfo:MemAvailable",
        },
        "accelerators": accelerators,
        "storage": {
            "path": "/workspace",
            "total_bytes": REPORTED_FS_TOTAL,
            "used_bytes": REPORTED_FS_TOTAL - REPORTED_FS_FREE,
            "free_bytes": REPORTED_FS_FREE,
            "scope": "mounted_filesystem_observation",
            "quota_known": False,
        },
        "workload": {
            "selected_model_ids": [],
            "running_model_ids": [],
            "loaded_model_ids": [],
            "reservations": None,
        },
    }


def unresolved_capacity_resolution():
    """A real-shaped resolution where the filesystem figure was rejected."""

    return {
        "schema_version": 1,
        "provider": "runpod_network_volume",
        "evidence": [
            {
                "schema_version": 1,
                "evidence_id": "filesystem_free",
                "source": "filesystem_statvfs",
                "scope": "mounted_filesystem",
                "type": "diagnostic",
                "value_bytes": REPORTED_FS_FREE,
                "confidence": "rejected",
                "accepted": False,
                "detail": (
                    "Filesystem figure appears to describe a "
                    "shared/provider backing filesystem and is not "
                    "accepted as customer quota."
                ),
            },
        ],
        "consensus": {
            "resolved_bytes": None,
            "agreement": None,
            "strongest_verified_lower_bound_bytes": None,
            "smallest_observed_upper_failure_bytes": None,
            "bound_disagreement": False,
        },
        "resolved": {
            "remaining_bytes": None,
            "effective_total_bytes": None,
            "basis": "unresolved",
            "confidence": "unknown",
        },
        "allocation_policy": {
            "warning_free_fraction": 0.2,
            "protected_free_fraction": 0.15,
            "minimum_reserve_bytes": 10_000_000_000,
            "reserve_bytes": None,
            "safe_allocatable_bytes": None,
        },
        "fallback": {
            "sonar_required": True,
            "maintenance_sonar_enabled": False,
        },
        "warnings": [],
    }


def verified_capacity_resolution():
    """A resolution backed by empirical evidence, as Sonar would leave it."""

    verified_lower_bound = 32 * GIB
    upper_failure = 48 * GIB
    reserve = 10_000_000_000
    safe_allocatable = verified_lower_bound - reserve

    return {
        "schema_version": 1,
        "provider": "runpod_network_volume",
        "evidence": [
            {
                "schema_version": 1,
                "evidence_id": "filesystem_free",
                "source": "filesystem_statvfs",
                "type": "diagnostic",
                "value_bytes": REPORTED_FS_FREE,
                "confidence": "rejected",
                "accepted": False,
            },
            {
                "schema_version": 1,
                "evidence_id": "empirical_probe",
                "source": "capacity_sonar",
                "type": "empirical",
                "value_bytes": verified_lower_bound,
                "confidence": "high",
                "accepted": True,
            },
        ],
        "consensus": {
            "resolved_bytes": verified_lower_bound,
            "agreement": True,
            "strongest_verified_lower_bound_bytes": (
                verified_lower_bound
            ),
            "smallest_observed_upper_failure_bytes": upper_failure,
            "bound_disagreement": False,
        },
        "resolved": {
            "remaining_bytes": verified_lower_bound,
            "effective_total_bytes": verified_lower_bound,
            "basis": "empirical_evidence",
            "confidence": "medium",
        },
        "allocation_policy": {
            "warning_free_fraction": 0.2,
            "protected_free_fraction": 0.15,
            "minimum_reserve_bytes": reserve,
            "reserve_bytes": reserve,
            "safe_allocatable_bytes": safe_allocatable,
        },
        "fallback": {
            "sonar_required": False,
            "maintenance_sonar_enabled": False,
        },
        "warnings": [],
    }


def storage_plan(
    capacity_resolution,
    *,
    platform_used_bytes=0,
    capacity_source="live_capacity_evidence",
    cache_valid=False,
):
    """Assemble a plan whose budget comes from the real budget owner."""

    budget = calculate_platform_storage_budget(
        capacity_resolution=capacity_resolution,
        platform_used_bytes=platform_used_bytes,
        platform_allocation_percent=100.0,
    )

    return {
        "schema_version": 1,
        "capacity": capacity_resolution,
        "capacity_source": capacity_source,
        "capacity_cache": {
            "valid": cache_valid,
            "reason": None if cache_valid else "cache_missing",
        },
        "calibration": None,
        "platform_usage": {
            "schema_version": 1,
            "data_root": "/workspace",
            "total_logical_bytes": platform_used_bytes,
        },
        "platform_usage_reconciliation": {
            "total_platform_used_bytes": platform_used_bytes,
        },
        "platform_usage_source": "reconciled_platform_storage",
        "platform_budget": budget,
        "dependency_chain": [],
    }, budget


class MemoryParityTests(unittest.TestCase):
    """The envelope must restate resource-safety figures, not recompute them."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_capacity = build_resource_capacity(self.snapshot)
        self.resource_safety = build_resource_safety(
            self.resource_capacity
        )
        self.envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
        )

    def oracle(self, pool_id):
        for pool in self.resource_safety["resource_pools"]:
            if pool["pool_id"] == pool_id:
                return pool

        raise AssertionError(f"no such pool: {pool_id}")

    def assert_pool_parity(self, pool_id):
        expected = self.oracle(pool_id)
        actual = self.envelope.memory_pool(pool_id)

        self.assertIsNotNone(actual)

        capacity = expected["capacity"]
        safety = expected["safety"]

        self.assertEqual(
            actual.reported_total_bytes,
            capacity["total_bytes"],
        )
        self.assertEqual(
            actual.reported_used_bytes,
            capacity["used_bytes"],
        )
        self.assertEqual(
            actual.reported_available_bytes,
            capacity["available_bytes"],
        )
        self.assertEqual(
            actual.protected_reserve_bytes,
            safety["protected_reserve_bytes"],
        )
        self.assertEqual(
            actual.safe_available_before_reservations_bytes,
            safety["safe_available_before_reservations_bytes"],
        )
        self.assertEqual(
            actual.memory_type,
            expected["memory_type"],
        )

        return actual

    def test_ram_parity(self):
        pool = self.assert_pool_parity("memory:system_ram")

        self.assertEqual(pool.memory_type, "system_ram")

        # Golden real-host values for C2 comparison.
        self.assertEqual(
            pool.protected_reserve_bytes,
            GOLDEN_RAM_PROTECTED,
        )
        self.assertEqual(
            pool.safe_available_before_reservations_bytes,
            GOLDEN_RAM_SAFE,
        )

    def test_accelerator_parity(self):
        pool = self.assert_pool_parity("accelerator:0:memory")

        self.assertEqual(pool.memory_type, "dedicated_vram")
        self.assertEqual(pool.scope["kind"], "accelerator")
        self.assertEqual(pool.scope["accelerator_index"], 0)

        self.assertEqual(
            pool.protected_reserve_bytes,
            GOLDEN_VRAM_PROTECTED,
        )
        self.assertEqual(
            pool.safe_available_before_reservations_bytes,
            GOLDEN_VRAM_SAFE,
        )

    def test_reported_available_is_not_the_safe_value(self):
        # The reported/protected/safe layers must stay distinct rather
        # than collapsing into one capacity number.
        pool = self.envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(pool.reported_available_bytes, HOST_VRAM_FREE)
        self.assertLess(
            pool.safe_available_before_reservations_bytes,
            pool.reported_available_bytes,
        )
        self.assertEqual(
            pool.reported_available_bytes
            - pool.protected_reserve_bytes,
            pool.safe_available_before_reservations_bytes,
        )

    def test_unresolved_pool_stays_unresolved(self):
        # A memory architecture the observer has not classified must not
        # acquire a protected reserve or a safe value.
        unclassified = snapshot(
            accelerators=[
                {
                    "index": 0,
                    "vendor": "exotic",
                    "name": "Unclassified Accelerator",
                    "memory": {
                        "total_bytes": HOST_VRAM_TOTAL,
                        "used_bytes": 0,
                        "free_bytes": HOST_VRAM_TOTAL,
                    },
                },
            ]
        )

        safety = build_resource_safety(
            build_resource_capacity(unclassified)
        )
        envelope = build_capacity_envelope(
            capacity_snapshot=unclassified,
            resource_safety=safety,
        )

        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(pool.memory_type, "accelerator_memory")
        self.assertFalse(pool.safety_resolved)
        self.assertEqual(
            pool.safety_reason,
            "memory_architecture_unresolved",
        )
        self.assertIsNone(pool.protected_reserve_bytes)
        self.assertIsNone(
            pool.safe_available_before_reservations_bytes
        )
        self.assertIn(
            "accelerator:0:memory",
            envelope.unresolved_pool_ids,
        )


class ReservationAccountingTests(unittest.TestCase):
    """Managed reservations must never be subtracted twice."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_safety = build_resource_safety(
            build_resource_capacity(self.snapshot)
        )

        capacities = reservation_capacities_from_resource_safety(
            self.resource_safety
        )

        self.ledger = ResourceReservationLedger(capacities)

        self.reserved_bytes = 8 * GIB

        self.ledger.reserve(
            "workload-a",
            {"accelerator:0:memory": self.reserved_bytes},
        )

    def test_reservation_figures_are_copied_from_the_ledger(self):
        snapshot_dict = self.ledger.snapshot().to_dict()

        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            reservation_snapshot=snapshot_dict,
        )

        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertTrue(envelope.reservations_applied)
        self.assertEqual(
            pool.managed_reserved_bytes,
            snapshot_dict["reserved"]["accelerator:0:memory"],
        )
        self.assertEqual(
            pool.safe_available_bytes,
            snapshot_dict["available"]["accelerator:0:memory"],
        )
        self.assertEqual(
            pool.ledger_capacity_bytes,
            snapshot_dict["capacities"]["accelerator:0:memory"],
        )

    def test_no_double_subtraction_after_capacity_refresh(self):
        # ResourceManager refreshes ledger capacities by adding managed
        # reservations back to the live observation, so the ledger's
        # available figure already equals observed safe availability.
        # Recomputing safe availability here would subtract the
        # reservation a second time.
        observed_safe = GOLDEN_VRAM_SAFE

        self.ledger.set_capacities(
            {
                "accelerator:0:memory": (
                    observed_safe + self.reserved_bytes
                ),
                "memory:system_ram": GOLDEN_RAM_SAFE,
            }
        )

        snapshot_dict = self.ledger.snapshot().to_dict()

        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            reservation_snapshot=snapshot_dict,
        )

        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(pool.safe_available_bytes, observed_safe)

        double_subtracted = (
            pool.safe_available_before_reservations_bytes
            - self.reserved_bytes
        )

        self.assertNotEqual(
            pool.safe_available_bytes,
            double_subtracted,
        )

    def test_absent_reservations_are_unknown_not_zero(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
        )

        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertFalse(envelope.reservations_applied)
        self.assertIsNone(pool.managed_reserved_bytes)
        self.assertIsNone(pool.safe_available_bytes)
        self.assertIsNotNone(
            pool.safe_available_before_reservations_bytes
        )


class StorageUnresolvedTests(unittest.TestCase):
    """Reported filesystem space must never become verified capacity."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_safety = build_resource_safety(
            build_resource_capacity(self.snapshot)
        )
        self.plan, self.budget = storage_plan(
            unresolved_capacity_resolution()
        )
        self.envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            storage_plan=self.plan,
        )
        self.pool = self.envelope.storage_pool(
            PLATFORM_DATA_STORAGE_POOL_ID
        )

    def test_reported_capacity_is_preserved(self):
        self.assertEqual(
            self.pool.reported_total_bytes,
            REPORTED_FS_TOTAL,
        )
        self.assertEqual(
            self.pool.reported_free_bytes,
            REPORTED_FS_FREE,
        )
        self.assertEqual(
            self.pool.reported_scope,
            "mounted_filesystem_observation",
        )
        self.assertFalse(
            self.pool.reported_accepted_as_capacity_evidence
        )

    def test_verified_capacity_stays_unresolved(self):
        self.assertIsNone(self.pool.verified_remaining_bytes)
        self.assertIsNone(self.pool.verified_effective_total_bytes)
        self.assertIsNone(self.pool.verified_lower_bound_bytes)
        self.assertEqual(self.pool.capacity_basis, "unresolved")
        self.assertEqual(self.pool.capacity_confidence, "unknown")

    def test_safe_storage_stays_unresolved(self):
        self.assertIsNone(self.pool.protected_reserve_bytes)
        self.assertIsNone(self.pool.safe_allocatable_bytes)
        self.assertIsNone(
            self.pool.available_for_new_platform_bytes
        )
        self.assertFalse(self.pool.budget_resolved)

    def test_budget_parity_with_the_budget_owner(self):
        self.assertEqual(
            self.pool.budget_reason,
            self.budget["reason"],
        )
        self.assertEqual(
            self.pool.available_for_new_platform_bytes,
            self.budget["available_for_new_platform_bytes"],
        )
        self.assertEqual(
            self.pool.platform_used_bytes,
            self.budget["platform_used_bytes"],
        )

    def test_no_reported_to_verified_promotion(self):
        # 238 TB reported, nothing verified: the contradiction must
        # survive normalization untouched.
        self.assertIsNotNone(self.pool.reported_free_bytes)
        self.assertIsNone(self.pool.verified_remaining_bytes)
        self.assertNotEqual(
            self.pool.verified_remaining_bytes,
            self.pool.reported_free_bytes,
        )


class StorageVerifiedTests(unittest.TestCase):
    """With empirical evidence, the envelope must restate it exactly."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_safety = build_resource_safety(
            build_resource_capacity(self.snapshot)
        )
        self.resolution = verified_capacity_resolution()
        self.plan, self.budget = storage_plan(
            self.resolution,
            capacity_source="valid_capacity_cache",
            cache_valid=True,
        )
        self.envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            storage_plan=self.plan,
        )
        self.pool = self.envelope.storage_pool(
            PLATFORM_DATA_STORAGE_POOL_ID
        )

    def test_bounds_and_basis_parity(self):
        consensus = self.resolution["consensus"]
        resolved = self.resolution["resolved"]

        self.assertEqual(
            self.pool.verified_lower_bound_bytes,
            consensus["strongest_verified_lower_bound_bytes"],
        )
        self.assertEqual(
            self.pool.observed_upper_failure_bytes,
            consensus["smallest_observed_upper_failure_bytes"],
        )
        self.assertEqual(
            self.pool.verified_remaining_bytes,
            resolved["remaining_bytes"],
        )
        self.assertEqual(
            self.pool.capacity_basis,
            "empirical_evidence",
        )
        self.assertEqual(
            self.pool.capacity_confidence,
            "medium",
        )

    def test_safe_capacity_parity(self):
        policy = self.resolution["allocation_policy"]

        self.assertEqual(
            self.pool.protected_reserve_bytes,
            policy["reserve_bytes"],
        )
        self.assertEqual(
            self.pool.safe_allocatable_bytes,
            policy["safe_allocatable_bytes"],
        )

    def test_budget_parity_with_the_budget_owner(self):
        self.assertTrue(self.pool.budget_resolved)
        self.assertEqual(
            self.pool.available_for_new_platform_bytes,
            self.budget["available_for_new_platform_bytes"],
        )
        self.assertEqual(
            self.pool.budget_basis,
            self.budget["basis"],
        )

    def test_safe_capacity_never_exceeds_the_verified_lower_bound(self):
        self.assertLessEqual(
            self.pool.safe_allocatable_bytes,
            self.pool.verified_lower_bound_bytes,
        )

    def test_evidence_freshness_is_represented(self):
        self.assertEqual(
            self.pool.capacity_source,
            "valid_capacity_cache",
        )
        self.assertTrue(self.pool.evidence_cache_valid)


class HostCapabilityProfileTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()
        self.resource_capacity = build_resource_capacity(self.snapshot)
        self.plan, _ = storage_plan(unresolved_capacity_resolution())
        self.profile = build_host_capability_profile(
            capacity_snapshot=self.snapshot,
            resource_capacity=self.resource_capacity,
            storage_plan=self.plan,
        )

    def test_stable_host_facts(self):
        self.assertEqual(
            self.profile.schema_version,
            CAPACITY_CONTRACTS_SCHEMA_VERSION,
        )
        self.assertEqual(self.profile.operating_system, "Linux")
        self.assertEqual(self.profile.architecture, "x86_64")
        self.assertEqual(self.profile.cpu_cores, 128)
        self.assertEqual(
            self.profile.ram_total_bytes,
            HOST_RAM_TOTAL,
        )

    def test_accelerator_capability(self):
        self.assertEqual(len(self.profile.accelerators), 1)

        accelerator = self.profile.accelerators[0]

        self.assertEqual(accelerator.pool_id, "accelerator:0:memory")
        self.assertEqual(accelerator.index, 0)
        self.assertEqual(accelerator.vendor, "nvidia")
        self.assertEqual(accelerator.memory_type, "dedicated_vram")
        self.assertEqual(
            accelerator.memory_total_bytes,
            HOST_VRAM_TOTAL,
        )

    def test_storage_pool_identity(self):
        self.assertEqual(len(self.profile.storage_pools), 1)

        pool = self.profile.storage_pools[0]

        self.assertEqual(pool.pool_id, PLATFORM_DATA_STORAGE_POOL_ID)
        self.assertEqual(pool.path, "/workspace")
        self.assertEqual(pool.provider, "runpod_network_volume")
        self.assertFalse(pool.quota_known)

    def test_storage_identity_is_supplied_never_measured(self):
        profile = build_host_capability_profile(
            capacity_snapshot=self.snapshot,
            resource_capacity=self.resource_capacity,
            storage_plan=self.plan,
            storage_identity={
                "device_id": 42,
                "mount_source": "10.0.0.1:/vol",
                "filesystem_type": "nfs4",
            },
        )

        pool = profile.storage_pools[0]

        self.assertEqual(pool.device_id, 42)
        self.assertEqual(pool.filesystem_type, "nfs4")

    def test_point_in_time_state_is_absent(self):
        # Live usage and reservations belong to CapacityEnvelope.
        serialized = self.profile.to_dict()

        self.assertNotIn("reservations", serialized)

        for key in serialized:
            self.assertNotIn("available", key)
            self.assertNotIn("used", key)


class MultiplePoolIdentityTests(unittest.TestCase):
    def test_two_accelerators_are_not_collapsed(self):
        two_gpus = snapshot(
            accelerators=[
                {
                    "index": 0,
                    "vendor": "nvidia",
                    "name": "GPU A",
                    "memory": {
                        "total_bytes": HOST_VRAM_TOTAL,
                        "used_bytes": 0,
                        "free_bytes": HOST_VRAM_TOTAL,
                    },
                },
                {
                    "index": 1,
                    "vendor": "nvidia",
                    "name": "GPU B",
                    "memory": {
                        "total_bytes": 16 * GIB,
                        "used_bytes": 2 * GIB,
                        "free_bytes": 14 * GIB,
                    },
                },
            ]
        )

        resource_capacity = build_resource_capacity(two_gpus)
        safety = build_resource_safety(resource_capacity)

        envelope = build_capacity_envelope(
            capacity_snapshot=two_gpus,
            resource_safety=safety,
        )
        profile = build_host_capability_profile(
            capacity_snapshot=two_gpus,
            resource_capacity=resource_capacity,
        )

        accelerator_pools = [
            pool
            for pool in envelope.memory_pools
            if pool.scope.get("kind") == "accelerator"
        ]

        self.assertEqual(len(accelerator_pools), 2)
        self.assertEqual(len(profile.accelerators), 2)

        self.assertEqual(
            {pool.pool_id for pool in accelerator_pools},
            {"accelerator:0:memory", "accelerator:1:memory"},
        )

        first = envelope.memory_pool("accelerator:0:memory")
        second = envelope.memory_pool("accelerator:1:memory")

        self.assertNotEqual(
            first.reported_total_bytes,
            second.reported_total_bytes,
        )
        self.assertNotEqual(
            first.safe_available_before_reservations_bytes,
            second.safe_available_before_reservations_bytes,
        )

    def test_storage_is_a_collection_not_a_scalar(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=snapshot(),
            resource_safety=build_resource_safety(
                build_resource_capacity(snapshot())
            ),
            storage_plan=storage_plan(
                unresolved_capacity_resolution()
            )[0],
        )

        self.assertIsInstance(envelope.storage_pools, tuple)
        self.assertEqual(len(envelope.storage_pools), 1)

    def test_storage_pools_are_absent_when_no_plan_is_supplied(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=snapshot(),
            resource_safety=build_resource_safety(
                build_resource_capacity(snapshot())
            ),
        )

        self.assertEqual(envelope.storage_pools, ())


class NormalizationPurityTests(unittest.TestCase):
    """Normalization consumes evidence; it never detects anything."""

    def test_no_detection_or_configuration_access(self):
        snap = snapshot()
        safety = build_resource_safety(build_resource_capacity(snap))
        plan, _ = storage_plan(unresolved_capacity_resolution())

        def forbidden(*args, **kwargs):
            raise AssertionError(
                "capacity contracts must not perform detection"
            )

        with mock.patch(
            "core.config.load_config",
            forbidden,
        ), mock.patch(
            "shutil.disk_usage",
            forbidden,
        ), mock.patch(
            "core.hardware.inspect_hardware",
            forbidden,
        ):
            envelope = build_capacity_envelope(
                capacity_snapshot=snap,
                resource_safety=safety,
                storage_plan=plan,
            )
            profile = build_host_capability_profile(
                capacity_snapshot=snap,
                resource_capacity=build_resource_capacity(snap),
                storage_plan=plan,
            )

        self.assertTrue(envelope.memory_pools)
        self.assertTrue(profile.accelerators)

    def test_contracts_are_immutable(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=snapshot(),
            resource_safety=build_resource_safety(
                build_resource_capacity(snapshot())
            ),
        )

        with self.assertRaises(Exception):
            envelope.schema_version = 2

        with self.assertRaises(Exception):
            envelope.memory_pools[0].safe_available_bytes = 1

    def test_non_mapping_inputs_are_rejected(self):
        with self.assertRaises(TypeError):
            build_capacity_envelope(
                capacity_snapshot=[],
                resource_safety={},
            )

        with self.assertRaises(TypeError):
            build_host_capability_profile(
                capacity_snapshot={},
                resource_capacity=None,
            )

    def test_serialization_round_trips_to_plain_data(self):
        import json

        envelope = build_capacity_envelope(
            capacity_snapshot=snapshot(),
            resource_safety=build_resource_safety(
                build_resource_capacity(snapshot())
            ),
            storage_plan=storage_plan(
                verified_capacity_resolution()
            )[0],
        )

        serialized = json.loads(json.dumps(envelope.to_dict()))

        self.assertEqual(
            serialized["schema_version"],
            CAPACITY_CONTRACTS_SCHEMA_VERSION,
        )
        self.assertEqual(len(serialized["storage_pools"]), 1)


if __name__ == "__main__":
    unittest.main()
