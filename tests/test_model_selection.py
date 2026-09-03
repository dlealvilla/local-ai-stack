"""Tests for the minimal single-model selector.

Two properties carry the weight. A candidate the feasibility gate
rejected must never become selectable, whatever a provider says about
it. And a provider that cannot be consulted must degrade to
closest-safe-fit rather than break selection.

Feasibility results come from the real C5 evaluator over real C1/C2
envelopes and C4 requirements, so the selector is exercised against the
verdicts the platform actually produces.
"""

from __future__ import annotations

import json
import unittest

from core.capacity_contracts import (
    build_capacity_envelope,
)
from core.capacity_feasibility import (
    VERDICT_COMPATIBLE,
    VERDICT_CONDITIONALLY_COMPATIBLE,
    VERDICT_UNSUPPORTED,
    evaluate_capacity_feasibility,
)
from core.model_evaluation import (
    MODEL_EVALUATION_SCHEMA_VERSION,
    ModelEvaluationEvidence,
    ModelEvaluationResult,
    unavailable,
)
from core.model_requirement import build_model_requirement
from core.model_selection import (
    MODEL_SELECTION_SCHEMA_VERSION,
    PROVIDER_FALLBACK,
    PROVIDER_NONE,
    STATUS_NO_SELECTION,
    STATUS_SELECTED,
    TIER_COMPATIBLE,
    TIER_CONDITIONAL,
    SelectionCandidate,
    select_model,
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
SAFE_RAM = 583_081_127_117

ARTIFACT_BYTES = 6_114_568_235


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


def characterization(lower_bound=64 * GIB):
    return {
        "schema_version": 1,
        "mode": "host",
        "verified_lower_bound_bytes": lower_bound,
        "capacity_failure_upper_bound_bytes": None,
    }


def requirement(
    *,
    name,
    vram_bytes,
    ram_bytes=32 * GIB,
    installed=True,
):
    model = {
        "schema_version": 1,
        "name": name,
        "architecture": "TestForCausalLM",
        "quantization": "awq",
        "context_length": 40960,
        "source": {
            "provider": "huggingface",
            "revision": "abc123",
        },
        "size": {
            "download_bytes": ARTIFACT_BYTES,
            "installed_bytes": (
                ARTIFACT_BYTES if installed else None
            ),
        },
        "format": {"weights": "safetensors"},
        "runtime": {"supported": ["vllm"]},
        "requirements": {
            "ram_bytes": ram_bytes,
            "vram_bytes": vram_bytes,
            "unified_memory_bytes": None,
        },
    }

    compatibility = dict(model)
    compatibility["compatibility"] = {
        "status": "compatible",
        "confidence": "medium",
        "reasons": [],
    }

    install_storage = {
        "schema_version": 1,
        "operation": "install",
        "resolved": True,
        "artifact": {
            "resolved": True,
            "bytes": ARTIFACT_BYTES,
            "confidence": "high",
        },
        "overhead_bytes": 1 * GIB,
        "peak_additional_bytes": (
            ARTIFACT_BYTES + 1 * GIB
        ),
        "confidence": "high",
    }

    return build_model_requirement(
        model=model,
        install_storage=install_storage,
        compatibility=compatibility,
    )


def candidate(
    *,
    name,
    vram_bytes,
    ram_bytes=32 * GIB,
    installed=True,
    evaluation_id=None,
    env=None,
):
    """A candidate whose feasibility comes from the real C5 evaluator."""

    built = requirement(
        name=name,
        vram_bytes=vram_bytes,
        ram_bytes=ram_bytes,
        installed=installed,
    )

    feasibility = evaluate_capacity_feasibility(
        requirement=built,
        envelope=env or envelope(),
        storage_characterization=(
            characterization()
        ),
    )

    return SelectionCandidate(
        candidate_id=name,
        requirement=built,
        feasibility=feasibility,
        evaluation_id=evaluation_id,
    )


def provider_result(*ranked, available=True, reason=None):
    """A provider response ranking the named candidates in order."""

    return ModelEvaluationResult(
        schema_version=(
            MODEL_EVALUATION_SCHEMA_VERSION
        ),
        provider="llmfit",
        available=available,
        reason=reason,
        evidence=tuple(
            ModelEvaluationEvidence(
                candidate_id=name,
                provider="llmfit",
                usable=True,
                rank=rank,
                overall_score=100.0 - rank,
                fit_level="Perfect",
                recommended_quantization="AWQ-4bit",
            )
            for rank, name in enumerate(ranked)
        ),
    )


class FakeProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate(self, *, candidates, envelope, config=None):
        self.calls.append(
            {
                "candidates": [
                    entry.candidate_id
                    for entry in candidates
                ],
                "envelope": envelope,
            }
        )

        return self.result


class EligibilityTierTests(unittest.TestCase):
    def test_compatible_preferred_over_conditional(self):
        env = envelope()

        # Unresolved RAM makes this one merely conditional.
        conditional = candidate(
            name="conditional-model",
            vram_bytes=8 * GIB,
            ram_bytes=None,
            env=env,
        )
        compatible = candidate(
            name="compatible-model",
            vram_bytes=20 * GIB,
            env=env,
        )

        self.assertEqual(
            conditional.feasibility.verdict,
            VERDICT_CONDITIONALLY_COMPATIBLE,
        )
        self.assertEqual(
            compatible.feasibility.verdict,
            VERDICT_COMPATIBLE,
        )

        # The conditional candidate is listed first and would win the
        # fallback on utilization, so only tiering can decide this.
        result = select_model(
            candidates=[conditional, compatible],
            envelope=env,
        )

        self.assertEqual(
            result.selected_candidate_id,
            "compatible-model",
        )
        self.assertEqual(
            result.eligibility_tier,
            TIER_COMPATIBLE,
        )
        self.assertEqual(
            result.considered_count,
            1,
        )

    def test_conditional_considered_only_without_compatible(self):
        env = envelope()

        conditional = candidate(
            name="conditional-model",
            vram_bytes=8 * GIB,
            ram_bytes=None,
            env=env,
        )

        result = select_model(
            candidates=[conditional],
            envelope=env,
        )

        self.assertEqual(
            result.status,
            STATUS_SELECTED,
        )
        self.assertEqual(
            result.selected_candidate_id,
            "conditional-model",
        )
        self.assertEqual(
            result.eligibility_tier,
            TIER_CONDITIONAL,
        )

    def test_unsupported_candidate_is_never_selected(self):
        env = envelope()

        too_large = candidate(
            name="too-large",
            vram_bytes=31 * GIB,
            env=env,
        )

        self.assertEqual(
            too_large.feasibility.verdict,
            VERDICT_UNSUPPORTED,
        )

        result = select_model(
            candidates=[too_large],
            envelope=env,
        )

        self.assertEqual(
            result.status,
            STATUS_NO_SELECTION,
        )
        self.assertIsNone(
            result.selected_candidate_id
        )
        self.assertEqual(
            result.excluded_unsupported_count,
            1,
        )

    def test_provider_cannot_override_unsupported(self):
        env = envelope()

        too_large = candidate(
            name="too-large",
            vram_bytes=31 * GIB,
            env=env,
        )
        fits = candidate(
            name="fits",
            vram_bytes=10 * GIB,
            env=env,
        )

        # The provider ranks the infeasible candidate first.
        provider = FakeProvider(
            provider_result("too-large", "fits")
        )

        result = select_model(
            candidates=[too_large, fits],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertEqual(
            result.selected_candidate_id,
            "fits",
        )

        # The infeasible candidate was never even offered to it.
        self.assertEqual(
            provider.calls[0]["candidates"],
            ["fits"],
        )


class ProviderSelectionTests(unittest.TestCase):
    def test_provider_evidence_selects_one_candidate(self):
        env = envelope()

        first = candidate(
            name="model-a",
            vram_bytes=10 * GIB,
            env=env,
        )
        second = candidate(
            name="model-b",
            vram_bytes=20 * GIB,
            env=env,
        )

        # Provider prefers model-a even though model-b has the higher
        # safe-fit utilization, so only provider ordering explains it.
        provider = FakeProvider(
            provider_result("model-a", "model-b")
        )

        result = select_model(
            candidates=[first, second],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertEqual(
            result.status,
            STATUS_SELECTED,
        )
        self.assertEqual(
            result.selected_candidate_id,
            "model-a",
        )
        self.assertEqual(
            result.selection_provider,
            "llmfit",
        )
        self.assertIsNotNone(result.evidence)
        self.assertEqual(
            result.evidence.rank,
            0,
        )
        self.assertEqual(
            result.evidence.recommended_quantization,
            "AWQ-4bit",
        )
        self.assertIsNone(
            result.fallback_utilization
        )

    def test_provider_receives_the_platform_envelope(self):
        env = envelope()

        provider = FakeProvider(
            provider_result("model-a")
        )

        select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                )
            ],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertIs(
            provider.calls[0]["envelope"],
            env,
        )

    def test_unmatched_candidate_still_participates_in_fallback(self):
        env = envelope()

        # Provider knows nothing about either candidate.
        provider = FakeProvider(
            ModelEvaluationResult(
                schema_version=(
                    MODEL_EVALUATION_SCHEMA_VERSION
                ),
                provider="llmfit",
                available=True,
                evidence=(
                    ModelEvaluationEvidence(
                        candidate_id="model-a",
                        provider="llmfit",
                        usable=False,
                        notes=("no match",),
                    ),
                ),
            )
        )

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                ),
                candidate(
                    name="model-b",
                    vram_bytes=20 * GIB,
                    env=env,
                ),
            ],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertEqual(
            result.selection_provider,
            PROVIDER_FALLBACK,
        )
        self.assertEqual(
            result.selected_candidate_id,
            "model-b",
        )
        self.assertIn(
            "usable llmfit evidence",
            result.reason,
        )


