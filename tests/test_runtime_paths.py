import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core import runtime_paths


class RuntimePathTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        # Redirect fixed /opt paths into the test tree, even on a deployed machine.
        self.paths = patch.object(
            runtime_paths, "Path",
            side_effect=lambda path: self.root / path.lstrip("/") if path.startswith("/opt/") else Path(path),
        )
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def executable(self, name, *, runnable=True):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n")
        path.chmod(0o700 if runnable else 0o600)
        return str(path)

    def test_runtimes_check_override_then_managed_then_system(self):
        for resolver, env, command, directory in (
            (runtime_paths.resolve_vllm_executable, "AI_VLLM_EXECUTABLE", "vllm", "vllm"),
            (runtime_paths.resolve_openwebui_executable, "AI_OPENWEBUI_EXECUTABLE", "open-webui", "openwebui"),
        ):
            with self.subTest(command=command):
                override = self.executable(f"{command}/override")
                managed = self.executable(f"opt/ai-stack/runtime/{directory}/.venv/bin/{command}")
                system = self.executable(f"{command}/system")
                with patch.dict(os.environ, {env: override}, clear=True), patch.object(runtime_paths.shutil, "which", return_value=system):
                    self.assertEqual(override, resolver())
                    Path(override).chmod(0o600)
                    self.assertEqual(managed, resolver())
                    Path(managed).unlink()
                    self.assertEqual(system, resolver())
                    Path(system).chmod(0o600)
                    self.assertIsNone(resolver())

    def test_platform_tools_use_override_or_managed_python(self):
        override = self.executable("python/override", runnable=False)
        managed = self.executable("opt/ai-stack/runtime/platform_tools/.venv/bin/python")
        with patch.dict(os.environ, {"AI_PLATFORM_TOOLS_PYTHON": override}, clear=True):
            self.assertEqual(managed, runtime_paths.resolve_platform_tools_python())
            Path(override).chmod(0o700)
            self.assertEqual(override, runtime_paths.resolve_platform_tools_python())
            Path(override).unlink()
            Path(managed).unlink()
            self.assertIsNone(runtime_paths.resolve_platform_tools_python())
