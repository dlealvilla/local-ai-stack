from adapters.model_source import (
    get_model_source_adapter,
)

from core.hardware import (
    inspect_hardware,
)

from core.model_compatibility import (
    evaluate_model_compatibility,
)


MODEL_CATALOG_SCHEMA_VERSION = 1


def list_catalog_models(
    config,
    *,
    search=None,
    source=None,
    limit=None,
):
    """
    Discover and normalize models from configured ModelSources,
    then evaluate them against one detected host snapshot.

    ModelSource:
        Where does this model come from?

    CompatibilityEvaluator:
        Is it a plausible candidate for this host?

    CapacityPlanner:
        Can it safely be downloaded/started alongside current
        workloads?

    These responsibilities deliberately remain separate.
    """

    catalog_config = config.get(
        "model_catalog",
        {},
    )

    configured_sources = (
        catalog_config.get(
            "sources",
            []
        )
    )

    default_limit = int(
        catalog_config.get(
            "default_limit",
            10,
        )
    )

    max_limit = int(
        catalog_config.get(
            "max_limit",
            50,
        )
    )

    resolved_limit = (
        int(limit)
        if limit is not None
        else default_limit
    )

    resolved_limit = max(
        1,
        min(
            resolved_limit,
            max_limit,
        ),
    )

    if source:
        sources = [
            source
        ]
    else:
        sources = list(
            configured_sources
        )

    # One hardware inspection per catalog request.
    hardware = inspect_hardware()

    models = []
    source_results = []

    for source_name in sources:

        if (
            source_name
            not in configured_sources
        ):
            source_results.append({
                "source": source_name,
                "status": "disabled",
                "models": 0,
                "error": (
                    "ModelSource is not enabled."
                ),
            })

            continue

        adapter = (
            get_model_source_adapter(
                source_name
            )
        )

        try:
            discovered = (
                adapter.discover(
                    config,
                    query=search,
                    limit=resolved_limit,
                )
            )

            evaluated = [
                evaluate_model_compatibility(
                    model,
                    hardware,
                    config,
                )
                for model in discovered
            ]

            models.extend(
                evaluated
            )

            source_results.append({
                "source": source_name,
                "status": "ok",
                "models": len(
                    evaluated
                ),
                "error": None,
            })

        except Exception as exc:
            source_results.append({
                "source": source_name,
                "status": "error",
                "models": 0,
                "error": str(exc),
            })

    return {
        "schema_version": (
            MODEL_CATALOG_SCHEMA_VERSION
        ),

        "query": {
            "search": search,
            "source": source,
            "limit": resolved_limit,
        },

        "sources": source_results,

        "models": models,
    }
