def build_model_identity(plan, config):
    """
    Build a normalized identity for the currently selected model.

    This distinguishes:
    - stored/local model identity
    - logical model name exposed to clients
    - inference provider

    PROVISIONAL:
    Routing and external-provider identities do not exist yet.
    The structure is designed so they can be added later.
    """

    selected = plan.get("selected_model")

    if selected is None:
        return None

    return {
        "logical_name": (
            config["inference"]["served_model_name"]
        ),

        "model_id": selected["name"],

        "source": {
            "type": "local",
            "path": selected["path"],
        },

        "provider": (
            config["inference"]["provider"]
        ),

        "metadata": {
            "architecture": selected.get(
                "architecture"
            ),
            "model_type": selected.get(
                "model_type"
            ),
            "quantization": selected.get(
                "quantization_method"
            ),
        },
    }


def build_service_identity(service):
    """
    Normalize identity for one platform service.

    Provider-specific settings remain outside this identity.
    """

    return {
        "service_id": service["id"],
        "role": service["role"],
        "provider": service["provider"],
        "enabled": service["enabled"],
    }
