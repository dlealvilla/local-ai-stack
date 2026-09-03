"""Tests for structured model feasibility against characterized capacity.

Envelopes come from the real C1/C2 normalization over a real
resource-safety calculation, and requirements from the real C4 builder,
so the comparison is exercised against figures the platform actually
produces rather than hand-made dataclasses.

The storage cases carry the load here: exceeding a proven lower bound is
an absence of evidence, not evidence of absence, and conflating the two
would wrongly reject candidates a bigger probe would have accepted.
"""

from __future__ import annotations

import json
import unittest

from core.capacity_contracts import (
    build_capacity_envelope,
)
from core.capacity_feasibility import (
    CAPACITY_FEASIBILITY_SCHEMA_VERSION,
    CHECK_FAIL,
    CHECK_PASS,
    CHECK_UNRESOLVED,
    RESOURCE_PRIMARY_INFERENCE_MEMORY,
    RESOURCE_RAM,
    RESOURCE_RUNTIME,
    RESOURCE_STORAGE,
    VERDICT_COMPATIBLE,
    VERDICT_CONDITIONALLY_COMPATIBLE,
    VERDICT_UNSUPPORTED,
    evaluate_capacity_feasibility,
)
from core.model_requirement import build_model_requirement
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

# Produced by the existing resource-safety implementation for the
# observation below.
SAFE_VRAM = 30_267_880_244
SAFE_RAM = 583_081_127_117

QWEN_ARTIFACT_BYTES = 6_114_568_235
QWEN_ACQUISITION_PEAK = 7_188_310_059


