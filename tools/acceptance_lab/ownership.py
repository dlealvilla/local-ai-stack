"""Positive ownership checks for future Pod teardown.

Name prefix ``machi-acceptance-`` is never sufficient on its own.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

OWNED_NAME_PREFIX = "machi-acceptance-"


@dataclass(frozen=True, slots=True)
class OwnershipVerdict:
    owned: bool
    reason: str


def is_owned_pod(
    connection: sqlite3.Connection,
    *,
    runpod_pod_id: str,
    ownership_token: str,
    campaign_id: str,
    pod_name: str,
) -> OwnershipVerdict:
    """Return owned only when every required fact agrees with one row."""
    if not runpod_pod_id or not ownership_token or not campaign_id or not pod_name:
        return OwnershipVerdict(False, "missing_required_fact")
    if not pod_name.startswith(OWNED_NAME_PREFIX):
        return OwnershipVerdict(False, "name_prefix_mismatch")
    rows = list(
        connection.execute(
            "SELECT server_instance_id, ownership_token, campaign_id, pod_name, "
            "ownership_verified FROM server_instance WHERE runpod_pod_id = ?",
            (runpod_pod_id,),
        )
    )
    if not rows:
        return OwnershipVerdict(False, "missing_db_record")
    if len(rows) != 1:
        return OwnershipVerdict(False, "pod_id_conflict")
    row = rows[0]
    if str(row["ownership_token"]) != ownership_token:
        return OwnershipVerdict(False, "ownership_token_mismatch")
    if str(row["campaign_id"]) != campaign_id:
        return OwnershipVerdict(False, "campaign_mismatch")
    if str(row["pod_name"]) != pod_name:
        return OwnershipVerdict(False, "pod_name_mismatch")
    if int(row["ownership_verified"]) != 1:
        return OwnershipVerdict(False, "ownership_not_verified")
    return OwnershipVerdict(True, "positive_ownership")


def is_owned_by_name_prefix(
    connection: sqlite3.Connection, *, pod_name: str
) -> OwnershipVerdict:
    """Prefix-only lookup. Always fail-closed."""
    del connection, pod_name
    return OwnershipVerdict(False, "name_prefix_insufficient")
