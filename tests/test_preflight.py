import unittest
from unittest.mock import call, patch

from core.preflight import run_preflight


class PreflightTests(unittest.TestCase):
    @staticmethod
    def make_config(
        gateway_provider="builtin_proxy",
        platform_api_enabled=True,
        frontend_enabled=True,
    ):
        return {
            "platform": {"data_root": "/workspace"},
            "frontend": {"enabled": frontend_enabled},
            "gateway": {"provider": gateway_provider},
            "network": {
                "inference_host": "127.0.0.1",
                "inference_port": 8000,
                "frontend_host": "127.0.0.1",
                "frontend_port": 3000,
                "api_host": "127.0.0.1",
                "api_port": 4000,
            },
            "platform_api": {
                "enabled": platform_api_enabled,
                "host": "127.0.0.1",
                "port": 4100,
            },
        }

    @staticmethod
    def port_result(host, port):
        return {
            "name": f"Port {host}:{port}",
            "status": "pass",
            "detail": "Available.",
        }

    def run_preflight_with_port_probe(self, config):
        with (
            patch("core.preflight.check_command", return_value={}),
            patch("core.preflight.resolve_vllm_executable", return_value="/usr/bin/vllm"),
            patch("core.preflight.check_nvidia_gpu", return_value={}),
            patch("core.preflight.check_path", return_value={}),
            patch(
                "core.preflight.check_port_available",
                side_effect=self.port_result,
            ) as port_probe,
        ):
            checks = run_preflight(
                {"runtime": {"executor": "process"}, "model": None},
                config,
            )

        return checks, port_probe

    def test_checks_ports_for_enabled_gateway_and_platform_api(self):
        _, port_probe = self.run_preflight_with_port_probe(self.make_config())

        self.assertEqual(
            [
                call("127.0.0.1", 8000),
                call("127.0.0.1", 3000),
                call("127.0.0.1", 4000),
                call("127.0.0.1", 4100),
            ],
            port_probe.call_args_list,
        )

    def test_skips_unused_direct_gateway_and_disabled_platform_api_ports(self):
        checks, port_probe = self.run_preflight_with_port_probe(
            self.make_config(
                gateway_provider="direct",
                platform_api_enabled=False,
            )
        )

        self.assertEqual(
            [
                call("127.0.0.1", 8000),
                call("127.0.0.1", 3000),
            ],
            port_probe.call_args_list,
        )
        checked_names = {check.get("name") for check in checks}
        self.assertNotIn("Port 127.0.0.1:4000", checked_names)
        self.assertNotIn("Port 127.0.0.1:4100", checked_names)


if __name__ == "__main__":
    unittest.main()