def snapshot(*, accelerators=None):
    if accelerators is None:
        accelerators = [
            {
                "index": 0,
                "vendor": "nvidia",
                "name": "NVIDIA GeForce RTX 5090",
                "memory": {
                    "total_bytes": HOST_VRAM_TOTAL,
                    "used_bytes": (
                        HOST_VRAM_TOTAL - HOST_VRAM_FREE
                    ),
                    "free_bytes": HOST_VRAM_FREE,
                },
            },
        ]

    return {
        "schema_version": 1,
        "generated_at": "2026-09-03T11:00:00+00:00",
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
        "accelerators": accelerators,
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


def envelope(
    *,
    accelerators=None,
    with_reservations=True,
    reserved_vram_bytes=0,
):
    snap = snapshot(accelerators=accelerators)
    safety = build_resource_safety(
        build_resource_capacity(snap)
    )

    reservation_snapshot = None

    if with_reservations:
        ledger = ResourceReservationLedger(
            reservation_capacities_from_resource_safety(
                safety
            )
        )

        if reserved_vram_bytes:
            ledger.reserve(
                "existing-workload",
                {
                    "accelerator:0:memory": (
                        reserved_vram_bytes
                    ),
                },
            )

        reservation_snapshot = (
            ledger.snapshot().to_dict()
        )

    return build_capacity_envelope(
        capacity_snapshot=snap,
        resource_safety=safety,
        reservation_snapshot=reservation_snapshot,
    )


def characterization(
    *,
    lower_bound=None,
    upper_bound=None,
):
    """A storage characterization result in HOST-mode shape."""

    return {
        "schema_version": 1,
        "mode": "host",
        "verified_lower_bound_bytes": lower_bound,
        "capacity_failure_upper_bound_bytes": (
            upper_bound
        ),
        "conservative_usable_bytes": lower_bound,
    }


def requirement(
    *,
    vram_bytes=None,
    ram_bytes=None,
    installed_bytes=None,
    acquisition_peak_bytes=QWEN_ACQUISITION_PEAK,
    runtime_status="compatible",
    vram_confidence=None,
):
    model = {
        "schema_version": 1,
        "name": "Qwen/Qwen3-8B-AWQ",
        "architecture": "Qwen3ForCausalLM",
        "quantization": "awq",
        "context_length": 40960,
        "source": {
            "provider": "huggingface",
            "revision": "4da05a8e",
        },
        "size": {
            "download_bytes": QWEN_ARTIFACT_BYTES,
            "installed_bytes": installed_bytes,
        },
        "format": {"weights": "safetensors"},
        "runtime": {"supported": ["vllm"]},
        "requirements": {
            "ram_bytes": ram_bytes,
            "vram_bytes": vram_bytes,
            "unified_memory_bytes": None,
        },
    }

    install_storage = None

    if acquisition_peak_bytes is not None:
        install_storage = {
            "schema_version": 1,
            "operation": "install",
            "resolved": True,
            "artifact": {
                "resolved": True,
                "bytes": QWEN_ARTIFACT_BYTES,
                "confidence": "high",
            },
            "overhead_bytes": (
                acquisition_peak_bytes
                - QWEN_ARTIFACT_BYTES
            ),
            "peak_additional_bytes": (
                acquisition_peak_bytes
            ),
            "confidence": "high",
        }

    compatibility = None

    if runtime_status is not None:
        compatibility = dict(model)
        compatibility["compatibility"] = {
            "status": runtime_status,
            "confidence": "medium",
            "reasons": [],
        }

    built = build_model_requirement(
        model=model,
        install_storage=install_storage,
        compatibility=compatibility,
    )

    if vram_confidence is None:
        return built

    # Exercise a low-confidence known figure without inventing an
    # estimator: substitute the confidence the estimator would report.
    from dataclasses import replace

    return replace(
        built,
        primary_inference_memory=replace(
            built.primary_inference_memory,
            confidence=vram_confidence,
        ),
    )


class PrimaryInferenceMemoryTests(unittest.TestCase):
    def test_vram_that_fits_passes(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=20 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        check = result.check(
            RESOURCE_PRIMARY_INFERENCE_MEMORY
        )

        self.assertEqual(check.status, CHECK_PASS)
        self.assertEqual(
            check.pool_id,
            "accelerator:0:memory",
        )
        self.assertEqual(
            check.available_bytes,
            SAFE_VRAM,
        )

    def test_vram_exceeding_safe_capacity_is_unsupported(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=31 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        self.assertEqual(
            result.check(
                RESOURCE_PRIMARY_INFERENCE_MEMORY
            ).status,
            CHECK_FAIL,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )
        self.assertEqual(
            result.limiting_factor,
            RESOURCE_PRIMARY_INFERENCE_MEMORY,
        )

    def test_safe_vram_is_used_not_physical_vram(self):
        # 31 GiB fits inside both 34.21 GB physical and 33.69 GB free,
        # but not inside the 30.27 GB safe envelope. Comparing against
        # either raw figure would wrongly pass.
        required = 31 * GIB

        self.assertLess(required, HOST_VRAM_TOTAL)
        self.assertLess(required, HOST_VRAM_FREE)
        self.assertGreater(required, SAFE_VRAM)

        check = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=required,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        ).check(RESOURCE_PRIMARY_INFERENCE_MEMORY)

        self.assertEqual(check.status, CHECK_FAIL)
        self.assertEqual(
            check.available_bytes,
            SAFE_VRAM,
        )
        self.assertNotEqual(
            check.available_bytes,
            HOST_VRAM_TOTAL,
        )
        self.assertNotEqual(
            check.available_bytes,
            HOST_VRAM_FREE,
        )

    def test_remaining_headroom_is_correct(self):
        required = 20 * GIB

        check = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=required,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        ).check(RESOURCE_PRIMARY_INFERENCE_MEMORY)

        self.assertEqual(
            check.remaining_bytes,
            SAFE_VRAM - required,
        )
        self.assertEqual(
            check.remaining_bytes,
            8_793_043_764,
        )

    def test_utilization_ratio_is_correct(self):
        required = 20 * GIB

        check = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=required,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        ).check(RESOURCE_PRIMARY_INFERENCE_MEMORY)

        self.assertAlmostEqual(
            check.utilization,
            required / SAFE_VRAM,
            places=9,
        )
        self.assertLess(check.utilization, 1.0)

    def test_low_confidence_known_value_remains_usable(self):
        # The approved rule: a known numeric value is usable, and only
        # a missing value is uncertainty. Confidence is preserved, not
        # converted into a conditional verdict.
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=20 * GIB,
                ram_bytes=32 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
                vram_confidence="low",
            ),
            envelope=envelope(),
        )

        check = result.check(
            RESOURCE_PRIMARY_INFERENCE_MEMORY
        )

        self.assertEqual(check.status, CHECK_PASS)
        self.assertEqual(check.confidence, "low")
        self.assertEqual(
            result.verdict,
            VERDICT_COMPATIBLE,
        )

    def test_existing_reservation_reduces_available_bytes(self):
        reserved = 8 * GIB

        check = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=25 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(
                reserved_vram_bytes=reserved
            ),
        ).check(RESOURCE_PRIMARY_INFERENCE_MEMORY)

        # Headroom is not subtracted twice: the ledger figure already
        # accounts for the reservation.
        self.assertEqual(
            check.available_bytes,
            SAFE_VRAM - reserved,
        )
        self.assertEqual(check.status, CHECK_FAIL)

    def test_missing_pool_is_a_definite_failure(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(accelerators=[]),
        )

        check = result.check(
            RESOURCE_PRIMARY_INFERENCE_MEMORY
        )

        self.assertEqual(check.status, CHECK_FAIL)
        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )

    def test_capacity_is_not_summed_across_devices(self):
        accelerators = [
            {
                "index": index,
                "vendor": "nvidia",
                "name": f"GPU {index}",
                "memory": {
                    "total_bytes": 16 * GIB,
                    "used_bytes": 0,
                    "free_bytes": 16 * GIB,
                },
            }
            for index in (0, 1)
        ]

        check = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=24 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(
                accelerators=accelerators
            ),
        ).check(RESOURCE_PRIMARY_INFERENCE_MEMORY)

        self.assertEqual(check.status, CHECK_FAIL)
        self.assertLess(
            check.available_bytes,
            16 * GIB,
        )


