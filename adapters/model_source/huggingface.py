import json
import os
import urllib.parse
import urllib.request

from core.model_metadata import (
    normalize_huggingface_model,
)


SOURCE_ID = "huggingface"


def discover(
    config,
    *,
    query=None,
    limit=None,
):
    """
    Search/browse the Hugging Face Hub through its public API.

    No huggingface_hub package is required by the platform core.

    HF_TOKEN may optionally be supplied through the environment.
    FUTURE:
    Credentials should move behind enterprise secret management.
    """

    source_config = (
        config.get(
            "model_source",
            {}
        ).get(
            "huggingface",
            {},
        )
    )

    base_url = source_config.get(
        "base_url",
        "https://huggingface.co",
    )

    timeout = float(
        source_config.get(
            "timeout_seconds",
            15,
        )
    )

    params = {
        "limit": int(
            limit or 10
        ),
        "sort": "downloads",
        "direction": "-1",
        "full": "true",
        "cardData": "true",
        "config": "true",
    }

    if query:
        params["search"] = query

    url = (
        base_url.rstrip("/")
        + "/api/models?"
        + urllib.parse.urlencode(
            params
        )
    )

    headers = {
        "Accept": "application/json",

        "User-Agent": (
            "AI-Stack-ModelCatalog/1"
        ),
    }

    token = os.environ.get(
        "HF_TOKEN"
    )

    if token:
        headers[
            "Authorization"
        ] = (
            "Bearer "
            + token
        )

    request = urllib.request.Request(
        url,
        headers=headers,
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        payload = json.load(
            response
        )

    if not isinstance(
        payload,
        list,
    ):
        raise RuntimeError(
            "Unexpected Hugging Face API response."
        )

    models = []

    for raw_model in payload:

        try:
            normalized = (
                normalize_huggingface_model(
                    raw_model,
                    base_url=base_url,
                )
            )

        except Exception:
            # A malformed individual record should not
            # make the whole source unavailable.
            continue

        models.append(
            normalized
        )

    return models