class FallbackTests(unittest.TestCase):
    def test_provider_failure_triggers_fallback(self):
        env = envelope()

        provider = FakeProvider(
            unavailable(
                "llmfit",
                "llmfit exited 1: boom",
            )
        )

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                ),
                candidate(
                    name="model-b",
                    vram_bytes=20 * GIB,
                    env=env,
                ),
            ],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertEqual(
            result.status,
            STATUS_SELECTED,
        )
        self.assertEqual(
            result.selection_provider,
            PROVIDER_FALLBACK,
        )
        self.assertIn("boom", result.reason)

    def test_no_provider_uses_fallback(self):
        env = envelope()

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                )
            ],
            envelope=env,
        )

        self.assertEqual(
            result.selection_provider,
            PROVIDER_FALLBACK,
        )
        self.assertIn(
            "no evaluation provider",
            result.reason,
        )

    def test_fallback_chooses_highest_utilization_within_one(self):
        env = envelope()

        candidates = [
            candidate(
                name="small",
                vram_bytes=5 * GIB,
                env=env,
            ),
            candidate(
                name="largest-fitting",
                vram_bytes=28 * GIB,
                env=env,
            ),
            candidate(
                name="medium",
                vram_bytes=15 * GIB,
                env=env,
            ),
        ]

        result = select_model(
            candidates=candidates,
            envelope=env,
        )

        self.assertEqual(
            result.selected_candidate_id,
            "largest-fitting",
        )
        self.assertAlmostEqual(
            result.fallback_utilization,
            (28 * GIB) / SAFE_VRAM,
            places=9,
        )
        self.assertLessEqual(
            result.fallback_utilization,
            1.0,
        )

    def test_fallback_tie_preserves_input_order(self):
        env = envelope()

        first = candidate(
            name="first",
            vram_bytes=12 * GIB,
            env=env,
        )
        second = candidate(
            name="second",
            vram_bytes=12 * GIB,
            env=env,
        )

        forward = select_model(
            candidates=[first, second],
            envelope=env,
        )
        reversed_order = select_model(
            candidates=[second, first],
            envelope=env,
        )

        self.assertEqual(
            forward.selected_candidate_id,
            "first",
        )
        self.assertEqual(
            reversed_order.selected_candidate_id,
            "second",
        )

    def test_no_resolvable_evidence_yields_no_selection(self):
        env = envelope()

        # Conditional because primary memory is unresolved, so there
        # is no utilization to select on and nothing may be guessed.
        unresolved = candidate(
            name="unresolved-memory",
            vram_bytes=None,
            env=env,
        )

        self.assertEqual(
            unresolved.feasibility.verdict,
            VERDICT_CONDITIONALLY_COMPATIBLE,
        )

        result = select_model(
            candidates=[unresolved],
            envelope=env,
        )

        self.assertEqual(
            result.status,
            STATUS_NO_SELECTION,
        )
        self.assertIsNone(
            result.selected_candidate_id
        )
        self.assertEqual(
            result.selection_provider,
            PROVIDER_NONE,
        )
        self.assertIn(
            "no eligible candidate has a resolved",
            result.reason,
        )

    def test_empty_candidate_set_yields_no_selection(self):
        result = select_model(
            candidates=[],
            envelope=envelope(),
        )

        self.assertEqual(
            result.status,
            STATUS_NO_SELECTION,
        )
        self.assertIsNone(
            result.eligibility_tier
        )

    def test_fallback_does_not_redo_feasibility(self):
        # The utilization used is exactly the figure C5 computed.
        env = envelope()

        only = candidate(
            name="model-a",
            vram_bytes=18 * GIB,
            env=env,
        )

        result = select_model(
            candidates=[only],
            envelope=env,
        )

        check = only.feasibility.check(
            "primary_inference_memory"
        )

        self.assertEqual(
            result.fallback_utilization,
            check.utilization,
        )


