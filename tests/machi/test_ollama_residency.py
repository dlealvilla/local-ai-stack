"""Provider residency observation. Fixtures only. No admission and no serve."""

from __future__ import annotations

from machi.adapters.model.ollama_api import (
    OllamaApiError,
    PreloadResult,
    RunningModel,
    UnloadResult,
)
from machi.adapters.model.ollama_residency import (
    ResidencyState,
    observe_residency,
    refresh_residency,
    release_residency,
)

DIGEST = "ab" * 32
OTHER = "cd" * 32


class _Api:
    def __init__(self, running: tuple[RunningModel, ...] = ()) -> None:
        self.running = running
        self.calls: list[str] = []
        self.fail = ""

    def list_models(self) -> tuple[object, ...]:
        return ()

    def show_model(self, name: str) -> None:
        del name

    def preload(self, name: str) -> PreloadResult:
        del name
        self.calls.append("preload")
        if self.fail == "preload":
            raise OllamaApiError("transport")
        self.running = (
            RunningModel(
                "smollm2:135m",
                f"sha256:{DIGEST}",
                10,
                20,
                "2026-09-24T10:00:00Z",
            ),
        )
        return PreloadResult("none", load_seconds=1.0)

    def running_models(self) -> tuple[RunningModel, ...]:
        self.calls.append("ps")
        if self.fail == "ps":
            raise OllamaApiError("transport")
        return self.running

    def generate_probe(self, name: str) -> object:
        del name
        raise AssertionError("residency must not probe tokens")

    def unload(self, name: str) -> UnloadResult:
        del name
        self.calls.append("unload")
        if self.fail == "unload":
            raise OllamaApiError("transport")
        self.running = ()
        return UnloadResult("none")


def test_expected_resident_cites_public_fields() -> None:
    api = _Api(
        (
            RunningModel(
                "smollm2:135m",
                f"sha256:{DIGEST}",
                10,
                374,
                "2026-09-24T10:00:00Z",
            ),
        )
    )
    seen = observe_residency(api, name="smollm2:135m", digest=DIGEST)
    assert seen.state is ResidencyState.EXPECTED_RESIDENT
    assert seen.digest == DIGEST
    assert seen.size_vram_bytes == 374
    assert seen.expires_at == "2026-09-24T10:00:00Z"


def test_absent_wrong_and_unreadable_states() -> None:
    assert observe_residency(_Api(), name="smollm2:135m", digest=DIGEST).state is (
        ResidencyState.ABSENT
    )
    wrong = _Api((RunningModel("smollm2:135m", OTHER, 10, 4, None),))
    assert (
        observe_residency(wrong, name="smollm2:135m", digest=DIGEST).state
        is ResidencyState.WRONG_IDENTITY
    )
    renamed = _Api((RunningModel("other:tag", DIGEST, 10, 4, None),))
    assert (
        observe_residency(renamed, name="smollm2:135m", digest=DIGEST).state
        is ResidencyState.WRONG_IDENTITY
    )
    broken = _Api()
    broken.fail = "ps"
    assert observe_residency(broken, name="smollm2:135m", digest=DIGEST).state is (
        ResidencyState.UNRESOLVED
    )
    assert observe_residency(_Api(), name="smollm2:135m", digest="tag").state is (
        ResidencyState.UNRESOLVED
    )


def test_refresh_and_release_use_public_calls_then_ps() -> None:
    api = _Api()
    refreshed = refresh_residency(api, name="smollm2:135m", digest=DIGEST)
    assert api.calls == ["preload", "ps"]
    assert refreshed.state is ResidencyState.EXPECTED_RESIDENT
    released = release_residency(api, name="smollm2:135m", digest=DIGEST)
    assert api.calls[-2:] == ["unload", "ps"]
    assert released.state is ResidencyState.ABSENT
    api.fail = "unload"
    assert (
        release_residency(api, name="smollm2:135m", digest=DIGEST).state
        is ResidencyState.UNRESOLVED
    )
