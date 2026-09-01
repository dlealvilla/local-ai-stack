from adapters.inference import get_inference_adapter
from adapters.frontend import get_frontend_adapter
from adapters.gateway import get_gateway_adapter
from adapters.platform_api import get_platform_api_adapter


def build_deployment_manifest(plan, config):
    """
    Build a complete description of the desired AI deployment.

    This manifest describes WHAT should exist.
    Executors will later decide HOW those services are launched.
    """

    services = []

    # ---------------------------------------------------------
    # Inference service
    # ---------------------------------------------------------

    inference_provider = plan["inference"]["provider"]

    inference_adapter = get_inference_adapter(
        inference_provider
    )

    inference_spec = inference_adapter.build_service_spec(
        plan,
        config
    )

    services.append({
        "id": "inference",
        "role": "inference",
        "provider": inference_provider,
        "enabled": True,
        "spec": inference_spec,
    })

    # ---------------------------------------------------------
    # Gateway service
    # ---------------------------------------------------------

    gateway_provider = plan["gateway"]["provider"]

    gateway_adapter = get_gateway_adapter(
        gateway_provider
    )

    gateway_spec = gateway_adapter.build_service_spec(
        plan,
        config
    )

    services.append({
        "id": "gateway",
        "role": "gateway",
        "provider": gateway_provider,
        "enabled": gateway_spec["process_required"],
        "spec": gateway_spec,
    })

    # ---------------------------------------------------------
    # Frontend service
    # ---------------------------------------------------------

    frontend = plan["frontend"]

    frontend_spec = None

    if frontend["enabled"]:
        frontend_adapter = get_frontend_adapter(
            frontend["provider"]
        )

        frontend_spec = frontend_adapter.build_service_spec(
            plan,
            config
        )

    services.append({
        "id": "frontend",
        "role": "frontend",
        "provider": frontend["provider"],
        "enabled": frontend["enabled"],
        "spec": frontend_spec,
    })

    # ---------------------------------------------------------
    # Platform control API service
    # ---------------------------------------------------------

    platform_api_config = config["platform_api"]

    if platform_api_config["enabled"]:
        platform_api_provider = platform_api_config[
            "provider"
        ]

        platform_api_adapter = get_platform_api_adapter(
            platform_api_provider
        )

        platform_api_spec = (
            platform_api_adapter.build_service_spec(
                plan,
                config,
            )
        )

        services.append({
            "id": "platform_api",
            "role": "platform_api",
            "provider": platform_api_provider,
            "enabled": True,
            "spec": platform_api_spec,
        })

    return {
        "stage": config["platform"]["stage"],

        "runtime": {
            "executor": config["runtime"]["executor"],
        },

        "model": (
            {
                "name": plan["selected_model"]["name"],
                "path": plan["selected_model"]["path"],
            }
            if plan["selected_model"]
            else None
        ),

        "services": services,
    }
