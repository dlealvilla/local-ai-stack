from adapters.usage_store import (
    jsonl,
    partitioned_jsonl,
)


USAGE_STORE_ADAPTERS = {
    "jsonl": jsonl,
    "partitioned_jsonl": (
        partitioned_jsonl
    ),
}


def get_usage_store_adapter(
    provider,
):
    adapter = (
        USAGE_STORE_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            f"Unsupported usage store provider: {provider}"
        )

    return adapter