class SuppliedEvaluationTests(unittest.TestCase):
    """A caller may supply an already-obtained provider response.

    This exists so a caller needing a second decision over a subset of
    the same candidates gets the same policy and the same evidence,
    rather than a second ranking rule or a second provider invocation
    that could answer differently.
    """

    def test_supplied_evaluation_skips_the_provider(self):
        env = envelope()

        provider = FakeProvider(
            provider_result("model-a")
        )

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                ),
                candidate(
                    name="model-b",
                    vram_bytes=20 * GIB,
                    env=env,
                ),
            ],
            envelope=env,
            evaluation_provider=provider,
            evaluation=provider_result("model-b"),
        )

        # The supplied evidence decided it, and the provider was
        # never consulted.
        self.assertEqual(
            result.selected_candidate_id,
            "model-b",
        )
        self.assertEqual(provider.calls, [])

    def test_the_evaluation_used_is_returned(self):
        env = envelope()

        provider = FakeProvider(
            provider_result("model-a")
        )

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                )
            ],
            envelope=env,
            evaluation_provider=provider,
        )

        self.assertIs(
            result.evaluation,
            provider.result,
        )

    def test_a_subset_decision_reuses_one_evaluation(self):
        env = envelope()

        candidates = [
            candidate(
                name="model-a",
                vram_bytes=20 * GIB,
                env=env,
            ),
            candidate(
                name="model-b",
                vram_bytes=10 * GIB,
                env=env,
            ),
            candidate(
                name="model-c",
                vram_bytes=5 * GIB,
                env=env,
            ),
        ]

        provider = FakeProvider(
            provider_result(
                "model-a",
                "model-c",
                "model-b",
            )
        )

        first = select_model(
            candidates=candidates,
            envelope=env,
            evaluation_provider=provider,
        )

        second = select_model(
            candidates=candidates[1:],
            envelope=env,
            evaluation=first.evaluation,
        )

        self.assertEqual(
            first.selected_candidate_id,
            "model-a",
        )

        # Provider ranking, not safe-fit ordering, decided the subset.
        self.assertEqual(
            second.selected_candidate_id,
            "model-c",
        )
        self.assertEqual(
            second.selection_provider,
            "llmfit",
        )
        self.assertEqual(len(provider.calls), 1)

    def test_supplied_unavailable_evaluation_falls_back(self):
        env = envelope()

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                ),
                candidate(
                    name="model-b",
                    vram_bytes=20 * GIB,
                    env=env,
                ),
            ],
            envelope=env,
            evaluation=unavailable(
                "llmfit",
                "executable missing",
            ),
        )

        self.assertEqual(
            result.selection_provider,
            PROVIDER_FALLBACK,
        )
        self.assertEqual(
            result.selected_candidate_id,
            "model-b",
        )

    def test_the_evaluation_stays_out_of_the_serialized_result(self):
        env = envelope()

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                )
            ],
            envelope=env,
            evaluation_provider=FakeProvider(
                provider_result("model-a")
            ),
        )

        self.assertIsNotNone(result.evaluation)
        self.assertNotIn(
            "evaluation",
            result.to_dict(),
        )


