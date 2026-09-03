"""Tests for automatic model selection and acquisition.

The acquisition seam and the inventory seam are injected so the whole
decision path can be exercised without moving bytes. Everything above
them is real: real curated candidate records, the real storage
estimator, the real C4 requirement contract, the real C5 feasibility
gate and the real C6 selector.

Two properties get the most attention, because they are the ones that
could hurt a host: that an infeasible candidate can never be acquired,
and that a failure whose aftermath cannot be proven clean stops the
process instead of triggering another attempt.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from core.capacity_contracts import (
    build_capacity_envelope,
)
from core.capacity_feasibility import (
    VERDICT_COMPATIBLE,
    VERDICT_CONDITIONALLY_COMPATIBLE,
    VERDICT_UNSUPPORTED,
)
from core.model_acquisition import (
    ATTEMPT_ACQUIRED,
    ATTEMPT_FAILED,
    ATTEMPT_REUSED,
    MODEL_ACQUISITION_SCHEMA_VERSION,
    RECOVERABLE_ERROR_CODES,
    STATUS_ACQUIRED,
    STATUS_FAILED,
    STATUS_FALLBACK_ACQUIRED,
    STATUS_FALLBACK_REUSED,
    STATUS_NO_SELECTION_RESULT,
    STATUS_REUSED,
    build_selection_candidates,
    select_and_acquire_model,
)
from core.model_candidates import (
    load_curated_candidates,
    normalize_candidate,
)
from core.model_evaluation import (
    MODEL_EVALUATION_SCHEMA_VERSION,
    ModelEvaluationEvidence,
    ModelEvaluationResult,
    unavailable,
)
from core.resource_capacity import build_resource_capacity
from core.resource_reservation_bridge import (
    reservation_capacities_from_resource_safety,
)
from core.resource_reservations import (
    ResourceReservationLedger,
)
from core.resource_safety import build_resource_safety

GIB = 1024 ** 3

HOST_RAM_TOTAL = 811_121_754_112
HOST_RAM_AVAILABLE = 664_193_302_528
HOST_VRAM_TOTAL = 34_207_694_848
HOST_VRAM_FREE = 33_688_649_728

SAFE_VRAM = 30_267_880_244


def snapshot():
    return {
        "schema_version": 1,
        "generated_at": "2026-09-03T12:00:00+00:00",
        "host": {
            "operating_system": "Linux",
            "architecture": "x86_64",
            "cpu_model": "AMD EPYC 9354 32-Core Processor",
            "cpu_cores": 128,
        },
        "memory": {
            "total_bytes": HOST_RAM_TOTAL,
            "used_bytes": (
                HOST_RAM_TOTAL - HOST_RAM_AVAILABLE
            ),
            "available_bytes": HOST_RAM_AVAILABLE,
            "availability_source": (
                "/proc/meminfo:MemAvailable"
            ),
        },
        "accelerators": [
            {
                "index": 0,
                "vendor": "nvidia",
                "name": "NVIDIA GeForce RTX 5090",
                "memory": {
                    "total_bytes": HOST_VRAM_TOTAL,
                    "used_bytes": (
                        HOST_VRAM_TOTAL
                        - HOST_VRAM_FREE
                    ),
                    "free_bytes": HOST_VRAM_FREE,
                },
            },
        ],
        "storage": {
            "path": "/workspace",
            "total_bytes": 2_361_183_241_434_822_606,
            "used_bytes": 1_600_000_000_000_000,
            "free_bytes": 734_439_407_617_638,
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


def envelope():
    snap = snapshot()
    safety = build_resource_safety(
        build_resource_capacity(snap)
    )

    ledger = ResourceReservationLedger(
        reservation_capacities_from_resource_safety(
            safety
        )
    )

    return build_capacity_envelope(
        capacity_snapshot=snap,
        resource_safety=safety,
        reservation_snapshot=(
            ledger.snapshot().to_dict()
        ),
    )


def characterization(lower_bound=256 * GIB):
    return {
        "schema_version": 1,
        "mode": "host",
        "verified_lower_bound_bytes": lower_bound,
        "capacity_failure_upper_bound_bytes": None,
    }


def config():
    return {
        "storage_capacity": {
            "model_operation_overhead_fraction": 0.10,
            "model_operation_overhead_min_bytes": (
                1 * GIB
            ),
        },
        "model_evaluation": {
            "provider": "llmfit",
            "enabled": True,
        },
    }


def candidate(
    *,
    candidate_id,
    vram_gb,
    download_gb=4.0,
    ram_gb=16.0,
    evaluation_id=None,
    provider="huggingface",
    runtimes=("vllm",),
):
    return normalize_candidate(
        {
            "candidate_id": candidate_id,
            "provider": provider,
            "source_model_id": (
                "Org/" + candidate_id
            ),
            "evaluation_id": evaluation_id,
            "architecture": "TestForCausalLM",
            "quantization": "awq",
            "context_length": 40960,
            "runtimes": list(runtimes),
            "download_gb": download_gb,
            "vram_gb": vram_gb,
            "ram_gb": ram_gb,
        }
    )


DEFAULT_SET = [
    candidate(
        candidate_id="large",
        vram_gb=20.0,
        download_gb=18.0,
        evaluation_id="Org/large",
    ),
    candidate(
        candidate_id="medium",
        vram_gb=10.0,
        download_gb=9.0,
        evaluation_id="Org/medium",
    ),
    candidate(
        candidate_id="small",
        vram_gb=4.0,
        download_gb=2.5,
        evaluation_id="Org/small",
    ),
]


class Inventory:
    """The inventory seam, holding whatever the test says is installed."""

    def __init__(self, installed=()):
        self.models = list(installed)
        self.calls = 0

    def __call__(self):
        self.calls += 1

        return {
            "schema_version": 1,
            "models": list(self.models),
        }

    def install(
        self,
        *,
        provider="huggingface",
        source_model_id,
        revision="abc123",
        model_id="installed",
        state="stored",
        download_state="completed",
    ):
        self.models.append(
            {
                "inventory_id": (
                    "local:" + model_id
                ),
                "model_id": model_id,
                "path": (
                    "/workspace/models/" + model_id
                ),
                "source": {
                    "provider": provider,
                    "source_model_id": (
                        source_model_id
                    ),
                    "revision": revision,
                },
                "artifact": {
                    "state": state,
                    "disk_usage_bytes": 1000,
                },
                "management": (
                    {
                        "download_state": (
                            download_state
                        )
                    }
                    if download_state
                    else None
                ),
            }
        )


class Acquirer:
    """The acquisition seam, scripted per source model id."""

    def __init__(self, outcomes=None, default=None):
        self.outcomes = outcomes or {}
        self.default = default or self.success
        self.calls = []

    @staticmethod
    def success(source_model_id):
        return {
            "ok": True,
            "action": "download_model",
            "result": {
                "status": "completed",
                "inventory_id": (
                    "local:"
                    + source_model_id.split("/")[-1]
                ),
                "model_id": (
                    source_model_id.split("/")[-1]
                ),
                "path": (
                    "/workspace/models/"
                    + source_model_id.split("/")[-1]
                ),
                "source": {
                    "provider": "huggingface",
                    "source_model_id": (
                        source_model_id
                    ),
                    "resolved_revision": "sha-1234",
                },
            },
            "storage_admission": {
                "allowed": True,
                "decision": "allow",
                "reason": None,
            },
        }

    @staticmethod
    def denied(reason="current_platform_storage_budget_unresolved"):
        def build(source_model_id):
            return {
                "ok": False,
                "action": "download_model",
                "error": {
                    "code": (
                        "storage_admission_denied"
                    ),
                    "detail": (
                        "Storage admission denied "
                        "the operation."
                    ),
                    "reason": reason,
                },
                "storage_admission": {
                    "allowed": False,
                    "decision": "deny",
                    "reason": reason,
                },
            }

        return build

    @staticmethod
    def error(code, detail="boom"):
        def build(source_model_id):
            return {
                "ok": False,
                "action": "download_model",
                "error": {
                    "code": code,
                    "detail": detail,
                },
            }

        return build

    def __call__(
        self,
        *,
        provider,
        source_model_id,
        revision=None,
        target_name=None,
    ):
        self.calls.append(
            {
                "provider": provider,
                "source_model_id": source_model_id,
                "revision": revision,
                "target_name": target_name,
            }
        )

        handler = self.outcomes.get(
            source_model_id,
            self.default,
        )

        return handler(source_model_id)


UNSET = object()


def run(
    *,
    candidates=None,
    acquirer=None,
    inventory=None,
    provider=None,
    storage=UNSET,
):
    return select_and_acquire_model(
        candidates=(
            DEFAULT_SET
            if candidates is None
            else candidates
        ),
        envelope=envelope(),
        storage_characterization=(
            characterization()
            if storage is UNSET
            else storage
        ),
        config=config(),
        evaluation_provider=provider,
        acquire=acquirer or Acquirer(),
        list_inventory=inventory or Inventory(),
    )


def evidence_provider(*ranked_ids, available=True):
    """A provider ranking candidates by the order named."""

    class Provider:
        provider = "llmfit"

        def __init__(self):
            self.calls = 0

        def evaluate(
            self,
            *,
            candidates,
            envelope,
            config=None,
        ):
            self.calls += 1

            if not available:
                return unavailable(
                    "llmfit",
                    "executable missing",
                )

            return ModelEvaluationResult(
                schema_version=(
                    MODEL_EVALUATION_SCHEMA_VERSION
                ),
                provider="llmfit",
                available=True,
                evidence=tuple(
                    ModelEvaluationEvidence(
                        candidate_id=name,
                        provider="llmfit",
                        usable=True,
                        rank=rank,
                        overall_score=(
                            100.0 - rank
                        ),
                    )
                    for rank, name in enumerate(
                        ranked_ids
                    )
                ),
            )

    return Provider()


class PipelineTests(unittest.TestCase):
    """C4 -> C5 -> C6 over a small candidate set."""

    def test_candidates_flow_through_requirement_and_feasibility(self):
        built = build_selection_candidates(
            candidates=DEFAULT_SET,
            envelope=envelope(),
            storage_characterization=(
                characterization()
            ),
            config=config(),
        )

        self.assertEqual(len(built), 3)

        for record, selection_candidate in built:
            requirement = (
                selection_candidate.requirement
            )

            # C4 normalized the declared metadata.
            self.assertEqual(
                requirement.model_id,
                record["candidate_id"],
            )
            self.assertEqual(
                requirement.quantization,
                "awq",
            )

            # The real estimator sized acquisition.
            self.assertIsNotNone(
                requirement.storage.acquisition_peak_bytes
            )
            self.assertGreater(
                requirement.storage.acquisition_peak_bytes,
                record["size"]["download_bytes"],
            )

            # C5 produced a verdict.
            self.assertEqual(
                selection_candidate.feasibility.verdict,
                VERDICT_COMPATIBLE,
            )

    def test_declared_order_is_preserved(self):
        built = build_selection_candidates(
            candidates=DEFAULT_SET,
            envelope=envelope(),
            storage_characterization=(
                characterization()
            ),
            config=config(),
        )

        self.assertEqual(
            [
                selection_candidate.candidate_id
                for _record, selection_candidate in built
            ],
            ["large", "medium", "small"],
        )

    def test_evaluation_id_is_carried_explicitly(self):
        built = build_selection_candidates(
            candidates=[
                candidate(
                    candidate_id="mapped",
                    vram_gb=8.0,
                    evaluation_id="Vendor/Other-Name",
                ),
                candidate(
                    candidate_id="unmapped",
                    vram_gb=6.0,
                ),
            ],
            envelope=envelope(),
            storage_characterization=(
                characterization()
            ),
            config=config(),
        )

        mapped = built[0][1]
        unmapped = built[1][1]

        self.assertEqual(
            mapped.provider_identity,
            "Vendor/Other-Name",
        )

        # No mapping declared means our own id, never a guess.
        self.assertEqual(
            unmapped.provider_identity,
            "unmapped",
        )

    def test_curated_set_loads_from_configuration(self):
        from core.config import load_config

        loaded = load_curated_candidates(
            load_config()
        )

        self.assertGreaterEqual(len(loaded), 2)

        for record in loaded:
            self.assertIn(
                "candidate_id",
                record,
            )
            self.assertIsNotNone(
                record["source"]["provider"]
            )
            self.assertIsNone(
                record["size"]["installed_bytes"],
                msg=(
                    "a curated candidate must not "
                    "claim to be installed"
                ),
            )

    def test_no_candidates_yields_no_selection(self):
        result = run(candidates=[])

        self.assertEqual(
            result.status,
            STATUS_NO_SELECTION_RESULT,
        )
        self.assertIsNone(
            result.selected_candidate_id
        )


class FeasibilityGateTests(unittest.TestCase):
    def test_unsupported_candidate_is_never_acquired(self):
        acquirer = Acquirer()

        too_large = candidate(
            candidate_id="too-large",
            vram_gb=31.0,
        )

        result = run(
            candidates=[too_large],
            acquirer=acquirer,
        )

        self.assertEqual(
            result.status,
            STATUS_NO_SELECTION_RESULT,
        )
        self.assertEqual(acquirer.calls, [])

    def test_provider_cannot_promote_an_unsupported_candidate(self):
        acquirer = Acquirer()

        # The provider ranks the infeasible candidate first.
        provider = evidence_provider(
            "too-large",
            "small",
        )

        result = run(
            candidates=[
                candidate(
                    candidate_id="too-large",
                    vram_gb=31.0,
                ),
                candidate(
                    candidate_id="small",
                    vram_gb=4.0,
                ),
            ],
            acquirer=acquirer,
            provider=provider,
        )

        self.assertEqual(
            result.selected_candidate_id,
            "small",
        )
        self.assertEqual(
            [
                call["source_model_id"]
                for call in acquirer.calls
            ],
            ["Org/small"],
        )

    def test_conditional_candidate_is_still_acquirable(self):
        # Unresolved storage characterization leaves storage
        # unresolved, so every candidate is merely conditional. The
        # authoritative gate for the mutation is admission, not this.
        acquirer = Acquirer()

        result = run(
            acquirer=acquirer,
            storage=None,
        )

        self.assertEqual(
            result.eligibility_tier,
            "conditional",
        )
        self.assertEqual(
            result.status,
            STATUS_ACQUIRED,
        )


class PrimaryAcquisitionTests(unittest.TestCase):
    def test_selected_candidate_is_acquired_through_the_seam(self):
        acquirer = Acquirer()

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
                "small",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_ACQUIRED,
        )
        self.assertEqual(
            result.selected_candidate_id,
            "large",
        )
        self.assertEqual(
            result.acquired_candidate_id,
            "large",
        )
        self.assertEqual(
            result.inventory_id,
            "local:large",
        )
        self.assertEqual(
            result.acquisition_provider,
            "huggingface",
        )

        # Exactly one attempt, with the candidate's own provider.
        self.assertEqual(len(acquirer.calls), 1)
        self.assertEqual(
            acquirer.calls[0]["provider"],
            "huggingface",
        )
        self.assertEqual(
            acquirer.calls[0]["target_name"],
            "large",
        )

    def test_success_does_not_attempt_the_fallback(self):
        acquirer = Acquirer()

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
                "small",
            ),
        )

        self.assertIsNone(
            result.fallback_attempt
        )

        # The fallback was still identified in advance.
        self.assertEqual(
            result.fallback_candidate_id,
            "medium",
        )
        self.assertEqual(len(acquirer.calls), 1)

    def test_acquisition_provider_comes_from_the_candidate(self):
        acquirer = Acquirer()

        run(
            candidates=[
                candidate(
                    candidate_id="offline",
                    vram_gb=6.0,
                    provider="local_files",
                )
            ],
            acquirer=acquirer,
        )

        self.assertEqual(
            acquirer.calls[0]["provider"],
            "local_files",
        )


class ReuseTests(unittest.TestCase):
    def test_installed_primary_is_reused(self):
        acquirer = Acquirer()
        inventory = Inventory()
        inventory.install(
            source_model_id="Org/large",
            model_id="large",
        )

        result = run(
            acquirer=acquirer,
            inventory=inventory,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_REUSED,
        )
        self.assertEqual(
            result.acquired_candidate_id,
            "large",
        )
        self.assertEqual(
            result.inventory_id,
            "local:large",
        )

        # Nothing was downloaded.
        self.assertEqual(acquirer.calls, [])

    def test_a_failed_transfer_record_is_not_reused(self):
        acquirer = Acquirer()
        inventory = Inventory()
        inventory.install(
            source_model_id="Org/large",
            model_id="large",
            download_state="failed",
        )

        result = run(
            acquirer=acquirer,
            inventory=inventory,
            provider=evidence_provider("large"),
        )

        self.assertEqual(
            result.status,
            STATUS_ACQUIRED,
        )
        self.assertEqual(len(acquirer.calls), 1)

    def test_a_discovered_model_without_management_is_reused(self):
        inventory = Inventory()
        inventory.install(
            source_model_id="Org/large",
            model_id="large",
            download_state=None,
        )

        acquirer = Acquirer()

        result = run(
            acquirer=acquirer,
            inventory=inventory,
            provider=evidence_provider("large"),
        )

        self.assertEqual(
            result.status,
            STATUS_REUSED,
        )
        self.assertEqual(acquirer.calls, [])

    def test_a_different_source_is_not_mistaken_for_the_candidate(self):
        inventory = Inventory()
        inventory.install(
            source_model_id="Other/model",
            model_id="other",
        )

        acquirer = Acquirer()

        run(
            acquirer=acquirer,
            inventory=inventory,
            provider=evidence_provider("large"),
        )

        self.assertEqual(len(acquirer.calls), 1)

    def test_a_pinned_revision_must_match(self):
        pinned = normalize_candidate(
            {
                "candidate_id": "pinned",
                "provider": "huggingface",
                "source_model_id": "Org/pinned",
                "revision": "wanted-sha",
                "vram_gb": 6.0,
                "download_gb": 3.0,
                "ram_gb": 16.0,
                "runtimes": ["vllm"],
            }
        )

        inventory = Inventory()
        inventory.install(
            source_model_id="Org/pinned",
            model_id="pinned",
            revision="a-different-sha",
        )

        acquirer = Acquirer()

        result = run(
            candidates=[pinned],
            acquirer=acquirer,
            inventory=inventory,
        )

        self.assertEqual(
            result.status,
            STATUS_ACQUIRED,
        )
        self.assertEqual(
            acquirer.calls[0]["revision"],
            "wanted-sha",
        )

    def test_destination_collision_is_treated_as_reuse(self):
        acquirer = Acquirer(
            default=Acquirer.error(
                "already_exists",
                "Destination already exists",
            )
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider("large"),
        )

        self.assertEqual(
            result.status,
            STATUS_REUSED,
        )

        # No fallback after a reuse.
        self.assertEqual(len(acquirer.calls), 1)


class LowerResourceFallbackTests(unittest.TestCase):
    def test_fallback_requires_strictly_lower_primary_memory(self):
        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
                "small",
            ),
        )

        self.assertEqual(
            result.fallback_candidate_id,
            "medium",
        )

        primary_memory = 20 * GIB
        fallback_memory = 10 * GIB

        self.assertLess(
            fallback_memory,
            primary_memory,
        )
        self.assertEqual(
            result.status,
            STATUS_FALLBACK_ACQUIRED,
        )

    def test_a_higher_resource_candidate_is_never_the_fallback(self):
        acquirer = Acquirer(
            outcomes={
                "Org/small": Acquirer.denied(),
            }
        )

        # The smallest candidate is selected, so nothing is lower.
        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "small",
                "medium",
                "large",
            ),
        )

        self.assertIsNone(
            result.fallback_candidate_id
        )
        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )
        self.assertEqual(len(acquirer.calls), 1)
        self.assertIn(
            "no lower-resource alternative",
            result.reason,
        )

    def test_compatible_fallback_preferred_over_conditional(self):
        # medium is compatible; conditional-mid has unresolved RAM but
        # sits between them on memory, so only tiering can decide.
        conditional_mid = normalize_candidate(
            {
                "candidate_id": "conditional-mid",
                "provider": "huggingface",
                "source_model_id": (
                    "Org/conditional-mid"
                ),
                "vram_gb": 15.0,
                "download_gb": 12.0,
                "runtimes": ["vllm"],
            }
        )

        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            candidates=[
                DEFAULT_SET[0],
                conditional_mid,
                DEFAULT_SET[1],
            ],
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "conditional-mid",
                "medium",
            ),
        )

        self.assertEqual(
            result.fallback_candidate_id,
            "medium",
        )

    def test_conditional_fallback_used_when_no_compatible_one_exists(self):
        conditional_low = normalize_candidate(
            {
                "candidate_id": "conditional-low",
                "provider": "huggingface",
                "source_model_id": (
                    "Org/conditional-low"
                ),
                "vram_gb": 8.0,
                "download_gb": 6.0,
                "runtimes": ["vllm"],
            }
        )

        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            candidates=[
                DEFAULT_SET[0],
                conditional_low,
            ],
            acquirer=acquirer,
            provider=evidence_provider("large"),
        )

        self.assertEqual(
            result.fallback_candidate_id,
            "conditional-low",
        )
        self.assertEqual(
            result.status,
            STATUS_FALLBACK_ACQUIRED,
        )

    def test_unsupported_is_never_the_fallback(self):
        # Lower-resource than the primary, but not runnable here.
        broken = normalize_candidate(
            {
                "candidate_id": "broken",
                "provider": "huggingface",
                "source_model_id": "Org/broken",
                "vram_gb": 5.0,
                "download_gb": 3.0,
                "ram_gb": 16.0,
                "runtimes": [],
                "compatibility": "unsupported",
            }
        )

        built = build_selection_candidates(
            candidates=[broken],
            envelope=envelope(),
            storage_characterization=(
                characterization()
            ),
            config=config(),
        )

        self.assertEqual(
            built[0][1].feasibility.verdict,
            VERDICT_UNSUPPORTED,
        )

        acquirer = Acquirer(
            outcomes={
                "Org/medium": Acquirer.denied(),
            }
        )

        result = run(
            candidates=[
                DEFAULT_SET[1],
                broken,
            ],
            acquirer=acquirer,
            provider=evidence_provider("medium"),
        )

        self.assertEqual(
            result.selected_candidate_id,
            "medium",
        )
        self.assertIsNone(
            result.fallback_candidate_id
        )
        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )
        self.assertEqual(len(acquirer.calls), 1)

    def test_fallback_uses_the_same_provider_ranking(self):
        # Two lower-resource alternatives; the provider prefers the
        # one that safe-fit ordering would NOT choose.
        provider = evidence_provider(
            "large",
            "small",
            "medium",
        )

        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            acquirer=acquirer,
            provider=provider,
        )

        self.assertEqual(
            result.fallback_candidate_id,
            "small",
        )

        # One provider invocation, reused for both decisions.
        self.assertEqual(provider.calls, 1)

    def test_fallback_falls_back_to_safe_fit_without_evidence(self):
        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(acquirer=acquirer)

        # No provider: closest safe fit picks the largest that fits,
        # then the largest lower-resource alternative.
        self.assertEqual(
            result.selected_candidate_id,
            "large",
        )
        self.assertEqual(
            result.fallback_candidate_id,
            "medium",
        )

    def test_unresolved_primary_memory_yields_no_fallback(self):
        no_memory = normalize_candidate(
            {
                "candidate_id": "unknown-memory",
                "provider": "huggingface",
                "source_model_id": (
                    "Org/unknown-memory"
                ),
                "download_gb": 3.0,
                "ram_gb": 16.0,
                "runtimes": ["vllm"],
            }
        )

        acquirer = Acquirer(
            outcomes={
                "Org/unknown-memory": (
                    Acquirer.denied()
                ),
            }
        )

        result = run(
            candidates=[no_memory],
            acquirer=acquirer,
            provider=evidence_provider(
                "unknown-memory"
            ),
        )

        self.assertIsNone(
            result.fallback_candidate_id
        )
        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )


class AttemptBoundTests(unittest.TestCase):
    def test_exactly_one_fallback_attempt(self):
        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
                "small",
            ),
        )

        self.assertEqual(len(acquirer.calls), 2)
        self.assertEqual(
            [
                call["source_model_id"]
                for call in acquirer.calls
            ],
            ["Org/large", "Org/medium"],
        )
        self.assertEqual(
            result.status,
            STATUS_FALLBACK_ACQUIRED,
        )

    def test_no_third_attempt_when_both_fail(self):
        acquirer = Acquirer(
            default=Acquirer.denied()
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
                "small",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )

        # Two attempts, never a third, even though a third
        # lower-resource candidate exists.
        self.assertEqual(len(acquirer.calls), 2)
        self.assertEqual(
            result.primary_attempt.outcome,
            ATTEMPT_FAILED,
        )
        self.assertEqual(
            result.fallback_attempt.outcome,
            ATTEMPT_FAILED,
        )

    def test_fallback_reuse_is_reported_distinctly(self):
        inventory = Inventory()
        inventory.install(
            source_model_id="Org/medium",
            model_id="medium",
        )

        acquirer = Acquirer(
            outcomes={
                "Org/large": Acquirer.denied(),
            }
        )

        result = run(
            acquirer=acquirer,
            inventory=inventory,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_FALLBACK_REUSED,
        )
        self.assertEqual(
            result.inventory_id,
            "local:medium",
        )

        # Only the primary was downloaded-attempted.
        self.assertEqual(len(acquirer.calls), 1)


class FailClosedTests(unittest.TestCase):
    def test_a_concurrent_storage_operation_fails_closed(self):
        # Another mutation holds the storage lock, so this process
        # cannot reason about platform state.
        acquirer = Acquirer(
            default=Acquirer.error(
                "storage_operation_busy",
                "Another storage operation is "
                "in progress.",
            )
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )
        self.assertEqual(len(acquirer.calls), 1)
        self.assertFalse(
            result.primary_attempt.recoverable
        )
        self.assertIn(
            "cannot prove safe",
            result.reason,
        )

    def test_an_unrecognized_failure_fails_closed(self):
        acquirer = Acquirer(
            default=Acquirer.error(
                "something_new_and_unclassified"
            )
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )
        self.assertEqual(len(acquirer.calls), 1)

    def test_an_unexpected_result_shape_fails_closed(self):
        acquirer = Acquirer(
            default=lambda source_model_id: None
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.status,
            STATUS_FAILED,
        )
        self.assertEqual(len(acquirer.calls), 1)

    def test_recoverable_codes_are_explicit_and_bounded(self):
        # Fallback is opt-in per failure kind, not the default.
        self.assertEqual(
            RECOVERABLE_ERROR_CODES,
            frozenset(
                {
                    "storage_admission_denied",
                    "storage_preflight_failed",
                    "transfer_failed",
                    "provider_not_enabled",
                    "storage_safety_not_implemented",
                }
            ),
        )
        self.assertNotIn(
            "storage_operation_busy",
            RECOVERABLE_ERROR_CODES,
        )

    def test_each_recoverable_code_permits_one_fallback(self):
        for code in RECOVERABLE_ERROR_CODES:
            acquirer = Acquirer(
                outcomes={
                    "Org/large": Acquirer.error(
                        code
                    ),
                }
            )

            result = run(
                acquirer=acquirer,
                provider=evidence_provider(
                    "large",
                    "medium",
                    "small",
                ),
            )

            self.assertEqual(
                result.status,
                STATUS_FALLBACK_ACQUIRED,
                msg=code,
            )
            self.assertEqual(
                len(acquirer.calls),
                2,
                msg=code,
            )


class StorageAuthorityTests(unittest.TestCase):
    def test_admission_denial_is_surfaced_not_bypassed(self):
        acquirer = Acquirer(
            default=Acquirer.denied(
                "current_platform_storage_budget_unresolved"
            )
        )

        result = run(
            acquirer=acquirer,
            provider=evidence_provider(
                "large",
                "medium",
            ),
        )

        self.assertEqual(
            result.primary_attempt.admission_reason,
            "current_platform_storage_budget_unresolved",
        )
        self.assertEqual(
            result.primary_attempt.error_code,
            "storage_admission_denied",
        )

    def test_orchestration_never_reads_filesystem_free_space(self):
        import inspect

        import core.model_acquisition as module

        source = inspect.getsource(module)

        for forbidden in (
            "disk_usage",
            "statvfs",
            "df ",
            "free_bytes",
        ):
            self.assertNotIn(
                forbidden,
                source,
                msg=forbidden,
            )

    def test_orchestration_does_not_own_storage_machinery(self):
        import core.model_acquisition as module

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

        forbidden = {
            "core.storage_characterization",
            "core.storage_probe",
            "core.storage_capacity_calibration",
            "core.storage_commit_admission",
            "core.storage_operation_lock",
            "core.storage_maintenance",
            "core.storage_maintenance_calibration",
        }

        self.assertEqual(
            imported & forbidden,
            set(),
            msg=(
                "acquisition must delegate storage "
                "safety to the existing seam"
            ),
        )


class NoRuntimeTests(unittest.TestCase):
    def test_no_runtime_inference_or_reservation_is_touched(self):
        import core.model_acquisition as module

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

        forbidden = {
            "core.lifecycle",
            "core.resource_manager",
            "core.deployment",
            "core.health",
            "core.runtime_manager",
        }

        self.assertEqual(
            imported & forbidden,
            set(),
        )

    def test_no_vendor_or_runtime_identifiers_in_code(self):
        # Asserted on executable code, not on prose, which names the
        # concerns this module deliberately leaves to others.
        joined = " ".join(sorted(code_symbols()))

        for forbidden in (
            "vllm",
            "nvidia",
            "cuda",
            "rocm",
            "metal",
            "mlx",
            "huggingface",
            "openai",
        ):
            self.assertNotIn(
                forbidden,
                joined,
                msg=forbidden,
            )

    def test_no_reservation_is_created_or_released(self):
        # Reservation capacity is read to build the envelope, which is
        # how existing allocations are accounted for. Creating or
        # releasing one is a different act and belongs to a later step.
        symbols = code_symbols()

        for forbidden in (
            "reserve",
            "release",
            "start",
            "stop",
            "restart",
        ):
            self.assertNotIn(
                forbidden,
                symbols,
                msg=forbidden,
            )

        # The ledger is only ever snapshotted.
        self.assertIn("snapshot", symbols)


class ResultContractTests(unittest.TestCase):
    def test_result_serializes_and_stays_small(self):
        result = run(
            provider=evidence_provider(
                "large",
                "medium",
            )
        )

        payload = json.loads(
            json.dumps(result.to_dict())
        )

        self.assertEqual(
            payload["schema_version"],
            MODEL_ACQUISITION_SCHEMA_VERSION,
        )
        self.assertEqual(
            payload["status"],
            STATUS_ACQUIRED,
        )
        self.assertEqual(
            payload["acquired_candidate_id"],
            "large",
        )
        self.assertEqual(
            payload["selection_provider"],
            "llmfit",
        )
        self.assertEqual(
            payload["eligibility_tier"],
            "compatible",
        )

        # A concise result, not an execution trace.
        self.assertLessEqual(
            len(payload),
            13,
        )
        self.assertNotIn(
            "evaluation",
            payload,
        )

    def test_every_status_is_reachable(self):
        seen = set()

        seen.add(
            run(
                provider=evidence_provider("large")
            ).status
        )

        inventory = Inventory()
        inventory.install(
            source_model_id="Org/large",
            model_id="large",
        )
        seen.add(
            run(inventory=inventory).status
        )

        seen.add(
            run(
                acquirer=Acquirer(
                    outcomes={
                        "Org/large": (
                            Acquirer.denied()
                        )
                    }
                ),
                provider=evidence_provider(
                    "large",
                    "medium",
                ),
            ).status
        )

        fallback_inventory = Inventory()
        fallback_inventory.install(
            source_model_id="Org/medium",
            model_id="medium",
        )
        seen.add(
            run(
                acquirer=Acquirer(
                    outcomes={
                        "Org/large": (
                            Acquirer.denied()
                        )
                    }
                ),
                inventory=fallback_inventory,
                provider=evidence_provider(
                    "large",
                    "medium",
                ),
            ).status
        )

        seen.add(
            run(
                acquirer=Acquirer(
                    default=Acquirer.denied()
                )
            ).status
        )

        seen.add(run(candidates=[]).status)

        self.assertEqual(
            seen,
            {
                STATUS_ACQUIRED,
                STATUS_REUSED,
                STATUS_FALLBACK_ACQUIRED,
                STATUS_FALLBACK_REUSED,
                STATUS_FAILED,
                STATUS_NO_SELECTION_RESULT,
            },
        )


def code_symbols():
    """Executable symbols of the orchestration, excluding docstrings."""

    import ast
    import inspect

    import core.model_acquisition as module

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
            text = ast.get_docstring(
                node,
                clean=False,
            )

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


class DiscoveredModelSnapshotTests(unittest.TestCase):
    """A model found on disk must not break capacity observation.

    Inventory stores `management: None` for a model discovered on disk
    with no persisted record, and `dict.get(key, {})` returns None for
    a key that exists holding None. Building the envelope therefore
    crashed on any host with an unmanaged local model, which is the
    normal state after an operator copies one in.
    """

    def test_none_valued_sections_are_tolerated(self):
        # Observes real host storage, so it runs where the platform
        # data root exists rather than being faked.
        import os

        from core.capacity_snapshot import (
            build_capacity_snapshot,
        )
        from core.config import load_config

        data_root = load_config()["platform"][
            "data_root"
        ]

        if not os.path.isdir(data_root):
            self.skipTest(
                "platform data root is not present "
                "on this machine"
            )

        discovered = {
            "inventory_id": "local:found",
            "model_id": "found",
            "path": "/workspace/models/found",
            "source": {
                "provider": "local_files",
                "source_model_id": "found",
                "revision": None,
            },
            "artifact": {
                "state": "stored",
                "disk_usage_bytes": 166,
            },
            "management": None,
            "deployment": None,
        }

        import core.capacity_snapshot as module

        with mock.patch.object(
            module,
            "list_model_inventory",
            lambda: {
                "schema_version": 1,
                "models": [discovered],
            },
        ):
            snapshot = build_capacity_snapshot()

        self.assertIn("storage", snapshot)
        self.assertIn("workload", snapshot)

        # The unmanaged artifact is counted as installed but not as
        # platform-managed usage.
        self.assertEqual(
            snapshot["workload"]["selected_model_ids"],
            [],
        )


class NoCallerMigrationTests(unittest.TestCase):
    def test_no_existing_module_consumes_the_orchestration(self):
        import inspect

        import core.control as control
        import platform_api.server as server

        for module in (control, server):
            source = inspect.getsource(module)

            self.assertNotIn(
                "model_acquisition",
                source,
                msg=module.__name__,
            )
            self.assertNotIn(
                "select_and_acquire_model",
                source,
                msg=module.__name__,
            )


if __name__ == "__main__":
    unittest.main()
