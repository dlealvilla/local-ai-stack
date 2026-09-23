"""Serving identity. A repeat of the same live instance uses the same id."""

from __future__ import annotations

import hashlib

from machi.serve.policy import POLICY_VERSION


def _digest(*parts: str) -> str:
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def instance_id(*, reservation_id: str, fingerprint: str, sequence: int) -> str:
    return (
        "sin_"
        + _digest(POLICY_VERSION, reservation_id, fingerprint, str(sequence))[:16]
    )


def endpoint_id(instance: str) -> str:
    return "ep_" + _digest("endpoint", instance)[:16]


def evidence_id(instance: str) -> str:
    return "npx_" + _digest("native", instance)[:16]


def transition_id(instance: str, sequence: int) -> str:
    return "trn_" + _digest("transition", instance, str(sequence))[:16]


def proof_id(instance: str, sequence: int) -> str:
    return "prf_" + _digest("proof", instance, str(sequence))[:16]


def exit_id(evidence: str) -> str:
    return "nex_" + _digest("exit", evidence)[:16]
