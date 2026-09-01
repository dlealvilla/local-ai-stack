def recommend_gpu_memory_utilization(hardware):
    gpus = hardware.get("gpus", [])

    if not gpus:
        return {
            "value": None,
            "status": "blocked",
            "confidence": "high",
            "reason": "No NVIDIA GPU was detected."
        }

    # vLLM 0.10.2 uses 0.90 as its normal default.
    engine_default = 0.90

    # Use the most constrained GPU when several GPUs are present.
    free_ratios = [
        gpu["vram_free_gb"] / gpu["vram_total_gb"]
        for gpu in gpus
        if gpu["vram_total_gb"] > 0
    ]

    if not free_ratios:
        return {
            "value": engine_default,
            "status": "candidate",
            "confidence": "low",
            "reason": (
                "GPU memory availability could not be calculated, "
                "so the vLLM engine default is being proposed."
            )
        }

    minimum_free_ratio = min(free_ratios)

    # Preliminary safety margin.
    # We leave 5% of total VRAM outside the proposed vLLM allocation.
    safe_ceiling = max(0.0, minimum_free_ratio - 0.05)

    recommendation = min(engine_default, safe_ceiling)
    recommendation = round(recommendation, 2)

    if recommendation < 0.50:
        status = "warning"
    else:
        status = "candidate"

    return {
        "value": recommendation,
        "status": status,
        "confidence": "medium",
        "engine_default": engine_default,
        "reason": (
            "Starts from the vLLM default of 0.90 and lowers it when "
            "current GPU usage requires additional headroom. "
            "This is a preliminary recommendation and will later be "
            "validated by an actual model startup test."
        )
    }


def build_service_spec(plan, config):
    model = plan.get("selected_model")

    if model is None:
        raise ValueError("Cannot build vLLM service: no model is selected.")

    inference_config = config["inference"]
    network_config = config["network"]
    performance = plan["performance"]

    return {
        "role": "inference",
        "provider": "vllm",

        "model": {
            "name": model["name"],
            "path": model["path"],
            "served_name": inference_config["served_model_name"],
        },

        "network": {
            "host": network_config["inference_host"],
            "port": network_config["inference_port"],
        },

        "performance": {
            "context_length": performance["context_length"],
            "gpu_memory_utilization": performance["gpu_memory_utilization"],
            "concurrency": performance["concurrency"],
        },

        "features": {
            "tool_calling": inference_config["tool_calling"],
        },
    }
