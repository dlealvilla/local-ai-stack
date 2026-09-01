from adapters.gateway import (
    resolve_gateway_endpoint,
)


def build_service_spec(plan, config):
    frontend = plan["frontend"]
    network = config["network"]

    if not frontend["enabled"]:
        return None

    gateway_endpoint = (
        resolve_gateway_endpoint(
            plan,
            config,
        )
    )

    return {
        "role": "frontend",
        "provider": "openwebui",

        "network": {
            "host": network["frontend_host"],
            "port": network["frontend_port"],
        },

        # Open WebUI now talks to the logical AI endpoint.
        # It no longer needs to know where vLLM lives.
        "upstream": gateway_endpoint,

        "data_dir": (
            config["platform"]["data_root"]
            + "/open-webui-data"
        ),
    }
