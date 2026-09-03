"""Tests for fresh-host platform readiness.

The question under test is narrow and worth stating precisely: can this
SERVER host the configured platform? A fresh host with no model is a
ready server, and conflating that with deployment readiness is the
confusion these tests exist to prevent.

Every check is an existing seam, so the checks themselves are patched
rather than reimplemented; what is asserted is the composition and the
verdict.
"""

from __future__ import annotations

import unittest
from unittest import mock

import core.host_readiness as host_readiness

from core.host_readiness import (
    HOST_READINESS_SCHEMA_VERSION,
    evaluate_host_readiness,
)


def hardware(*, gpus=None):
    if gpus is None:
        gpus = [
            {
                "vendor": "nvidia",
                "name": "NVIDIA GeForce RTX 5090",
                "vram_total_gb": 31.84,
                "vram_free_gb": 31.8,
            },
        ]

    return {
        "operating_system": "Linux",
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 9354 32-Core Processor",
        "cpu_cores": 128,
        "ram_total_gb": 755.0,
        "gpus": gpus,
    }


def config(*, frontend_enabled=False):
    return {
        "runtime": {"executor": "process"},
        "inference": {"provider": "vllm"},
        "frontend": {
            "enabled": frontend_enabled,
            "provider": "openwebui",
        },
        "model_transfer": {
            "enabled": True,
            "providers": ["huggingface"],
        },
    }


class ReadyHostTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            mock.patch.object(
                host_readiness,
                "check_command",
                lambda name: {
                    "name": f"{name} command",
                    "status": "pass",
                    "detail": f"/usr/bin/{name}",
                },
            ),
            mock.patch.object(
                host_readiness,
                "check_nvidia_gpu",
                lambda: {
                    "name": "NVIDIA GPU",
                    "status": "pass",
                    "detail": (
                        "NVIDIA GeForce RTX 5090"
                    ),
                },
            ),
            mock.patch.object(
                host_readiness,
                "runtime_is_ready",
                lambda name: True,
            ),
            mock.patch.object(
                host_readiness,
                "runtime_executable",
                lambda name: (
                    f"/opt/ai-stack/runtime/{name}/.venv/bin/x"
                ),
            ),
        ]

        for patch in self.patches:
            patch.start()

        self.addCleanup(self.stop_patches)

    def stop_patches(self):
        for patch in self.patches:
            patch.stop()

    def test_provisioned_host_is_ready(self):
        readiness = evaluate_host_readiness(
            config(),
            hardware=hardware(),
        )

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["blocking"], [])
        self.assertEqual(
            readiness["schema_version"],
            HOST_READINESS_SCHEMA_VERSION,
        )

    def test_host_is_detected_and_reported(self):
        readiness = evaluate_host_readiness(
            config(),
            hardware=hardware(),
        )

        host = readiness["host"]

        self.assertEqual(
            host["operating_system"],
            "Linux",
        )
        self.assertEqual(
            host["architecture"],
            "x86_64",
        )
        self.assertEqual(host["cpu_cores"], 128)
        self.assertEqual(host["ram_total_gb"], 755.0)
        self.assertEqual(
            host["accelerators"][0]["name"],
            "NVIDIA GeForce RTX 5090",
        )

    def test_configuration_decides_which_runtimes_matter(self):
        # A host with no frontend configured must not be penalised
        # for lacking one.
        without = evaluate_host_readiness(
            config(frontend_enabled=False),
            hardware=hardware(),
        )

        names = [
            check["name"]
            for check in without["checks"]
        ]

        self.assertIn("vllm runtime", names)
        self.assertIn(
            "platform_tools runtime",
            names,
        )
        self.assertNotIn("openwebui runtime", names)

        with_frontend = evaluate_host_readiness(
            config(frontend_enabled=True),
            hardware=hardware(),
        )

        self.assertIn(
            "openwebui runtime",
            [
                check["name"]
                for check in with_frontend["checks"]
            ],
        )

    def test_model_selection_is_out_of_scope(self):
        # The decisive semantic: a fresh host with no model is a ready
        # SERVER. ./ai preflight owns the model question.
        readiness = evaluate_host_readiness(
            config(),
            hardware=hardware(),
        )

        self.assertTrue(readiness["ready"])

        for check in readiness["checks"]:
            self.assertNotIn(
                "model",
                check["name"].lower(),
            )

        self.assertIn(
            "model selection is not",
            readiness["scope"],
        )

    def test_no_accelerator_detected_is_reported(self):
        readiness = evaluate_host_readiness(
            config(),
            hardware=hardware(gpus=[]),
        )

        self.assertEqual(
            readiness["host"]["accelerators"],
            [],
        )


class UnreadyHostTests(unittest.TestCase):
    def test_unprovisioned_runtime_blocks_readiness(self):
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
            lambda name: name != "vllm",
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            readiness = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        self.assertFalse(readiness["ready"])
        self.assertEqual(
            readiness["blocking"],
            ["vllm runtime"],
        )

        check = next(
            entry
            for entry in readiness["checks"]
            if entry["name"] == "vllm runtime"
        )

        self.assertEqual(check["status"], "fail")
        self.assertIn(
            "./ai prepare",
            check["detail"],
        )

    def test_missing_accelerator_blocks_readiness(self):
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
                "status": "fail",
                "detail": (
                    "nvidia-smi was not found."
                ),
            },
        ), mock.patch.object(
            host_readiness,
            "runtime_is_ready",
            lambda name: True,
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            readiness = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        self.assertFalse(readiness["ready"])
        self.assertIn(
            "NVIDIA GPU",
            readiness["blocking"],
        )

    def test_missing_interpreter_blocks_readiness(self):
        with mock.patch.object(
            host_readiness,
            "check_command",
            lambda name: {
                "name": f"{name} command",
                "status": "fail",
                "detail": "not found",
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
            lambda name: True,
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            readiness = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        self.assertFalse(readiness["ready"])
        self.assertIn(
            "python3 command",
            readiness["blocking"],
        )


class SideEffectTests(unittest.TestCase):
    def test_evaluation_is_read_only(self):
        # Safe to run repeatedly: it provisions nothing and creates
        # nothing.
        def forbidden(*args, **kwargs):
            raise AssertionError(
                "host readiness must not provision or create state"
            )

        with mock.patch(
            "core.runtime_manager.ensure_runtime",
            forbidden,
        ), mock.patch(
            "pathlib.Path.mkdir",
            forbidden,
        ), mock.patch(
            "subprocess.run",
            forbidden,
        ), mock.patch.object(
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
            lambda name: True,
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            first = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )
            second = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        self.assertEqual(first, second)

    def test_detection_is_only_performed_when_not_supplied(self):
        with mock.patch.object(
            host_readiness,
            "inspect_hardware",
            side_effect=AssertionError(
                "hardware was supplied; detection must be skipped"
            ),
        ), mock.patch.object(
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
            lambda name: True,
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            readiness = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        self.assertTrue(readiness["ready"])

    def test_result_is_plain_serializable_data(self):
        import json

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
            lambda name: True,
        ), mock.patch.object(
            host_readiness,
            "runtime_executable",
            lambda name: "/x",
        ):
            readiness = evaluate_host_readiness(
                config(),
                hardware=hardware(),
            )

        restored = json.loads(
            json.dumps(readiness)
        )

        self.assertTrue(restored["ready"])
        self.assertEqual(
            restored["schema_version"],
            HOST_READINESS_SCHEMA_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
