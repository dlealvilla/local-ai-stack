from __future__ import annotations

import copy
import unittest

from core.config import load_config
from core.deployment import build_deployment_manifest
from core.preflight import run_preflight
from core.runtime_manager import required_runtimes


OPEN_WEBUI_CHECK = "Open WebUI data"

# Ports outside the configured platform defaults so preflight's
# availability probes never contend with a real deployment.
TEST_INFERENCE_PORT = 59320
TEST_FRONTEND_PORT = 59321
TEST_GATEWAY_PORT = 59322
TEST_PLATFORM_API_PORT = 59323


def build_config(frontend_enabled=False, frontend_provider="openwebui"):
    return {
        "platform": {
            "stage": "test",
            "data_root": "/tmp/ai-stack-test",
        },

        "runtime": {
            "executor": "process",
        },

        "inference": {
            "provider": "vllm",
            "served_model_name": "local-llm",
            "tool_calling": False,
        },

        "gateway": {
            "provider": "builtin_proxy",
        },

        "frontend": {
            "provider": frontend_provider,
            "enabled": frontend_enabled,
        },

        "platform_api": {
            "provider": "builtin_http",
            "enabled": True,
            "host": "127.0.0.1",
            "port": TEST_PLATFORM_API_PORT,
        },

        "network": {
            "inference_host": "127.0.0.1",
            "inference_port": TEST_INFERENCE_PORT,
            "frontend_host": "127.0.0.1",
            "frontend_port": TEST_FRONTEND_PORT,
            "api_host": "127.0.0.1",
            "api_port": TEST_GATEWAY_PORT,
        },

        "model_transfer": {
            "enabled": True,
            "providers": ["huggingface", "local_files"],
        },

        "analytics": {
            "enabled": False,
            "provider": "disabled",
        },
    }


def build_plan(config):
    return {
        "selected_model": None,
        "model_reason": "test",

        "inference": config["inference"],
        "gateway": config["gateway"],
        "frontend": config["frontend"],

        "performance": {
            "context_length": 8192,
            "gpu_memory_utilization": 0.85,
            "concurrency": 4,
        },
    }


def check_names(config):
    manifest = build_deployment_manifest(
        build_plan(config),
        config,
    )

    return [
        check["name"]
        for check in run_preflight(manifest, config)
    ]


class ShippedDefaultTests(unittest.TestCase):
    def test_default_configuration_disables_frontend(self):
        # A: the backend is deployable with no end-user frontend.
        config = load_config()

        self.assertFalse(config["frontend"]["enabled"])

    def test_open_webui_remains_a_supported_provider(self):
        # Disabling the frontend must not remove provider support.
        config = load_config()

        self.assertEqual(
            config["frontend"]["provider"],
            "openwebui",
        )


class RequiredRuntimeTests(unittest.TestCase):
    def test_default_configuration_excludes_openwebui(self):
        # B: ./ai prepare provisions backend runtimes only.
        runtimes = required_runtimes(load_config())

        self.assertNotIn("openwebui", runtimes)
        self.assertIn("vllm", runtimes)

    def test_enabled_frontend_still_requires_its_runtime(self):
        # C: explicitly enabling Open WebUI restores its runtime.
        config = copy.deepcopy(load_config())
        config["frontend"]["enabled"] = True
        config["frontend"]["provider"] = "openwebui"

        self.assertIn(
            "openwebui",
            required_runtimes(config),
        )


class FrontendPreflightTests(unittest.TestCase):
    def test_disabled_frontend_skips_open_webui_check(self):
        # D: no Open WebUI readiness failure without a frontend.
        names = check_names(
            build_config(frontend_enabled=False)
        )

        self.assertNotIn(OPEN_WEBUI_CHECK, names)

    def test_enabled_open_webui_retains_its_check(self):
        # E: the provider-specific check is preserved.
        names = check_names(
            build_config(frontend_enabled=True)
        )

        self.assertIn(OPEN_WEBUI_CHECK, names)

    def test_check_is_gated_on_provider_not_just_enablement(self):
        # The check is provider-specific, so a future non-Open-WebUI
        # frontend will not inherit an Open WebUI readiness failure.
        config = build_config(frontend_enabled=True)

        manifest = build_deployment_manifest(
            build_plan(config),
            config,
        )

        config["frontend"]["provider"] = "future_frontend"

        names = [
            check["name"]
            for check in run_preflight(manifest, config)
        ]

        self.assertNotIn(OPEN_WEBUI_CHECK, names)


if __name__ == "__main__":
    unittest.main()
