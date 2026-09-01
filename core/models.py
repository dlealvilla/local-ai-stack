import os
import json


def get_model_root():
    data_root = os.environ.get("AI_DATA_ROOT", "/workspace")
    return os.path.join(data_root, "models")


def get_directory_size_gb(path):
    total_bytes = 0

    for root, dirs, files in os.walk(path):
        for filename in files:
            file_path = os.path.join(root, filename)

            try:
                total_bytes += os.path.getsize(file_path)
            except OSError:
                pass

    return total_bytes / (1024 ** 3)


def detect_weight_formats(path):
    formats = set()

    for filename in os.listdir(path):
        lower = filename.lower()

        if lower.endswith(".safetensors"):
            formats.add("safetensors")

        elif lower.endswith(".gguf"):
            formats.add("gguf")

        elif lower.endswith(".bin"):
            formats.add("bin")

    return sorted(formats)


def read_model_config(path):
    config_path = os.path.join(path, "config.json")

    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def inspect_model(name, path):
    config = read_model_config(path)
    weight_formats = detect_weight_formats(path)

    architectures = config.get("architectures", [])

    quantization = config.get("quantization_config", {})

    return {
        "name": name,
        "path": path,
        "size_gb": get_directory_size_gb(path),
        "has_config": bool(config),
        "weight_formats": weight_formats,
        "architecture": architectures[0] if architectures else None,
        "model_type": config.get("model_type"),
        "max_position_embeddings": config.get("max_position_embeddings"),

        "hidden_size": config.get("hidden_size"),
        "num_hidden_layers": config.get("num_hidden_layers"),
        "num_attention_heads": config.get("num_attention_heads"),
        "num_key_value_heads": config.get(
            "num_key_value_heads",
            config.get("num_attention_heads")
        ),
        "head_dim": config.get("head_dim"),
        "torch_dtype": config.get("torch_dtype"),

        "quantization_method": quantization.get("quant_method"),
        "looks_like_model": bool(config or weight_formats)
    }


def list_local_models():
    model_root = get_model_root()

    if not os.path.isdir(model_root):
        return []

    models = []

    for name in sorted(os.listdir(model_root)):
        path = os.path.join(model_root, name)

        if not os.path.isdir(path):
            continue

        model = inspect_model(name, path)

        if model["looks_like_model"]:
            models.append(model)

    return models
