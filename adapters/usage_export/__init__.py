from adapters.usage_export import (
    disabled,
)


USAGE_EXPORT_ADAPTERS = {
    "disabled": disabled,
}


def get_usage_export_adapter(
    provider,
):
    adapter = (
        USAGE_EXPORT_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            f"Unsupported usage export provider: {provider}"
        )

    return adapter
