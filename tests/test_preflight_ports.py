import unittest
from unittest.mock import patch

from core.preflight import run_preflight


def _manifest():
    return {
        "runtime": {"executor": "docker"},
        "model": None,
    }


def _config(*, gateway_provider="builtin_proxy", frontend_enabled=True, platform_api_enabled=True):
    return {
        "platform": {"data_root": "/tmp/data"},
        "network": {
            "inference_host": "127.0.0.1",
            "inference_port": 8000,
            "api_host": "127.0.0.1",
            "api_port": 4000,
            "frontend_host": "127.0.0.1",
            "frontend_port": 3000,
        },
        "gateway": {"provider": gateway_provider},
        "frontend": {"enabled": frontend_enabled},
        "platform_api": {
            "enabled": platform_api_enabled,
            "host": "127.0.0.1",
            "port": 4100,
        },
    }


class PreflightPortTests(unittest.TestCase):
    def test_run_preflight_checks_gateway_and_platform_api_ports_when_enabled(self):
        with (
            patch("core.preflight.check_command", return_value={"name": "docker", "status": "pass", "detail": ""}),
            patch("core.preflight.check_docker_daemon", return_value={"name": "daemon", "status": "pass", "detail": ""}),
            patch("core.preflight.check_nvidia_gpu", return_value={"name": "gpu", "status": "pass", "detail": ""}),
            patch("core.preflight.check_path", return_value={"name": "path", "status": "pass", "detail": ""}),
            patch(
                "core.preflight.check_port_available",
                side_effect=lambda host, port: {"name": f"Port {host}:{port}", "status": "pass", "detail": ""},
            ) as mock_port,
        ):
            checks = run_preflight(_manifest(), _config())

        self.assertEqual(
            [
                ("127.0.0.1", 8000),
                ("127.0.0.1", 4000),
                ("127.0.0.1", 3000),
                ("127.0.0.1", 4100),
            ],
            [call.args for call in mock_port.call_args_list],
        )
        names = [c["name"] for c in checks]
        self.assertIn("Port 127.0.0.1:4000", names)
        self.assertIn("Port 127.0.0.1:4100", names)

    def test_run_preflight_skips_direct_gateway_and_disabled_platform_api_ports(self):
        with (
            patch("core.preflight.check_command", return_value={"name": "docker", "status": "pass", "detail": ""}),
            patch("core.preflight.check_docker_daemon", return_value={"name": "daemon", "status": "pass", "detail": ""}),
            patch("core.preflight.check_nvidia_gpu", return_value={"name": "gpu", "status": "pass", "detail": ""}),
            patch("core.preflight.check_path", return_value={"name": "path", "status": "pass", "detail": ""}),
            patch(
                "core.preflight.check_port_available",
                side_effect=lambda host, port: {"name": f"Port {host}:{port}", "status": "pass", "detail": ""},
            ) as mock_port,
        ):
            run_preflight(
                _manifest(),
                _config(gateway_provider="direct", frontend_enabled=False, platform_api_enabled=False),
            )

        self.assertEqual([("127.0.0.1", 8000)], [call.args for call in mock_port.call_args_list])
