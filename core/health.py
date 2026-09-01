import json
import urllib.error
import urllib.request


def http_get(url, timeout=5):
    try:
        with urllib.request.urlopen(
            url,
            timeout=timeout,
        ) as response:
            body = response.read()

            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
                "body": body,
                "error": None,
            }

    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "body": b"",
            "error": str(exc),
        }


def check_service_health(service):
    """
    Check whether a deployed service is functionally healthy.

    PROVISIONAL:
    Health probes are currently defined for the providers
    used by the first working vertical slice.

    Future versions should use provider-specific health
    adapters and richer readiness/degraded states.
    """

    service_id = service["id"]
    provider = service["provider"]
    spec = service["spec"]

    network = spec["network"]

    base_url = (
        f"http://{network['host']}:"
        f"{network['port']}"
    )

    if provider == "vllm":
        result = http_get(
            f"{base_url}/v1/models"
        )

        if not result["ok"]:
            return {
                "service": service_id,
                "provider": provider,
                "healthy": False,
                "detail": (
                    result["error"]
                    or
                    f"HTTP {result['status_code']}"
                ),
            }

        try:
            payload = json.loads(
                result["body"]
            )

            models = [
                model.get("id")
                for model
                in payload.get("data", [])
            ]

        except Exception:
            return {
                "service": service_id,
                "provider": provider,
                "healthy": False,
                "detail": (
                    "API responded but returned "
                    "unexpected model data."
                ),
            }

        return {
            "service": service_id,
            "provider": provider,
            "healthy": True,
            "detail": (
                "OpenAI-compatible API ready; "
                f"models: {models}"
            ),
        }

    if provider == "builtin_proxy":
        result = http_get(
            f"{base_url}/live"
        )

        return {
            "service": service_id,
            "provider": provider,
            "healthy": result["ok"],
            "detail": (
                f"HTTP {result['status_code']}"
                if result["ok"]
                else (
                    result["error"]
                    or "Gateway liveness failed"
                )
            ),
        }

    if provider == "builtin_http":
        result = http_get(
            f"{base_url}/live"
        )

        return {
            "service": service_id,
            "provider": provider,
            "healthy": result["ok"],
            "detail": (
                f"HTTP {result['status_code']}"
                if result["ok"]
                else (
                    result["error"]
                    or "Platform API liveness failed"
                )
            ),
        }

    if provider == "openwebui":
        result = http_get(
            base_url
        )

        return {
            "service": service_id,
            "provider": provider,
            "healthy": result["ok"],
            "detail": (
                f"HTTP {result['status_code']}"
                if result["ok"]
                else (
                    result["error"]
                    or "HTTP request failed"
                )
            ),
        }

    return {
        "service": service_id,
        "provider": provider,
        "healthy": False,
        "detail": (
            "No health probe is defined "
            "for this provider yet."
        ),
    }


def check_deployment_health(manifest):
    results = []

    for service in manifest["services"]:
        if not service["enabled"]:
            continue

        results.append(
            check_service_health(service)
        )

    return results
