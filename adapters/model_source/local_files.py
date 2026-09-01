from core.model_metadata import (
    normalize_local_model,
)

from core.models import (
    list_local_models,
)


SOURCE_ID = "local_files"


def discover(
    config,
    *,
    query=None,
    limit=None,
):
    models = [
        normalize_local_model(
            model
        )
        for model in list_local_models()
    ]

    if query:
        needle = query.lower()

        models = [
            model
            for model in models
            if (
                needle
                in model["name"].lower()
                or needle
                in str(
                    model.get(
                        "family"
                    )
                    or ""
                ).lower()
                or needle
                in str(
                    model.get(
                        "architecture"
                    )
                    or ""
                ).lower()
            )
        ]

    if limit is not None:
        models = models[
            :limit
        ]

    return models
