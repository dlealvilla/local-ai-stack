from adapters.gateway import (
    builtin_proxy,
    direct,
)


GATEWAY_ADAPTERS = {
    "direct": direct,
    "builtin_proxy": builtin_proxy,
}


def get_gateway_adapter(provider):
    adapter = GATEWAY_ADAPTERS.get(provider)

    if adapter is None:
        raise ValueError(
            f"Unsupported gateway provider: {provider}"
        )

    return adapter


def resolve_gateway_endpoint(plan, config):
    """
    Return the logical AI endpoint clients should use.

    direct:
        inference endpoint

    process-backed gateway:
        gateway endpoint
    """

    provider = plan["gateway"]["provider"]

    adapter = get_gateway_adapter(
        provider
    )

    spec = adapter.build_service_spec(
        plan,
        config,
    )

    return spec["endpoint"]
