from pathlib import Path


MODEL_METADATA_SCHEMA_VERSION = 1


def _first(
    model,
    *names,
):
    for name in names:
        value = model.get(name)

        if value is not None:
            return value

    return None


def _installed_size_bytes(model):
    value = _first(
        model,
        "size_bytes",
        "installed_size_bytes",
    )

    if value is not None:
        return int(value)

    size_gb = _first(
        model,
        "size_gb",
    )

    if size_gb is not None:
        return int(
            float(size_gb)
            * 1024 ** 3
        )

    return None


def _local_weight_format(model):
    explicit = _first(
        model,
        "weight_format",
        "weights_format",
        "weights",
    )

    if explicit:
        return explicit

    model_path = model.get(
        "path"
    )

    if not model_path:
        return None

    path = Path(
        model_path
    )

    if not path.exists():
        return None

    extensions = {
        file.suffix.lower()
        for file in path.rglob("*")
        if file.is_file()
    }

    if ".safetensors" in extensions:
        return "safetensors"

    if ".gguf" in extensions:
        return "gguf"

    if ".bin" in extensions:
        return "pytorch_bin"

    return None


def _hf_parameter_count(model):
    safetensors = (
        model.get("safetensors")
        or {}
    )

    parameters = (
        safetensors.get(
            "parameters"
        )
        or {}
    )

    if not isinstance(
        parameters,
        dict,
    ):
        return None

    total = parameters.get(
        "total"
    )

    if isinstance(
        total,
        (int, float),
    ):
        return int(total)

    numeric = [
        value
        for value in parameters.values()
        if isinstance(
            value,
            (int, float),
        )
    ]

    if numeric:
        return int(
            sum(numeric)
        )

    return None


def _hf_weight_format(model):
    siblings = (
        model.get("siblings")
        or []
    )

    names = []

    for sibling in siblings:
        if not isinstance(
            sibling,
            dict,
        ):
            continue

        name = (
            sibling.get("rfilename")
            or sibling.get("path")
        )

        if name:
            names.append(
                name.lower()
            )

    if any(
        name.endswith(".safetensors")
        for name in names
    ):
        return "safetensors"

    if any(
        name.endswith(".gguf")
        for name in names
    ):
        return "gguf"

    if any(
        name.endswith(".bin")
        for name in names
    ):
        return "pytorch_bin"

    return None


def _hf_quantization(model):
    config = (
        model.get("config")
        or {}
    )

    quantization_config = (
        config.get(
            "quantization_config"
        )
        or {}
    )

    method = (
        quantization_config.get(
            "quant_method"
        )
    )

    if method:
        return method

    tags = [
        str(tag).lower()
        for tag in (
            model.get("tags")
            or []
        )
    ]

    known = (
        "awq",
        "gptq",
        "gguf",
        "bnb",
        "bitsandbytes",
        "fp8",
    )

    for candidate in known:
        if candidate in tags:
            return candidate

    return None


def _hf_context_length(model):
    config = (
        model.get("config")
        or {}
    )

    for key in (
        "max_position_embeddings",
        "n_positions",
        "seq_length",
        "max_sequence_length",
    ):
        value = config.get(
            key
        )

        if isinstance(
            value,
            int,
        ):
            return value

    return None


def normalize_local_model(model):
    """
    Normalize an already-installed local model.
    """

    name = model["name"]

    return {
        "schema_version": (
            MODEL_METADATA_SCHEMA_VERSION
        ),

        "catalog_id": (
            f"local_files:{name}"
        ),

        "name": name,

        "family": _first(
            model,
            "model_type",
            "family",
        ),

        "architecture": _first(
            model,
            "architecture",
        ),

        "parameters": {
            "count": None,
        },

        "quantization": _first(
            model,
            "quantization_method",
            "quantization",
        ),

        "context_length": _first(
            model,
            "max_position_embeddings",
            "context_length",
        ),

        "source": {
            "provider": "local_files",
            "source_model_id": name,
            "revision": None,
            "license": None,
            "location": model.get(
                "path"
            ),
        },

        "size": {
            "download_bytes": None,

            "installed_bytes": (
                _installed_size_bytes(
                    model
                )
            ),
        },

        "format": {
            "weights": (
                _local_weight_format(
                    model
                )
            ),
        },

        "discovery": {
            "pipeline_tag": None,
            "library": None,
            "downloads": None,
            "gated": None,
            "private": False,
            "tags": [],
        },

        "runtime": {
            "supported": [],
        },

        "requirements": {
            "ram_bytes": None,
            "vram_bytes": None,
            "unified_memory_bytes": None,
        },

        "compatibility": {
            "status": "not_evaluated",
            "reasons": [],
            "recommendations": [],
        },
    }


def normalize_huggingface_model(
    model,
    *,
    base_url,
):
    """
    Normalize Hugging Face Hub metadata.

    Missing data remains None rather than being guessed.
    """

    repo_id = (
        model.get("id")
        or model.get("modelId")
    )

    if not repo_id:
        raise ValueError(
            "Hugging Face model is missing an ID."
        )

    config = (
        model.get("config")
        or {}
    )

    architectures = (
        config.get("architectures")
        or []
    )

    architecture = (
        architectures[0]
        if architectures
        else None
    )

    card_data = (
        model.get("cardData")
        or {}
    )

    used_storage = (
        model.get("usedStorage")
    )

    if not isinstance(
        used_storage,
        (int, float),
    ):
        used_storage = None

    return {
        "schema_version": (
            MODEL_METADATA_SCHEMA_VERSION
        ),

        "catalog_id": (
            f"huggingface:{repo_id}"
        ),

        "name": repo_id,

        "family": (
            config.get(
                "model_type"
            )
        ),

        "architecture": architecture,

        "parameters": {
            "count": (
                _hf_parameter_count(
                    model
                )
            ),
        },

        "quantization": (
            _hf_quantization(
                model
            )
        ),

        "context_length": (
            _hf_context_length(
                model
            )
        ),

        "source": {
            "provider": "huggingface",

            "source_model_id": (
                repo_id
            ),

            "revision": model.get(
                "sha"
            ),

            "license": (
                card_data.get(
                    "license"
                )
            ),

            "location": (
                base_url.rstrip("/")
                + "/"
                + repo_id
            ),
        },

        "size": {
            # Hub metadata may expose repository storage,
            # but exact downloadable artifact size depends
            # on files/revision selected.
            "download_bytes": (
                int(used_storage)
                if used_storage is not None
                else None
            ),

            "installed_bytes": None,
        },

        "format": {
            "weights": (
                _hf_weight_format(
                    model
                )
            ),
        },

        "discovery": {
            "pipeline_tag": (
                model.get(
                    "pipeline_tag"
                )
            ),

            "library": (
                model.get(
                    "library_name"
                )
            ),

            "downloads": (
                model.get(
                    "downloads"
                )
            ),

            "gated": (
                model.get(
                    "gated"
                )
            ),

            "private": (
                model.get(
                    "private",
                    False,
                )
            ),

            "tags": (
                model.get("tags")
                or []
            ),
        },

        "runtime": {
            # Compatibility evaluator owns this.
            "supported": [],
        },

        "requirements": {
            "ram_bytes": None,
            "vram_bytes": None,
            "unified_memory_bytes": None,
        },

        "compatibility": {
            "status": "not_evaluated",
            "reasons": [],
            "recommendations": [],
        },
    }
