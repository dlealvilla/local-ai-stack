"""Gated and private access. Credentials are not stored here."""

from __future__ import annotations

from machi.model.contracts import ModelFailure


def access_failure(
    *,
    gated: bool,
    private: bool,
    credential_present: bool,
) -> ModelFailure | None:
    """Missing access is a typed failure. A present credential is not recorded."""
    if credential_present or not (gated or private):
        return None
    if gated:
        return ModelFailure.GATED_ACCESS_REQUIRED
    return ModelFailure.ACCESS_DENIED
