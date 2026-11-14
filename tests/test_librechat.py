import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapters.frontend.librechat as librechat_adapter
import adapters.frontend.openwebui as openwebui_adapter
from adapters.executor.docker import DockerExecutor
from adapters.frontend import get_frontend_adapter
from adapters.frontend.librechat import (
    build_service_spec,
    render_librechat_yaml,
    write_librechat_config,
)
from core.health import check_service_health

GATEWAY_URL = "http" + "://127.0.0.1:8080"


class LibreChatFrontendTests(unittest.TestCase):
    def _sample_config(self, data_root="/var/lib/ai-stack"):
        return {
            "network": {
                "frontend_host": "127.0.0.1",
                "frontend_port": 3080,
                "gateway_host": "127.0.0.1",
                "gateway_port": 8080,
            },
            "platform": {
                "data_root": data_root,
            },
        }

    def test_frontend_adapter_registry(self):
        self.assertIs(get_frontend_adapter("librechat"), librechat_adapter)
        self.assertIs(get_frontend_adapter("openwebui"), openwebui_adapter)

    def test_build_service_spec_enabled_and_disabled(self):
        config = self._sample_config()
        plan = {"frontend": {"enabled": True, "provider": "librechat"}}
        spec = build_service_spec(plan, config)
        self.assertIsNotNone(spec)
        self.assertEqual(spec["provider"], "librechat")
        self.assertEqual(spec["upstream"], GATEWAY_URL)
        self.assertTrue(spec["data_dir"].endswith("/librechat-data"))
        self.assertTrue(spec["mongo_data_dir"].endswith("/librechat-mongo"))
        self.assertTrue(spec["config_path"].endswith("/librechat-data/librechat.yaml"))

        disabled_plan = {"frontend": {"enabled": False, "provider": "librechat"}}
        self.assertIsNone(build_service_spec(disabled_plan, config))

    def test_write_and_render_librechat_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = os.path.join(tmpdir, "librechat-data")
            config_path = os.path.join(tmpdir, "librechat-data", "librechat.yaml")
            write_librechat_config( data_dir,GATEWAY_URL)
            content = Path(config_path).read_text(encoding="utf-8")
            self.assertIn(f'baseURL: "{GATEWAY_URL}/v1"', content)

        rendered = render_librechat_yaml(f"{GATEWAY_URL}/v1")
        self.assertIn(f'baseURL: "{GATEWAY_URL}/v1"', rendered)
        self.assertNotIn("/v1/v1", rendered)

    def test_docker_executor_librechat_and_openwebui(self):
        executor = DockerExecutor()
        librechat_manifest = {
            "services": [
                {
                    "role": "frontend",
                    "enabled": True,
                    "provider": "librechat",
                    "spec": {
                        "network": {"host": "127.0.0.1", "port": 3080},
                        "upstream": GATEWAY_URL,
                        "data_dir": "/var/lib/ai-stack/librechat-data",
                        "mongo_data_dir": "/var/lib/ai-stack/librechat-mongo",
                        "config_path": "/var/lib/ai-stack/librechat-data/librechat.yaml",
                    },
                }
            ]
        }
        cmds = executor.build_deployment_commands(librechat_manifest)
        self.assertEqual(len(cmds), 2)
        joined = "\n".join(cmds)
        self.assertIn("ai-stack-librechat-mongo", joined)
        self.assertIn("/var/lib/ai-stack/librechat-mongo:/data/db", joined)
        self.assertIn("ai-stack-frontend", joined)
        self.assertIn("MONGO_URI=", joined)
        self.assertIn("librechat.yaml", joined)

        openwebui_manifest = {
            "services": [
                {
                    "role": "inference",
                    "provider": "vllm",
                    "enabled": True,
                    "spec": {"network": {"host": "127.0.0.1", "port": 8000}, "model_path": "/models/test"},
                },
                {
                    "role": "frontend",
                    "enabled": True,
                    "provider": "openwebui",
                    "spec": {
                        "network": {"host": "127.0.0.1", "port": 3000},
                        "upstream": GATEWAY_URL,
                        "data_dir": "/var/lib/ai-stack/openwebui-data",
                    },
                },
            ]
        }
        ow_cmds = executor.build_deployment_commands(openwebui_manifest)
        frontend_cmds = [c for c in ow_cmds if "ai-stack-frontend" in c or "ai-stack-librechat-mongo" in c]
        self.assertEqual(len(frontend_cmds), 1)
        self.assertIn("ai-stack-frontend", frontend_cmds[0])
        self.assertNotIn("ai-stack-librechat-mongo", "\n".join(ow_cmds))

    def test_check_service_health_librechat(self):
        service = {
            "id": "frontend",
            "provider": "librechat",
            "spec": {"network": {"host": "127.0.0.1", "port": 3080}},
        }
        with patch("core.health.http_get", return_value={"ok": True, "status_code": 200, "error": None}) as mock_get:
            result = check_service_health(service)
        mock_get.assert_called_once()
        self.assertEqual(result["provider"], "librechat")
        self.assertTrue(result["healthy"])


if __name__ == "__main__":
    unittest.main()
