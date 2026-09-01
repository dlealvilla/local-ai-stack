from adapters.platform_api import builtin_http


PLATFORM_API_ADAPTERS = {
    "builtin_http": builtin_http,
}


def get_platform_api_adapter(provider):
    try:
        return PLATFORM_API_ADAPTERS[provider]
    except KeyError:
        raise ValueError(
            f"Unsupported Platform API provider: {provider}"
        )