class RamTests(unittest.TestCase):
    def test_known_ram_that_fits_passes(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                ram_bytes=32 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        check = result.check(RESOURCE_RAM)

        self.assertEqual(check.status, CHECK_PASS)
        self.assertEqual(
            check.available_bytes,
            SAFE_RAM,
        )
        self.assertEqual(
            check.pool_id,
            "memory:system_ram",
        )
        self.assertEqual(
            result.verdict,
            VERDICT_COMPATIBLE,
        )

    def test_known_ram_that_exceeds_is_unsupported(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                ram_bytes=900 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        self.assertEqual(
            result.check(RESOURCE_RAM).status,
            CHECK_FAIL,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )
        self.assertEqual(
            result.limiting_factor,
            RESOURCE_RAM,
        )

    def test_unresolved_ram_yields_conditional(self):
        # The current real state: no RAM estimator exists.
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                ram_bytes=None,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        check = result.check(RESOURCE_RAM)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )
        self.assertIsNone(check.required_bytes)
        self.assertNotEqual(check.status, CHECK_PASS)
        self.assertEqual(
            result.verdict,
            VERDICT_CONDITIONALLY_COMPATIBLE,
        )
        self.assertIn(
            RESOURCE_RAM,
            result.unresolved_resources,
        )


class StorageBoundTests(unittest.TestCase):
    """Absence of evidence is not evidence of absence."""

    def absent_model(self, **kwargs):
        return requirement(
            vram_bytes=8 * GIB,
            ram_bytes=16 * GIB,
            installed_bytes=None,
            **kwargs,
        )

    def test_requirement_within_lower_bound_passes(self):
        result = evaluate_capacity_feasibility(
            requirement=self.absent_model(),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=64 * GIB,
            ),
        )

        check = result.check(RESOURCE_STORAGE)

        self.assertEqual(check.status, CHECK_PASS)
        self.assertEqual(
            check.required_bytes,
            QWEN_ACQUISITION_PEAK,
        )
        self.assertEqual(
            check.available_bytes,
            64 * GIB,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_COMPATIBLE,
        )

    def test_requirement_above_lower_bound_is_unresolved(self):
        # Proven >= 64 GiB, candidate needs 80 GiB, no failure bound.
        # This must NOT be unsupported: a larger probe might succeed.
        result = evaluate_capacity_feasibility(
            requirement=self.absent_model(
                acquisition_peak_bytes=80 * GIB,
            ),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=64 * GIB,
            ),
        )

        check = result.check(RESOURCE_STORAGE)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )
        self.assertNotEqual(check.status, CHECK_FAIL)
        self.assertEqual(
            check.required_bytes,
            80 * GIB,
        )
        self.assertEqual(
            check.available_bytes,
            64 * GIB,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_CONDITIONALLY_COMPATIBLE,
        )
        self.assertIn(
            "no capacity failure proves it cannot fit",
            check.reason,
        )

    def test_conclusive_capacity_failure_is_unsupported(self):
        # Proven >= 32 GiB and proven to fail at 48 GiB; a 64 GiB
        # requirement is at or above the failure bound.
        result = evaluate_capacity_feasibility(
            requirement=self.absent_model(
                acquisition_peak_bytes=64 * GIB,
            ),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=32 * GIB,
                upper_bound=48 * GIB,
            ),
        )

        check = result.check(RESOURCE_STORAGE)

        self.assertEqual(check.status, CHECK_FAIL)
        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )
        self.assertEqual(
            result.limiting_factor,
            RESOURCE_STORAGE,
        )

    def test_between_the_bounds_is_unresolved(self):
        # Proven >= 32 GiB, failure at 48 GiB, requirement 40 GiB:
        # neither proven possible nor proven impossible.
        check = evaluate_capacity_feasibility(
            requirement=self.absent_model(
                acquisition_peak_bytes=40 * GIB,
            ),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=32 * GIB,
                upper_bound=48 * GIB,
            ),
        ).check(RESOURCE_STORAGE)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )

    def test_no_characterization_is_unresolved(self):
        check = evaluate_capacity_feasibility(
            requirement=self.absent_model(),
            envelope=envelope(),
        ).check(RESOURCE_STORAGE)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )
        self.assertIn(
            "no storage characterization",
            check.reason,
        )

    def test_unresolved_characterization_is_unresolved(self):
        # A host characterization that never got a successful probe.
        check = evaluate_capacity_feasibility(
            requirement=self.absent_model(),
            envelope=envelope(),
            storage_characterization=characterization(),
        ).check(RESOURCE_STORAGE)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )

    def test_installed_model_needs_no_acquisition_storage(self):
        # A characterization that could never fit an acquisition is
        # irrelevant once the artifact is on disk.
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                ram_bytes=16 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=1024,
                upper_bound=2048,
            ),
        )

        check = result.check(RESOURCE_STORAGE)

        self.assertEqual(check.status, CHECK_PASS)
        self.assertIsNone(check.required_bytes)
        self.assertIn(
            "already installed",
            check.reason,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_COMPATIBLE,
        )

    def test_reported_free_space_is_never_consulted(self):
        # The snapshot advertises ~668 TiB free. With no proven
        # evidence the verdict must still be unresolved.
        built = envelope()

        result = evaluate_capacity_feasibility(
            requirement=self.absent_model(),
            envelope=built,
            storage_characterization=characterization(),
        )

        check = result.check(RESOURCE_STORAGE)

        self.assertEqual(
            check.status,
            CHECK_UNRESOLVED,
        )
        self.assertIsNone(check.available_bytes)


