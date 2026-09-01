from datetime import datetime, timezone
from uuid import uuid4


USAGE_EVENT_SCHEMA_VERSION = 1


def new_usage_event_id():
    return str(uuid4())


def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def build_usage_event(
    *,
    event_id,
    started_at,
    method,
    path,
    requested_model,
    actual_model,
    logical_model,
    provider,
    service_id,
    status_code,
    latency_ms,
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
    streaming=False,
    error=None,
):
    """
    Normalized AI usage event.

    The event is owned by the platform core.

    Storage implementations belong in adapters.

    PROVISIONAL:
    User/team/application identity, cost and route-decision
    information are not implemented yet.
    """

    return {
        "schema_version": USAGE_EVENT_SCHEMA_VERSION,
        "event_id": event_id,
        "started_at": started_at,

        "request": {
            "method": method,
            "path": path,
            "requested_model": requested_model,
            "streaming": streaming,
        },

        "route": {
            "logical_model": logical_model,
            "actual_model": actual_model,
            "provider": provider,
            "service_id": service_id,

            # FUTURE:
            # Store actual router decision information.
            "route_reason": "single_local_upstream",
        },

        "response": {
            "status_code": status_code,
            "success": (
                status_code is not None
                and 200 <= status_code < 400
            ),
            "error": error,
        },

        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },

        "performance": {
            "latency_ms": round(
                latency_ms,
                3,
            ),
        },

        "identity": {
            # FUTURE:
            # Authenticated platform identity.
            "user_id": None,
            "team_id": None,
            "application_id": None,
        },

        "cost": {
            # FUTURE:
            # Vendor pricing or local infrastructure-derived cost.
            "currency": None,
            "amount": None,
            "method": None,
        },
    }
