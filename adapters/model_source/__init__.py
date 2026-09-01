from adapters.model_source import (
    huggingface,
    local_files,
)


MODEL_SOURCE_ADAPTERS = {
    "local_files": local_files,
    "huggingface": huggingface,
}


def get_model_source_adapter(
    provider,
):
    adapter = (
        MODEL_SOURCE_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            f"Unsupported ModelSource: {provider}"
        )

    return adapter