class RuntimeTests(unittest.TestCase):
    def test_incompatible_runtime_is_unsupported(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                ram_bytes=16 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
                runtime_status="unsupported",
            ),
            envelope=envelope(),
        )

        self.assertEqual(
            result.check(RESOURCE_RUNTIME).status,
            CHECK_FAIL,
        )
        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )
        self.assertEqual(
            result.limiting_factor,
            RESOURCE_RUNTIME,
        )

    def test_compatibility_is_not_re_evaluated(self):
        import inspect

        import core.capacity_feasibility as module

        source = inspect.getsource(module)

        for forbidden in (
            "evaluate_model_compatibility",
            "_candidate_runtimes",
            "STATIC_GPU_WEIGHT_BUDGET",
            "vram_total_gb",
            "inspect_hardware",
        ):
            self.assertNotIn(forbidden, source)


class VerdictAggregationTests(unittest.TestCase):
    def test_hard_failure_dominates_unresolved_dimensions(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=31 * GIB,
                ram_bytes=None,
                installed_bytes=None,
            ),
            envelope=envelope(),
            storage_characterization=characterization(),
        )

        self.assertEqual(
            result.verdict,
            VERDICT_UNSUPPORTED,
        )
        self.assertEqual(
            result.limiting_factor,
            RESOURCE_PRIMARY_INFERENCE_MEMORY,
        )

        # The unknowns are still reported, not hidden.
        self.assertIn(
            RESOURCE_RAM,
            result.unresolved_resources,
        )
        self.assertIn(
            RESOURCE_STORAGE,
            result.unresolved_resources,
        )

    def test_all_resolved_and_passing_is_compatible(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=20 * GIB,
                ram_bytes=32 * GIB,
                installed_bytes=None,
            ),
            envelope=envelope(),
            storage_characterization=characterization(
                lower_bound=64 * GIB,
            ),
        )

        self.assertEqual(
            result.verdict,
            VERDICT_COMPATIBLE,
        )
        self.assertIsNone(result.limiting_factor)
        self.assertEqual(
            result.unresolved_resources,
            (),
        )

        for check in result.checks:
            self.assertEqual(
                check.status,
                CHECK_PASS,
                msg=check.resource,
            )

    def test_limiting_factor_is_deterministic(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=64 * GIB,
                ram_bytes=900 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
                runtime_status="unsupported",
            ),
            envelope=envelope(),
        )

        self.assertEqual(
            result.limiting_factor,
            RESOURCE_RUNTIME,
        )

    def test_checks_are_reported_in_a_fixed_order(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        self.assertEqual(
            [check.resource for check in result.checks],
            [
                RESOURCE_RUNTIME,
                RESOURCE_PRIMARY_INFERENCE_MEMORY,
                RESOURCE_RAM,
                RESOURCE_STORAGE,
            ],
        )


class BoundaryTests(unittest.TestCase):
    def test_no_ranking_or_selection_behavior_exists(self):
        # Structural, not prose-based: one entry point taking a single
        # requirement, and no score or rank on either contract.
        import inspect

        import core.capacity_feasibility as module

        entry_points = [
            name
            for name in dir(module)
            if name.startswith("evaluate")
        ]

        self.assertEqual(
            entry_points,
            ["evaluate_capacity_feasibility"],
        )

        signature = inspect.signature(
            module.evaluate_capacity_feasibility
        )

        self.assertEqual(
            sorted(signature.parameters),
            [
                "envelope",
                "requirement",
                "storage_characterization",
            ],
        )

        from core.capacity_feasibility import (
            FeasibilityResult,
            ResourceCheck,
        )

        for contract in (
            FeasibilityResult,
            ResourceCheck,
        ):
            fields = set(
                contract.__dataclass_fields__
            )

            for forbidden in (
                "score",
                "rank",
                "utility",
                "priority",
                "preferred",
            ):
                self.assertNotIn(forbidden, fields)

    def test_no_probing_estimating_or_detection_is_imported(self):
        import core.capacity_feasibility as module

        forbidden_modules = {
            "core.storage_probe",
            "core.storage_sonar",
            "core.storage_characterization",
            "core.storage_capacity_calibration",
            "core.storage_capacity_cache",
            "core.requirements",
            "core.model_storage_requirements",
            "core.model_feasibility",
            "core.model_compatibility",
            "core.model_catalog",
            "core.model_inventory",
            "core.resource_safety",
            "core.hardware",
            "core.control",
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

    def test_result_shape_and_serialization(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=20 * GIB,
                ram_bytes=32 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        restored = json.loads(
            json.dumps(result.to_dict())
        )

        self.assertEqual(
            restored["schema_version"],
            CAPACITY_FEASIBILITY_SCHEMA_VERSION,
        )
        self.assertEqual(
            restored["verdict"],
            VERDICT_COMPATIBLE,
        )
        self.assertEqual(len(restored["checks"]), 4)
        self.assertEqual(
            restored["model_id"],
            "Qwen/Qwen3-8B-AWQ",
        )
        self.assertEqual(
            restored["quantization"],
            "awq",
        )

    def test_verdict_vocabulary_is_exactly_three_values(self):
        self.assertEqual(
            {
                VERDICT_COMPATIBLE,
                VERDICT_CONDITIONALLY_COMPATIBLE,
                VERDICT_UNSUPPORTED,
            },
            {
                "compatible",
                "conditionally_compatible",
                "unsupported",
            },
        )

    def test_result_is_immutable(self):
        result = evaluate_capacity_feasibility(
            requirement=requirement(
                vram_bytes=8 * GIB,
                installed_bytes=QWEN_ARTIFACT_BYTES,
            ),
            envelope=envelope(),
        )

        with self.assertRaises(Exception):
            result.verdict = VERDICT_COMPATIBLE

        with self.assertRaises(Exception):
            result.checks[0].status = CHECK_PASS

    def test_wrong_input_types_are_rejected(self):
        with self.assertRaises(TypeError):
            evaluate_capacity_feasibility(
                requirement={},
                envelope=envelope(),
            )

        with self.assertRaises(TypeError):
            evaluate_capacity_feasibility(
                requirement=requirement(),
                envelope={},
            )

        with self.assertRaises(TypeError):
            evaluate_capacity_feasibility(
                requirement=requirement(),
                envelope=envelope(),
                storage_characterization=[],
            )


class NoCallerMigrationTests(unittest.TestCase):
    def test_no_production_caller_imports_the_layer(self):
        import inspect

        import core.control as control
        import core.deployment as deployment
        import core.model_feasibility as model_feasibility
        import core.storage_commit_admission as admission
        import platform_api.server as server

        for module in (
            control,
            deployment,
            model_feasibility,
            admission,
            server,
        ):
            source = inspect.getsource(module)

            self.assertNotIn(
                "capacity_feasibility",
                source,
                msg=module.__name__,
            )
            self.assertNotIn(
                "evaluate_capacity_feasibility",
                source,
                msg=module.__name__,
            )


if __name__ == "__main__":
    unittest.main()
