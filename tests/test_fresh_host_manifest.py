from __future__ import annotations

import tempfile
import unittest

from core.deployment import build_deployment_manifest
from core.health import check_deployment_health
from core.preflight import run_preflight
from core.status import get_manifest_runtime_status


# Ports deliberately outside the configured platform defaults so
# these tests never contend with a real local deployment.
TEST_INFERENCE_PORT = 59310
TEST_FRONTEND_PORT = 59311
TEST_GATEWAY_PORT = 59312
TEST_PLATFORM_API_PORT = 59313


def build_config():
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
            "enabled": True,
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


def build_plan(selected_model=None, model_reason="test"):
    config = build_config()

    return {
        "selected_model": selected_model,
        "model_reason": model_reason,

        "inference": config["inference"],
        "gateway": config["gateway"],
        "frontend": config["frontend"],

        "performance": {
            "context_length": 8192,
            "gpu_memory_utilization": 0.85,
            "concurrency": 4,
        },
    }


def selected_model_fixture():
    return {
        "name": "test-model",
        "path": "/tmp/ai-stack-test/models/test-model",
        "size_gb": 1.0,
        "architecture": "TestForCausalLM",
        "model_type": "test",
        "quantization_method": None,
        "max_position_embeddings": 8192,
    }


def find_service(manifest, service_id):
    for service in manifest["services"]:
        if service["id"] == service_id:
            return service

    raise AssertionError(
        f"Service not present in manifest: {service_id}"
    )


class NoModelManifestTests(unittest.TestCase):
    """
    A host with an empty model inventory must remain representable.
    """

    def test_manifest_construction_does_not_raise(self):
        # A: previously raised ValueError from the vLLM adapter.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        self.assertIsNone(manifest["model"])

    def test_inference_is_present_but_unsatisfied(self):
        # B: inference is described, not invented.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        inference = find_service(manifest, "inference")

        self.assertFalse(inference["enabled"])
        self.assertIsNone(inference["spec"])
        self.assertEqual(inference["role"], "inference")
        self.assertEqual(inference["provider"], "vllm")

    def test_no_dummy_model_is_invented(self):
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        self.assertIsNone(manifest["model"])

        for service in manifest["services"]:
            if service["spec"] is None:
                continue

            self.assertNotIn(
                "model",
                service["spec"],
                "No service may fabricate a model reference.",
            )

    def test_other_services_are_unaffected(self):
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        gateway = find_service(manifest, "gateway")
        platform_api = find_service(manifest, "platform_api")

        self.assertTrue(gateway["enabled"])
        self.assertIsNotNone(gateway["spec"])
        self.assertTrue(platform_api["enabled"])
        self.assertIsNotNone(platform_api["spec"])

    def test_inference_is_not_startable(self):
        # E (unit half): the CLI start loop only acts on enabled
        # services, so an unsatisfied inference service can never
        # reach the process executor.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        startable = [
            service["id"]
            for service in manifest["services"]
            if service["enabled"]
        ]

        self.assertNotIn("inference", startable)

    def test_stop_has_no_inference_service_to_act_on(self):
        # F: stop iterates the same enabled set, so it is a no-op
        # for inference rather than an error.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        stoppable = [
            service["id"]
            for service in reversed(manifest["services"])
            if service["enabled"]
        ]

        self.assertNotIn("inference", stoppable)


class NoModelPreflightTests(unittest.TestCase):
    def test_preflight_reports_missing_model_as_failure(self):
        # C: a normal readiness failure, not an exception.
        config = build_config()

        manifest = build_deployment_manifest(
            build_plan(),
            config,
        )

        checks = run_preflight(manifest, config)

        model_checks = [
            check
            for check in checks
            if check["name"] == "Selected model"
        ]

        self.assertEqual(len(model_checks), 1)
        self.assertEqual(model_checks[0]["status"], "fail")

        ready = all(
            check["status"] != "fail"
            for check in checks
        )

        self.assertFalse(
            ready,
            "A host with no model must not report ready.",
        )


class NoModelObservationTests(unittest.TestCase):
    def test_status_can_be_produced(self):
        # D: status composes without an inference spec.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        services = get_manifest_runtime_status(manifest)

        observed = [item["id"] for item in services]

        self.assertNotIn("inference", observed)

    def test_health_can_be_produced(self):
        # D: health skips unsatisfied services instead of
        # dereferencing a missing spec.
        manifest = build_deployment_manifest(
            build_plan(),
            build_config(),
        )

        results = check_deployment_health(manifest)

        checked = [item["service"] for item in results]

        self.assertNotIn("inference", checked)


class SelectedModelRegressionTests(unittest.TestCase):
    """
    G: existing behavior with a selected model is unchanged.
    """

    def test_inference_service_is_built_normally(self):
        model = selected_model_fixture()

        manifest = build_deployment_manifest(
            build_plan(selected_model=model),
            build_config(),
        )

        inference = find_service(manifest, "inference")

        self.assertTrue(inference["enabled"])
        self.assertIsNotNone(inference["spec"])
        self.assertEqual(
            inference["spec"]["model"]["name"],
            "test-model",
        )
        self.assertEqual(
            inference["spec"]["network"]["port"],
            TEST_INFERENCE_PORT,
        )

    def test_manifest_model_is_populated(self):
        model = selected_model_fixture()

        manifest = build_deployment_manifest(
            build_plan(selected_model=model),
            build_config(),
        )

        self.assertEqual(
            manifest["model"],
            {
                "name": "test-model",
                "path": model["path"],
            },
        )

    def test_preflight_checks_the_model_path(self):
        config = build_config()
        model = selected_model_fixture()

        # The selected-model check must inspect the real artifact
        # path rather than reporting the no-model failure.
        with tempfile.TemporaryDirectory() as model_path:
            model["path"] = model_path

            manifest = build_deployment_manifest(
                build_plan(selected_model=model),
                config,
            )

            checks = run_preflight(manifest, config)

        model_checks = [
            check
            for check in checks
            if check["name"] == "Selected model"
        ]

        self.assertEqual(len(model_checks), 1)
        self.assertEqual(model_checks[0]["status"], "pass")
        self.assertEqual(
            model_checks[0]["detail"],
            model_path,
        )


if __name__ == "__main__":
    unittest.main()
