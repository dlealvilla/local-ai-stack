"""C4 parity tests for the normalized ModelRequirement contract.

The oracle is the existing estimators. Where an estimator is cheap and
pure it is called for real (`estimate_model_install_storage`,
`evaluate_model_compatibility`, `build_model_resource_requirements`
against a temporary weight file), so parity is asserted against what
the platform actually produces rather than against numbers restated in
the test.

Two absences are asserted deliberately: RAM has no estimator, and the
inference-memory figure is explicitly provisional. C4 must represent
both honestly rather than inventing a value.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.capacity_contracts import (
    PLATFORM_DATA_STORAGE_POOL_ID,
)
from core.model_compatibility import (
    evaluate_model_compatibility,
)
from core.model_requirement import (
    BASIS_NOT_IMPLEMENTED,
    BASIS_UNRESOLVED_MISSING_INPUT,
    BASIS_UNRESOLVED_NO_ESTIMATOR,
    DEDICATED_VRAM,
    MODEL_REQUIREMENT_SCHEMA_VERSION,
    SYSTEM_RAM,
    build_model_requirement,
)
from core.model_storage_requirements import (
    estimate_model_install_storage,
)
from core.requirements import (
    build_model_resource_requirements,
)

GIB = 1024 ** 3

# The resolved immutable Qwen/Qwen3-8B-AWQ manifest.
QWEN_ARTIFACT_BYTES = 6_114_568_235
QWEN_REVISION = "4da05a8edb55c6046cce958586c33b61da07bb79"

HOST_VRAM_TOTAL = 34_207_694_848
HOST_RAM_TOTAL = 811_121_754_112


def inventory_model(
    *,
    installed_bytes=QWEN_ARTIFACT_BYTES,
    path="/workspace/models/qwen3-8b-awq",
    revision=QWEN_REVISION,
    context_length=40960,
):
    """An inventory record in the shape list_model_inventory returns."""

    return {
        "schema_version": 1,
        "inventory_id": "qwen3-8b-awq",
        "model_id": "qwen3-8b-awq",
        "path": path,
        "source": {
            "provider": "huggingface",
            "source_model_id": "Qwen/Qwen3-8B-AWQ",
            "revision": revision,
        },
        "artifact": {
            "state": "stored",
            "disk_usage_bytes": installed_bytes,
            "weight_formats": ["safetensors"],
            "integrity": None,
        },
        "deployment": {
            "runtime": "vllm",
            "selected": True,
            "service_state": "stopped",
            "load_state": "unloaded",
        },
        "metadata": {
            "architecture": "Qwen3ForCausalLM",
            "family": "qwen3",
            "quantization": "awq",
            "context_length": context_length,
        },
        "format": {
            "weights": "safetensors",
        },
        "size": {
            "installed_bytes": installed_bytes,
            "download_bytes": installed_bytes,
        },
    }


def candidate_model(
    *,
    weights="safetensors",
    installed_bytes=None,
    download_bytes=QWEN_ARTIFACT_BYTES,
    context_length=40960,
):
    """A record in the canonical candidate shape.

    This is what `core.model_metadata.normalize_*` produces and what
    `evaluate_model_compatibility` and the storage estimators consume.
    Note `requirements` ships with every figure unset.
    """

    return {
        "schema_version": 1,
        "catalog_id": "huggingface:Qwen/Qwen3-8B-AWQ",
        "name": "Qwen/Qwen3-8B-AWQ",
        "family": "qwen3",
        "architecture": "Qwen3ForCausalLM",
        "parameters": {"count": None},
        "quantization": "awq",
        "context_length": context_length,
        "source": {
            "provider": "huggingface",
            "source_model_id": "Qwen/Qwen3-8B-AWQ",
            "revision": QWEN_REVISION,
            "license": "apache-2.0",
            "location": None,
        },
        "size": {
            "download_bytes": download_bytes,
            "installed_bytes": installed_bytes,
        },
        "format": {"weights": weights},
        "discovery": {
            "pipeline_tag": "text-generation",
            "library": "transformers",
            "downloads": 12345,
            "gated": False,
            "private": False,
            "tags": [],
        },
        "runtime": {"supported": []},
        "requirements": {
            "ram_bytes": None,
            "vram_bytes": None,
            "unified_memory_bytes": None,
        },
        "compatibility": {
            "status": "not_evaluated",
            "reasons": [],
            "recommendations": [],
        },
    }


def real_compatibility(model=None):
    """The real evaluator's output: the ENRICHED candidate record."""

    return evaluate_model_compatibility(
        model if model is not None else candidate_model(),
        linux_nvidia_hardware(),
        {},
    )


