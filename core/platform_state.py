from datetime import datetime, timezone

from core.config import load_config
from core.planner import build_initial_plan
from core.deployment import build_deployment_manifest
from core.status import get_runtime_status
from core.health import check_deployment_health
from core.identity import build_model_identity, build_service_identity


# PROVISIONAL SCHEMA VERSION:
# This gives future API/UI consumers an explicit contract version.
# We can evolve the contents later without pretending the shape is permanent.
PLATFORM_STATE_SCHEMA_VERSION = 1


def build_platform_state():
    """
    Build one normalized view of the current AI platform.

    This intentionally separates:

    desired
        what the platform intends to run

    observed
        what is actually running

    health
        whether the running service is functionally healthy

    Future Platform API and Admin UI layers should consume this
    normalized state rather than calling individual implementation
    modules directly.
    """

    config = load_config()
    plan = build_initial_plan()

    manifest = build_deployment_manifest(
        plan,
        config,
    )

    model_identity = build_model_identity(
        plan,
        config,
    )

    runtime_status = get_runtime_status(
        plan,
        config,
    )

    health_results = check_deployment_health(
        manifest
    )

    runtime_by_service = {
        item["id"]: item
        for item in runtime_status
    }

    health_by_service = {
        item["service"]: item
        for item in health_results
    }

    services = []

    for service in manifest["services"]:
        service_id = service["id"]
        role = service["role"]

        runtime = runtime_by_service.get(service_id)
        health = health_by_service.get(service_id)

        observed = {
            "running": (
                runtime["running"]
                if runtime
                else False
            ),
            "host": (
                runtime["host"]
                if runtime
                else None
            ),
            "port": (
                runtime["port"]
                if runtime
                else None
            ),
        }

        if health is not None:
            normalized_health = {
                "healthy": health["healthy"],
                "detail": health["detail"],
            }

        elif not service["enabled"]:
            normalized_health = {
                "healthy": None,
                "detail": (
                    "No process is required for "
                    "this service configuration."
                ),
            }

        else:
            normalized_health = {
                "healthy": None,
                "detail": "Health has not been observed.",
            }

        services.append({
            "id": service_id,
            "role": role,
            "provider": service["provider"],
            "enabled": service["enabled"],

            "identity": build_service_identity(
                service
            ),

            # Adapter/provider-specific details remain nested here.
            # The generic platform layer does not need to understand them.
            "desired": {
                "spec": service["spec"],
            },

            "observed": observed,
            "health": normalized_health,
        })

    return {
        "schema_version": PLATFORM_STATE_SCHEMA_VERSION,
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "platform": {
            "stage": manifest["stage"],
        },

        "hardware": plan["hardware"],

        "model": {
            "identity": model_identity,
            "selected": plan["selected_model"],
            "selection_reason": plan["model_reason"],
        },

        "planning": {
            "capacity": plan["capacity"],
            "preliminary_fit": plan["preliminary_fit"],

            "performance": {
                "requested": (
                    plan["performance_requested"]
                ),
                "effective": plan["performance"],
                "recommendations": (
                    plan[
                        "performance_recommendations"
                    ]
                ),
                "settings": plan["performance_settings"],
            },
        },

        "deployment": {
            "runtime": manifest["runtime"],
            "model": manifest["model"],
            "services": services,
        },
    }
