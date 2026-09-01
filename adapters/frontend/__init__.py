from adapters.frontend import openwebui


FRONTEND_ADAPTERS = {
    "openwebui": openwebui,
}


def get_frontend_adapter(provider):
    adapter = FRONTEND_ADAPTERS.get(provider)

    if adapter is None:
        raise ValueError(
            f"Unsupported frontend provider: {provider}"
        )

    return adapter
