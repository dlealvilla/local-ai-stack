"""Tests that the evaluation provider is provisioned only when enabled.

The product requirement is plug-and-play: enabling the provider should
make the tool appear on the next `./ai prepare`. The constraint is that
it must never become a platform prerequisite, so a disabled provider
adds no requirement and cannot make a host report as not ready.

Provisioning itself is the existing runtime mechanism, so these tests
assert the wiring rather than reimplementing installation.
"""

from __future__ import annotations

import unittest
from unittest import mock

import core.host_readiness as host_readiness

from core.host_readiness import evaluate_host_readiness
from core.runtime_manager import (
    RUNTIME_PROFILES,
    required_runtimes,
)


def config(*, enabled, provider="llmfit"):
    return {
        "runtime": {"executor": "process"},
        "inference": {"provider": "vllm"},
        "frontend": {
            "enabled": False,
            "provider": "openwebui",
        },
        "model_transfer": {
            "enabled": True,
            "providers": ["huggingface"],
        },
        "model_evaluation": {
            "provider": provider,
            "enabled": enabled,
        },
    }


def hardware():
    return {
        "operating_system": "Linux",
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 9354 32-Core Processor",
        "cpu_cores": 128,
        "ram_total_gb": 755.0,
        "gpus": [
            {
                "vendor": "nvidia",
                "name": "NVIDIA GeForce RTX 5090",
                "vram_total_gb": 31.84,
                "vram_free_gb": 31.8,
            },
        ],
    }


class RequirementWiringTests(unittest.TestCase):
    def test_disabled_provider_is_not_required(self):
        required = required_runtimes(
            config(enabled=False)
        )

        self.assertNotIn("llmfit", required)
        self.assertEqual(
            required,
            ["vllm", "platform_tools"],
        )

    def test_enabled_provider_is_required(self):
        required = required_runtimes(
            config(enabled=True)
        )

        self.assertIn("llmfit", required)

    def test_requirement_list_stays_deduplicated(self):
        required = required_runtimes(
            config(enabled=True)
        )

        self.assertEqual(
            len(required),
            len(set(required)),
        )

    def test_unknown_provider_adds_no_requirement(self):
        # A provider with no runtime profile cannot be provisioned, and
        # must not break preparation.
        required = required_runtimes(
            config(
                enabled=True,
                provider="some-future-provider",
            )
        )

        self.assertEqual(
            required,
            ["vllm", "platform_tools"],
        )

    def test_provider_has_a_runtime_profile(self):
        profile = RUNTIME_PROFILES["llmfit"]

        self.assertEqual(
            profile["executable"],
            ".venv/bin/llmfit",
        )
        self.assertTrue(
            any(
                package.startswith("llmfit==")
                for package in profile["packages"]
            )
        )

        # Provisioned by the existing uv mechanism: no compiler, no
        # container, no system package manager.
        self.assertIsNone(
            profile["torch_backend"]
        )

    def test_shipped_default_is_opt_in(self):
        from core.config import load_config

        settings = load_config()[
            "model_evaluation"
        ]

        self.assertFalse(settings["enabled"])
        self.assertEqual(
            settings["provider"],
            "llmfit",
        )


class PrepareBehaviorTests(unittest.TestCase):
    """`./ai prepare` provisions exactly the required runtimes."""

    def prepared(self, *, enabled, ready):
        provisioned = []

        def ensure_runtime(name):
            provisioned.append(name)

            return {
                "name": name,
                "status": (
                    "existing" if ready else "created"
                ),
                "executable": f"/opt/{name}/bin",
            }

        for name in required_runtimes(
            config(enabled=enabled)
        ):
            ensure_runtime(name)

        return provisioned

    def test_disabled_provider_is_not_provisioned(self):
        self.assertNotIn(
            "llmfit",
            self.prepared(
                enabled=False,
                ready=False,
            ),
        )

    def test_enabled_and_missing_provider_is_provisioned(self):
        self.assertIn(
            "llmfit",
            self.prepared(
                enabled=True,
                ready=False,
            ),
        )

    def test_second_prepare_reuses_an_existing_provider(self):
        # Reuse is the existing runtime_is_ready short-circuit; assert
        # it reports existing rather than recreating.
        with mock.patch(
            "core.runtime_manager.runtime_is_ready",
            lambda name: True,
        ), mock.patch(
            "subprocess.run",
            side_effect=AssertionError(
                "a ready runtime must not be reinstalled"
            ),
        ):
            from core.runtime_manager import (
                ensure_runtime,
            )

            result = ensure_runtime("llmfit")

        self.assertEqual(
            result["status"],
            "existing",
        )
        self.assertTrue(
            result["executable"].endswith(
                ".venv/bin/llmfit"
            )
        )


class ReadinessTests(unittest.TestCase):
    def readiness(self, *, enabled, llmfit_ready):
        with mock.patch.object(
            host_readiness,
            "check_command",
            lambda name: {
                "name": f"{name} command",
                "status": "pass",
                "detail": "ok",
            },
        ), mock.patch.object(
            host_readiness,
            "check_nvidia_gpu",
            lambda: {
                "name": "NVIDIA GPU",
                "status": "pass",
                "detail": "ok",
            },
        ), mock.patch.object(
            host_readiness,
            "runtime_is_ready",
            lambda name: (
                llmfit_ready
                if name == "llmfit"
                else True
            ),
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: f"/opt/{name}",
        ):
            return evaluate_host_readiness(
                config(enabled=enabled),
                hardware=hardware(),
            )

    def test_disabled_provider_is_not_a_platform_failure(self):
        readiness = self.readiness(
            enabled=False,
            llmfit_ready=False,
        )

        self.assertTrue(readiness["ready"])

        names = [
            check["name"]
            for check in readiness["checks"]
        ]

        self.assertNotIn("llmfit runtime", names)

    def test_enabled_and_ready_provider_is_reported(self):
        readiness = self.readiness(
            enabled=True,
            llmfit_ready=True,
        )

        self.assertTrue(readiness["ready"])

        check = next(
            entry
            for entry in readiness["checks"]
            if entry["name"] == "llmfit runtime"
        )

        self.assertEqual(check["status"], "pass")

    def test_enabled_but_missing_provider_blocks_readiness(self):
        # Having asked for the provider, a host without it is not
        # ready — but only because it was asked for.
        readiness = self.readiness(
            enabled=True,
            llmfit_ready=False,
        )

        self.assertFalse(readiness["ready"])
        self.assertIn(
            "llmfit runtime",
            readiness["blocking"],
        )


if __name__ == "__main__":
    unittest.main()
