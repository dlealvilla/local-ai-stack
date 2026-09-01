import os
import subprocess
import sys

from core.runtime_paths import (
    resolve_openwebui_executable,
    resolve_vllm_executable,
)


class ProcessExecutor:
    name = "process"

    def build_command(self, service_spec):
        provider = service_spec["provider"]

        if provider == "vllm":
            return self._build_vllm_command(
                service_spec
            )

        if provider == "openwebui":
            return self._build_openwebui_command(
                service_spec
            )

        if provider == "builtin_http":
            return self._build_platform_api_command(
                service_spec
            )

        if provider == "builtin_proxy":
            return self._build_gateway_command(
                service_spec
            )

        raise ValueError(
            f"ProcessExecutor does not yet support: "
            f"{provider}"
        )


    def _build_vllm_command(self, spec):
        executable = resolve_vllm_executable()

        if executable is None:
            raise RuntimeError(
                "No usable native vLLM runtime found."
            )

        model = spec["model"]
        network = spec["network"]
        performance = spec["performance"]

        return [
            executable,
            "serve",
            model["path"],

            "--served-model-name",
            model["served_name"],

            "--host",
            network["host"],

            "--port",
            str(network["port"]),

            "--max-model-len",
            str(performance["context_length"]),

            "--gpu-memory-utilization",
            str(
                performance[
                    "gpu_memory_utilization"
                ]
            ),
        ]


    def _build_openwebui_command(self, spec):
        executable = resolve_openwebui_executable()

        if executable is None:
            raise RuntimeError(
                "No usable native Open WebUI "
                "runtime found."
            )

        network = spec["network"]

        return [
            executable,
            "serve",

            "--host",
            network["host"],

            "--port",
            str(network["port"]),
        ]


    def _build_gateway_command(self, spec):
        # PROVISIONAL:
        # Built-in gateway currently runs directly from product source.
        return [
            sys.executable,
            "-m",
            "gateway_service.server",
        ]


    def _build_platform_api_command(self, spec):
        # PROVISIONAL:
        # Platform API currently runs directly from product source
        # using the controller's Python interpreter.
        return [
            sys.executable,
            "-m",
            "platform_api.server",
        ]


    def build_environment(self, service_spec):
        environment = os.environ.copy()

        if service_spec["provider"] == "openwebui":
            upstream = service_spec["upstream"]

            environment["DATA_DIR"] = (
                service_spec["data_dir"]
            )

            environment[
                "OPENAI_API_BASE_URL"
            ] = (
                f"http://{upstream['host']}:"
                f"{upstream['port']}/v1"
            )

            environment[
                "OPENAI_API_KEY"
            ] = "none"

        return environment


    def preview(self, service_spec):
        return " ".join(
            self.build_command(service_spec)
        )


    def start(self, service_spec):
        return subprocess.Popen(
            self.build_command(service_spec),
            env=self.build_environment(
                service_spec
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
