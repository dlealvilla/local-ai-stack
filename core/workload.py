WORKLOAD_PROFILES = {
    "interactive": {
        "description": "Balanced interactive chat for multiple users.",
        "priority": "balanced",
        "latency_priority": "high",
        "throughput_priority": "medium",
        "concurrency_priority": "medium"
    },

    "personal": {
        "description": "Optimized primarily for one interactive user.",
        "priority": "latency",
        "latency_priority": "high",
        "throughput_priority": "low",
        "concurrency_priority": "low"
    },

    "throughput": {
        "description": "Optimized for serving many requests efficiently.",
        "priority": "throughput",
        "latency_priority": "medium",
        "throughput_priority": "high",
        "concurrency_priority": "high"
    }
}


def get_workload_profile(name):
    return WORKLOAD_PROFILES.get(name)


def resolve_workload(config):
    profile_name = config["performance"]["profile"]
    profile = get_workload_profile(profile_name)

    if profile is None:
        return {
            "name": profile_name,
            "valid": False,
            "reason": f"Unknown workload profile: {profile_name}"
        }

    return {
        "name": profile_name,
        "valid": True,
        **profile
    }
