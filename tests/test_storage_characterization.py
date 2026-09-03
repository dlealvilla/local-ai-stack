"""C3B tests for decision-bounded storage characterization.

The behaviour under test is a stopping policy, so almost every test
asserts on the probe SEQUENCE, not just the answer. A run that reaches
the right conclusion after climbing toward the pool ceiling is the
defect, not a pass.

Probes are injected as probe-shaped dicts. Persistence is deliberately
real, against a temporary data root, so the ordering invariant from C3A
is exercised rather than mocked away.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest import mock

import core.storage_characterization as characterization

from core.storage_capacity_cache import (
    read_empirical_probe_evidence,
    record_empirical_probe_evidence,
)
from core.storage_characterization import (
    MODE_DEEP,
    MODE_HOST,
    MODE_TRANSACTION,
    STATUS_BOUNDED_INCOMPLETE,
    STATUS_COMPLETE_FOR_HOST,
    STATUS_COMPLETE_FOR_TRANSACTION,
    STATUS_INCONCLUSIVE,
    STOP_ATTEMPT_BUDGET_REACHED,
    STOP_INCONCLUSIVE_PROBE_FAILURE,
    STOP_NUMERICAL_TOLERANCE_REACHED,
    STOP_PROBE_LIMIT_REACHED,
    STOP_DOWNWARD_BUDGET_REACHED,
    STOP_REFINEMENT_BUDGET_REACHED,
    STOP_UPWARD_BUDGET_REACHED,
    STOP_TIME_BUDGET_REACHED,
    STOP_TRANSACTION_PROVEN_FEASIBLE,
    STOP_TRANSACTION_PROVEN_INFEASIBLE,
    build_storage_characterization_policy,
    characterize_storage,
)

GIB = 1024 ** 3
MIB = 1024 ** 2

TIB = 1024 ** 4

SANITY = 64 * MIB

# The real resolved Qwen/Qwen3-8B-AWQ transaction requirement.
QWEN_REQUIRED_BYTES = 7_188_310_059


def success(requested_bytes, duration=0.25):
    return {
        "schema_version": 1,
        "supported": True,
        "success": True,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "reservation_accepted": True,
        "reported_allocated_bytes": 0,
        "allocation_visibility": "not_reported",
        "duration_seconds": duration,
        "reason": None,
    }


def capacity_failure(requested_bytes, reason="no_space"):
    return {
        "schema_version": 1,
        "supported": True,
        "success": False,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "duration_seconds": 0.4,
        "reason": reason,
        "errno": 28,
        "detail": "simulated capacity refusal",
    }


def inconclusive(requested_bytes, reason="operation_not_supported"):
    return {
        "schema_version": 1,
        "supported": False,
        "success": False,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "duration_seconds": 0.01,
        "reason": reason,
        "errno": 95,
        "detail": "simulated unsupported primitive",
    }


class CharacterizationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_root = Path(self.tmp.name)

        self.config = {
            "platform": {
                "data_root": str(self.data_root),
            },
            "storage_capacity": {
                "probe_enabled": True,
                "probe_max_gb": 64.0,
                "sonar_max_automatic_gb": 64.0,
                "sonar_start_mb": 64,
                "sonar_max_attempts": 32,
                "sonar_growth_factor": 2.0,
                "capacity_cache_ttl_seconds": 900,
            },
        }

        self.requested = []

    def probes_from(self, responder):
        """Wrap a responder so every requested size is recorded."""

        def probe_implementation(requested_bytes, **kwargs):
            self.requested.append(requested_bytes)
            return responder(requested_bytes)

        return probe_implementation

    def always(self, *responses):
        """Return each response in order, by probe index."""

        queue = list(responses)

        def responder(requested_bytes):
            if not queue:
                raise AssertionError(
                    "unexpected extra probe at "
                    f"{requested_bytes} bytes"
                )

            return queue.pop(0)(requested_bytes)

        return responder

    def seed_evidence(self, probe_result, requested_bytes):
        record_empirical_probe_evidence(
            probe_result,
            requested_bytes=requested_bytes,
            config=self.config,
        )

    def run_transaction(self, responder, **kwargs):
        return characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=kwargs.pop(
                "required_bytes",
                QWEN_REQUIRED_BYTES,
            ),
            config=self.config,
            probe_implementation=self.probes_from(responder),
            **kwargs,
        )


class EvidenceReuseTests(CharacterizationTestCase):
    def test_existing_success_resolves_transaction_with_zero_probes(self):
        # Case A: a previous 32 GiB success answers a 6.70 GiB
        # question outright. This is precisely what the interrupted
        # run threw away.
        self.seed_evidence(success(32 * GIB), 32 * GIB)

        result = self.run_transaction(
            self.always()  # any probe is a failure of the test
        )

        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_FEASIBLE,
        )
        self.assertEqual(result["probe_count_this_run"], 0)
        self.assertEqual(self.requested, [])
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            32 * GIB,
        )
        self.assertEqual(
            result["status"],
            STATUS_COMPLETE_FOR_TRANSACTION,
        )
        self.assertTrue(
            result["reused_evidence_record_ids"]
        )

    def test_existing_failure_resolves_transaction_with_zero_probes(self):
        # Case B: a classified failure at or below the requirement
        # settles it without probing.
        self.seed_evidence(
            capacity_failure(4 * GIB),
            4 * GIB,
        )

        result = self.run_transaction(self.always())

        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_INFEASIBLE,
        )
        self.assertEqual(result["probe_count_this_run"], 0)
        self.assertEqual(self.requested, [])

    def test_inconclusive_facts_establish_no_bounds(self):
        self.seed_evidence(
            inconclusive(32 * GIB),
            32 * GIB,
        )

        # The record exists...
        self.assertEqual(
            len(
                read_empirical_probe_evidence(
                    self.config
                )["records"]
            ),
            1,
        )

        # ...but bounds nothing, so a sanity probe still runs.
        result = self.run_transaction(
            self.always(success, success)
        )

        self.assertEqual(
            self.requested,
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_FEASIBLE,
        )

    def test_evidence_from_a_different_pool_is_not_reused(self):
        record_empirical_probe_evidence(
            success(32 * GIB),
            requested_bytes=32 * GIB,
            config=self.config,
            storage_identity={
                "resolved_path": "/other/pool",
                "device_id": 999999,
                "mount_source": "other:/vol",
                "filesystem_type": "nfs4",
            },
        )

        result = self.run_transaction(
            self.always(success, success)
        )

        # Had it been reused, zero probes would have run.
        self.assertEqual(
            self.requested,
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["reused_evidence_record_ids"],
            [],
        )

    def test_stale_evidence_is_not_reused(self):
        self.seed_evidence(success(32 * GIB), 32 * GIB)

        # Advance the cache module's clock an hour past the existing
        # 900-second freshness window, without changing that value.
        import core.storage_capacity_cache as cache_module

        one_hour_on = cache_module._utc_now() + timedelta(
            seconds=3600
        )

        with mock.patch.object(
            cache_module,
            "_utc_now",
            return_value=one_hour_on,
        ):
            result = self.run_transaction(
                self.always(success, success)
            )

        # Stale evidence bounds nothing, so probing starts over.
        self.assertEqual(
            self.requested,
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["reused_evidence_record_ids"],
            [],
        )

        # The historical fact is retained regardless.
        self.assertEqual(
            len(
                [
                    entry
                    for entry in read_empirical_probe_evidence(
                        self.config
                    )["records"]
                    if entry["requested_bytes"] == 32 * GIB
                ]
            ),
            1,
        )


class TransactionLogicTests(CharacterizationTestCase):
    def test_sanity_then_target_then_stop(self):
        result = self.run_transaction(
            self.always(success, success)
        )

        self.assertEqual(
            self.requested,
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_FEASIBLE,
        )
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            QWEN_REQUIRED_BYTES,
        )
        self.assertEqual(
            result["conservative_usable_bytes"],
            QWEN_REQUIRED_BYTES,
        )

        # The decisive property: nothing above the requirement.
        self.assertEqual(
            [
                size
                for size in self.requested
                if size > QWEN_REQUIRED_BYTES
            ],
            [],
        )

    def test_target_capacity_failure_stops_without_bisection(self):
        result = self.run_transaction(
            self.always(success, capacity_failure)
        )

        self.assertEqual(
            self.requested,
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_INFEASIBLE,
        )
        self.assertEqual(
            result["capacity_failure_upper_bound_bytes"],
            QWEN_REQUIRED_BYTES,
        )

        # No refinement between 64 MiB and the requirement.
        self.assertEqual(result["probe_count_this_run"], 2)

    def test_target_inconclusive_stops_inconclusive(self):
        result = self.run_transaction(
            self.always(success, inconclusive)
        )

        self.assertEqual(
            result["stop_reason"],
            STOP_INCONCLUSIVE_PROBE_FAILURE,
        )
        self.assertEqual(
            result["status"],
            STATUS_INCONCLUSIVE,
        )

        # Crucially NOT interpreted as insufficient capacity.
        self.assertIsNone(
            result["capacity_failure_upper_bound_bytes"]
        )
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            SANITY,
        )

    def test_inconclusive_sanity_probe_never_starts_the_target(self):
        result = self.run_transaction(
            self.always(inconclusive)
        )

        self.assertEqual(self.requested, [SANITY])
        self.assertEqual(
            result["stop_reason"],
            STOP_INCONCLUSIVE_PROBE_FAILURE,
        )
        self.assertIsNone(
            result["verified_lower_bound_bytes"]
        )

    def test_capacity_failure_at_sanity_size_proves_infeasible(self):
        result = self.run_transaction(
            self.always(capacity_failure)
        )

        self.assertEqual(self.requested, [SANITY])
        self.assertEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_INFEASIBLE,
        )

    def test_no_extra_reserve_is_added_to_the_requirement(self):
        # The requirement is already the safe figure from the
        # planning layer, so the probe must be exactly R.
        result = self.run_transaction(
            self.always(success, success)
        )

        self.assertEqual(
            self.requested[1],
            QWEN_REQUIRED_BYTES,
        )
        self.assertEqual(
            result["required_bytes"],
            QWEN_REQUIRED_BYTES,
        )

    def test_requirement_above_probe_limit_is_unresolved(self):
        result = self.run_transaction(
            self.always(success),
            required_bytes=128 * GIB,
        )

        self.assertEqual(self.requested, [SANITY])
        self.assertEqual(
            result["stop_reason"],
            STOP_PROBE_LIMIT_REACHED,
        )
        self.assertEqual(
            result["status"],
            STATUS_BOUNDED_INCOMPLETE,
        )

        # Policy-limited is NOT infeasible.
        self.assertIsNone(
            result["capacity_failure_upper_bound_bytes"]
        )
        self.assertNotEqual(
            result["stop_reason"],
            STOP_TRANSACTION_PROVEN_INFEASIBLE,
        )

    def test_transaction_mode_requires_a_requirement(self):
        with self.assertRaises(ValueError):
            characterize_storage(
                mode=MODE_TRANSACTION,
                config=self.config,
            )


class PersistenceOrderingTests(CharacterizationTestCase):
    def test_each_fact_is_durable_before_the_next_probe(self):
        durable_counts = []

        def responder(requested_bytes):
            durable_counts.append(
                len(
                    read_empirical_probe_evidence(
                        self.config
                    )["records"]
                )
            )

            return success(requested_bytes)

        self.run_transaction(responder)

        # Probe N sees exactly N durable facts.
        self.assertEqual(durable_counts, [0, 1])

    def test_facts_are_durable_before_the_result_returns(self):
        result = self.run_transaction(
            self.always(success, success)
        )

        stored = read_empirical_probe_evidence(
            self.config
        )["records"]

        self.assertEqual(len(stored), 2)
        self.assertEqual(
            [entry["requested_bytes"] for entry in stored],
            [SANITY, QWEN_REQUIRED_BYTES],
        )
        self.assertEqual(
            result["created_evidence_record_ids"],
            [entry["record_id"] for entry in stored],
        )


class HostCharacterizationTests(CharacterizationTestCase):
    """Final HOST policy: 32 GiB start, x2 up to 15, /2 down to 8,
    midpoint refinement to 5, 15% tolerance, no time limit, no ceiling.

    Probes are answered by a pool with a real boundary rather than a
    fixed script, so each search runs to its natural stop and the whole
    sequence can be asserted. The sequence is the behaviour.
    """

    def pool(self, ceiling_bytes):
        def responder(requested_bytes):
            if requested_bytes <= ceiling_bytes:
                return success(requested_bytes)

            return capacity_failure(requested_bytes)

        return responder

    def run_host(self, responder, policy=None, monotonic=None):
        return characterize_storage(
            mode=MODE_HOST,
            config=self.config,
            policy=policy,
            monotonic=monotonic,
            probe_implementation=self.probes_from(
                responder
            ),
        )

    # --- starting point and direction ---------------------------------

    def test_initial_probe_is_32_gib(self):
        self.run_host(self.pool(50 * GIB))

        self.assertEqual(
            self.requested[0],
            32 * GIB,
        )

    def test_success_climbs_by_doubling(self):
        self.run_host(self.pool(10_000 * GIB))

        self.assertEqual(
            self.requested[:5],
            [
                32 * GIB,
                64 * GIB,
                128 * GIB,
                256 * GIB,
                512 * GIB,
            ],
        )

    def test_initial_failure_backs_off_by_halving(self):
        self.run_host(self.pool(1))

        self.assertEqual(
            self.requested[:4],
            [
                32 * GIB,
                16 * GIB,
                8 * GIB,
                4 * GIB,
            ],
        )

    def test_initial_probe_counts_toward_the_direction_it_establishes(self):
        # Succeeding makes it iteration 1 upward.
        upward = self.run_host(
            self.pool(40 * GIB)
        )

        self.assertEqual(
            upward["upward_iterations"],
            2,
        )
        self.assertEqual(
            upward["downward_iterations"],
            0,
        )

        # Failing makes it iteration 1 downward.
        self.requested = []
        self.setUp()

        downward = self.run_host(self.pool(1))

        self.assertEqual(
            downward["downward_iterations"],
            8,
        )
        self.assertEqual(
            downward["upward_iterations"],
            0,
        )

    # --- directional budgets ------------------------------------------

    def test_at_most_eight_upward_probes_and_no_ninth(self):
        attempts = []

        def responder(requested_bytes):
            attempts.append(requested_bytes)

            if len(attempts) > 8:
                raise AssertionError(
                    "a ninth upward probe started "
                    "despite the 8-probe budget"
                )

            return success(requested_bytes)

        result = self.run_host(responder)

        self.assertEqual(len(attempts), 8)
        self.assertEqual(
            result["upward_iterations"],
            8,
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_UPWARD_BUDGET_REACHED,
        )

        # The whole fresh upward sequence, 32 GiB doubled seven times.
        self.assertEqual(
            self.requested,
            [
                32 * GIB,
                64 * GIB,
                128 * GIB,
                256 * GIB,
                512 * GIB,
                1024 * GIB,
                2048 * GIB,
                4096 * GIB,
            ],
        )
        self.assertEqual(
            self.requested[-1],
            4 * TIB,
        )

    def test_at_most_eight_downward_probes_and_no_ninth(self):
        attempts = []

        def responder(requested_bytes):
            attempts.append(requested_bytes)

            if len(attempts) > 8:
                raise AssertionError(
                    "a ninth downward probe started "
                    "despite the 8-probe budget"
                )

            return capacity_failure(requested_bytes)

        result = self.run_host(responder)

        self.assertEqual(len(attempts), 8)
        self.assertEqual(
            result["downward_iterations"],
            8,
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_DOWNWARD_BUDGET_REACHED,
        )

        # 32 GiB halved seven times.
        self.assertEqual(
            self.requested,
            [
                32 * GIB // (2 ** step)
                for step in range(8)
            ],
        )

    def test_budgets_are_reported(self):
        result = self.run_host(self.pool(50 * GIB))

        self.assertEqual(
            result["iteration_budgets"],
            {
                "upward": 8,
                "downward": 8,
                "refinement": 5,
            },
        )

    # --- refinement ---------------------------------------------------

    def test_bracket_switches_to_midpoint_refinement(self):
        result = self.run_host(self.pool(50 * GIB))

        self.assertEqual(
            self.requested,
            [
                32 * GIB,
                64 * GIB,
                48 * GIB,
                56 * GIB,
                52 * GIB,
            ],
        )
        self.assertEqual(
            result["upward_iterations"],
            2,
        )
        self.assertEqual(
            result["refinement_iterations"],
            3,
        )

    def test_bracket_within_15_percent_stops_immediately(self):
        self.seed_evidence(success(40 * GIB), 40 * GIB)
        self.seed_evidence(
            capacity_failure(44 * GIB),
            44 * GIB,
        )

        result = self.run_host(self.pool(42 * GIB))

        self.assertEqual(self.requested, [])
        self.assertEqual(
            result["stop_reason"],
            STOP_NUMERICAL_TOLERANCE_REACHED,
        )
        self.assertEqual(
            result["status"],
            STATUS_COMPLETE_FOR_HOST,
        )
        self.assertAlmostEqual(
            result["relative_uncertainty"],
            4 / 40,
            places=6,
        )

    def test_bracket_above_15_percent_refines(self):
        self.seed_evidence(success(32 * GIB), 32 * GIB)
        self.seed_evidence(
            capacity_failure(64 * GIB),
            64 * GIB,
        )

        result = self.run_host(self.pool(50 * GIB))

        self.assertEqual(
            self.requested,
            [48 * GIB, 56 * GIB, 52 * GIB],
        )
        self.assertLessEqual(
            result["relative_uncertainty"],
            0.15,
        )

    def test_at_most_five_refinement_probes_and_no_sixth(self):
        # A wide bracket that bisection cannot close to 15% within
        # five midpoints.
        self.seed_evidence(success(1 * GIB), 1 * GIB)
        self.seed_evidence(
            capacity_failure(1024 * GIB),
            1024 * GIB,
        )

        attempts = []

        def responder(requested_bytes):
            attempts.append(requested_bytes)

            if len(attempts) > 5:
                raise AssertionError(
                    "a sixth refinement probe started "
                    "despite the 5-probe budget"
                )

            return capacity_failure(requested_bytes)

        result = self.run_host(responder)

        self.assertEqual(len(attempts), 5)
        self.assertEqual(
            result["refinement_iterations"],
            5,
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_REFINEMENT_BUDGET_REACHED,
        )
        self.assertEqual(
            result["status"],
            STATUS_BOUNDED_INCOMPLETE,
        )

        # Repeated failures walked the upper bound down by halves.
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            1 * GIB,
        )
        self.assertGreater(
            result["relative_uncertainty"],
            0.15,
        )

    # --- no time limit, no ceiling ------------------------------------

    def test_host_ignores_the_foreground_time_deadline(self):
        # A clock that jumps far past the 900-second deadline on every
        # reading must not stop a host characterization.
        def monotonic():
            monotonic.calls += 1
            return monotonic.calls * 100_000.0

        monotonic.calls = 0

        result = self.run_host(
            self.pool(50 * GIB),
            monotonic=monotonic,
        )

        self.assertGreater(
            result["elapsed_seconds"],
            result["policy"][
                "max_foreground_duration_seconds"
            ],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_NUMERICAL_TOLERANCE_REACHED,
        )
        self.assertEqual(len(self.requested), 5)

    def test_host_probes_far_above_the_64_gib_guardrail(self):
        result = self.run_host(self.pool(300 * GIB))

        policy_ceiling = result["policy"][
            "max_single_probe_bytes"
        ]

        self.assertEqual(
            policy_ceiling,
            64 * GIB,
        )

        # The climb reaches 256 GiB, brackets at 512 GiB and refines
        # to 288 GiB, every step above the 64 GiB guardrail.
        self.assertEqual(
            self.requested,
            [
                32 * GIB,
                64 * GIB,
                128 * GIB,
                256 * GIB,
                512 * GIB,
                384 * GIB,
                320 * GIB,
                288 * GIB,
            ],
        )
        self.assertGreater(
            max(self.requested),
            policy_ceiling,
        )
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            288 * GIB,
        )
        self.assertNotEqual(
            result["stop_reason"],
            STOP_PROBE_LIMIT_REACHED,
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_NUMERICAL_TOLERANCE_REACHED,
        )

    def test_host_passes_no_probe_ceiling_to_the_probe(self):
        seen = {}

        def probe_implementation(
            requested_bytes,
            **kwargs
        ):
            seen.update(kwargs)
            return success(requested_bytes)

        characterize_storage(
            mode=MODE_HOST,
            config=self.config,
            probe_implementation=(
                probe_implementation
            ),
        )

        self.assertIn("max_probe_bytes", seen)
        self.assertIsNone(seen["max_probe_bytes"])

    def test_transaction_still_passes_its_ceiling(self):
        seen = {}

        def probe_implementation(
            requested_bytes,
            **kwargs
        ):
            seen.update(kwargs)
            return success(requested_bytes)

        characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=8 * GIB,
            config=self.config,
            probe_implementation=(
                probe_implementation
            ),
        )

        self.assertEqual(
            seen["max_probe_bytes"],
            64 * GIB,
        )

    def test_transaction_retains_its_ceiling_and_timing(self):
        # A requirement above the ceiling is policy-limited, not
        # infeasible, and the time budget still applies.
        result = characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=128 * GIB,
            config=self.config,
            probe_implementation=self.probes_from(
                self.pool(10_000 * GIB)
            ),
        )

        self.assertEqual(
            result["stop_reason"],
            STOP_PROBE_LIMIT_REACHED,
        )
        self.assertIsNone(
            result[
                "capacity_failure_upper_bound_bytes"
            ]
        )

        # And the timing guard is still wired for transactions: the
        # clock starts at zero, then reads past the deadline.
        self.requested = []

        readings = [0.0, 100_000.0]

        def monotonic():
            if len(readings) > 1:
                return readings.pop(0)

            return readings[0]

        timed = characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=8 * GIB,
            config=self.config,
            monotonic=monotonic,
            probe_implementation=self.probes_from(
                self.pool(10_000 * GIB)
            ),
        )

        self.assertEqual(
            timed["stop_reason"],
            STOP_TIME_BUDGET_REACHED,
        )
        self.assertEqual(self.requested, [])

    # --- honesty ------------------------------------------------------

    def test_all_success_upward_invents_no_upper_bound(self):
        result = self.run_host(
            self.pool(10 ** 18)
        )

        self.assertEqual(
            result["upward_iterations"],
            8,
        )
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            4 * TIB,
        )
        self.assertIsNone(
            result[
                "capacity_failure_upper_bound_bytes"
            ]
        )
        self.assertIsNone(
            result["relative_uncertainty"]
        )
        self.assertEqual(
            result["status"],
            STATUS_BOUNDED_INCOMPLETE,
        )

    def test_no_success_downward_leaves_capacity_unresolved(self):
        result = self.run_host(self.pool(1))

        self.assertIsNone(
            result["verified_lower_bound_bytes"]
        )
        self.assertIsNone(
            result["conservative_usable_bytes"]
        )
        self.assertIsNotNone(
            result[
                "capacity_failure_upper_bound_bytes"
            ]
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_DOWNWARD_BUDGET_REACHED,
        )

    def test_inconclusive_never_creates_an_upper_bound(self):
        result = self.run_host(
            lambda size: inconclusive(size)
        )

        self.assertEqual(
            self.requested,
            [32 * GIB],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_INCONCLUSIVE_PROBE_FAILURE,
        )
        self.assertEqual(
            result["status"],
            STATUS_INCONCLUSIVE,
        )
        self.assertIsNone(
            result[
                "capacity_failure_upper_bound_bytes"
            ]
        )
        self.assertIsNone(
            result["conservative_usable_bytes"]
        )

    def test_inconclusive_after_success_keeps_the_lower_bound(self):
        def responder(requested_bytes):
            if requested_bytes > 32 * GIB:
                return inconclusive(requested_bytes)

            return success(requested_bytes)

        result = self.run_host(responder)

        self.assertEqual(
            result["conservative_usable_bytes"],
            32 * GIB,
        )
        self.assertIsNone(
            result[
                "capacity_failure_upper_bound_bytes"
            ]
        )

    def test_conservative_value_is_always_the_lower_bound(self):
        result = self.run_host(self.pool(50 * GIB))

        lower = result["verified_lower_bound_bytes"]
        upper = result[
            "capacity_failure_upper_bound_bytes"
        ]

        self.assertEqual(
            result["conservative_usable_bytes"],
            lower,
        )
        self.assertEqual(lower, 48 * GIB)
        self.assertEqual(upper, 52 * GIB)

        # Never the midpoint, the average, the failure bound or the
        # pool's real 50 GiB boundary.
        self.assertNotEqual(
            result["conservative_usable_bytes"],
            (lower + upper) // 2,
        )
        self.assertNotEqual(
            result["conservative_usable_bytes"],
            upper,
        )
        self.assertLess(
            result["conservative_usable_bytes"],
            50 * GIB,
        )

    # --- evidence and independence ------------------------------------

    def test_durable_evidence_is_reused(self):
        # A previous 32 GiB success means the climb resumes at 64 GiB
        # rather than re-probing 32 GiB.
        self.seed_evidence(success(32 * GIB), 32 * GIB)

        result = self.run_host(self.pool(50 * GIB))

        self.assertEqual(
            self.requested[0],
            64 * GIB,
        )
        self.assertNotIn(32 * GIB, self.requested)
        self.assertTrue(
            result["reused_evidence_record_ids"]
        )

    def test_durable_bracket_starts_refinement_directly(self):
        self.seed_evidence(success(32 * GIB), 32 * GIB)
        self.seed_evidence(
            capacity_failure(64 * GIB),
            64 * GIB,
        )

        result = self.run_host(self.pool(50 * GIB))

        # Straight to the midpoint; no directional probes at all.
        self.assertEqual(
            self.requested[0],
            48 * GIB,
        )
        self.assertEqual(
            result["upward_iterations"],
            0,
        )
        self.assertEqual(
            result["downward_iterations"],
            0,
        )

    def test_host_has_no_model_or_catalogue_input(self):
        import inspect

        signature = inspect.signature(
            characterize_storage
        )

        self.assertEqual(
            sorted(signature.parameters),
            [
                "config",
                "mode",
                "monotonic",
                "policy",
                "probe_implementation",
                "provider",
                "required_bytes",
            ],
        )

        result = self.run_host(self.pool(50 * GIB))

        self.assertIsNone(result["required_bytes"])
        self.assertEqual(result["mode"], MODE_HOST)

    def test_no_sanity_probe_consumes_a_host_iteration(self):
        self.run_host(self.pool(50 * GIB))

        self.assertNotIn(SANITY, self.requested)
        self.assertEqual(
            self.requested[0],
            32 * GIB,
        )

    def test_policy_defaults_match_the_final_policy(self):
        policy = build_storage_characterization_policy(
            self.config
        )

        self.assertEqual(
            policy.initial_probe_bytes,
            32 * GIB,
        )
        self.assertEqual(
            policy.relative_tolerance,
            0.15,
        )
        self.assertEqual(policy.growth_factor, 2.0)
        self.assertEqual(
            policy.max_upward_iterations,
            8,
        )
        self.assertEqual(
            policy.max_downward_iterations,
            8,
        )
        self.assertEqual(
            policy.max_refinement_iterations,
            5,
        )

    def test_no_acquisition_feasibility_or_selector_behavior(self):
        # Asserted by the module's actual imports rather than by
        # scanning prose, which trips on the docstring explaining what
        # the module deliberately does not do.
        import core.storage_characterization as module

        forbidden_modules = {
            "core.control",
            "core.model_catalog",
            "core.model_inventory",
            "core.model_requirement",
            "core.model_feasibility",
            "core.model_compatibility",
            "core.capacity_feasibility",
            "core.capacity_contracts",
            "core.model_transfer",
        }

        imported = {
            getattr(
                getattr(module, name),
                "__module__",
                "",
            )
            or ""
            for name in dir(module)
            if not name.startswith("__")
        }

        self.assertEqual(
            imported & forbidden_modules,
            set(),
        )


class ModelIndependenceTests(unittest.TestCase):
    def test_no_model_layer_dependency(self):
        import inspect

        source = inspect.getsource(characterization)

        for forbidden in (
            "model_catalog",
            "model_requirement",
            "model_feasibility",
            "model_compatibility",
            "model_selector",
            "model_inventory",
            "qwen",
            "Qwen",
        ):
            self.assertNotIn(
                forbidden,
                source,
                msg=(
                    "storage characterization must stay "
                    f"model-agnostic but mentions {forbidden}"
                ),
            )

    def test_module_imports_no_model_modules(self):
        import core.storage_characterization as module

        for name in dir(module):
            value = getattr(module, name)
            module_name = getattr(
                value,
                "__module__",
                "",
            ) or ""

            self.assertNotIn("model", module_name)


class NumericalConvergenceTests(CharacterizationTestCase):
    def test_relative_tolerance_stops_refinement(self):
        # L = 40 GiB, U = 41 GiB. Absolute width 1 GiB equals the
        # absolute tolerance, and 1/40 = 2.5% is inside 5%.
        self.seed_evidence(success(40 * GIB), 40 * GIB)
        self.seed_evidence(
            capacity_failure(41 * GIB),
            41 * GIB,
        )

        result = characterize_storage(
            mode=MODE_DEEP,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always()
            ),
        )

        self.assertEqual(self.requested, [])
        self.assertEqual(
            result["stop_reason"],
            STOP_NUMERICAL_TOLERANCE_REACHED,
        )
        self.assertAlmostEqual(
            result["relative_uncertainty"],
            1 / 40,
            places=6,
        )

    def test_relative_rule_dominates_for_large_pools(self):
        # L = 100 GiB, U = 110 GiB: 10 GiB far exceeds the 1 GiB
        # absolute tolerance but 10% is within the 15% relative
        # tolerance.
        policy = build_storage_characterization_policy(
            self.config
        )

        self.assertEqual(policy.relative_tolerance, 0.15)

        self.assertTrue(
            characterization._within_tolerance(
                100 * GIB,
                110 * GIB,
                policy,
            )
        )

        # 20 GiB apart is 20%, outside tolerance.
        self.assertFalse(
            characterization._within_tolerance(
                100 * GIB,
                120 * GIB,
                policy,
            )
        )

    def test_absolute_rule_dominates_for_small_pools(self):
        policy = build_storage_characterization_policy(
            self.config
        )

        # 1 GiB apart on a 4 GiB pool is 25% relative, but the
        # absolute tolerance is 1 GiB, so it stops.
        self.assertTrue(
            characterization._within_tolerance(
                4 * GIB,
                5 * GIB,
                policy,
            )
        )

    def test_conservative_result_remains_the_lower_bound(self):
        self.seed_evidence(success(40 * GIB), 40 * GIB)
        self.seed_evidence(
            capacity_failure(44 * GIB),
            44 * GIB,
        )

        result = characterize_storage(
            mode=MODE_HOST,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always()
            ),
        )

        midpoint = 42 * GIB

        self.assertEqual(
            result["conservative_usable_bytes"],
            40 * GIB,
        )
        self.assertNotEqual(
            result["conservative_usable_bytes"],
            midpoint,
        )
        self.assertNotEqual(
            result["conservative_usable_bytes"],
            44 * GIB,
        )

    def test_tolerance_policy_is_distinct_from_consensus_tolerance(self):
        policy = build_storage_characterization_policy(
            self.config
        )

        self.assertEqual(policy.relative_tolerance, 0.15)
        self.assertEqual(
            policy.absolute_tolerance_bytes,
            1 * GIB,
        )

        # The consensus values are 0.10 and 2 GB and must not leak in.
        self.assertNotEqual(
            policy.relative_tolerance,
            self.config["storage_capacity"].get(
                "consensus_relative_tolerance",
                0.10,
            ),
        )


class BudgetTests(CharacterizationTestCase):
    def clock(self, values):
        queue = list(values)

        def monotonic():
            if len(queue) > 1:
                return queue.pop(0)

            return queue[0]

        return monotonic

    def test_time_budget_prevents_starting_another_probe(self):
        self.seed_evidence(success(1 * GIB), 1 * GIB)

        # First reading starts the clock, the next is past 900 s.
        result = characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=QWEN_REQUIRED_BYTES,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always()
            ),
            monotonic=self.clock([0.0, 901.0]),
        )

        self.assertEqual(self.requested, [])
        self.assertEqual(
            result["stop_reason"],
            STOP_TIME_BUDGET_REACHED,
        )
        self.assertEqual(
            result["status"],
            STATUS_BOUNDED_INCOMPLETE,
        )

        # Strongest conservative evidence is still returned.
        self.assertEqual(
            result["conservative_usable_bytes"],
            1 * GIB,
        )

    def test_time_budget_is_checked_after_each_completed_probe(self):
        # The probe that was already running is allowed to finish;
        # C3B cannot interrupt it. Only the NEXT probe is prevented.
        result = characterize_storage(
            mode=MODE_DEEP,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always(success, success)
            ),
            monotonic=self.clock([0.0, 0.0, 0.0, 950.0]),
        )

        self.assertEqual(
            result["stop_reason"],
            STOP_TIME_BUDGET_REACHED,
        )
        self.assertGreaterEqual(
            result["probe_count_this_run"],
            1,
        )

    def test_in_flight_probe_is_not_claimed_cancellable(self):
        # An honest contract: the elapsed time may exceed the budget
        # because the running probe cannot be stopped. C3C addresses
        # cooperative cancellation.
        long_probe_clock = self.clock([0.0, 0.0, 5000.0])

        result = characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=QWEN_REQUIRED_BYTES,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always(success)
            ),
            monotonic=long_probe_clock,
        )

        self.assertEqual(len(self.requested), 1)
        self.assertGreater(
            result["elapsed_seconds"],
            result["policy"][
                "max_foreground_duration_seconds"
            ],
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_TIME_BUDGET_REACHED,
        )

    def test_attempt_budget_prevents_the_next_probe(self):
        config = dict(self.config)
        config["storage_capacity"] = dict(
            self.config["storage_capacity"]
        )
        config["storage_capacity"][
            "sonar_max_attempts"
        ] = 1

        result = characterize_storage(
            mode=MODE_TRANSACTION,
            required_bytes=QWEN_REQUIRED_BYTES,
            config=config,
            probe_implementation=self.probes_from(
                self.always(success)
            ),
        )

        # Sanity probe consumed the single attempt.
        self.assertEqual(self.requested, [SANITY])
        self.assertEqual(
            result["stop_reason"],
            STOP_ATTEMPT_BUDGET_REACHED,
        )
        self.assertEqual(
            result["conservative_usable_bytes"],
            SANITY,
        )

    def test_policy_defaults_come_from_existing_configuration(self):
        policy = build_storage_characterization_policy(
            self.config
        )

        self.assertEqual(policy.sanity_probe_bytes, SANITY)
        self.assertEqual(policy.attempt_budget, 32)
        self.assertEqual(policy.growth_factor, 2.0)
        self.assertEqual(
            policy.max_single_probe_bytes,
            64 * GIB,
        )
        self.assertEqual(
            policy.max_foreground_duration_seconds,
            900.0,
        )

    def test_max_single_probe_uses_the_lower_existing_ceiling(self):
        config = dict(self.config)
        config["storage_capacity"] = dict(
            self.config["storage_capacity"]
        )
        config["storage_capacity"]["probe_max_gb"] = 16.0

        policy = build_storage_characterization_policy(
            config
        )

        self.assertEqual(
            policy.max_single_probe_bytes,
            16 * GIB,
        )

    def test_probe_cost_is_observable(self):
        result = self.run_transaction(
            self.always(success, success)
        )

        self.assertEqual(result["probe_count_this_run"], 2)
        self.assertEqual(
            result[
                "total_requested_probe_bytes_this_run"
            ],
            SANITY + QWEN_REQUIRED_BYTES,
        )
        self.assertGreater(
            result["total_probe_duration_seconds"],
            0.0,
        )


class DeepModeTests(CharacterizationTestCase):
    def test_deep_expands_then_refines(self):
        self.seed_evidence(success(8 * GIB), 8 * GIB)

        responses = []

        def responder(requested_bytes):
            responses.append(requested_bytes)

            if requested_bytes >= 32 * GIB:
                return capacity_failure(requested_bytes)

            return success(requested_bytes)

        result = characterize_storage(
            mode=MODE_DEEP,
            config=self.config,
            probe_implementation=self.probes_from(
                responder
            ),
        )

        # Geometric expansion 16, 32 then midpoint refinement.
        self.assertEqual(self.requested[0], 16 * GIB)
        self.assertEqual(self.requested[1], 32 * GIB)
        self.assertGreater(len(self.requested), 2)

        self.assertEqual(
            result["stop_reason"],
            STOP_NUMERICAL_TOLERANCE_REACHED,
        )
        # Read the tolerance from policy rather than restating it, so
        # this stays true if the default is retuned.
        policy = build_storage_characterization_policy(
            self.config
        )

        self.assertLessEqual(
            result["absolute_uncertainty_bytes"],
            max(
                policy.absolute_tolerance_bytes,
                int(
                    policy.relative_tolerance
                    * result[
                        "verified_lower_bound_bytes"
                    ]
                ),
            ),
        )

    def test_deep_clamps_expansion_to_the_safety_limit(self):
        self.seed_evidence(success(48 * GIB), 48 * GIB)

        result = characterize_storage(
            mode=MODE_DEEP,
            config=self.config,
            probe_implementation=self.probes_from(
                self.always(success)
            ),
        )

        # 96 GiB would exceed the limit, so 64 GiB is probed instead.
        self.assertEqual(self.requested, [64 * GIB])
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            64 * GIB,
        )
        self.assertEqual(
            result["stop_reason"],
            STOP_PROBE_LIMIT_REACHED,
        )


class BackwardCompatibilityTests(CharacterizationTestCase):
    def test_existing_search_entry_point_is_unchanged(self):
        # The old accuracy-oriented search still climbs and refines
        # exactly as before: C3B is additive, not a replacement.
        from core.storage_sonar import (
            adaptive_capacity_search,
        )

        attempts = []

        def probe(size):
            attempts.append(size)
            return size <= 10 * MIB

        result = adaptive_capacity_search(
            probe=probe,
            start_bytes=1 * MIB,
            resolution_bytes=1 * MIB,
            maximum_probe_bytes=64 * MIB,
        )

        self.assertEqual(
            result["algorithm"],
            "seeded_exponential_backoff_binary",
        )
        # It brackets 8/16 MiB then bisects down to a 1 MiB
        # resolution: accuracy-oriented refinement, as before.
        self.assertEqual(
            result["verified_lower_bound_bytes"],
            10 * MIB,
        )
        self.assertEqual(
            result["observed_upper_failure_bytes"],
            11 * MIB,
        )
        self.assertTrue(result["boundary_bracketed"])
        self.assertEqual(
            result["stopping_reason"],
            "resolution_reached",
        )

        # Still the old geometric climb from the start size.
        self.assertEqual(
            attempts[:4],
            [
                1 * MIB,
                2 * MIB,
                4 * MIB,
                8 * MIB,
            ],
        )

    def test_calibration_coordinator_is_untouched(self):
        import inspect

        import core.storage_capacity_calibration as module

        source = inspect.getsource(module)

        self.assertNotIn(
            "storage_characterization",
            source,
        )
        self.assertNotIn(
            "characterize_storage",
            source,
        )

    def test_production_resolution_does_not_consume_characterization(self):
        import inspect

        import core.storage_capacity_resolution as resolution
        import core.storage_commit_admission as admission

        for module in (resolution, admission):
            self.assertNotIn(
                "storage_characterization",
                inspect.getsource(module),
            )


class ContractTests(CharacterizationTestCase):
    def test_result_shape(self):
        result = self.run_transaction(
            self.always(success, success)
        )

        for field in (
            "schema_version",
            "mode",
            "policy",
            "storage_identity",
            "storage_generation",
            "started_at",
            "completed_at",
            "elapsed_seconds",
            "required_bytes",
            "verified_lower_bound_bytes",
            "capacity_failure_upper_bound_bytes",
            "conservative_usable_bytes",
            "absolute_uncertainty_bytes",
            "relative_uncertainty",
            "status",
            "stop_reason",
            "probe_count_this_run",
            "total_requested_probe_bytes_this_run",
            "probes",
            "reused_evidence_record_ids",
            "created_evidence_record_ids",
            "iterations",
        ):
            self.assertIn(field, result)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["mode"], MODE_TRANSACTION)

    def test_result_is_json_serializable(self):
        import json

        result = self.run_transaction(
            self.always(success, success)
        )

        restored = json.loads(json.dumps(result))

        self.assertEqual(
            restored["stop_reason"],
            STOP_TRANSACTION_PROVEN_FEASIBLE,
        )

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            characterize_storage(
                mode="ceiling_hunt",
                config=self.config,
            )

    def test_invalid_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            characterize_storage(
                mode=MODE_TRANSACTION,
                required_bytes=0,
                config=self.config,
            )


if __name__ == "__main__":
    unittest.main()
