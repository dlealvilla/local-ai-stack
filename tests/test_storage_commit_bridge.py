"""Tests for commit-time transaction storage verification.

The bridge exists because a host whose capacity has never been
characterized resolves no storage budget, and commit admission then
denies every mutation forever. What is under test is therefore not
"does a probe run" but a set of safety properties: that the proof is
only ever gathered when the budget is genuinely unresolved, that it
proves the amount this operation actually needs, that admission still
runs and still decides, and that a proof gathered to authorize one
download never becomes the platform's reported capacity.

Probes are injected as probe-shaped dicts. Everything above them is
real: the real requirement estimator, the real C3B characterization
policy, the real C3A persistence, the real capacity resolver, the real
budget policy and the real commit admission.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import core.storage_planning as planning

from core.model_storage_requirements import (
    estimate_model_install_storage,
)
from core.storage_capacity_cache import (
    read_capacity_cache,
    read_empirical_probe_evidence,
)
from core.storage_characterization import (
    MODE_HOST,
    MODE_TRANSACTION,
    characterize_storage,
)
from core.storage_commit_admission import (
    evaluate_storage_commit_admission,
)
from core.storage_planning import (
    build_storage_plan,
    build_storage_plan_for_commit,
)

GIB = 1024 ** 3

#
# The shared cluster figure the reference network volume advertises.
# It describes the backend, never this account's allocation.
#
SHARED_POOL_FREE = 664 * (1024 ** 4)

#
# `minimum_reserve_gb`, restated here on purpose: these tests pin the
# derivation to the policy that is actually configured, so a change to
# the reserve has to be acknowledged rather than absorbed.
#
MINIMUM_RESERVE = 10_000_000_000


MANIFEST_BYTES = 19_000_000_000


def settings(data_root, lock_path):
    return {
        "platform": {
            "data_root": str(data_root),
        },
        "model_transfer": {
            "enabled": True,
            "providers": ["huggingface"],
            "staging_root": "data/model-transfers",
        },
        "storage_capacity": {
            "provider": "runpod_network_volume",
            "probe_enabled": True,
            "probe_max_gb": 64.0,
            "probe_directory": "data/capacity-probes",
            "sonar_max_automatic_gb": 64.0,
            "sonar_start_mb": 64,
            "sonar_max_attempts": 32,
            "sonar_growth_factor": 2.0,
            "sonar_fallback_enabled": True,
            "maintenance_sonar_enabled": False,
            "quota_override_gb": 0.0,
            "consensus_relative_tolerance": 0.10,
            "consensus_absolute_gb": 2.0,
            "warning_free_fraction": 0.20,
            "protected_free_fraction": 0.15,
            "minimum_reserve_gb": 10.0,
            "platform_allocation_percent": 100.0,
            "model_operation_overhead_fraction": 0.10,
            "model_operation_overhead_min_gb": 1.0,
            "capacity_cache_enabled": True,
            "capacity_cache_ttl_seconds": 900,
            "storage_operation_lock_path": str(
                lock_path
            ),
            "maintenance_lock_path": str(
                lock_path
            ),
            "storage_operation_lock_wait_seconds": 0.0,
        },
    }


def shared_network_volume(config=None):
    """What the reference network volume actually reports.

    The FUSE figure describes a 2.1P shared cluster and is rejected
    by the resolver, which is exactly why nothing resolves until
    something is proven.
    """

    return {
        "schema_version": 1,
        "provider": "runpod_network_volume",
        "detection": {
            "provider": "runpod_network_volume",
            "reason": "Detected network volume.",
        },
        "path": "/workspace",
        "mount": {
            "source": "mfsmount",
            "filesystem_type": "fuse.mfs",
        },
        "filesystem": {
            "total_bytes": 2 * (1024 ** 5),
            "free_bytes": SHARED_POOL_FREE,
        },
        "quota": {
            "known": False,
            "total_bytes": None,
            "source": None,
        },
        "confidence": "medium",
        "notes": [],
    }


def no_platform_usage(config=None):
    return {
        "schema_version": 1,
        "filesystem": {
            "model_scope_bytes": 0,
            "transfer_staging_bytes": 0,
            "raw": {"scopes": {}, "warnings": []},
        },
        "reconciliation": {},
        "total_platform_used_bytes": 0,
        "warnings": [],
    }


def requirement_for(manifest_bytes=MANIFEST_BYTES):
    """The real storage-requirement seam, on a resolved manifest.

    A resolved manifest is high-confidence sizing, which is what
    commit admission demands before it will authorize anything.
    """

    return estimate_model_install_storage(
        {
            "source": {
                "provider": "huggingface",
                "source_model_id": "Org/model",
            },
            "size": {
                "manifest_bytes": manifest_bytes,
            },
        },
        overhead_fraction=0.10,
        overhead_min_bytes=GIB,
    )


def resolved_plan():
    """A plan whose budget already resolves, needing no proof."""

    return {
        "schema_version": 1,
        "capacity": {
            "resolved": {
                "remaining_bytes": 900_000_000_000,
                "basis": "verified_lower_bound",
                "confidence": "medium",
            },
        },
        "capacity_source": "valid_capacity_cache",
        "platform_budget": {
            "schema_version": 1,
            "resolved": True,
            "reason": None,
            "basis": "remaining_capacity_only",
            "platform_allocation_percent": 100.0,
            "platform_used_bytes": 0,
            "safe_remaining_bytes": 800_000_000_000,
            "safe_total_pool_bytes": None,
            "platform_total_budget_bytes": None,
            "platform_policy_remaining_bytes": None,
            "available_for_new_platform_bytes": (
                800_000_000_000
            ),
        },
    }


class Probe:
    """A probe mechanism with a known, fixed truth behind it."""

    def __init__(
        self,
        *,
        capacity_bytes=None,
        supported=True,
    ):
        self.capacity_bytes = capacity_bytes
        self.supported = supported
        self.requests = []

    def __call__(
        self,
        requested_bytes,
        *,
        config=None,
        max_probe_bytes=None,
    ):
        requested_bytes = int(requested_bytes)

        self.requests.append(requested_bytes)

        if not self.supported:
            return {
                "schema_version": 1,
                "supported": False,
                "success": False,
                "method": "posix_fallocate",
                "requested_bytes": requested_bytes,
                "duration_seconds": 0.01,
                "reason": "operation_not_supported",
                "errno": 95,
                "detail": "simulated unsupported primitive",
            }

        if (
            self.capacity_bytes is not None
            and requested_bytes > self.capacity_bytes
        ):
            return {
                "schema_version": 1,
                "supported": True,
                "success": False,
                "method": "posix_fallocate",
                "requested_bytes": requested_bytes,
                "duration_seconds": 0.4,
                "reason": "no_space",
                "errno": 28,
                "detail": "simulated capacity refusal",
            }

        return {
            "schema_version": 1,
            "supported": True,
            "success": True,
            "method": "posix_fallocate",
            "requested_bytes": requested_bytes,
            "reservation_accepted": True,
            "reported_allocated_bytes": 0,
            "allocation_visibility": "not_reported",
            "duration_seconds": 0.25,
            "reason": None,
        }


class Characterizer:
    """The real C3B entry point, with its probe mechanism injected."""

    def __init__(self, probe):
        self.probe = probe
        self.calls = []


    def __call__(
        self,
        *,
        mode,
        required_bytes,
        config,
    ):
        self.calls.append((mode, required_bytes))

        return characterize_storage(
            mode=mode,
            required_bytes=required_bytes,
            config=config,
            probe_implementation=self.probe,
        )

    @property
    def modes(self):
        return [mode for mode, _bytes in self.calls]

    @property
    def targets(self):
        return [target for _mode, target in self.calls]


class BridgeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.data_root = Path(self.tmp.name)

        self.config = settings(
            self.data_root,
            self.data_root / "storage.lock",
        )

        self.requirement = requirement_for()

        self.required_bytes = self.requirement[
            "peak_additional_bytes"
        ]

        #
        # The reserve is withheld from whatever capacity resolves, so
        # proving only the operation size would deny the operation the
        # proof was gathered for.
        #
        self.expected_target = (
            self.required_bytes + MINIMUM_RESERVE
        )

        patches = [
            mock.patch.object(
                planning,
                "reconcile_platform_storage_usage",
                no_platform_usage,
            ),
            mock.patch(
                "core.storage_capacity_resolution"
                ".inspect_storage_capacity",
                shared_network_volume,
            ),
        ]

        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def bridge(self, characterizer, storage_plan=None):
        return build_storage_plan_for_commit(
            self.requirement,
            config=self.config,
            storage_plan=storage_plan,
            characterize=characterizer,
        )

    def unresolved_plan(self):
        plan = build_storage_plan(
            config=self.config,
            calibrate_if_required=False,
        )

        self.assertFalse(
            plan["platform_budget"]["resolved"]
        )

        return plan


class WhenNoProofIsNeededTests(BridgeTestCase):
    def test_resolved_budget_is_left_completely_alone(self):
        characterizer = Characterizer(Probe())

        plan = resolved_plan()

        self.assertIs(
            self.bridge(characterizer, storage_plan=plan),
            plan,
        )

        self.assertEqual(characterizer.calls, [])

    def test_unresolved_requirement_is_left_to_admission(self):
        characterizer = Characterizer(Probe())

        unusable = dict(self.requirement)
        unusable["resolved"] = False

        plan = self.unresolved_plan()

        self.assertIs(
            build_storage_plan_for_commit(
                unusable,
                config=self.config,
                storage_plan=plan,
                characterize=characterizer,
            ),
            plan,
        )

        self.assertEqual(characterizer.calls, [])


class ProofTargetTests(BridgeTestCase):
    def test_unresolved_budget_asks_the_transaction_question(self):
        characterizer = Characterizer(
            Probe(capacity_bytes=400 * GIB)
        )

        self.bridge(
            characterizer,
            storage_plan=self.unresolved_plan(),
        )

        self.assertEqual(
            characterizer.modes,
            [MODE_TRANSACTION],
        )

    def test_host_characterization_is_never_asked_for(self):
        characterizer = Characterizer(
            Probe(capacity_bytes=400 * GIB)
        )

        self.bridge(
            characterizer,
            storage_plan=self.unresolved_plan(),
        )

        self.assertNotIn(MODE_HOST, characterizer.modes)

    def test_target_is_this_operation_plus_the_withheld_reserve(self):
        characterizer = Characterizer(
            Probe(capacity_bytes=400 * GIB)
        )

        self.bridge(
            characterizer,
            storage_plan=self.unresolved_plan(),
        )

        self.assertEqual(
            characterizer.targets,
            [self.expected_target],
        )

    def test_target_is_the_smallest_amount_that_admits(self):
        """One byte less must not be enough."""

        for candidate, expected in (
            (self.expected_target, True),
            (self.expected_target - 1, False),
        ):
            with self.subTest(candidate=candidate):
                budget = planning._plan_with_lower_bound(
                    candidate,
                    required_bytes=self.required_bytes,
                    config=self.config,
                )["platform_budget"]

                self.assertEqual(
                    budget["available_for_new_platform_bytes"]
                    >= self.required_bytes,
                    expected,
                )

    def test_probe_requests_the_characterized_target(self):
        probe = Probe(capacity_bytes=400 * GIB)

        self.bridge(
            Characterizer(probe),
            storage_plan=self.unresolved_plan(),
        )

        self.assertIn(self.expected_target, probe.requests)


class ProvenCapacityTests(BridgeTestCase):
    def test_budget_resolves_from_the_verified_lower_bound(self):
        plan = self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        resolved = plan["capacity"]["resolved"]

        self.assertEqual(
            resolved["basis"],
            "verified_lower_bound",
        )

        self.assertEqual(
            resolved["remaining_bytes"],
            self.expected_target,
        )

        self.assertTrue(
            plan["platform_budget"]["resolved"]
        )

        self.assertEqual(
            plan["capacity_source"],
            "supplied_empirical_evidence",
        )

    def test_proof_is_recorded_as_a_lower_bound_only(self):
        """A reservation of N proves at least N, and nothing more."""

        plan = self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        proofs = [
            item
            for item in plan["capacity"]["evidence"]
            if item["source"]
            == "storage_transaction_characterization"
        ]

        self.assertEqual(len(proofs), 1)

        self.assertEqual(
            proofs[0]["type"],
            "remaining_lower_bound",
        )

        self.assertEqual(
            proofs[0]["value_bytes"],
            self.expected_target,
        )

    def test_proof_never_claims_a_total_capacity(self):
        plan = self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        self.assertIsNone(
            plan["capacity"]["resolved"][
                "effective_total_bytes"
            ]
        )

        self.assertEqual(
            plan["platform_budget"]["basis"],
            "remaining_capacity_only",
        )


class HonestEvidenceTests(BridgeTestCase):
    """The proof answers one commit. It must not outlive that."""

    def test_proof_is_not_written_to_the_capacity_cache(self):
        self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        self.assertIsNone(
            read_capacity_cache(self.config)
        )

    def test_platform_capacity_stays_unresolved_afterwards(self):
        self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        after = build_storage_plan(
            config=self.config,
            calibrate_if_required=False,
        )

        self.assertFalse(
            after["platform_budget"]["resolved"]
        )

        self.assertEqual(
            after["platform_budget"]["reason"],
            "safe_capacity_unresolved",
        )

    def test_shared_pool_free_space_is_not_authority(self):
        plan = self.unresolved_plan()

        filesystem = [
            item
            for item in plan["capacity"]["evidence"]
            if item["evidence_id"] == "filesystem_free"
        ]

        self.assertEqual(len(filesystem), 1)

        self.assertFalse(filesystem[0]["accepted"])

        self.assertEqual(
            filesystem[0]["value_bytes"],
            SHARED_POOL_FREE,
        )

        self.assertIsNone(
            plan["platform_budget"][
                "available_for_new_platform_bytes"
            ]
        )


class InconclusiveProofTests(BridgeTestCase):
    def test_capacity_failure_leaves_the_denial_unchanged(self):
        plan = self.unresolved_plan()

        self.assertIs(
            self.bridge(
                Characterizer(Probe(capacity_bytes=GIB)),
                storage_plan=plan,
            ),
            plan,
        )

    def test_unsupported_probe_is_never_guessed_into_capacity(self):
        plan = self.unresolved_plan()

        self.assertIs(
            self.bridge(
                Characterizer(Probe(supported=False)),
                storage_plan=plan,
            ),
            plan,
        )

    def test_a_bound_below_the_target_proves_nothing(self):
        """Enough for the artifact is not enough for the commit."""

        plan = self.unresolved_plan()

        self.assertIs(
            self.bridge(
                Characterizer(
                    Probe(
                        capacity_bytes=(
                            self.required_bytes
                        )
                    )
                ),
                storage_plan=plan,
            ),
            plan,
        )


class AdmissionTests(BridgeTestCase):
    """Proof changes what the plan sees. Admission still decides."""

    def test_admission_allows_only_after_its_own_verification(self):
        plan = self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        verification = Probe(capacity_bytes=400 * GIB)

        admission = evaluate_storage_commit_admission(
            self.requirement,
            config=self.config,
            storage_plan=plan,
            probe=verification,
        )

        self.assertTrue(admission["allowed"])

        self.assertEqual(
            verification.requests,
            [self.required_bytes],
        )

        self.assertTrue(
            admission["guarantee"][
                "point_in_time_capacity_verified"
            ]
        )

    def test_proof_does_not_survive_a_failed_verification(self):
        plan = self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        admission = evaluate_storage_commit_admission(
            self.requirement,
            config=self.config,
            storage_plan=plan,
            probe=Probe(capacity_bytes=GIB),
        )

        self.assertFalse(admission["allowed"])

        self.assertEqual(
            admission["reason"],
            "operation_sized_verification_failed",
        )

    def test_denial_keeps_its_existing_reason(self):
        plan = self.bridge(
            Characterizer(Probe(supported=False)),
            storage_plan=self.unresolved_plan(),
        )

        admission = evaluate_storage_commit_admission(
            self.requirement,
            config=self.config,
            storage_plan=plan,
            verify_now=False,
        )

        self.assertFalse(admission["allowed"])

        self.assertEqual(
            admission["reason"],
            "current_platform_storage_budget_unresolved",
        )


class DurableEvidenceTests(BridgeTestCase):
    def test_every_probe_is_persisted_as_a_durable_fact(self):
        self.bridge(
            Characterizer(Probe(capacity_bytes=400 * GIB)),
            storage_plan=self.unresolved_plan(),
        )

        records = read_empirical_probe_evidence(
            self.config
        )["records"]

        self.assertIn(
            self.expected_target,
            [
                record["requested_bytes"]
                for record in records
            ],
        )

        proven = [
            record
            for record in records
            if record["requested_bytes"]
            == self.expected_target
        ]

        self.assertEqual(
            proven[0]["outcome"],
            "success",
        )

    def test_a_repeat_commit_reuses_the_durable_proof(self):
        probe = Probe(capacity_bytes=400 * GIB)

        self.bridge(
            Characterizer(probe),
            storage_plan=self.unresolved_plan(),
        )

        already_probed = len(probe.requests)

        plan = self.bridge(
            Characterizer(probe),
            storage_plan=self.unresolved_plan(),
        )

        self.assertEqual(
            len(probe.requests),
            already_probed,
        )

        self.assertTrue(
            plan["platform_budget"]["resolved"]
        )

    def test_a_smaller_commit_is_covered_by_a_larger_proof(self):
        """A proven 30 GB answers a 3 GB question with no probing."""

        probe = Probe(capacity_bytes=400 * GIB)

        self.bridge(
            Characterizer(probe),
            storage_plan=self.unresolved_plan(),
        )

        already_probed = len(probe.requests)

        smaller = requirement_for(2_000_000_000)

        characterizer = Characterizer(probe)

        plan = build_storage_plan_for_commit(
            smaller,
            config=self.config,
            storage_plan=self.unresolved_plan(),
            characterize=characterizer,
        )

        self.assertEqual(
            len(probe.requests),
            already_probed,
        )

        self.assertTrue(
            plan["platform_budget"]["resolved"]
        )

    def test_a_smaller_commit_probes_when_nothing_covers_it(self):
        """A refusal above does not answer a smaller question."""

        probe = Probe(capacity_bytes=GIB)

        self.bridge(
            Characterizer(probe),
            storage_plan=self.unresolved_plan(),
        )

        already_probed = len(probe.requests)

        smaller = requirement_for(2_000_000_000)

        build_storage_plan_for_commit(
            smaller,
            config=self.config,
            storage_plan=self.unresolved_plan(),
            characterize=Characterizer(probe),
        )

        self.assertGreater(
            len(probe.requests),
            already_probed,
        )


class DownloadPathTests(BridgeTestCase):
    """The real acquisition seam, with only the bytes faked.

    The transfer, the manifest and the probe mechanism are injected.
    The lock, the requirement estimator, the bridge, the admission and
    the ordering between them are real.
    """

    def setUp(self):
        super().setUp()

        self.events = []

        self.probe = Probe(capacity_bytes=400 * GIB)

        self.transfers = []

        patches = [
            mock.patch(
                "core.config.load_config",
                lambda: self.config,
            ),
            mock.patch(
                "core.storage_capacity_cache.load_config",
                lambda: self.config,
            ),
            mock.patch(
                "core.model_remote_storage_preflight"
                ".build_huggingface_storage_candidate",
                self.candidate,
            ),
            mock.patch(
                "core.model_transfer.download_model",
                self.transfer,
            ),
            mock.patch(
                "core.storage_characterization"
                ".probe_required_capacity",
                self.observed_probe,
            ),
            mock.patch(
                "core.storage_commit_admission"
                ".probe_required_capacity",
                self.observed_probe,
            ),
        ]

        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def observed_probe(self, requested_bytes, **kwargs):
        self.events.append(
            ("probe", int(requested_bytes))
        )

        return self.probe(requested_bytes, **kwargs)

    def candidate(self, source_model_id, *, revision="main"):
        return {
            "source": {
                "provider": "huggingface",
                "source_model_id": source_model_id,
                "revision": "sha-immutable",
                "requested_revision": revision,
            },
            "size": {
                "manifest_bytes": MANIFEST_BYTES,
            },
            "remote_manifest": {
                "resolved": True,
                "exactness": (
                    "complete_repository_manifest"
                ),
                "total_bytes": MANIFEST_BYTES,
            },
        }

    def transfer(
        self,
        *,
        provider,
        source_model_id,
        revision,
        target_name=None,
    ):
        self.events.append(("transfer", revision))

        self.transfers.append(revision)

        return {
            "status": "completed",
            "inventory_id": "local:model",
            "model_id": "model",
            "path": str(
                self.data_root / "models" / "model"
            ),
            "source": {
                "provider": provider,
                "source_model_id": source_model_id,
                "resolved_revision": revision,
            },
        }

    def download(self):
        from core.control import (
            download_inventory_model,
        )

        return download_inventory_model(
            provider="huggingface",
            source_model_id="Org/model",
        )

    def test_bytes_move_only_after_admission_allows(self):
        outcome = self.download()

        self.assertTrue(
            outcome["ok"],
            msg=outcome.get("error"),
        )

        self.assertTrue(
            outcome["storage_admission"]["allowed"]
        )

        kinds = [kind for kind, _detail in self.events]

        self.assertEqual(kinds.count("transfer"), 1)

        #
        # Every probe, including the admission's own operation-sized
        # verification, precedes the only mutation.
        #
        self.assertEqual(
            kinds.index("transfer"),
            len(kinds) - 1,
        )

        self.assertEqual(
            self.transfers,
            ["sha-immutable"],
        )

    def test_the_bridge_proves_before_admission_verifies(self):
        self.download()

        probed = [
            size
            for kind, size in self.events
            if kind == "probe"
        ]

        self.assertEqual(
            probed[-2:],
            [
                self.expected_target,
                self.required_bytes,
            ],
        )

    def test_a_denied_commit_never_reaches_the_transfer(self):
        self.probe = Probe(capacity_bytes=GIB)

        outcome = self.download()

        self.assertFalse(outcome["ok"])

        self.assertEqual(
            outcome["error"]["code"],
            "storage_admission_denied",
        )

        self.assertEqual(
            outcome["error"]["reason"],
            "current_platform_storage_budget_unresolved",
        )

        self.assertEqual(self.transfers, [])

    def test_proof_happens_inside_the_lock_already_held(self):
        """Re-entering the shared flock would deadlock the download."""

        from core.storage_operation_lock import (
            StorageOperationBusyError,
            storage_operation_lock,
        )

        contended = []

        def probe_while_locked(requested_bytes, **kwargs):
            try:
                with storage_operation_lock(
                    "intruder",
                    config=self.config,
                ):
                    contended.append(False)

            except StorageOperationBusyError:
                contended.append(True)

            return self.observed_probe(
                requested_bytes,
                **kwargs,
            )

        with mock.patch(
            "core.storage_characterization"
            ".probe_required_capacity",
            probe_while_locked,
        ):
            outcome = self.download()

        self.assertTrue(outcome["ok"])

        self.assertTrue(contended)

        self.assertTrue(all(contended))


def module_symbols(module):
    """Executable symbols of a module, excluding its docstrings.

    Docstrings legitimately name the concerns a module avoids, so
    reading them as usage would fail every module that explains
    itself.
    """

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))

    docstrings = set()

    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Module,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            text = ast.get_docstring(node, clean=False)

            if text is not None:
                docstrings.add(text)

    symbols = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            symbols.add(node.id.lower())

        elif isinstance(node, ast.Attribute):
            symbols.add(node.attr.lower())

        elif isinstance(node, ast.alias):
            symbols.add(node.name.lower())

        elif isinstance(node, ast.Constant):
            if (
                isinstance(node.value, str)
                and node.value not in docstrings
            ):
                symbols.add(node.value.lower())

    return symbols


class MechanismBoundaryTests(unittest.TestCase):
    def test_the_old_calibration_coordinator_is_not_reached(self):
        """The 48-minute ceiling search is not what commit needs."""

        import ast
        import inspect

        tree = ast.parse(
            inspect.getsource(
                planning.build_storage_plan_for_commit
            )
        )

        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
        }

        self.assertNotIn(
            "calibrate_storage_capacity",
            called,
        )

    def test_characterization_never_takes_the_storage_lock(self):
        """It runs inside a lock the mutation path already holds."""

        import core.storage_characterization as module

        symbols = module_symbols(module)

        for name in (
            "storage_operation_lock",
            "storage_operation_busy_error",
        ):
            self.assertNotIn(name, symbols)

    def test_acquisition_orchestration_learns_no_storage_mechanism(
        self,
    ):
        import core.model_acquisition as module

        symbols = module_symbols(module)

        for name in (
            "characterize_storage",
            "build_storage_plan",
            "build_storage_plan_for_commit",
            "probe_required_capacity",
            "evaluate_storage_commit_admission",
        ):
            self.assertNotIn(name, symbols)


if __name__ == "__main__":
    unittest.main()
