"""Ollama public API seam. This increment's implementation is a fixture."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

TAGS_PATH = "/api/tags"
SHOW_PATH = "/api/show"
PS_PATH = "/api/ps"
GENERATE_PATH = "/api/generate"


@dataclass(frozen=True, slots=True)
class ListedModel:
    name: str
    digest: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ShownModel:
    name: str
    digest: str
    size_bytes: int | None
    family: str | None = None
    quantization: str | None = None
    context_length: int | None = None
    dtype: str | None = None
    layer_count: int | None = None
    key_value_heads: int | None = None
    head_dim: int | None = None


@dataclass(frozen=True, slots=True)
class RunningModel:
    name: str
    digest: str
    size_bytes: int | None
    size_vram_bytes: int | None


@dataclass(frozen=True, slots=True)
class GenerateResult:
    failure: str
    digest: str
    size_bytes: int | None
    size_vram_bytes: int | None
    output_tokens: int
    load_seconds: float | None
    generation_seconds: float | None


@dataclass(frozen=True, slots=True)
class UnloadResult:
    failure: str


class OllamaModelApi(Protocol):
    """v0.34.3 public calls Chunk 3 needs. No private scheduler surface."""

    def list_models(self) -> tuple[ListedModel, ...]:
        """GET /api/tags."""

    def show_model(self, name: str) -> ShownModel | None:
        """POST /api/show."""

    def running_models(self) -> tuple[RunningModel, ...]:
        """GET /api/ps."""

    def generate(self, name: str) -> GenerateResult:
        """POST /api/generate for the qualification token."""

    def unload(self, name: str) -> UnloadResult:
        """Release residency. Failure stays separate from the token result."""


class FixtureOutcome(StrEnum):
    PASS = "pass"
    NO_FIT = "no_fit"
    HOST_FAILURE = "host_failure"
    DIGEST_MISMATCH = "digest_mismatch"
    MISSING_FROM_PS = "missing_from_ps"
    NO_TOKEN = "no_token"
    UNLOAD_FAILURE = "unload_failure"


class FakeOllamaApi:
    """In-memory catalog. It does not open a socket or store prompt text."""

    def __init__(
        self,
        *,
        name: str,
        digest: str,
        outcome: FixtureOutcome,
        size_bytes: int = 1000,
        size_vram_bytes: int = 800,
        other_digest: str = "cd" * 32,
    ) -> None:
        self.name = name
        self.digest = digest
        self.outcome = outcome
        self.size_bytes = size_bytes
        self.size_vram_bytes = size_vram_bytes
        self.other_digest = other_digest
        self.calls: list[str] = []

    def list_models(self) -> tuple[ListedModel, ...]:
        self.calls.append(TAGS_PATH)
        return (
            ListedModel(
                name=self.name, digest=self.digest, size_bytes=self.size_bytes
            ),
        )

    def show_model(self, name: str) -> ShownModel | None:
        self.calls.append(SHOW_PATH)
        if name != self.name:
            return None
        digest = self.digest
        if self.outcome is FixtureOutcome.DIGEST_MISMATCH:
            digest = self.other_digest
        return ShownModel(
            name=name,
            digest=digest,
            size_bytes=self.size_bytes,
        )

    def running_models(self) -> tuple[RunningModel, ...]:
        self.calls.append(PS_PATH)
        if self.outcome is FixtureOutcome.MISSING_FROM_PS:
            return ()
        if self.outcome in {
            FixtureOutcome.NO_FIT,
            FixtureOutcome.HOST_FAILURE,
            FixtureOutcome.DIGEST_MISMATCH,
        }:
            return ()
        return (
            RunningModel(
                name=self.name,
                digest=self.digest,
                size_bytes=self.size_bytes,
                size_vram_bytes=self.size_vram_bytes,
            ),
        )

    def generate(self, name: str) -> GenerateResult:
        del name
        self.calls.append(GENERATE_PATH)
        failure = "none"
        tokens = 4
        if self.outcome is FixtureOutcome.HOST_FAILURE:
            failure = "host"
            tokens = 0
        elif self.outcome is FixtureOutcome.NO_FIT:
            failure = "no_fit"
            tokens = 0
        elif self.outcome is FixtureOutcome.NO_TOKEN:
            tokens = 0
        return GenerateResult(
            failure=failure,
            digest=self.digest,
            size_bytes=self.size_bytes,
            size_vram_bytes=self.size_vram_bytes,
            output_tokens=tokens,
            load_seconds=0.2,
            generation_seconds=0.1,
        )

    def unload(self, name: str) -> UnloadResult:
        del name
        self.calls.append("unload")
        if self.outcome is FixtureOutcome.UNLOAD_FAILURE:
            return UnloadResult("unload_failed")
        return UnloadResult("none")
