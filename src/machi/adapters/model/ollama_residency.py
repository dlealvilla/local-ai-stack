"""Observe Ollama residency. This does not admit resources or serve."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from machi.adapters.model.ollama_api import (
    OllamaApiError,
    OllamaModelApi,
    RunningModel,
)
from machi.kernel.errors import ValidationError
from machi.model.provider_candidate import canonical_digest


class ResidencyState(StrEnum):
    """What /api/ps says about one expected name and digest."""

    ABSENT = "absent"
    EXPECTED_RESIDENT = "expected_resident"
    WRONG_IDENTITY = "wrong_identity"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ResidencyObservation:
    """Public residency facts. Absent means those fields were not cited."""

    state: ResidencyState
    name: str | None
    digest: str | None
    size_vram_bytes: int | None
    expires_at: str | None
    reason: str


def observe_residency(
    api: OllamaModelApi, *, name: str, digest: str
) -> ResidencyObservation:
    """Classify the current /api/ps view. A tag is not an identity."""
    expected = _digest(digest)
    if expected is None:
        return _unresolved("expected digest is not a sha256")
    try:
        running = api.running_models()
    except OllamaApiError:
        return _unresolved("running models were not readable")
    matched: list[RunningModel] = []
    wrong: list[RunningModel] = []
    for item in running:
        item_digest = _digest(item.digest)
        same_name = item.name == name
        same_digest = item_digest == expected
        if same_name and same_digest:
            matched.append(item)
            continue
        if same_name or same_digest:
            wrong.append(item)
    if len(matched) == 1 and not wrong:
        return _cite(
            ResidencyState.EXPECTED_RESIDENT, matched[0], "name and digest match"
        )
    if matched or len(wrong) > 1:
        return _unresolved("residency is ambiguous")
    if wrong:
        return _cite(
            ResidencyState.WRONG_IDENTITY,
            wrong[0],
            "resident identity does not match the expected pair",
        )
    return ResidencyObservation(
        ResidencyState.ABSENT, None, None, None, None, "expected model is not resident"
    )


def refresh_residency(
    api: OllamaModelApi, *, name: str, digest: str
) -> ResidencyObservation:
    """Ask the provider to keep the model, then read /api/ps."""
    try:
        api.preload(name)
    except OllamaApiError:
        return _unresolved("residency refresh failed")
    return observe_residency(api, name=name, digest=digest)


def release_residency(
    api: OllamaModelApi, *, name: str, digest: str
) -> ResidencyObservation:
    """Ask the provider to unload, then read /api/ps."""
    try:
        api.unload(name)
    except OllamaApiError:
        return _unresolved("residency release failed")
    return observe_residency(api, name=name, digest=digest)


def _digest(value: str) -> str | None:
    try:
        return canonical_digest(value)
    except ValidationError:
        return None


def _unresolved(reason: str) -> ResidencyObservation:
    return ResidencyObservation(
        ResidencyState.UNRESOLVED, None, None, None, None, reason
    )


def _cite(
    state: ResidencyState, item: RunningModel, reason: str
) -> ResidencyObservation:
    return ResidencyObservation(
        state,
        item.name,
        _digest(item.digest),
        item.size_vram_bytes,
        item.expires_at,
        reason,
    )
