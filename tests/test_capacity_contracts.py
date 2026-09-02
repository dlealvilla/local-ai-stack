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
    build_headroom_policy,
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
            actual.observed_safe_available_bytes,
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
            pool.observed_safe_available_bytes,
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
            pool.observed_safe_available_bytes,
            GOLDEN_VRAM_SAFE,
        )

    def test_reported_available_is_not_the_safe_value(self):
        # The reported/protected/safe layers must stay distinct rather
        # than collapsing into one capacity number.
        pool = self.envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(pool.reported_available_bytes, HOST_VRAM_FREE)
        self.assertLess(
            pool.observed_safe_available_bytes,
            pool.reported_available_bytes,
        )
        self.assertEqual(
            pool.reported_available_bytes
            - pool.protected_reserve_bytes,
            pool.observed_safe_available_bytes,
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
            pool.observed_safe_available_bytes
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
            pool.safe_available_for_additional_workload_bytes,
            snapshot_dict["available"]["accelerator:0:memory"],
        )
        self.assertEqual(
            pool.reconstructed_safe_pool_capacity_bytes,
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

        self.assertEqual(
            pool.safe_available_for_additional_workload_bytes,
            observed_safe,
        )

        double_subtracted = (
            pool.observed_safe_available_bytes
            - self.reserved_bytes
        )

        self.assertNotEqual(
            pool.safe_available_for_additional_workload_bytes,
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
        self.assertIsNone(pool.safe_available_for_additional_workload_bytes)
        self.assertIsNotNone(
            pool.observed_safe_available_bytes
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
            first.observed_safe_available_bytes,
            second.observed_safe_available_bytes,
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
            envelope.memory_pools[0].protected_reserve_bytes = 1

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


class HeadroomPolicyTests(unittest.TestCase):
    """Policy is an input read from its owner, never a second calculator."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_safety = build_resource_safety(
            build_resource_capacity(self.snapshot)
        )
        self.plan, _ = storage_plan(verified_capacity_resolution())
        self.policy = build_headroom_policy(
            resource_safety=self.resource_safety,
            storage_plan=self.plan,
        )

    def test_ram_policy_matches_resource_safety(self):
        owner = self.resource_safety["policy"]["system_ram"]
        policy = self.policy.for_memory_type("system_ram")

        self.assertEqual(
            policy.reserve_fraction,
            owner["reserve_fraction"],
        )
        self.assertEqual(
            policy.minimum_reserve_bytes,
            owner["minimum_reserve_bytes"],
        )

        # Current validated defaults.
        self.assertEqual(policy.reserve_fraction, 0.10)
        self.assertEqual(policy.minimum_reserve_bytes, 4 * GIB)

    def test_dedicated_vram_policy_matches_resource_safety(self):
        owner = self.resource_safety["policy"]["dedicated_vram"]
        policy = self.policy.for_memory_type("dedicated_vram")

        self.assertEqual(
            policy.reserve_fraction,
            owner["reserve_fraction"],
        )
        self.assertEqual(
            policy.minimum_reserve_bytes,
            owner["minimum_reserve_bytes"],
        )

        self.assertEqual(policy.reserve_fraction, 0.10)
        self.assertEqual(policy.minimum_reserve_bytes, 1 * GIB)

    def test_fail_closed_architectures_carry_a_strategy_not_a_fraction(self):
        unified = self.policy.for_memory_type("unified_memory")

        self.assertFalse(unified.resolved)
        self.assertIsNone(unified.reserve_fraction)
        self.assertEqual(
            unified.strategy,
            self.resource_safety["policy"]["unified_memory"][
                "strategy"
            ],
        )

    def test_policy_follows_an_administrator_override(self):
        # Reading the policy the calculation actually applied means an
        # override cannot desynchronize policy from result.
        override = {
            "system_ram": {
                "reserve_fraction": 0.25,
                "minimum_reserve_bytes": 8 * GIB,
            },
            "dedicated_vram": {
                "reserve_fraction": 0.10,
                "minimum_reserve_bytes": 1 * GIB,
            },
        }

        safety = build_resource_safety(
            build_resource_capacity(self.snapshot),
            policy=override,
        )

        policy = build_headroom_policy(resource_safety=safety)

        self.assertEqual(
            policy.for_memory_type("system_ram").reserve_fraction,
            0.25,
        )

    def test_storage_policy_is_read_from_the_storage_owner(self):
        owner = self.plan["capacity"]["allocation_policy"]

        self.assertEqual(
            self.policy.storage.protected_free_fraction,
            owner["protected_free_fraction"],
        )
        self.assertEqual(
            self.policy.storage.minimum_reserve_bytes,
            owner["minimum_reserve_bytes"],
        )
        self.assertEqual(
            self.policy.storage.platform_allocation_percent,
            self.plan["platform_budget"][
                "platform_allocation_percent"
            ],
        )

    def test_storage_policy_absent_without_a_storage_plan(self):
        policy = build_headroom_policy(
            resource_safety=self.resource_safety
        )

        self.assertIsNone(policy.storage)

    def test_policy_is_an_input_not_a_result(self):
        # The policy carries no calculated byte figures, and the
        # calculated reserve is not on the policy.
        policy = self.policy.for_memory_type("dedicated_vram")

        self.assertFalse(
            hasattr(policy, "protected_reserve_bytes")
        )

        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
        )
        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(
            pool.protected_reserve_bytes,
            GOLDEN_VRAM_PROTECTED,
        )
        self.assertNotEqual(
            pool.protected_reserve_bytes,
            policy.minimum_reserve_bytes,
        )

    def test_envelope_links_a_pool_to_the_policy_that_produced_it(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            storage_plan=self.plan,
        )

        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertEqual(pool.headroom_policy_key, "dedicated_vram")

        linked = envelope.policy_for("accelerator:0:memory")

        self.assertEqual(linked.memory_type, "dedicated_vram")
        self.assertEqual(linked.reserve_fraction, 0.10)

        # The full explainable chain: policy -> reserve -> safe.
        self.assertEqual(
            pool.reported_total_bytes,
            HOST_VRAM_TOTAL,
        )
        self.assertEqual(
            int(
                linked.reserve_fraction * pool.reported_total_bytes
            ),
            pool.protected_reserve_bytes,
        )

    def test_policy_schema_version(self):
        self.assertEqual(
            self.policy.schema_version,
            CAPACITY_CONTRACTS_SCHEMA_VERSION,
        )


class AccountingSemanticsTests(unittest.TestCase):
    """The three questions an engineer must be able to answer."""

    def setUp(self):
        self.snapshot = snapshot()
        self.resource_safety = build_resource_safety(
            build_resource_capacity(self.snapshot)
        )
        self.pool_id = "accelerator:0:memory"
        self.reserved = 8 * GIB

        self.ledger = ResourceReservationLedger(
            reservation_capacities_from_resource_safety(
                self.resource_safety
            )
        )

    def envelope_with_ledger(self):
        return build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
            reservation_snapshot=(
                self.ledger.snapshot().to_dict()
            ),
        )

    def test_reservation_not_yet_physically_consumed(self):
        # The observation still shows the memory free, so ledger
        # capacity stays at the pre-reservation observed figure via the
        # min() guard and only the ledger's available figure drops.
        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        pool = self.envelope_with_ledger().memory_pool(self.pool_id)

        self.assertEqual(
            pool.reconstructed_safe_pool_capacity_bytes,
            GOLDEN_VRAM_SAFE,
        )
        self.assertEqual(
            pool.managed_reserved_bytes,
            self.reserved,
        )
        self.assertEqual(
            pool.safe_available_for_additional_workload_bytes,
            GOLDEN_VRAM_SAFE - self.reserved,
        )

    def test_reservation_physically_consumed_is_not_subtracted_twice(self):
        # Once the workload consumes memory, the live observation drops
        # by the reserved amount. ResourceManager reconstructs the pool
        # total by adding managed reservations back, so the additional
        # capacity figure must not fall a second time.
        consumed_snapshot = snapshot()
        consumed_snapshot["accelerators"][0]["memory"] = {
            "total_bytes": HOST_VRAM_TOTAL,
            "used_bytes": HOST_VRAM_USED + self.reserved,
            "free_bytes": HOST_VRAM_FREE - self.reserved,
        }

        consumed_safety = build_resource_safety(
            build_resource_capacity(consumed_snapshot)
        )

        observed_now = next(
            pool["safety"][
                "safe_available_before_reservations_bytes"
            ]
            for pool in consumed_safety["resource_pools"]
            if pool["pool_id"] == self.pool_id
        )

        self.assertEqual(
            observed_now,
            GOLDEN_VRAM_SAFE - self.reserved,
        )

        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        # Reconstruction as ResourceManager performs it.
        self.ledger.set_capacities(
            {
                self.pool_id: min(
                    GOLDEN_VRAM_SAFE,
                    observed_now + self.reserved,
                ),
            }
        )

        envelope = build_capacity_envelope(
            capacity_snapshot=consumed_snapshot,
            resource_safety=consumed_safety,
            reservation_snapshot=(
                self.ledger.snapshot().to_dict()
            ),
        )
        pool = envelope.memory_pool(self.pool_id)

        naive = observed_now - self.reserved

        self.assertEqual(
            pool.observed_safe_available_bytes,
            observed_now,
        )
        self.assertEqual(
            pool.reconstructed_safe_pool_capacity_bytes,
            GOLDEN_VRAM_SAFE,
        )
        self.assertEqual(
            pool.safe_available_for_additional_workload_bytes,
            GOLDEN_VRAM_SAFE - self.reserved,
        )
        self.assertNotEqual(
            pool.safe_available_for_additional_workload_bytes,
            naive,
        )

    def test_additional_capacity_matches_the_authoritative_ledger(self):
        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        ledger_view = self.ledger.snapshot().to_dict()
        pool = self.envelope_with_ledger().memory_pool(self.pool_id)

        self.assertEqual(
            pool.safe_available_for_additional_workload_bytes,
            ledger_view["available"][self.pool_id],
        )
        self.assertEqual(
            pool.reconstructed_safe_pool_capacity_bytes,
            ledger_view["capacities"][self.pool_id],
        )

    def test_managed_reserved_is_separate_from_pool_capacity(self):
        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        pool = self.envelope_with_ledger().memory_pool(self.pool_id)

        self.assertNotEqual(
            pool.managed_reserved_bytes,
            pool.reconstructed_safe_pool_capacity_bytes,
        )
        self.assertEqual(
            pool.reconstructed_safe_pool_capacity_bytes
            - pool.managed_reserved_bytes,
            pool.safe_available_for_additional_workload_bytes,
        )

    def test_unmanaged_usage_only_when_derivable(self):
        # With no managed reservations, observed usage is unmanaged.
        pool = self.envelope_with_ledger().memory_pool(self.pool_id)

        self.assertEqual(
            pool.unmanaged_usage_bytes,
            HOST_VRAM_USED,
        )
        self.assertEqual(
            pool.unmanaged_usage_basis,
            "all_observed_usage_unmanaged",
        )

        # Once a reservation exists the split is not derivable, because
        # a reservation is an entitlement rather than a measurement.
        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        pool = self.envelope_with_ledger().memory_pool(self.pool_id)

        self.assertIsNone(pool.unmanaged_usage_bytes)
        self.assertEqual(
            pool.unmanaged_usage_basis,
            "not_derivable_with_active_reservations",
        )

    def test_unmanaged_usage_unknown_without_reservation_state(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=self.snapshot,
            resource_safety=self.resource_safety,
        )
        pool = envelope.memory_pool(self.pool_id)

        self.assertIsNone(pool.unmanaged_usage_bytes)
        self.assertEqual(
            pool.unmanaged_usage_basis,
            "managed_reservation_state_unknown",
        )

    def test_explain_chain_is_ordered_and_attributed(self):
        self.ledger.reserve(
            "workload-a",
            {self.pool_id: self.reserved},
        )

        pool = self.envelope_with_ledger().memory_pool(self.pool_id)
        chain = pool.explain()

        self.assertEqual(
            [entry["stage"] for entry in chain],
            [
                "reported_total",
                "reported_available",
                "protected_reserve",
                "observed_safe_available",
                "reconstructed_safe_pool_capacity",
                "managed_reserved",
                "safe_available_for_additional_workload",
            ],
        )

        owners = {entry["owner"] for entry in chain}

        self.assertEqual(
            owners,
            {
                "capacity_snapshot",
                "resource_safety",
                "reservation_ledger",
            },
        )


class CpuScopeTests(unittest.TestCase):
    def test_cpu_capability_without_fabricated_capacity(self):
        snap = snapshot()
        safety = build_resource_safety(
            build_resource_capacity(snap)
        )

        profile = build_host_capability_profile(
            capacity_snapshot=snap,
            resource_capacity=build_resource_capacity(snap),
        )
        envelope = build_capacity_envelope(
            capacity_snapshot=snap,
            resource_safety=safety,
        )

        # Capability is known.
        self.assertEqual(profile.cpu_cores, 128)
        self.assertIsNotNone(profile.cpu_model)

        # Capacity policy is not.
        status = envelope.cpu_capacity_status

        self.assertTrue(status.capability_known)
        self.assertFalse(status.effective_capacity_available)
        self.assertFalse(status.headroom_policy_available)
        self.assertEqual(
            status.reason,
            "cpu_capacity_policy_not_yet_resolved",
        )

        # No CPU pool and no CPU headroom policy was invented.
        self.assertEqual(
            [
                pool.pool_id
                for pool in envelope.memory_pools
                if "cpu" in pool.pool_id
            ],
            [],
        )
        self.assertIsNone(
            envelope.headroom_policy.for_memory_type("cpu")
        )

    def test_no_effective_total_is_fabricated_for_memory(self):
        envelope = build_capacity_envelope(
            capacity_snapshot=snapshot(),
            resource_safety=build_resource_safety(
                build_resource_capacity(snapshot())
            ),
        )
        pool = envelope.memory_pool("accelerator:0:memory")

        self.assertFalse(hasattr(pool, "effective_total_bytes"))


class StorageHeadroomRepresentationTests(unittest.TestCase):
    def test_unresolved_storage_has_no_policy_result(self):
        snap = snapshot()
        safety = build_resource_safety(
            build_resource_capacity(snap)
        )
        plan, _ = storage_plan(unresolved_capacity_resolution())

        envelope = build_capacity_envelope(
            capacity_snapshot=snap,
            resource_safety=safety,
            storage_plan=plan,
        )
        pool = envelope.storage_pool(PLATFORM_DATA_STORAGE_POOL_ID)

        # The policy input still exists.
        self.assertEqual(
            envelope.headroom_policy.storage.protected_free_fraction,
            0.15,
        )

        # The calculated result does not.
        self.assertIsNone(pool.protected_reserve_bytes)
        self.assertIsNone(pool.safe_allocatable_bytes)
        self.assertFalse(pool.budget_resolved)

        # And the reported signal is not promoted to fill the gap.
        self.assertEqual(
            pool.reported_free_bytes,
            REPORTED_FS_FREE,
        )
        self.assertFalse(
            pool.reported_accepted_as_capacity_evidence
        )

    def test_storage_explain_chain_keeps_reported_separate(self):
        snap = snapshot()
        plan, budget = storage_plan(verified_capacity_resolution())

        envelope = build_capacity_envelope(
            capacity_snapshot=snap,
            resource_safety=build_resource_safety(
                build_resource_capacity(snap)
            ),
            storage_plan=plan,
        )
        chain = envelope.storage_pool(
            PLATFORM_DATA_STORAGE_POOL_ID
        ).explain()

        stages = {entry["stage"]: entry for entry in chain}

        self.assertEqual(
            stages["reported_free"]["value_bytes"],
            REPORTED_FS_FREE,
        )
        self.assertEqual(
            stages["verified_lower_bound"]["value_bytes"],
            32 * GIB,
        )
        self.assertEqual(
            stages["available_for_new_platform"]["value_bytes"],
            budget["available_for_new_platform_bytes"],
        )

        # Safe allocatable never exceeds verified evidence.
        self.assertLessEqual(
            stages["safe_allocatable"]["value_bytes"],
            stages["verified_lower_bound"]["value_bytes"],
        )
        self.assertLess(
            stages["safe_allocatable"]["value_bytes"],
            stages["reported_free"]["value_bytes"],
        )


if __name__ == "__main__":
    unittest.main()