class PortabilityTests(unittest.TestCase):
    def test_selector_core_has_no_vendor_logic(self):
        import inspect

        import core.model_selection as module

        source = inspect.getsource(module).lower()

        for forbidden in (
            "nvidia",
            "cuda",
            "rocm",
            "metal",
            "mlx",
            "intel",
            "dedicated_vram",
        ):
            self.assertNotIn(
                forbidden,
                source,
                msg=forbidden,
            )

    def test_selector_core_has_no_provider_parsing(self):
        import core.model_selection as module

        source = inspect_source(module)

        for forbidden in (
            "json.loads",
            "subprocess",
            "llmfit",
            "score_components",
            "best_quant",
        ):
            self.assertNotIn(
                forbidden,
                source,
                msg=forbidden,
            )

    def test_selector_core_imports_no_adapter(self):
        import core.model_selection as module

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

        for name in imported:
            self.assertFalse(
                name.startswith("adapters."),
                msg=name,
            )

    def test_no_acquisition_inference_sonar_or_reservation(self):
        import core.model_selection as module

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

        forbidden_modules = {
            "core.control",
            "core.model_transfer",
            "core.storage_characterization",
            "core.storage_probe",
            "core.storage_capacity_calibration",
            "core.resource_manager",
            "core.resource_reservations",
            "core.lifecycle",
            "core.model_catalog",
        }

        self.assertEqual(
            imported & forbidden_modules,
            set(),
        )