def linux_nvidia_hardware():
    return {
        "operating_system": "Linux",
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 9335 32-Core Processor",
        "cpu_cores": 128,
        "ram_total_gb": HOST_RAM_TOTAL / GIB,
        "gpus": [
            {
                "vendor": "nvidia",
                "name": (
                    "NVIDIA RTX PRO 4500 Blackwell "
                    "Server Edition"
                ),
                "vram_total_gb": HOST_VRAM_TOTAL / GIB,
                "vram_free_gb": 33_688_649_728 / GIB,
            },
        ],
    }


def real_install_storage():
    """The real estimator's output, with the shipped overhead policy.

    `model_operation_overhead_fraction = 0.10` and
    `model_operation_overhead_min_gb = 1.0` are the values
    config/defaults.toml ships and core.control passes.
    """

    return estimate_model_install_storage(
        {
            "model_id": "Qwen/Qwen3-8B-AWQ",
            "size": {
                "download_bytes": QWEN_ARTIFACT_BYTES,
            },
        },
        overhead_fraction=0.10,
        overhead_min_bytes=1 * GIB,
    )


def feasibility_with_provisional_estimate(
    weight_bytes=QWEN_ARTIFACT_BYTES,
):
    """A feasibility result carrying the real provisional estimate.

    The estimate is produced by the real code path: a temporary weight
    file is measured by `build_model_resource_requirements`, then the
    private provisional estimator is applied to that evidence. Nothing
    is hand-computed.
    """

    import core.model_feasibility as feasibility_module

    with tempfile.TemporaryDirectory() as tmp:
        weights = Path(tmp) / "model.safetensors"
        weights.write_bytes(b"\0" * 1024)

        requirements = build_model_resource_requirements(
            {
                "model_id": "qwen3-8b-awq",
                "path": tmp,
                "runtime": "vllm",
            }
        )

    # Substitute the real measured artifact size with the manifest
    # size, then let the real estimator derive the figure.
    requirements["artifact_evidence"]["weight_files"] = {
        "resolved": True,
        "bytes": weight_bytes,
        "confidence": "high",
        "method": "exact_local_weight_file_measurement",
    }

    estimate = (
        feasibility_module._provisional_memory_estimate(
            requirements
        )
    )

    return {
        "schema_version": 1,
        "model_id": "qwen3-8b-awq",
        "dimensions": {
            "memory": {
                "status": "unknown",
                "provisional_estimate": estimate,
            },
        },
        "model_resource_requirements": requirements,
    }, estimate


