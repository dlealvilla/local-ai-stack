"""Positive ownership requires pod id, token, campaign, and name."""

from __future__ import annotations

import sqlite3

from tools.acceptance_lab.ownership import is_owned_by_name_prefix, is_owned_pod
from tools.acceptance_lab.store import insert_row


def _seed(connection: sqlite3.Connection) -> None:
    insert_row(
        connection,
        "campaign",
        {
            "campaign_id": "camp_own",
            "name": "own",
            "purpose": "ownership",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "status": "active",
            "provider_scope_json": {"nvidia": "ACTIVE"},
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "server_instance",
        {
            "server_instance_id": "srv_own",
            "campaign_id": "camp_own",
            "ownership_token": "own_token_valid",
            "runpod_pod_id": "pod_owned",
            "pod_name": "machi-acceptance-nvidia-abc",
            "target_provider": "nvidia",
            "lifecycle_status": "running",
            "ownership_verified": 1,
            "historical_import": 0,
        },
    )


def test_valid_owned_pod(connection: sqlite3.Connection) -> None:
    _seed(connection)
    verdict = is_owned_pod(
        connection,
        runpod_pod_id="pod_owned",
        ownership_token="own_token_valid",
        campaign_id="camp_own",
        pod_name="machi-acceptance-nvidia-abc",
    )
    assert verdict.owned is True
    assert verdict.reason == "positive_ownership"


def test_name_prefix_alone_is_not_owned(connection: sqlite3.Connection) -> None:
    _seed(connection)
    verdict = is_owned_by_name_prefix(
        connection, pod_name="machi-acceptance-nvidia-abc"
    )
    assert verdict.owned is False
    assert verdict.reason == "name_prefix_insufficient"


def test_missing_db_record(connection: sqlite3.Connection) -> None:
    _seed(connection)
    verdict = is_owned_pod(
        connection,
        runpod_pod_id="pod_unknown",
        ownership_token="own_token_valid",
        campaign_id="camp_own",
        pod_name="machi-acceptance-nvidia-abc",
    )
    assert verdict.owned is False
    assert verdict.reason == "missing_db_record"


def test_token_mismatch_is_not_owned(connection: sqlite3.Connection) -> None:
    _seed(connection)
    verdict = is_owned_pod(
        connection,
        runpod_pod_id="pod_owned",
        ownership_token="own_wrong",
        campaign_id="camp_own",
        pod_name="machi-acceptance-nvidia-abc",
    )
    assert verdict.owned is False
    assert verdict.reason == "ownership_token_mismatch"


def test_name_prefix_mismatch_is_not_owned(connection: sqlite3.Connection) -> None:
    _seed(connection)
    verdict = is_owned_pod(
        connection,
        runpod_pod_id="pod_owned",
        ownership_token="own_token_valid",
        campaign_id="camp_own",
        pod_name="other-prefix-nvidia-abc",
    )
    assert verdict.owned is False
    assert verdict.reason == "name_prefix_mismatch"


def test_unverified_row_is_not_owned(connection: sqlite3.Connection) -> None:
    insert_row(
        connection,
        "campaign",
        {
            "campaign_id": "camp_uv",
            "name": "own",
            "purpose": "ownership",
            "created_at_utc": "2026-09-16T00:00:00.000Z",
            "status": "active",
            "provider_scope_json": {"nvidia": "ACTIVE"},
            "historical_import": 0,
        },
    )
    insert_row(
        connection,
        "server_instance",
        {
            "server_instance_id": "srv_uv",
            "campaign_id": "camp_uv",
            "ownership_token": "own_token_uv",
            "runpod_pod_id": "pod_uv",
            "pod_name": "machi-acceptance-nvidia-uv",
            "target_provider": "nvidia",
            "lifecycle_status": "running",
            "ownership_verified": 0,
            "historical_import": 0,
        },
    )
    verdict = is_owned_pod(
        connection,
        runpod_pod_id="pod_uv",
        ownership_token="own_token_uv",
        campaign_id="camp_uv",
        pod_name="machi-acceptance-nvidia-uv",
    )
    assert verdict.owned is False
    assert verdict.reason == "ownership_not_verified"
