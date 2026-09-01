from adapters.storage_capacity import (
    generic_filesystem,
    runpod_network_volume,
)


STORAGE_CAPACITY_PROVIDERS = {
    "generic_filesystem": (
        generic_filesystem
    ),

    "runpod_network_volume": (
        runpod_network_volume
    ),
}


def get_storage_capacity_provider(
    provider,
):
    adapter = (
        STORAGE_CAPACITY_PROVIDERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            "Unsupported StorageCapacity provider: "
            + str(provider)
        )

    return adapter
