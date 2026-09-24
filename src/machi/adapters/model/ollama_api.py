"""Ollama public API seam for v0.34.3. This increment is a fixture."""

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
    """GET /api/tags. Digest lives here, not on show."""

    name: str
    digest: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ShownModel:
    """POST /api/show. Metadata only. v0.34.3 does not return a digest."""

    name: str
    size_bytes: int | None
    family: str | None = None
    quantization: str | None = None
    format_label: str | None = None
    context_length: int | None = None
    dtype: str | None = None
    layer_count: int | None = None
    key_value_heads: int | None = None
    head_dim: int | None = None


@dataclass(frozen=True, slots=True)
class RunningModel:
    """GET /api/ps. Name and digest together are the residency proof."""

    name: str
    digest: str
    size_bytes: int | None
    size_vram_bytes: int | None
    expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class PreloadResult:
    """Empty POST /api/generate. Load duration is the initial load."""

    failure: str
    load_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class GenerateResult:
    """Real small POST /api/generate. Its load_duration is not initial load."""

    failure: str
    input_tokens: int
    output_tokens: int
    generation_seconds: float | None


@dataclass(frozen=True, slots=True)
class UnloadResult:
    failure: str


class OllamaApiError(Exception):
    """Typed public-API failure. The message is a code, not a response body."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OllamaModelApi(Protocol):
    """Public v0.34.3 calls. No private scheduler surface."""

    def list_models(self) -> tuple[ListedModel, ...]:
        """GET /api/tags."""

    def show_model(self, name: str) -> ShownModel | None:
        """POST /api/show."""

    def preload(self, name: str) -> PreloadResult:
        """Empty generate. This is not the token probe."""

    def running_models(self) -> tuple[RunningModel, ...]:
        """GET /api/ps."""

    def generate_probe(self, name: str) -> GenerateResult:
        """Real token request."""

    def unload(self, name: str) -> UnloadResult:
        """Ask the provider to drop residency."""


class FixtureOutcome(StrEnum):
    PASS = "pass"
    NO_FIT = "no_fit"
    HOST_FAILURE = "host_failure"
    CATALOG_DRIFT = "catalog_drift"
    PRELOAD_IDENTITY_MISMATCH = "preload_identity_mismatch"
    POST_TOKEN_IDENTITY_MISMATCH = "post_token_identity_mismatch"
    NO_TOKEN = "no_token"
    UNLOAD_FAILURE = "unload_failure"
    RESIDENT_AFTER_UNLOAD = "resident_after_unload"


class FakeOllamaApi:
    """In-memory catalog. It does not open a socket or store prompt text."""

    def __init__(
        self,
        *,
        name: str,
        digest: str,
        outcome: FixtureOutcome = FixtureOutcome.PASS,
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
        self.tag_digest = digest
        if outcome is FixtureOutcome.CATALOG_DRIFT:
            self.tag_digest = other_digest
        self.preload_failure = "none"
        self.after_preload_digest = digest
        self.after_token_digest = digest
        self.output_tokens = 4
        self.input_tokens = 3
        self.unload_failure = "none"
        self.remain_after_unload = False
        self._phase = "idle"
        self.calls: list[str] = []
        if outcome is FixtureOutcome.NO_FIT:
            self.preload_failure = "no_fit"
        elif outcome is FixtureOutcome.HOST_FAILURE:
            self.preload_failure = "host"
        elif outcome is FixtureOutcome.PRELOAD_IDENTITY_MISMATCH:
            self.after_preload_digest = other_digest
        elif outcome is FixtureOutcome.POST_TOKEN_IDENTITY_MISMATCH:
            self.after_token_digest = other_digest
        elif outcome is FixtureOutcome.NO_TOKEN:
            self.output_tokens = 0
        elif outcome is FixtureOutcome.UNLOAD_FAILURE:
            self.unload_failure = "unload_failed"
        elif outcome is FixtureOutcome.RESIDENT_AFTER_UNLOAD:
            self.remain_after_unload = True

    def list_models(self) -> tuple[ListedModel, ...]:
        self.calls.append(TAGS_PATH)
        return (
            ListedModel(
                name=self.name, digest=self.tag_digest, size_bytes=self.size_bytes
            ),
        )

    def show_model(self, name: str) -> ShownModel | None:
        self.calls.append(SHOW_PATH)
        if name != self.name:
            return None
        return ShownModel(name=name, size_bytes=self.size_bytes)

    def preload(self, name: str) -> PreloadResult:
        del name
        self.calls.append("preload")
        if self.preload_failure != "none":
            return PreloadResult(self.preload_failure)
        self._phase = "loaded"
        return PreloadResult("none", load_seconds=1.5)

    def running_models(self) -> tuple[RunningModel, ...]:
        self.calls.append(PS_PATH)
        if self._phase == "unloaded":
            if not self.remain_after_unload:
                return ()
            return (self._running(self.digest),)
        if self._phase == "loaded":
            return (self._running(self.after_preload_digest),)
        if self._phase == "token":
            return (self._running(self.after_token_digest),)
        return ()

    def generate_probe(self, name: str) -> GenerateResult:
        del name
        self.calls.append("generate_probe")
        self._phase = "token"
        return GenerateResult(
            failure="none",
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            generation_seconds=0.1,
        )

    def unload(self, name: str) -> UnloadResult:
        del name
        self.calls.append("unload")
        if self.unload_failure != "none":
            return UnloadResult(self.unload_failure)
        self._phase = "unloaded"
        return UnloadResult("none")

    def _running(self, digest: str) -> RunningModel:
        return RunningModel(
            name=self.name,
            digest=digest,
            size_bytes=self.size_bytes,
            size_vram_bytes=self.size_vram_bytes,
        )
