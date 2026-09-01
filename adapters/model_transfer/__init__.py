from adapters.model_transfer import (
    huggingface,
    local_files,
)


MODEL_TRANSFER_ADAPTERS = {
    "huggingface": huggingface,
    "local_files": local_files,
}


def get_model_transfer_adapter(provider):
    adapter = MODEL_TRANSFER_ADAPTERS.get(
        provider
    )

    if adapter is None:
        raise ValueError(
            f"Unsupported ModelTransfer provider: {provider}"
        )

    return adapter
