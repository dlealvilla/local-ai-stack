from core.hardware import inspect_hardware
from core.models import list_local_models
from core.config import load_config
from core.requirements import estimate_model_requirements
from core.workload import resolve_workload
from core.settings import build_performance_settings
from adapters.inference import get_inference_adapter


def collect_deployment_context():
    return {
        "hardware": inspect_hardware(),
        "models": list_local_models(),
        "config": load_config()
    }


def classify_preliminary_fit(hardware, requirements, weight_capacity):
    if not hardware["gpus"]:
        return {
            "status": "blocked",
            "reason": "No supported GPU was detected."
        }

    if requirements is None:
        return {
            "status": "unknown",
            "reason": "No model has been selected."
        }

    fits = weight_capacity["weight_files_fit_in_total_vram"]

    if fits is False:
        return {
            "status": "blocked",
            "reason": (
                "The model weight files alone are larger than the "
                "total detected GPU VRAM."
            )
        }

    if fits is True:
        return {
            "status": "candidate",
            "reason": (
                "The model weights fit within total detected GPU VRAM. "
                "Runtime memory requirements still need to be evaluated."
            )
        }

    return {
        "status": "unknown",
        "reason": "There is not enough information to assess the model."
    }


def build_initial_plan():
    context = collect_deployment_context()

    hardware = context["hardware"]
    models = context["models"]
    config = context["config"]

    requested_model = config["model"]["selection"]
    workload = resolve_workload(config)

    selected_model = None
    model_reason = None

    if requested_model == "auto":
        if len(models) == 1:
            selected_model = models[0]
            model_reason = "Exactly one local model is available."
        elif len(models) == 0:
            model_reason = "No local models are available."
        else:
            model_reason = (
                "Multiple local models are available, so automatic selection "
                "has been left unresolved."
            )
    else:
        for model in models:
            if model["name"] == requested_model:
                selected_model = model
                model_reason = "The model was explicitly selected in configuration."
                break

        if selected_model is None:
            model_reason = (
                f"The configured model '{requested_model}' was not found locally."
            )

    capacity = {
        "gpu_available": False,
        "gpu_count": len(hardware["gpus"]),
        "gpu_vram_total_gb": None,
        "gpu_vram_free_gb_observed": None,
        "model_size_gb": None
    }

    if hardware["gpus"]:
        capacity["gpu_available"] = True
        capacity["gpu_vram_total_gb"] = sum(
            gpu["vram_total_gb"] for gpu in hardware["gpus"]
        )
        capacity["gpu_vram_free_gb_observed"] = sum(
            gpu["vram_free_gb"] for gpu in hardware["gpus"]
        )

    requirements = None
    weight_capacity = {
        "weight_files_fit_in_total_vram": None,
        "total_vram_after_weights_gb": None,
        "weight_to_total_vram_ratio": None,
        "warning": (
            "This compares model weight-file size with total GPU VRAM only. "
            "It is a static capacity check, not a complete runtime-fit calculation."
        )
    }

    model_limits = {
        "max_context_length": None
    }

    if selected_model:
        capacity["model_size_gb"] = selected_model["size_gb"]

        model_limits["max_context_length"] = (
            selected_model.get("max_position_embeddings")
        )

        requirements = estimate_model_requirements(selected_model)

        if capacity["gpu_vram_total_gb"] is not None:
            weight_size = requirements["weight_size_gb"]
            total_vram = capacity["gpu_vram_total_gb"]

            weight_capacity["weight_files_fit_in_total_vram"] = (
                weight_size < total_vram
            )
            weight_capacity["total_vram_after_weights_gb"] = (
                total_vram - weight_size
            )

            if total_vram > 0:
                weight_capacity["weight_to_total_vram_ratio"] = (
                    weight_size / total_vram
                )

    preliminary_fit = classify_preliminary_fit(
        hardware,
        requirements,
        weight_capacity
    )

    requested_performance = dict(config["performance"])
    resolved_performance = dict(requested_performance)
    performance_recommendations = {}

    inference_provider = config["inference"]["provider"]
    inference_adapter = get_inference_adapter(inference_provider)

    if requested_performance["gpu_memory_utilization"] == "auto":
        recommendation = (
            inference_adapter.recommend_gpu_memory_utilization(hardware)
        )

        resolved_performance["gpu_memory_utilization"] = (
            recommendation["value"]
        )

        performance_recommendations["gpu_memory_utilization"] = (
            recommendation
        )

    performance_settings = (
        build_performance_settings(
            requested=requested_performance,
            effective=resolved_performance,
            recommendations=performance_recommendations,
        )
    )

    return {
        "hardware": hardware,
        "selected_model": selected_model,
        "model_reason": model_reason,
        "capacity": capacity,
        "requirements": requirements,
        "model_limits": model_limits,
        "weight_capacity": weight_capacity,
        "preliminary_fit": preliminary_fit,
        "workload": workload,
        "performance_requested": requested_performance,
        "performance": resolved_performance,
        "performance_recommendations": performance_recommendations,
        "performance_settings": performance_settings,
        "frontend": config["frontend"],
        "gateway": config["gateway"],
        "inference": config["inference"]
    }
