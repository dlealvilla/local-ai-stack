"""C3A tests for durable empirical storage-probe evidence.

The defect being fixed: roughly 48 minutes of real probing produced no
reusable evidence because probe results were persisted only after the
entire calibration returned. These tests assert that every completed
probe becomes an immutable classified fact before the next probe starts,
and that an interruption can neither erase earlier facts nor fabricate
new ones.

This module is also the first unit coverage of the storage capacity
cache and probe classification, which previously had none.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import core.storage_capacity_cache as cache_module
import core.storage_capacity_calibration as calibration_module

from core.storage_capacity_cache import (
    EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION,
    PROBE_OUTCOME_CAPACITY_FAILURE,
    PROBE_OUTCOME_INCONCLUSIVE,
    PROBE_OUTCOME_SUCCESS,
    advance_storage_generation,
    classify_probe_result,
    eligible_empirical_probe_evidence,
    get_capacity_cache_status,
    invalidate_capacity_cache,
    read_capacity_cache,
    read_empirical_probe_evidence,
    read_storage_generation,
    record_empirical_probe_evidence,
    resolve_empirical_probe_evidence_path,
)
from core.storage_commit_admission import (
    evaluate_storage_commit_admission,
)

GIB = 1024 ** 3
MIB = 1024 ** 2


def success_probe(requested_bytes, *, duration=0.25):
    """A completed successful probe, shaped exactly as the probe returns."""

    return {
        "schema_version": 1,
        "supported": True,
        "success": True,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "reservation_accepted": True,
        "reported_allocated_bytes": requested_bytes,
        "allocation_visibility": "observable",
        "duration_seconds": duration,
        "reason": None,
    }


def capacity_failure_probe(requested_bytes, reason="no_space", errno=28):
    return {
        "schema_version": 1,
        "supported": True,
        "success": False,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "duration_seconds": 0.5,
        "reason": reason,
        "errno": errno,
        "detail": f"[Errno {errno}] simulated {reason}",
    }


def unsupported_probe(requested_bytes):
    return {
        "schema_version": 1,
        "supported": False,
        "success": False,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "duration_seconds": 0.01,
        "reason": "operation_not_supported",
        "errno": 95,
        "detail": "[Errno 95] Operation not supported",
    }


def permission_probe(requested_bytes):
    return {
        "schema_version": 1,
        "supported": True,
        "success": False,
        "method": "posix_fallocate",
        "requested_bytes": requested_bytes,
        "duration_seconds": 0.01,
        "reason": "os_error_13",
        "errno": 13,
        "detail": "[Errno 13] Permission denied",
    }


class EvidenceTestCase(unittest.TestCase):
    """Each test gets its own real data root; nothing is mocked away."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.config = {
            "platform": {
                "data_root": str(self.data_root),
            },
            "storage_capacity": {
                "probe_enabled": True,
                "probe_max_gb": 64.0,
                "probe_directory": "data/capacity-probes",
                "capacity_cache_ttl_seconds": 900,
                "sonar_start_mb": 64,
                "sonar_resolution_mb": 256,
                "sonar_max_automatic_gb": 64.0,
                "sonar_fallback_enabled": True,
                "platform_allocation_percent": 100.0,
            },
        }

    def evidence_path(self):
        return resolve_empirical_probe_evidence_path(self.config)

    def records(self):
        return read_empirical_probe_evidence(self.config)["records"]


