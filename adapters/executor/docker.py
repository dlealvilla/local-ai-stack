class DockerExecutor:
    """
    Docker deployment executor.

    It can translate the complete deployment manifest into
    Docker commands.

    This remains preview-only for now.
    """

    name = "docker"
    network_name = "ai-stack-network"

    def build_inference_command(self, service):
        spec = service["spec"]

        model = spec["model"]
        network = spec["network"]
        performance = spec["performance"]

        image = "vllm/vllm-openai:v0.10.2"

        return [
            "docker", "run",
            "-d",
            "--rm",
            "--name", "ai-stack-inference",
            "--network", self.network_name,
            "--gpus", "all",
            "--ipc=host",

            "-v",
            "/workspace/models:/workspace/models:ro",

            "-p",
            f"{network['host']}:{network['port']}:{network['port']}",

            image,

            "--model", model["path"],
            "--served-model-name", model["served_name"],

            "--host", "0.0.0.0",
            "--port", str(network["port"]),

            "--max-model-len",
            str(performance["context_length"]),

            "--gpu-memory-utilization",
            str(performance["gpu_memory_utilization"]),
        ]


    def build_frontend_command(self, service, manifest):
        spec = service["spec"]
        network = spec["network"]

        # Version currently comes from our bootstrap configuration.
        image = "ghcr.io/open-webui/open-webui:v0.11.0"

        inference = next(
            item
            for item in manifest["services"]
            if item["role"] == "inference"
        )

        inference_port = inference["spec"]["network"]["port"]

        upstream = (
            f"http://ai-stack-inference:"
            f"{inference_port}/v1"
        )

        return [
            "docker", "run",
            "-d",
            "--rm",
            "--name", "ai-stack-frontend",
            "--network", self.network_name,

            "-p",
            f"{network['host']}:{network['port']}:8080",

            "-v",
            "/workspace/open-webui-data:/app/backend/data",

            "-e",
            f"OPENAI_API_BASE_URL={upstream}",

            "-e",
            "OPENAI_API_KEY=none",

            image,
        ]


    def build_command(self, service_spec):
        """
        Compatibility method for the earlier inference-only code.
        """

        fake_service = {
            "role": "inference",
            "provider": service_spec["provider"],
            "spec": service_spec,
        }

        return self.build_inference_command(fake_service)


    def preview(self, service_spec):
        return " ".join(
            self.build_command(service_spec)
        )


    def build_deployment_commands(self, manifest):
        commands = []

        # Shared private network for communication between containers.
        commands.append([
            "docker",
            "network",
            "create",
            self.network_name,
        ])

        for service in manifest["services"]:
            if not service["enabled"]:
                continue

            if service["role"] == "inference":
                command = self.build_inference_command(
                    service
                )

            elif service["role"] == "frontend":
                command = self.build_frontend_command(
                    service,
                    manifest
                )

            else:
                raise ValueError(
                    "Docker execution is not yet implemented "
                    f"for service role: {service['role']}"
                )

            commands.append(command)

        return commands


    def preview_deployment(self, manifest):
        return [
            " ".join(command)
            for command in self.build_deployment_commands(manifest)
        ]
