from adapters.frontend import librechat, openwebui


FRONTEND_ADAPTERS = {
    "librechat": librechat,
    "openwebui": openwebui,
}


def get_frontend_adapter(provider):
    adapter = FRONTEND_ADAPTERS.get(provider)

    if adapter is None:
        raise ValueError(
            f"Unsupported frontend provider: {provider}"
        )

    return adapter
