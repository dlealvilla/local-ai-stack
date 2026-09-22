"""Reservation identity. A repeat of the same hold uses the same id."""

from __future__ import annotations

import hashlib

from machi.admit.policy import POLICY_VERSION


def reservation_id(
    *,
    plan_id: str,
    fingerprint: str,
    request_id: str,
    capacity_evidence_id: str,
    sequence: int,
) -> str:
    raw = "\n".join(
        (
            POLICY_VERSION,
            plan_id,
            fingerprint,
            request_id,
            capacity_evidence_id,
            str(sequence),
        )
    )
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"rsv_{digest[:16]}"


def release_id(reservation: str) -> str:
    digest = hashlib.sha256(f"release\n{reservation}".encode()).hexdigest()
    return f"rel_{digest[:16]}"
