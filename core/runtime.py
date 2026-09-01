def build_runtime_spec(plan):
    services = []

    inference = plan["inference"]
    services.append({
        "role": "inference",
        "provider": inference["provider"],
        "enabled": True
    })

    gateway = plan["gateway"]
    services.append({
        "role": "gateway",
        "provider": gateway["provider"],
        "enabled": gateway["provider"] != "direct"
    })

    frontend = plan["frontend"]
    services.append({
        "role": "frontend",
        "provider": frontend["provider"],
        "enabled": frontend["enabled"]
    })

    return {
        "services": services,
        "model": (
            plan["selected_model"]["name"]
            if plan["selected_model"]
            else None
        )
    }
