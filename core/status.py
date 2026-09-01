import socket

from core.deployment import build_deployment_manifest


def check_port(host, port, timeout=1.0):
    try:
        with socket.create_connection(
            (host, port),
            timeout=timeout,
        ):
            return True
    except (
        ConnectionRefusedError,
        TimeoutError,
        OSError,
    ):
        return False


def get_manifest_runtime_status(manifest):
    """
    Observe enabled network services generically.

    This avoids teaching status logic about specific providers.
    """

    services = []

    for service in manifest["services"]:
        if not service["enabled"]:
            continue

        spec = service.get("spec") or {}
        network = spec.get("network")

        if not network:
            continue

        host = network["host"]
        port = network["port"]

        services.append({
            "id": service["id"],
            "role": service["role"],
            "provider": service["provider"],
            "host": host,
            "port": port,
            "running": check_port(
                host,
                port,
            ),
        })

    return services


def get_runtime_status(plan, config):
    # Backward-compatible entry point used by the existing CLI.
    manifest = build_deployment_manifest(
        plan,
        config,
    )

    return get_manifest_runtime_status(
        manifest
    )