class StorageParityTests(unittest.TestCase):
    def setUp(self):
        self.model = inventory_model()
        self.install_storage = real_install_storage()

        self.requirement = build_model_requirement(
            model=self.model,
            install_storage=self.install_storage,
        )

    def test_acquisition_peak_matches_the_storage_estimator(self):
        storage = self.requirement.storage

        self.assertEqual(
            storage.acquisition_peak_bytes,
            self.install_storage[
                "peak_additional_bytes"
            ],
        )
        self.assertEqual(
            storage.artifact_bytes,
            self.install_storage["artifact"]["bytes"],
        )
        self.assertEqual(
            storage.overhead_bytes,
            self.install_storage["overhead_bytes"],
        )
        self.assertEqual(
            storage.confidence,
            self.install_storage["confidence"],
        )

    def test_installed_and_peak_are_distinct_concepts(self):
        storage = self.requirement.storage

        self.assertEqual(
            storage.installed_bytes,
            QWEN_ARTIFACT_BYTES,
        )

        # The transient install peak exceeds the artifact itself, so
        # the two must never be conflated.
        self.assertGreater(
            storage.acquisition_peak_bytes,
            storage.installed_bytes,
        )

    def test_target_pool_uses_the_capacity_contract_identity(self):
        self.assertEqual(
            self.requirement.storage.target_pool_id,
            PLATFORM_DATA_STORAGE_POOL_ID,
        )

    def test_missing_estimator_yields_unresolved_not_zero(self):
        requirement = build_model_requirement(
            model=self.model,
        )

        storage = requirement.storage

        self.assertIsNone(
            storage.acquisition_peak_bytes
        )
        self.assertIsNone(storage.artifact_bytes)
        self.assertEqual(
            storage.basis,
            BASIS_UNRESOLVED_MISSING_INPUT,
        )
        self.assertIn(
            "storage.acquisition_peak_bytes",
            requirement.unresolved_fields,
        )

        # Installed bytes still come from the inventory record.
        self.assertEqual(
            storage.installed_bytes,
            QWEN_ARTIFACT_BYTES,
        )

    def test_uninstalled_model_has_no_installed_bytes(self):
        model = inventory_model(installed_bytes=None)

        requirement = build_model_requirement(
            model=model,
            install_storage=self.install_storage,
        )

        self.assertIsNone(
            requirement.storage.installed_bytes
        )
        self.assertIn(
            "storage.installed_bytes",
            requirement.unresolved_fields,
        )

        # But the acquisition peak is known, which is exactly the
        # case that matters before a download.
        self.assertIsNotNone(
            requirement.storage.acquisition_peak_bytes
        )


