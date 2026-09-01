def get_model_manifest_adapter(
    provider,
):
    """
    Resolve a replaceable remote model-manifest provider.

    Core owns the manifest/preflight concept.
    Adapters own provider-specific metadata retrieval.
    """

    provider = str(
        provider
    ).strip().lower()


    if provider == "huggingface":
        from adapters.model_manifest import (
            huggingface,
        )

        return huggingface


    raise ValueError(
        "Unsupported model-manifest provider: "
        + provider
    )