class ClassificationTests(EvidenceTestCase):
    def test_success_requires_supported_success_and_acceptance(self):
        outcome, classification = classify_probe_result(
            success_probe(1 * GIB)
        )

        self.assertEqual(outcome, PROBE_OUTCOME_SUCCESS)
        self.assertIsNone(classification)

    def test_capacity_and_quota_failures_are_classified(self):
        for reason in ("no_space", "quota_exceeded"):
            outcome, classification = classify_probe_result(
                capacity_failure_probe(8 * GIB, reason=reason)
            )

            self.assertEqual(
                outcome,
                PROBE_OUTCOME_CAPACITY_FAILURE,
            )
            self.assertEqual(classification, reason)

    def test_non_capacity_failures_are_inconclusive(self):
        # None of these say anything about how much space exists, so
        # none may ever contribute an upper bound.
        for probe in (
            unsupported_probe(8 * GIB),
            permission_probe(8 * GIB),
            {
                "schema_version": 1,
                "supported": True,
                "success": False,
                "reason": "probe_limit_exceeded",
                "requested_bytes": 128 * GIB,
            },
            {
                "schema_version": 1,
                "supported": True,
                "success": False,
                "reason": "file_too_large",
                "requested_bytes": 128 * GIB,
            },
            {
                "schema_version": 1,
                "supported": True,
                "success": False,
                "reason": "probe_disabled",
            },
        ):
            outcome, _ = classify_probe_result(probe)

            self.assertEqual(
                outcome,
                PROBE_OUTCOME_INCONCLUSIVE,
                msg=probe.get("reason"),
            )

    def test_accepted_reservation_is_required_for_success(self):
        probe = success_probe(1 * GIB)
        probe["reservation_accepted"] = False

        outcome, _ = classify_probe_result(probe)

        self.assertNotEqual(outcome, PROBE_OUTCOME_SUCCESS)


class ImmediatePersistenceTests(EvidenceTestCase):
    def test_success_persists_immediately(self):
        record = record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        self.assertTrue(self.evidence_path().exists())

        stored = self.records()

        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0]["record_id"],
            record["record_id"],
        )
        self.assertEqual(
            stored[0]["outcome"],
            PROBE_OUTCOME_SUCCESS,
        )
        self.assertEqual(
            stored[0]["requested_bytes"],
            32 * GIB,
        )
        self.assertEqual(
            stored[0]["schema_version"],
            EMPIRICAL_PROBE_EVIDENCE_SCHEMA_VERSION,
        )

    def test_capacity_failure_persists_immediately(self):
        record_empirical_probe_evidence(
            capacity_failure_probe(48 * GIB),
            config=self.config,
        )

        stored = self.records()

        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0]["outcome"],
            PROBE_OUTCOME_CAPACITY_FAILURE,
        )
        self.assertEqual(
            stored[0]["failure_classification"],
            "no_space",
        )
        self.assertEqual(stored[0]["errno"], 28)

    def test_non_capacity_failure_is_not_upper_bound_evidence(self):
        record_empirical_probe_evidence(
            permission_probe(48 * GIB),
            config=self.config,
        )

        stored = self.records()

        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0]["outcome"],
            PROBE_OUTCOME_INCONCLUSIVE,
        )
        self.assertNotEqual(
            stored[0]["outcome"],
            PROBE_OUTCOME_CAPACITY_FAILURE,
        )

        # Nothing in the store may be read as a capacity boundary.
        self.assertEqual(
            [
                entry
                for entry in stored
                if entry["outcome"]
                == PROBE_OUTCOME_CAPACITY_FAILURE
            ],
            [],
        )

    def test_record_carries_identity_timing_and_generation(self):
        advance_storage_generation(
            "test_setup",
            config=self.config,
        )

        started = datetime.now(timezone.utc)

        record = record_empirical_probe_evidence(
            success_probe(1 * GIB, duration=1.5),
            provider="runpod_network_volume",
            started_at=started,
            config=self.config,
        )

        self.assertEqual(
            record["storage_identity"]["resolved_path"],
            str(self.data_root.resolve()),
        )
        self.assertIsInstance(
            record["storage_identity"]["device_id"],
            int,
        )
        self.assertEqual(
            record["provider"],
            "runpod_network_volume",
        )
        self.assertEqual(
            record["probe_method"],
            "posix_fallocate",
        )
        self.assertEqual(
            record["probe_implementation"],
            "core.storage_probe.probe_required_capacity",
        )
        self.assertEqual(record["duration_seconds"], 1.5)
        self.assertEqual(
            record["started_at"],
            started.isoformat(),
        )
        self.assertIsNotNone(record["completed_at"])

        # The fact remembers the generation it was observed in.
        self.assertEqual(
            record["storage_generation"],
            read_storage_generation(self.config)["generation"],
        )

    def test_multiple_probes_survive_independently(self):
        for size in (1 * GIB, 8 * GIB, 32 * GIB):
            record_empirical_probe_evidence(
                success_probe(size),
                config=self.config,
            )

        record_empirical_probe_evidence(
            capacity_failure_probe(48 * GIB),
            config=self.config,
        )

        stored = self.records()

        self.assertEqual(len(stored), 4)
        self.assertEqual(
            [entry["requested_bytes"] for entry in stored],
            [1 * GIB, 8 * GIB, 32 * GIB, 48 * GIB],
        )

        # Distinct identities, so nothing overwrote anything.
        self.assertEqual(
            len({entry["record_id"] for entry in stored}),
            4,
        )

    def test_later_failure_does_not_erase_earlier_success(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )
        record_empirical_probe_evidence(
            capacity_failure_probe(48 * GIB),
            config=self.config,
        )
        record_empirical_probe_evidence(
            permission_probe(64 * GIB),
            config=self.config,
        )

        stored = self.records()

        successes = [
            entry
            for entry in stored
            if entry["outcome"] == PROBE_OUTCOME_SUCCESS
        ]

        self.assertEqual(len(successes), 1)
        self.assertEqual(
            successes[0]["requested_bytes"],
            32 * GIB,
        )

    def test_facts_are_immutable_once_written(self):
        first = record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        record_empirical_probe_evidence(
            capacity_failure_probe(32 * GIB),
            config=self.config,
        )

        stored = self.records()

        preserved = next(
            entry
            for entry in stored
            if entry["record_id"] == first["record_id"]
        )

        # A later contradictory observation at the same size does not
        # rewrite history.
        self.assertEqual(
            preserved["outcome"],
            PROBE_OUTCOME_SUCCESS,
        )
        self.assertEqual(preserved, first)


