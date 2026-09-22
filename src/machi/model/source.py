"""Normalized source view. Adapters fill it. The domain does not."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceFileInfo:
    relative_path: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class SourceView:
    """One explicit reference after revision resolution."""

    repository: str
    requested_revision: str
    immutable_revision: str
    files: tuple[SourceFileInfo, ...]
    config_text: str | None
    index_text: str | None
    license_id: str | None
    gated: bool
    private: bool
