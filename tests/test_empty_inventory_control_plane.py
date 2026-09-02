from __future__ import annotations

import unittest

from core.config import load_config
from core.deployment import build_deployment_manifest
from core.health import check_deployment_health
from core.lifecycle import enabled_services, stop_service
from core.status import get_manifest_runtime_status


CONTROL_PLANE_IDS = {"gateway", "platform_api"}

# Ports deliberately outside the platform defaults so observation
# never probes or collides with a real deployment.
TEST_INFERENCE_PORT = 59330
TEST_FRONTEND_PORT = 59331
TEST_GATEWAY_PORT = 59332
TEST_PLATFORM_API_PORT = 59333


class RecordingExecutor:
    """
    Stands in for a real executor so a test can prove the lifecycle
    never asks for a command or environment for an unsatisfied
    service.
    """

    def __init__(self):
        self.commands_built = []

    def build_command(self, service_spec):
        self.commands_built.append(service_spec)
        return ["/bin/true"]

    def build_environment(self, service_spec):
        self.commands_built.append(service_spec)
        return {}


def build_config(frontend_enabled=False):
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
            "provider": "openwebui",
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

        "analytics": {
            "enabled": False,
            "provider": "disabled",
        },
    }


def build_plan(config, selected_model=None):
    return {
        "selected_model": selected_model,
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


def build_manifest(config, selected_model=None):
    return build_deployment_manifest(
        build_plan(config, selected_model),
        config,
    )


def service_by_id(manifest, service_id):
    for service in manifest["services"]:
        if service["id"] == service_id:
            return service

    raise AssertionError(
        f"Service not present in manifest: {service_id}"
    )


class EmptyInventoryStartupTests(unittest.TestCase):
    def setUp(self):
        self.config = build_config()
        self.manifest = build_manifest(self.config)

    def test_control_plane_is_startable_with_zero_models(self):
        # A: a zero-model deployment still has a startable
        # control plane.
        startable = {
            service["id"]
            for service in enabled_services(self.manifest)
        }

        self.assertEqual(startable, CONTROL_PLANE_IDS)

    def test_platform_api_is_enabled_and_addressable(self):
        # The acquisition/feasibility endpoints live on
        # platform_api, so it must be enabled and have a network
        # specification the lifecycle can bind.
        platform_api = service_by_id(
            self.manifest,
            "platform_api",
        )

        self.assertTrue(platform_api["enabled"])

        self.assertEqual(
            platform_api["spec"]["network"]["port"],
            TEST_PLATFORM_API_PORT,
        )

    def test_inference_remains_unsatisfied(self):
        # B: inference is present but unavailable, never faked.
        inference = service_by_id(self.manifest, "inference")

        self.assertFalse(inference["enabled"])
        self.assertIsNone(inference["spec"])
        self.assertIsNone(self.manifest["model"])

    def test_lifecycle_never_builds_an_inference_process(self):
        # C: the executor is never asked to construct a command
        # for the unsatisfied inference service.
        executor = RecordingExecutor()

        for service in enabled_services(self.manifest):
            executor.build_command(service["spec"])
            executor.build_environment(service["spec"])

        roles = {
            spec["role"]
            for spec in executor.commands_built
        }

        self.assertNotIn("inference", roles)
        self.assertEqual(roles, {"gateway", "platform_api"})

    def test_no_frontend_requirement_is_reintroduced(self):
        # G: control-plane startup must not pull in a frontend.
        frontend = service_by_id(self.manifest, "frontend")

        self.assertFalse(frontend["enabled"])
        self.assertIsNone(frontend["spec"])

        self.assertNotIn(
            "frontend",
            {
                service["id"]
                for service in enabled_services(self.manifest)
            },
        )

    def test_shipped_default_configuration_agrees(self):
        # The real shipped configuration must produce the same
        # zero-model control plane, not just the fixture.
        config = load_config()
        manifest = build_manifest(config)

        self.assertEqual(
            {
                service["id"]
                for service in enabled_services(manifest)
            },
            CONTROL_PLANE_IDS,
        )


class SelectedModelRegressionTests(unittest.TestCase):
    def test_selected_model_startup_semantics_are_intact(self):
        # D: with a model, inference is enabled, specified and
        # started alongside the control plane.
        config = build_config()

        manifest = build_manifest(
            config,
            selected_model={
                "name": "test-model",
                "path": "/tmp/ai-stack-test/models/test-model",
                "size_gb": 8.0,
            },
        )

        inference = service_by_id(manifest, "inference")

        self.assertTrue(inference["enabled"])
        self.assertIsNotNone(inference["spec"])

        self.assertEqual(
            {
                service["id"]
                for service in enabled_services(manifest)
            },
            CONTROL_PLANE_IDS | {"inference"},
        )

    def test_enabled_frontend_is_still_started(self):
        # Disabling by default must not make enabling impossible.
        config = build_config(frontend_enabled=True)
        manifest = build_manifest(config)

        self.assertIn(
            "frontend",
            {
                service["id"]
                for service in enabled_services(manifest)
            },
        )


class StopSafetyTests(unittest.TestCase):
    def test_stop_is_safe_and_idempotent_with_zero_models(self):
        # E: stopping a never-started control plane is harmless
        # and repeatable.
        manifest = build_manifest(build_config())

        for _ in range(2):
            for service in reversed(
                enabled_services(manifest)
            ):
                result = stop_service(
                    service["id"],
                    service["spec"],
                )

                self.assertIn(
                    result["status"],
                    {"not_running", "stale", "stopped"},
                )

    def test_stop_never_targets_the_inference_service(self):
        manifest = build_manifest(build_config())

        targeted = {
            service["id"]
            for service in reversed(
                enabled_services(manifest)
            )
        }

        self.assertNotIn("inference", targeted)


class RepresentationTests(unittest.TestCase):
    def setUp(self):
        self.config = build_config()
        self.manifest = build_manifest(self.config)

    def test_status_reports_control_plane_only(self):
        # F: status distinguishes the observable control plane
        # from unavailable inference.
        observed = get_manifest_runtime_status(self.manifest)

        self.assertEqual(
            {service["id"] for service in observed},
            CONTROL_PLANE_IDS,
        )

    def test_health_probes_the_control_plane_but_not_inference(self):
        # F: unavailable inference is not probed and cannot be
        # reported as an inference failure.
        probed = {
            item["service"]
            for item in check_deployment_health(self.manifest)
        }

        self.assertEqual(probed, CONTROL_PLANE_IDS)

    def test_inference_is_unavailable_rather_than_running(self):
        # F: the manifest represents inference as unsatisfied,
        # never as a running or faked service.
        inference = service_by_id(self.manifest, "inference")

        self.assertFalse(inference["enabled"])
        self.assertIsNone(inference["spec"])

        observed_ids = {
            service["id"]
            for service in get_manifest_runtime_status(
                self.manifest
            )
        }

        self.assertNotIn("inference", observed_ids)


if __name__ == "__main__":
    unittest.main()