class InterruptionTests(EvidenceTestCase):
    """Interruption must preserve facts and fabricate none."""

    def calibrate_with_probes(self, probe_side_effect):
        # Force the sonar fallback path: capacity is unresolved, so
        # calibration probes. Only the probe implementation is faked.
        unresolved = {
            "provider": "test_provider",
            "resolved": {
                "remaining_bytes": None,
                "effective_total_bytes": None,
                "basis": "unresolved",
                "confidence": "unknown",
            },
            "fallback": {"sonar_required": True},
        }

        with mock.patch.object(
            calibration_module,
            "resolve_storage_capacity",
            return_value=unresolved,
        ), mock.patch.object(
            calibration_module,
            "probe_required_capacity",
            side_effect=probe_side_effect,
        ):
            return calibration_module.calibrate_storage_capacity(
                config=self.config,
            )

    def test_interrupted_probe_creates_no_completed_fact(self):
        calls = []

        def probes(requested_bytes, **kwargs):
            calls.append(requested_bytes)

            if len(calls) <= 2:
                return success_probe(requested_bytes)

            # The third probe never completes, exactly as SIGINT
            # during a real 42 GB write.
            raise KeyboardInterrupt("interrupted mid-probe")

        with self.assertRaises(KeyboardInterrupt):
            self.calibrate_with_probes(probes)

        stored = self.records()

        # The two completed probes survived the interruption.
        self.assertEqual(len(stored), 2)
        self.assertEqual(
            [entry["requested_bytes"] for entry in stored],
            calls[:2],
        )

        # The interrupted probe produced no fact of any kind.
        self.assertNotIn(
            calls[2],
            [entry["requested_bytes"] for entry in stored],
        )
        self.assertEqual(
            [
                entry
                for entry in stored
                if entry["outcome"] != PROBE_OUTCOME_SUCCESS
            ],
            [],
        )

    def test_evidence_exists_without_a_completed_calibration(self):
        # The whole point: no CharacterizationResult is required for
        # the facts to be durable.
        def probes(requested_bytes, **kwargs):
            if requested_bytes >= 8 * GIB:
                raise KeyboardInterrupt("interrupted")

            return success_probe(requested_bytes)

        with self.assertRaises(KeyboardInterrupt):
            self.calibrate_with_probes(probes)

        stored = self.records()

        self.assertTrue(stored)
        self.assertTrue(
            all(
                entry["outcome"] == PROBE_OUTCOME_SUCCESS
                for entry in stored
            )
        )

        # No calibration cache was written.
        self.assertIsNone(read_capacity_cache(self.config))

    def test_persistence_precedes_the_next_probe(self):
        observed_counts = []

        def probes(requested_bytes, **kwargs):
            # Before this probe runs, every earlier probe must
            # already be durable on disk.
            observed_counts.append(len(self.records()))

            return success_probe(requested_bytes)

        self.calibrate_with_probes(probes)

        self.assertEqual(
            observed_counts,
            list(range(len(observed_counts))),
        )