class InferenceMemoryParityTests(unittest.TestCase):
    def setUp(self):
        (
            self.feasibility,
            self.estimate,
        ) = feasibility_with_provisional_estimate()

        self.requirement = build_model_requirement(
            model=inventory_model(),
            feasibility=self.feasibility,
        )

    def test_matches_the_provisional_estimator(self):
        memory = (
            self.requirement.primary_inference_memory
        )

        self.assertEqual(
            memory.required_bytes,
            self.estimate[
                "estimated_runtime_target_bytes"
            ],
        )
        self.assertEqual(
            memory.memory_type,
            DEDICATED_VRAM,
        )

    def test_low_confidence_is_carried_through_not_upgraded(self):
        memory = (
            self.requirement.primary_inference_memory
        )

        self.assertEqual(
            memory.confidence,
            self.estimate["confidence"],
        )
        self.assertEqual(memory.confidence, "low")
        self.assertEqual(
            memory.basis,
            "model_feasibility.provisional_estimate",
        )

    def test_estimate_is_weights_plus_the_existing_margin(self):
        # Parity with the documented provisional formula, asserted
        # against the estimator's own output rather than recomputed
        # inside the contract.
        expected = QWEN_ARTIFACT_BYTES + max(
            1 * GIB,
            int(QWEN_ARTIFACT_BYTES * 0.25),
        )

        self.assertEqual(
            self.requirement.primary_inference_memory
            .required_bytes,
            expected,
        )

    def test_unresolved_estimate_stays_unresolved(self):
        feasibility = {
            "dimensions": {
                "memory": {
                    "provisional_estimate": {
                        "resolved": False,
                        "confidence": "unresolved",
                        "estimated_runtime_target_bytes": None,
                        "reason": (
                            "Local weight artifact evidence "
                            "is unresolved."
                        ),
                    },
                },
            },
        }

        requirement = build_model_requirement(
            model=inventory_model(),
            feasibility=feasibility,
        )

        memory = (
            requirement.primary_inference_memory
        )

        self.assertIsNone(memory.required_bytes)
        self.assertFalse(memory.resolved)
        self.assertIn(
            "primary_inference_memory.required_bytes",
            requirement.unresolved_fields,
        )

    def test_absent_feasibility_is_unresolved(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        memory = (
            requirement.primary_inference_memory
        )

        self.assertIsNone(memory.required_bytes)
        self.assertEqual(
            memory.basis,
            BASIS_UNRESOLVED_MISSING_INPUT,
        )


class RamHonestyTests(unittest.TestCase):
    """No RAM estimator exists, so none may be invented."""

    def test_ram_is_reported_unresolved_with_a_reason(self):
        (
            feasibility,
            _,
        ) = feasibility_with_provisional_estimate()

        requirement = build_model_requirement(
            model=inventory_model(),
            feasibility=feasibility,
            install_storage=real_install_storage(),
        )

        ram = requirement.ram

        self.assertEqual(ram.memory_type, SYSTEM_RAM)
        self.assertIsNone(ram.required_bytes)
        self.assertFalse(ram.resolved)
        self.assertEqual(
            ram.basis,
            BASIS_UNRESOLVED_NO_ESTIMATOR,
        )
        self.assertIn(
            "ram.required_bytes",
            requirement.unresolved_fields,
        )

    def test_ram_is_not_approximated_from_weight_size(self):
        requirement = build_model_requirement(
            model=inventory_model(),
            install_storage=real_install_storage(),
        )

        self.assertNotEqual(
            requirement.ram.required_bytes,
            QWEN_ARTIFACT_BYTES,
        )
        self.assertIsNone(
            requirement.ram.required_bytes
        )

    def test_source_really_has_no_ram_requirement(self):
        # Guards the claim above: the resource envelope still leaves
        # system_ram_bytes unresolved.
        with tempfile.TemporaryDirectory() as tmp:
            weights = Path(tmp) / "model.safetensors"
            weights.write_bytes(b"\0" * 2048)

            envelope = (
                build_model_resource_requirements(
                    {
                        "model_id": "probe",
                        "path": tmp,
                        "runtime": "vllm",
                    }
                )
            )

        self.assertIsNone(
            envelope["target_requirements"][
                "system_ram_bytes"
            ]
        )
        self.assertIn(
            "system_ram_bytes",
            envelope["unresolved_fields"],
        )


class RuntimeCompatibilityParityTests(unittest.TestCase):
    def setUp(self):
        # The real evaluator returns the ENRICHED candidate record.
        self.compatibility = real_compatibility()

        self.requirement = build_model_requirement(
            model=candidate_model(),
            compatibility=self.compatibility,
        )

    def test_status_and_confidence_match_the_evaluator(self):
        verdict = self.compatibility["compatibility"]
        actual = self.requirement.runtime_compatibility

        self.assertEqual(
            actual.status,
            verdict["status"],
        )
        self.assertEqual(
            actual.confidence,
            verdict["confidence"],
        )
        self.assertEqual(
            actual.reasons,
            tuple(verdict["reasons"]),
        )

    def test_candidate_runtimes_are_read_from_the_enriched_model(self):
        actual = self.requirement.runtime_compatibility

        self.assertEqual(
            actual.candidate_runtimes,
            tuple(
                self.compatibility["runtime"][
                    "supported"
                ]
            ),
        )

        # A safetensors model on Linux with an NVIDIA GPU yields vLLM.
        self.assertIn("vllm", actual.candidate_runtimes)

    def test_weight_formats_and_architecture_are_carried(self):
        actual = self.requirement.runtime_compatibility

        self.assertEqual(
            actual.weight_formats,
            ("safetensors",),
        )
        self.assertEqual(
            actual.architecture,
            "Qwen3ForCausalLM",
        )

    def test_absent_compatibility_is_unresolved(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        actual = requirement.runtime_compatibility

        self.assertIsNone(actual.status)
        self.assertEqual(actual.candidate_runtimes, ())
        self.assertIn(
            "runtime_compatibility.status",
            requirement.unresolved_fields,
        )

    def test_unsupported_host_is_reported_not_hidden(self):
        # A GGUF model has no validated runtime on this platform.
        model = candidate_model(weights="gguf")

        compatibility = real_compatibility(model)

        requirement = build_model_requirement(
            model=model,
            compatibility=compatibility,
        )

        self.assertEqual(
            requirement.runtime_compatibility.status,
            compatibility["compatibility"]["status"],
        )
        self.assertEqual(
            requirement.runtime_compatibility
            .candidate_runtimes,
            ("llama_cpp",),
        )


class AssumptionTests(unittest.TestCase):
    def test_context_length_comes_from_model_metadata(self):
        requirement = build_model_requirement(
            model=inventory_model(context_length=40960),
        )

        self.assertEqual(
            requirement.assumptions.context_length,
            40960,
        )
        self.assertEqual(
            requirement.assumptions.basis[
                "context_length"
            ],
            "model_metadata",
        )

    def test_missing_context_length_is_unresolved(self):
        requirement = build_model_requirement(
            model=inventory_model(context_length=None),
        )

        self.assertIsNone(
            requirement.assumptions.context_length
        )
        self.assertIn(
            "assumptions.context_length",
            requirement.unresolved_fields,
        )

    def test_concurrency_is_caller_supplied(self):
        requirement = build_model_requirement(
            model=inventory_model(),
            concurrency=8,
        )

        self.assertEqual(
            requirement.assumptions.concurrency,
            8,
        )
        self.assertEqual(
            requirement.assumptions.basis[
                "concurrency"
            ],
            "caller_supplied",
        )

    def test_concurrency_unresolved_without_a_caller_value(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        self.assertIsNone(
            requirement.assumptions.concurrency
        )
        self.assertIn(
            "assumptions.concurrency",
            requirement.unresolved_fields,
        )

    def test_offload_is_recorded_as_not_implemented(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        self.assertIsNone(
            requirement.assumptions.offload
        )
        self.assertEqual(
            requirement.assumptions.basis["offload"],
            BASIS_NOT_IMPLEMENTED,
        )
        self.assertIn(
            "assumptions.offload",
            requirement.unresolved_fields,
        )


class IdentityTests(unittest.TestCase):
    def test_identity_fields(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        self.assertEqual(
            requirement.schema_version,
            MODEL_REQUIREMENT_SCHEMA_VERSION,
        )
        self.assertEqual(
            requirement.model_id,
            "qwen3-8b-awq",
        )
        self.assertEqual(
            requirement.revision,
            QWEN_REVISION,
        )
        self.assertEqual(requirement.runtime, "vllm")
        self.assertEqual(
            requirement.quantization,
            "awq",
        )

    def test_catalogue_style_record_without_deployment(self):
        catalogue_entry = {
            "model_id": "Qwen/Qwen3-8B-AWQ",
            "source": {
                "provider": "huggingface",
                "revision": "main",
            },
            "metadata": {
                "quantization": "awq",
                "context_length": None,
                "architecture": None,
            },
        }

        requirement = build_model_requirement(
            model=catalogue_entry,
        )

        self.assertEqual(
            requirement.model_id,
            "Qwen/Qwen3-8B-AWQ",
        )
        self.assertEqual(
            requirement.revision,
            "main",
        )
        self.assertIsNone(requirement.runtime)
        self.assertIsNone(
            requirement.storage.installed_bytes
        )

    def test_memory_requirement_lookup_by_type(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        self.assertIs(
            requirement.memory_requirement(
                SYSTEM_RAM
            ),
            requirement.ram,
        )
        self.assertIs(
            requirement.memory_requirement(
                DEDICATED_VRAM
            ),
            requirement.primary_inference_memory,
        )
        self.assertIsNone(
            requirement.memory_requirement(
                "unified_memory"
            )
        )


class ContractHygieneTests(unittest.TestCase):
    def test_normalization_performs_no_detection(self):
        def forbidden(*args, **kwargs):
            raise AssertionError(
                "ModelRequirement must not detect anything"
            )

        (
            feasibility,
            _,
        ) = feasibility_with_provisional_estimate()

        compatibility = real_compatibility()

        install_storage = real_install_storage()

        with mock.patch(
            "core.config.load_config",
            forbidden,
        ), mock.patch(
            "core.hardware.inspect_hardware",
            forbidden,
        ), mock.patch(
            "os.walk",
            forbidden,
        ), mock.patch(
            "shutil.disk_usage",
            forbidden,
        ):
            requirement = build_model_requirement(
                model=inventory_model(),
                feasibility=feasibility,
                install_storage=install_storage,
                compatibility=compatibility,
                concurrency=4,
            )

        self.assertEqual(
            requirement.model_id,
            "qwen3-8b-awq",
        )

    def test_contract_is_immutable(self):
        requirement = build_model_requirement(
            model=inventory_model(),
        )

        with self.assertRaises(Exception):
            requirement.model_id = "other"

        with self.assertRaises(Exception):
            requirement.storage.installed_bytes = 1

    def test_serializes_to_plain_data(self):
        (
            feasibility,
            _,
        ) = feasibility_with_provisional_estimate()

        requirement = build_model_requirement(
            model=inventory_model(),
            feasibility=feasibility,
            install_storage=real_install_storage(),
            compatibility=real_compatibility(),
            concurrency=4,
        )

        restored = json.loads(
            json.dumps(requirement.to_dict())
        )

        self.assertEqual(
            restored["schema_version"],
            MODEL_REQUIREMENT_SCHEMA_VERSION,
        )
        self.assertEqual(
            restored["storage"]["target_pool_id"],
            PLATFORM_DATA_STORAGE_POOL_ID,
        )
        self.assertEqual(
            restored["primary_inference_memory"][
                "memory_type"
            ],
            DEDICATED_VRAM,
        )
        self.assertIn(
            "ram.required_bytes",
            restored["unresolved_fields"],
        )

    def test_non_mapping_inputs_are_rejected(self):
        with self.assertRaises(TypeError):
            build_model_requirement(model=[])

        with self.assertRaises(TypeError):
            build_model_requirement(
                model=inventory_model(),
                feasibility=[],
            )

    def test_no_selection_or_feasibility_logic_is_present(self):
        # C4 normalizes; it must not decide anything.
        import inspect

        import core.model_requirement as module

        source = inspect.getsource(module)

        for forbidden in (
            "selector",
            "safe_available",
            "fits",
            "verdict_for",
            "capacity_envelope",
        ):
            self.assertNotIn(forbidden, source)


class DualShapeNormalizationTests(unittest.TestCase):
    """One contract over both record shapes the platform uses.

    Candidates are evaluated before acquisition and inventory records
    after it. Without this, C5 would need to know which shape it holds.
    """

    def test_identity_normalizes_from_either_shape(self):
        from_inventory = build_model_requirement(
            model=inventory_model(),
        )
        from_candidate = build_model_requirement(
            model=candidate_model(),
        )

        # Different id conventions, same normalized fields elsewhere.
        self.assertEqual(
            from_inventory.model_id,
            "qwen3-8b-awq",
        )
        self.assertEqual(
            from_candidate.model_id,
            "Qwen/Qwen3-8B-AWQ",
        )

        for requirement in (
            from_inventory,
            from_candidate,
        ):
            self.assertEqual(
                requirement.revision,
                QWEN_REVISION,
            )
            self.assertEqual(
                requirement.quantization,
                "awq",
            )
            self.assertEqual(
                requirement.assumptions.context_length,
                40960,
            )
            self.assertEqual(
                requirement.runtime_compatibility
                .architecture,
                "Qwen3ForCausalLM",
            )

    def test_installed_bytes_read_from_either_shape(self):
        # Inventory keeps it under artifact.disk_usage_bytes.
        self.assertEqual(
            build_model_requirement(
                model=inventory_model(),
            ).storage.installed_bytes,
            QWEN_ARTIFACT_BYTES,
        )

        # Candidates keep it under size.installed_bytes, and it is
        # absent for a model that is not installed yet.
        self.assertIsNone(
            build_model_requirement(
                model=candidate_model(),
            ).storage.installed_bytes
        )
        self.assertEqual(
            build_model_requirement(
                model=candidate_model(
                    installed_bytes=QWEN_ARTIFACT_BYTES
                ),
            ).storage.installed_bytes,
            QWEN_ARTIFACT_BYTES,
        )

    def test_weight_formats_read_from_either_shape(self):
        self.assertEqual(
            build_model_requirement(
                model=inventory_model(),
            ).runtime_compatibility.weight_formats,
            ("safetensors",),
        )
        self.assertEqual(
            build_model_requirement(
                model=candidate_model(),
            ).runtime_compatibility.weight_formats,
            ("safetensors",),
        )

    def test_chosen_runtime_exists_only_once_deployed(self):
        # A candidate has runtime.supported, not a chosen runtime.
        self.assertIsNone(
            build_model_requirement(
                model=candidate_model(),
            ).runtime
        )
        self.assertEqual(
            build_model_requirement(
                model=inventory_model(),
            ).runtime,
            "vllm",
        )

    def test_declared_requirement_slots_are_honoured_when_filled(self):
        # The candidate record reserves ram_bytes and vram_bytes for a
        # future estimator. Nothing fills them today, so the contract
        # reports unresolved; if one did, it must be read rather than
        # ignored.
        empty = build_model_requirement(
            model=candidate_model(),
        )

        self.assertIsNone(empty.ram.required_bytes)
        self.assertEqual(
            empty.ram.basis,
            BASIS_UNRESOLVED_NO_ESTIMATOR,
        )

        model = candidate_model()
        model["requirements"]["ram_bytes"] = 24 * GIB
        model["requirements"]["vram_bytes"] = 20 * GIB

        filled = build_model_requirement(model=model)

        self.assertEqual(
            filled.ram.required_bytes,
            24 * GIB,
        )
        self.assertEqual(
            filled.ram.basis,
            "model_record.requirements.ram_bytes",
        )
        self.assertEqual(
            filled.primary_inference_memory
            .required_bytes,
            20 * GIB,
        )

    def test_shipped_candidate_records_declare_nothing(self):
        # Guards the claim: the canonical normalizer leaves every
        # requirement figure unset.
        from core.model_metadata import (
            normalize_local_model,
        )

        normalized = normalize_local_model(
            {
                "name": "qwen3-8b-awq",
                "path": "/workspace/models/qwen3-8b-awq",
                "architecture": "Qwen3ForCausalLM",
            }
        )

        self.assertEqual(
            normalized["requirements"],
            {
                "ram_bytes": None,
                "vram_bytes": None,
                "unified_memory_bytes": None,
            },
        )

        requirement = build_model_requirement(
            model=normalized,
        )

        self.assertIsNone(requirement.ram.required_bytes)
        self.assertIsNone(
            requirement.primary_inference_memory
            .required_bytes
        )


class NoCallerMigrationTests(unittest.TestCase):
    def test_no_existing_module_consumes_the_contract(self):
        import inspect

        import core.control as control
        import core.deployment as deployment
        import core.model_feasibility as feasibility
        import core.model_storage_requirements as storage
        import core.requirements as requirements
        import platform_api.server as server

        # Match the import path and builder name, not the substring
        # "model_requirement", which already appears inside the
        # pre-existing estimate_model_requirements().
        for module in (
            control,
            deployment,
            feasibility,
            storage,
            requirements,
            server,
        ):
            source = inspect.getsource(module)

            self.assertNotIn(
                "core.model_requirement",
                source,
                msg=module.__name__,
            )
            self.assertNotIn(
                "build_model_requirement",
                source,
                msg=module.__name__,
            )


if __name__ == "__main__":
    unittest.main()
