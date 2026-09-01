def build_service_spec(plan, config):
    """
    Minimal process-backed AI gateway.

    PROVISIONAL:
    Currently forwards requests to one local inference backend.
    """

    network = config["network"]

    endpoint = {
        "host": network["api_host"],
        "port": network["api_port"],
    }

    analytics = config.get(
        "analytics",
        {},
    )

    return {
        "role": "gateway",
        "provider": "builtin_proxy",
        "process_required": True,

        "network": endpoint,
        "endpoint": endpoint,

        "upstream": {
            "host": network["inference_host"],
            "port": network["inference_port"],
        },

        "analytics": {
            "enabled": analytics.get(
                "enabled",
                False,
            ),
            "provider": analytics.get(
                "provider"
            ),
        },
    }