class ProbeArtifactTests(EvidenceTestCase):
    def test_orphaned_probe_artifact_is_not_evidence(self):
        probe_dir = self.data_root / "data" / "capacity-probes"
        probe_dir.mkdir(parents=True)

        orphan = probe_dir / "capacity-probe-orphan.tmp"
        orphan.write_bytes(b"\0" * 1024)

        self.assertTrue(orphan.exists())

        evidence = read_empirical_probe_evidence(self.config)

        self.assertEqual(evidence["records"], [])
        self.assertEqual(evidence["reason"], "evidence_missing")


class ReuseEligibilityTests(EvidenceTestCase):
    def test_identity_mismatch_prevents_reuse(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
            storage_identity={
                "resolved_path": "/some/other/pool",
                "device_id": 999999,
                "mount_source": "other:/vol",
                "filesystem_type": "nfs4",
            },
        )

        status = eligible_empirical_probe_evidence(self.config)

        self.assertEqual(status["eligible"], [])
        self.assertEqual(len(status["ineligible"]), 1)
        self.assertIn(
            "storage_identity_changed",
            status["ineligible"][0]["reasons"],
        )

        # The historical fact is retained, merely not reusable.
        self.assertEqual(len(self.records()), 1)

    def test_fresh_matching_evidence_is_eligible(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        status = eligible_empirical_probe_evidence(self.config)

        self.assertEqual(len(status["eligible"]), 1)
        self.assertEqual(status["ineligible"], [])
        self.assertEqual(status["ttl_seconds"], 900)

    def test_stale_evidence_follows_existing_ttl(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        later = datetime.now(timezone.utc) + timedelta(
            seconds=901
        )

        status = eligible_empirical_probe_evidence(
            self.config,
            now=later,
        )

        self.assertEqual(status["eligible"], [])
        self.assertIn(
            "evidence_stale",
            status["ineligible"][0]["reasons"],
        )

        # Stale facts are retained, not deleted.
        self.assertEqual(len(self.records()), 1)

    def test_ttl_boundary_uses_the_configured_value(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        just_inside = datetime.now(timezone.utc) + timedelta(
            seconds=800
        )

        status = eligible_empirical_probe_evidence(
            self.config,
            now=just_inside,
        )

        self.assertEqual(len(status["eligible"]), 1)


class DurabilityTests(EvidenceTestCase):
    def test_atomic_write_leaves_no_partial_or_temp_files(self):
        for size in (1 * GIB, 2 * GIB):
            record_empirical_probe_evidence(
                success_probe(size),
                config=self.config,
            )

        directory = self.evidence_path().parent

        self.assertEqual(
            [
                entry.name
                for entry in directory.iterdir()
                if entry.name.endswith(".tmp")
            ],
            [],
        )

        # The persisted file is complete, parseable JSON.
        payload = json.loads(
            self.evidence_path().read_text(encoding="utf-8")
        )

        self.assertEqual(len(payload["records"]), 2)

    def test_partial_json_is_never_read_as_evidence(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        # Simulate a torn file that a non-atomic writer could leave.
        path = self.evidence_path()
        truncated = path.read_text(encoding="utf-8")[:40]
        path.write_text(truncated, encoding="utf-8")

        evidence = read_empirical_probe_evidence(self.config)

        self.assertEqual(evidence["records"], [])
        self.assertEqual(
            evidence["reason"],
            "evidence_unreadable",
        )

        # And recording again recovers a valid store.
        record_empirical_probe_evidence(
            success_probe(1 * GIB),
            config=self.config,
        )

        self.assertEqual(len(self.records()), 1)

    def test_malformed_records_are_discarded_not_trusted(self):
        path = self.evidence_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "records": [
                        {"outcome": "not_a_real_outcome"},
                        "not even a mapping",
                        {
                            "record_id": "abc",
                            "outcome": PROBE_OUTCOME_SUCCESS,
                            "requested_bytes": 4 * GIB,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        stored = self.records()

        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["record_id"], "abc")

    def test_persistence_failure_is_not_silent(self):
        # Failing loudly matters: continuing to probe without
        # durability would silently reproduce the original defect.
        with mock.patch(
            "core.storage_capacity_cache._atomic_write_json",
            side_effect=OSError("read-only filesystem"),
        ):
            with self.assertRaises(OSError):
                record_empirical_probe_evidence(
                    success_probe(1 * GIB),
                    config=self.config,
                )


class BackwardCompatibilityTests(EvidenceTestCase):
    def test_missing_evidence_file_is_not_corrupt_state(self):
        evidence = read_empirical_probe_evidence(self.config)

        self.assertEqual(evidence["reason"], "evidence_missing")
        self.assertEqual(evidence["records"], [])
        self.assertFalse(self.evidence_path().exists())

    def test_existing_cache_and_generation_paths_still_work(self):
        # A predecessor deployment has a calibration cache and a
        # generation file and no probe history.
        self.assertIsNone(read_capacity_cache(self.config))

        generation = read_storage_generation(self.config)

        self.assertEqual(generation["generation"], 0)
        self.assertEqual(
            generation["reason"],
            "initial_generation",
        )

        status = get_capacity_cache_status(
            current_platform_used_bytes=0,
            config=self.config,
        )

        self.assertFalse(status["valid"])
        self.assertEqual(status["reason"], "cache_missing")

    def test_cache_status_unaffected_by_probe_history(self):
        before = get_capacity_cache_status(
            current_platform_used_bytes=0,
            config=self.config,
        )

        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        after = get_capacity_cache_status(
            current_platform_used_bytes=0,
            config=self.config,
        )

        self.assertEqual(before, after)

    def test_evidence_file_sits_beside_the_existing_files(self):
        record_empirical_probe_evidence(
            success_probe(1 * GIB),
            config=self.config,
        )

        self.assertEqual(
            self.evidence_path().name,
            "empirical-probes.json",
        )
        self.assertEqual(
            self.evidence_path().parent.name,
            "storage-capacity",
        )


class GenerationAndInvalidationTests(EvidenceTestCase):
    def test_generation_behavior_is_unchanged(self):
        self.assertEqual(
            read_storage_generation(self.config)["generation"],
            0,
        )

        advance_storage_generation(
            "model_installed",
            config=self.config,
        )

        self.assertEqual(
            read_storage_generation(self.config)["generation"],
            1,
        )

    def test_invalidation_behavior_is_unchanged(self):
        result = invalidate_capacity_cache(
            "model_installed",
            config=self.config,
        )

        self.assertFalse(result["invalidated"])
        self.assertEqual(result["reason"], "cache_missing")
        self.assertEqual(
            read_storage_generation(self.config)["generation"],
            1,
        )

    def test_invalidation_does_not_delete_historical_facts(self):
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        invalidate_capacity_cache(
            "model_installed",
            config=self.config,
        )

        stored = self.records()

        self.assertEqual(len(stored), 1)

        # The fact records the pre-mutation generation, so a later
        # policy can tell it apart from post-mutation evidence.
        self.assertEqual(stored[0]["storage_generation"], 0)
        self.assertEqual(
            read_storage_generation(self.config)["generation"],
            1,
        )


class AdmissionUnchangedTests(EvidenceTestCase):
    """Evidence is durable but deliberately unused by production."""

    def requirement(self):
        return {
            "schema_version": 1,
            "operation": "install",
            "resolved": True,
            "reason": None,
            "artifact": {
                "resolved": True,
                "bytes": 6_114_568_235,
                "confidence": "high",
            },
            "overhead_bytes": 1_073_741_824,
            "peak_additional_bytes": 7_188_310_059,
            "confidence": "high",
        }

    def unresolved_plan(self):
        return {
            "schema_version": 1,
            "capacity": {
                "resolved": {
                    "remaining_bytes": None,
                    "basis": "unresolved",
                    "confidence": "unknown",
                },
            },
            "platform_usage": {
                "free_bytes": 238_077_691_035_648,
            },
            "platform_usage_reconciliation": {
                "total_platform_used_bytes": 0,
            },
            "platform_budget": {
                "schema_version": 1,
                "resolved": False,
                "reason": "safe_capacity_unresolved",
                "platform_used_bytes": 0,
                "available_for_new_platform_bytes": None,
            },
        }

    def test_admission_still_denies_with_durable_evidence_present(self):
        baseline = evaluate_storage_commit_admission(
            self.requirement(),
            config=self.config,
            storage_plan=self.unresolved_plan(),
            verify_now=False,
        )

        self.assertFalse(baseline["allowed"])
        self.assertEqual(
            baseline["reason"],
            "current_platform_storage_budget_unresolved",
        )

        # A 32 GiB success is now durably recorded, far above the
        # 6.7 GiB requirement. Admission must be unmoved: consuming
        # these facts is C3B's decision, not C3A's.
        record_empirical_probe_evidence(
            success_probe(32 * GIB),
            config=self.config,
        )

        after = evaluate_storage_commit_admission(
            self.requirement(),
            config=self.config,
            storage_plan=self.unresolved_plan(),
            verify_now=False,
        )

        self.assertEqual(after["allowed"], baseline["allowed"])
        self.assertEqual(after["reason"], baseline["reason"])
        self.assertEqual(
            after["decision"],
            baseline["decision"],
        )


class RetentionTests(EvidenceTestCase):
    def test_load_bearing_facts_survive_history_bounding(self):
        strongest_success = 40 * GIB
        tightest_failure = 41 * GIB

        record_empirical_probe_evidence(
            success_probe(strongest_success),
            config=self.config,
        )
        record_empirical_probe_evidence(
            capacity_failure_probe(tightest_failure),
            config=self.config,
        )

        # A small bound exercises the same logic without hundreds of
        # fsync round trips.
        bound = 10

        with mock.patch.object(
            cache_module,
            "EMPIRICAL_PROBE_EVIDENCE_RETENTION",
            bound,
        ):
            for index in range(bound + 20):
                record_empirical_probe_evidence(
                    success_probe(1 * MIB + index),
                    config=self.config,
                )

            stored = self.records()

        self.assertLessEqual(len(stored), bound)

        sizes = {entry["requested_bytes"] for entry in stored}

        self.assertIn(strongest_success, sizes)
        self.assertIn(tightest_failure, sizes)

    def test_small_histories_are_never_pruned(self):
        for index in range(10):
            record_empirical_probe_evidence(
                success_probe(1 * GIB + index),
                config=self.config,
            )

        self.assertEqual(len(self.records()), 10)


if __name__ == "__main__":
    unittest.main()
