"""Deterministic plan identity. Wall-clock time is not an input."""

from __future__ import annotations

import hashlib


def plan_fingerprint(*parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()
    return digest[:32]


def plan_id(fingerprint: str) -> str:
    return f"plan_{fingerprint[:16]}"


def request_id(fingerprint: str) -> str:
    return f"preq_{fingerprint[:16]}"


def decision_id(fingerprint: str) -> str:
    return f"pdec_{fingerprint[:16]}"
