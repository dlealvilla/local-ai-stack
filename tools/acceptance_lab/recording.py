"""Helpers that snapshot policy and common campaign rows."""

from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

from tools.acceptance_lab.ids import stable_id
from tools.acceptance_lab.jsonutil import sha256_canonical
from tools.acceptance_lab.store import insert_or_ignore
from tools.acceptance_lab.timeutil import format_utc


def estimated_cost_usd(hourly_price_usd: float, runtime_seconds: int) -> float:
    """Calculate an estimate. Never treat the result as an actual charge."""
    if runtime_seconds < 0:
        raise ValueError("runtime_seconds must be non-negative")
    return hourly_price_usd * (runtime_seconds / 3600.0)


def record_policy(
    connection: sqlite3.Connection,
    *,
    campaign_id: str,
    policy: dict[str, Any],
    when: dt.datetime,
    historical_import: bool = False,
) -> str:
    del historical_import
    policy_id = stable_id("pol", campaign_id, sha256_canonical(policy))
    insert_or_ignore(
        connection,
        "policy_snapshot",
        {
            "policy_id": policy_id,
            "campaign_id": campaign_id,
            "created_at_utc": format_utc(when),
            "policy_json": policy,
            "policy_sha256": sha256_canonical(policy),
            "active_provider_set": policy["active_providers"],
            "max_nvidia_hourly_usd": policy["max_nvidia_hourly_usd"],
            "max_amd_hourly_usd": policy["max_amd_hourly_usd"],
            "max_session_usd": policy["max_session_usd"],
            "max_daily_usd": policy["max_daily_usd"],
            "balance_floor_usd": policy["balance_floor_usd"],
            "max_concurrent_pods": policy["max_concurrent_pods"],
            "max_pod_lifetime_seconds": policy["max_pod_lifetime_seconds"],
            "max_provision_retries": policy["max_provision_retries"],
            "max_nvidia_servers": policy["max_nvidia_servers"],
            "max_amd_servers": policy["max_amd_servers"],
            "allow_secure_cloud": int(policy["allow_secure_cloud"]),
            "allow_community_cloud": int(policy["allow_community_cloud"]),
            "allow_network_volume": int(policy["allow_network_volume"]),
            "hang_action": policy["hang_action"],
            "success_teardown_action": policy["success_teardown_action"],
            "product_failure_teardown_action": policy[
                "product_failure_teardown_action"
            ],
            "selection_strategy": policy["selection_strategy"],
            "first_amd_target": policy["first_amd_target"],
            "apple_policy": policy["apple_policy"],
            "intel_policy": policy["intel_policy"],
        },
    )
    return policy_id


def record_campaign(
    connection: sqlite3.Connection,
    *,
    campaign_id: str,
    name: str,
    purpose: str,
    status: str,
    when: dt.datetime,
    provider_scope: dict[str, Any],
    notes: str,
    historical_import: bool,
    started: dt.datetime | None = None,
    finished: dt.datetime | None = None,
) -> None:
    insert_or_ignore(
        connection,
        "campaign",
        {
            "campaign_id": campaign_id,
            "name": name,
            "purpose": purpose,
            "created_at_utc": format_utc(when),
            "started_at_utc": format_utc(started) if started else None,
            "finished_at_utc": format_utc(finished) if finished else None,
            "status": status,
            "provider_scope_json": provider_scope,
            "notes": notes,
            "historical_import": int(historical_import),
        },
    )
