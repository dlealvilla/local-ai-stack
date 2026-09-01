from collections import defaultdict
from datetime import datetime, timezone


ANALYTICS_SCHEMA_VERSION = 1


def _parse_time(value):
    if not value:
        return None

    value = value.strip()

    if value.endswith("Z"):
        value = (
            value[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        value
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def filter_usage_events(
    events,
    *,
    start=None,
    end=None,
    model=None,
    provider=None,
):
    """
    Filter raw UsageEvents before aggregation.

    start:
        inclusive UTC timestamp

    end:
        exclusive UTC timestamp

    model:
        matches actual_model or logical_model

    provider:
        matches route provider
    """

    start_time = _parse_time(
        start
    )

    end_time = _parse_time(
        end
    )

    filtered = []

    for event in events:
        if not isinstance(
            event,
            dict,
        ):
            continue

        route = event.get(
            "route",
            {},
        )

        if model:
            actual_model = route.get(
                "actual_model"
            )

            logical_model = route.get(
                "logical_model"
            )

            if model not in (
                actual_model,
                logical_model,
            ):
                continue

        if provider:
            if (
                route.get("provider")
                != provider
            ):
                continue

        if start_time or end_time:
            started_at = event.get(
                "started_at"
            )

            if not started_at:
                continue

            try:
                event_time = _parse_time(
                    started_at
                )
            except Exception:
                continue

            if (
                start_time
                and event_time < start_time
            ):
                continue

            if (
                end_time
                and event_time >= end_time
            ):
                continue

        filtered.append(
            event
        )

    return filtered


def _new_bucket():
    return {
        "requests": 0,
        "successful_requests": 0,
        "errors": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "_latencies": [],
    }


def _add_event(
    bucket,
    event,
):
    bucket["requests"] += 1

    response = event.get(
        "response",
        {},
    )

    if response.get("success") is True:
        bucket[
            "successful_requests"
        ] += 1
    else:
        bucket["errors"] += 1

    usage = event.get(
        "usage",
        {},
    )

    bucket["input_tokens"] += (
        usage.get("input_tokens")
        or 0
    )

    bucket["output_tokens"] += (
        usage.get("output_tokens")
        or 0
    )

    bucket["total_tokens"] += (
        usage.get("total_tokens")
        or 0
    )

    latency = (
        event.get(
            "performance",
            {},
        ).get(
            "latency_ms"
        )
    )

    if latency is not None:
        bucket["_latencies"].append(
            float(latency)
        )


def _finish_bucket(bucket):
    latencies = bucket.pop(
        "_latencies",
        [],
    )

    requests = bucket[
        "requests"
    ]

    bucket["error_rate"] = (
        round(
            bucket["errors"]
            / requests,
            6,
        )
        if requests
        else 0.0
    )

    bucket[
        "average_latency_ms"
    ] = (
        round(
            sum(latencies)
            / len(latencies),
            3,
        )
        if latencies
        else None
    )

    return bucket


def summarize_usage(events):
    """
    Convert filtered UsageEvents into analytics.

    PROVISIONAL:
    Aggregation currently happens in memory.
    """

    totals = _new_bucket()

    by_model = defaultdict(
        _new_bucket
    )

    by_provider = defaultdict(
        _new_bucket
    )

    by_day = defaultdict(
        _new_bucket
    )

    for event in events:
        if not isinstance(
            event,
            dict,
        ):
            continue

        _add_event(
            totals,
            event,
        )

        route = event.get(
            "route",
            {},
        )

        model = (
            route.get(
                "actual_model"
            )
            or route.get(
                "logical_model"
            )
            or "unknown"
        )

        provider = (
            route.get(
                "provider"
            )
            or "unknown"
        )

        started_at = event.get(
            "started_at"
        )

        day = (
            started_at[:10]
            if isinstance(
                started_at,
                str,
            )
            and len(started_at) >= 10
            else "unknown"
        )

        _add_event(
            by_model[model],
            event,
        )

        _add_event(
            by_provider[provider],
            event,
        )

        _add_event(
            by_day[day],
            event,
        )

    return {
        "schema_version": (
            ANALYTICS_SCHEMA_VERSION
        ),

        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "totals": _finish_bucket(
            totals
        ),

        "by_model": [
            {
                "model": model,
                **_finish_bucket(
                    bucket
                ),
            }
            for model, bucket
            in sorted(
                by_model.items()
            )
        ],

        "by_provider": [
            {
                "provider": provider,
                **_finish_bucket(
                    bucket
                ),
            }
            for provider, bucket
            in sorted(
                by_provider.items()
            )
        ],

        "by_day": [
            {
                "date": day,
                **_finish_bucket(
                    bucket
                ),
            }
            for day, bucket
            in sorted(
                by_day.items()
            )
        ],
    }
