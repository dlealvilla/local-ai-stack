from __future__ import annotations

import unittest

from adapters.resource_manager.vllm_service_spec import (
    VllmInventoryServiceSpecProvider,
    VllmServiceSpecError,
)


def inventory():
    return {
        "schema_version": 1,
        "models": [
            {
                "model_id":
                    "qwen3-8b-awq",
                "path":
                    "/models/qwen3-8b-awq",
            },
            {
                "model_id":
                    "tiny",
                "path":
                    "/models/tiny",
            },
        ],
    }


def base_config():
    return {
        "inference": {
            "served_model_name":
                "qwen3-8b-awq",
            "tool_calling": True,
        },
        "network": {
            "inference_host":
                "127.0.0.1",
            "inference_port":
                8000,
        },
    }


def performance():
    return {
        "context_length": 4096,
        "gpu_memory_utilization": 0.5,
        "concurrency": 1,
    }


class VllmServiceSpecProviderTests(
    unittest.TestCase
):
    def make_provider(self):
        return (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance=performance(),
                inventory_provider=inventory,
            )
        )

    def test_builds_existing_vllm_service_spec_shape(self):
        provider = self.make_provider()

        spec = provider.build(
            model_id="qwen3-8b-awq",
            metadata={},
        )

        self.assertEqual(
            spec["role"],
            "inference",
        )

        self.assertEqual(
            spec["provider"],
            "vllm",
        )

        self.assertEqual(
            spec["model"]["name"],
            "qwen3-8b-awq",
        )

        self.assertEqual(
            spec["model"]["path"],
            "/models/qwen3-8b-awq",
        )

        self.assertEqual(
            spec["model"]["served_name"],
            "qwen3-8b-awq",
        )

        self.assertEqual(
            spec["performance"][
                "context_length"
            ],
            4096,
        )

    def test_metadata_can_override_performance_only(self):
        provider = self.make_provider()

        spec = provider.build(
            model_id="qwen3-8b-awq",
            metadata={
                "performance": {
                    "concurrency": 2,
                }
            },
        )

        self.assertEqual(
            spec["performance"][
                "concurrency"
            ],
            2,
        )

        self.assertEqual(
            spec["performance"][
                "context_length"
            ],
            4096,
        )

    def test_unknown_model_fails_closed(self):
        provider = self.make_provider()

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="missing",
                metadata={},
            )

    def test_wrong_inventory_schema_fails_closed(self):
        provider = (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance=performance(),
                inventory_provider=lambda: {
                    "schema_version": 2,
                    "models": [],
                },
            )
        )

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="qwen3-8b-awq",
                metadata={},
            )

    def test_missing_models_contract_fails_closed(self):
        provider = (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance=performance(),
                inventory_provider=lambda: {
                    "schema_version": 1,
                    "records": [],
                },
            )
        )

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="qwen3-8b-awq",
                metadata={},
            )

    def test_missing_model_path_fails_closed(self):
        provider = (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance=performance(),
                inventory_provider=lambda: {
                    "schema_version": 1,
                    "models": [
                        {
                            "model_id": "broken",
                            "path": None,
                        }
                    ],
                },
            )
        )

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="broken",
                metadata={},
            )

    def test_missing_performance_contract_fails(self):
        provider = (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance={
                    "context_length": 4096,
                },
                inventory_provider=inventory,
            )
        )

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="qwen3-8b-awq",
                metadata={},
            )

    def test_duplicate_model_id_fails_closed(self):
        provider = (
            VllmInventoryServiceSpecProvider(
                config=base_config(),
                performance=performance(),
                inventory_provider=lambda: {
                    "schema_version": 1,
                    "models": [
                        {
                            "model_id":
                                "qwen3-8b-awq",
                            "path": "/a",
                        },
                        {
                            "model_id":
                                "qwen3-8b-awq",
                            "path": "/b",
                        },
                    ],
                },
            )
        )

        with self.assertRaises(
            VllmServiceSpecError
        ):
            provider.build(
                model_id="qwen3-8b-awq",
                metadata={},
            )

    def test_inputs_are_not_mutated(self):
        config = base_config()
        perf = performance()

        original_config = repr(
            config
        )

        original_perf = repr(
            perf
        )

        provider = (
            VllmInventoryServiceSpecProvider(
                config=config,
                performance=perf,
                inventory_provider=inventory,
            )
        )

        provider.build(
            model_id="qwen3-8b-awq",
            metadata={
                "performance": {
                    "concurrency": 3,
                }
            },
        )

        self.assertEqual(
            repr(config),
            original_config,
        )

        self.assertEqual(
            repr(perf),
            original_perf,
        )


if __name__ == "__main__":
    unittest.main()
