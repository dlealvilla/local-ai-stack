def build_service_spec(plan, config):
    api = config["platform_api"]

    return {
        "role": "platform_api",
        "provider": "builtin_http",

        "network": {
            "host": api["host"],
            "port": api["port"],
        },
    }
