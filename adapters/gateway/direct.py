def build_service_spec(plan, config):
    """
    Direct gateway mode.

    No separate gateway process exists.
    Clients connect directly to the inference API.
    """

    network = config["network"]

    return {
        "role": "gateway",
        "provider": "direct",

        "process_required": False,

        "upstream": {
            "host": network["inference_host"],
            "port": network["inference_port"],
        },

        "endpoint": {
            "host": network["inference_host"],
            "port": network["inference_port"],
        },
    }
