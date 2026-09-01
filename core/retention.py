from datetime import (
    datetime,
    timedelta,
    timezone,
)


def build_usage_retention_policy(
    config,
):
    """
    Normalize local analytics retention policy.

    Retention policy belongs to the platform core.

    Storage adapters decide HOW expiration is performed.
    """

    analytics = config[
        "analytics"
    ]

    days = analytics.get(
        "local_retention_days",
        7,
    )

    return {
        "enabled": (
            days is not None
            and days > 0
        ),
        "retention_days": days,
    }


def apply_usage_retention(
    *,
    config,
    usage_store,
):
    policy = (
        build_usage_retention_policy(
            config
        )
    )

    if not policy["enabled"]:
        return {
            "policy": policy,
            "removed_events": 0,
            "removed_partitions": 0,
        }

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            days=policy[
                "retention_days"
            ]
        )
    )

    result = usage_store.prune_before(
        cutoff.isoformat(),
        config,
    )

    return {
        "policy": policy,
        **result,
    }
