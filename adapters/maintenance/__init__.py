from adapters.maintenance import (
    lifecycle_cli,
)


MAINTENANCE_LIFECYCLE_ADAPTERS = {
    "current_cli": lifecycle_cli,
}


def get_maintenance_lifecycle_adapter(
    provider="current_cli",
):
    adapter = (
        MAINTENANCE_LIFECYCLE_ADAPTERS.get(
            provider
        )
    )

    if adapter is None:
        raise ValueError(
            "Unsupported maintenance lifecycle adapter: "
            + str(provider)
        )

    return adapter