def inspect_source(module):
    import inspect

    return inspect.getsource(module)


class ContractTests(unittest.TestCase):
    def test_result_shape_and_serialization(self):
        env = envelope()

        provider = FakeProvider(
            provider_result("model-a")
        )

        result = select_model(
            candidates=[
                candidate(
                    name="model-a",
                    vram_bytes=10 * GIB,
                    env=env,
                )
            ],
            envelope=env,
            evaluation_provider=provider,
        )

        restored = json.loads(
            json.dumps(result.to_dict())
        )

        self.assertEqual(
            restored["schema_version"],
            MODEL_SELECTION_SCHEMA_VERSION,
        )
        self.assertEqual(
            restored["status"],
            STATUS_SELECTED,
        )
        self.assertEqual(
            restored["selected_candidate_id"],
            "model-a",
        )
        self.assertEqual(
            restored["evidence"]["provider"],
            "llmfit",
        )

    def test_selects_exactly_one_candidate(self):
        env = envelope()

        result = select_model(
            candidates=[
                candidate(
                    name=f"model-{index}",
                    vram_bytes=(5 + index) * GIB,
                    env=env,
                )
                for index in range(5)
            ],
            envelope=env,
        )

        self.assertEqual(
            result.status,
            STATUS_SELECTED,
        )
        self.assertIsInstance(
            result.selected_candidate_id,
            str,
        )

    def test_wrong_candidate_type_is_rejected(self):
        with self.assertRaises(TypeError):
            select_model(
                candidates=[{"id": "x"}],
                envelope=envelope(),
            )


class NoCallerMigrationTests(unittest.TestCase):
    def test_no_production_caller_imports_the_selector(self):
        import inspect

        import core.control as control
        import core.deployment as deployment
        import platform_api.server as server

        for module in (
            control,
            deployment,
            server,
        ):
            source = inspect.getsource(module)

            self.assertNotIn(
                "model_selection",
                source,
                msg=module.__name__,
            )
            self.assertNotIn(
                "select_model",
                source,
                msg=module.__name__,
            )


if __name__ == "__main__":
    unittest.main()
