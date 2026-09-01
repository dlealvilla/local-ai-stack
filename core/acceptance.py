import json
import time
import urllib.request


def json_request(
    url,
    payload=None,
    timeout=60,
):
    data = None
    headers = {}

    if payload is not None:
        data = json.dumps(
            payload
        ).encode("utf-8")

        headers["Content-Type"] = (
            "application/json"
        )

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:
        body = response.read()

        return (
            response.status,
            json.loads(body)
            if body
            else None,
        )


def http_request(
    url,
    timeout=10,
):
    with urllib.request.urlopen(
        url,
        timeout=timeout,
    ) as response:
        return response.status


def tracked_json_request(
    url,
    payload,
):
    """
    Send a JSON request and return response headers as well.

    Used by acceptance testing to correlate a gateway response
    with the persisted UsageEvent.
    """

    data = json.dumps(
        payload
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:

        status = response.status

        headers = dict(
            response.headers.items()
        )

        body = json.load(
            response
        )

    return (
        status,
        body,
        headers,
    )


def run_acceptance_test(
    inference_url,
    frontend_url,
    platform_api_url,
    model_name,
    usage_event_lookup=None,
):
    """
    Validate the complete first vertical slice.

    PROVISIONAL:
    This currently tests one local OpenAI-compatible
    inference endpoint and one Open WebUI frontend.

    Future acceptance tests should expand through the
    platform gateway, analytics layer, Platform API,
    external providers, routing and Admin UI.
    """

    results = []

    # 1. Model endpoint.
    try:
        status, payload = json_request(
            f"{inference_url}/v1/models"
        )

        models = [
            item.get("id")
            for item
            in payload.get("data", [])
        ]

        passed = (
            200 <= status < 300
            and model_name in models
        )

        results.append({
            "name": "Inference model discovery",
            "passed": passed,
            "detail": (
                f"models={models}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": "Inference model discovery",
            "passed": False,
            "detail": str(exc),
        })


    # 2. Real generation request.
    try:
        status, payload = json_request(
            f"{inference_url}/v1/chat/completions",
            payload={
                "model": model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Reply briefly with a "
                            "confirmation that the AI "
                            "Stack acceptance test works."
                        ),
                    }
                ],
                "temperature": 0,
                "max_tokens": 64,
            },
            timeout=120,
        )

        choices = payload.get(
            "choices",
            []
        )

        content = ""

        if choices:
            content = (
                choices[0]
                .get("message", {})
                .get("content", "")
                or ""
            ).strip()

        usage = payload.get(
            "usage",
            {}
        )

        passed = (
            200 <= status < 300
            and bool(choices)
            and bool(content)
        )

        results.append({
            "name": "Real inference request",
            "passed": passed,
            "detail": (
                f"response={content!r}"
            ),
            "usage": {
                "prompt_tokens": usage.get(
                    "prompt_tokens"
                ),
                "completion_tokens": usage.get(
                    "completion_tokens"
                ),
                "total_tokens": usage.get(
                    "total_tokens"
                ),
            },
        })

    except Exception as exc:
        results.append({
            "name": "Real inference request",
            "passed": False,
            "detail": str(exc),
        })


    # 3. Gateway usage-event correlation.
    try:
        request_payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Reply briefly: usage event test."
                    ),
                }
            ],
            "temperature": 0,
            "max_tokens": 24,
        }

        (
            status,
            response_payload,
            response_headers,
        ) = tracked_json_request(
            (
                f"{inference_url}"
                "/v1/chat/completions"
            ),
            request_payload,
        )

        request_id = (
            response_headers.get(
                "X-AI-Stack-Request-ID"
            )
            or response_headers.get(
                "X-Ai-Stack-Request-Id"
            )
        )

        event = None

        if (
            request_id
            and usage_event_lookup
        ):
            # Recording occurs immediately after the gateway
            # finishes forwarding the response. Retry briefly
            # to avoid a race between client receipt and disk write.
            for _ in range(50):
                event = usage_event_lookup(
                    request_id
                )

                if event is not None:
                    break

                time.sleep(
                    0.1
                )

        upstream_usage = (
            response_payload.get(
                "usage"
            )
            or {}
        )

        stored_usage = (
            event.get(
                "usage",
                {}
            )
            if event
            else {}
        )

        passed = (
            200 <= status < 300
            and request_id is not None
            and event is not None
            and event.get(
                "event_id"
            ) == request_id
            and event.get(
                "request",
                {}
            ).get(
                "path"
            ) == "/v1/chat/completions"
            and event.get(
                "request",
                {}
            ).get(
                "requested_model"
            ) == model_name
            and event.get(
                "response",
                {}
            ).get(
                "success"
            ) is True
            and stored_usage.get(
                "total_tokens"
            ) == upstream_usage.get(
                "total_tokens"
            )
            and stored_usage.get(
                "total_tokens"
            ) is not None
        )

        results.append({
            "name": (
                "Gateway usage event correlation"
            ),
            "passed": passed,
            "detail": (
                f"request_id={request_id}, "
                f"upstream_tokens="
                f"{upstream_usage.get('total_tokens')}, "
                f"stored_tokens="
                f"{stored_usage.get('total_tokens')}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": (
                "Gateway usage event correlation"
            ),
            "passed": False,
            "detail": str(exc),
        })


    # 3. Platform API liveness.
    try:
        status, payload = json_request(
            f"{platform_api_url}/live"
        )

        passed = (
            200 <= status < 300
            and payload.get("status") == "ok"
        )

        results.append({
            "name": "Platform API liveness",
            "passed": passed,
            "detail": (
                f"HTTP {status}, "
                f"status={payload.get('status')}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": "Platform API liveness",
            "passed": False,
            "detail": str(exc),
        })


    # 4. Platform state contract.
    try:
        status, payload = json_request(
            f"{platform_api_url}/state"
        )

        schema_version = payload.get(
            "schema_version"
        )

        services = [
            service.get("id")
            for service
            in payload.get(
                "deployment",
                {}
            ).get(
                "services",
                []
            )
        ]

        passed = (
            200 <= status < 300
            and schema_version == 1
            and "inference" in services
            and "frontend" in services
            and "platform_api" in services
        )

        results.append({
            "name": "Platform state API",
            "passed": passed,
            "detail": (
                f"schema_version={schema_version}, "
                f"services={services}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": "Platform state API",
            "passed": False,
            "detail": str(exc),
        })


    # Analytics summary API.
    try:
        status, payload = json_request(
            f"{platform_api_url}/analytics/summary"
        )

        summary = (
            payload.get("summary")
            or {}
        )

        totals = (
            summary.get("totals")
            or {}
        )

        by_model = (
            summary.get("by_model")
            or []
        )

        by_provider = (
            summary.get("by_provider")
            or []
        )

        by_day = (
            summary.get("by_day")
            or []
        )

        passed = (
            200 <= status < 300
            and payload.get("enabled") is True
            and summary.get("schema_version") == 1
            and totals.get("requests", 0) >= 1
            and totals.get(
                "successful_requests",
                0,
            ) >= 1
            and totals.get(
                "total_tokens",
                0,
            ) >= 1
            and len(by_model) >= 1
            and len(by_provider) >= 1
            and len(by_day) >= 1
        )

        results.append({
            "name": "Analytics summary API",
            "passed": passed,
            "detail": (
                f"requests={totals.get('requests')}, "
                f"tokens={totals.get('total_tokens')}, "
                f"models={len(by_model)}, "
                f"providers={len(by_provider)}, "
                f"days={len(by_day)}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": "Analytics summary API",
            "passed": False,
            "detail": str(exc),
        })


    # 3. Frontend.
    try:
        status = http_request(
            frontend_url
        )

        results.append({
            "name": "Open WebUI",
            "passed": (
                200 <= status < 300
            ),
            "detail": (
                f"HTTP {status}"
            ),
        })

    except Exception as exc:
        results.append({
            "name": "Open WebUI",
            "passed": False,
            "detail": str(exc),
        })

    return results
