from adapters.model_inventory_store import (
    json_file,
)


MODEL_INVENTORY_STORE_ADAPTERS = {
    "json_file": json_file,
}


def get_model_inventory_store(
    provider,
):
    adapter = (
        MODEL_INVENTORY_STORE_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            "Unsupported model inventory store: "
            + str(provider)
        )

    return adapter
