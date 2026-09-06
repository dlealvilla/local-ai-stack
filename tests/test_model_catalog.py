"""Stage 1.4A — curated catalog, normalized metadata, no selection.

The catalog describes candidates. It does not decide whether this host
can run them, download them, or rank them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.http.console import asset_root
from kultrun.adapters.model_source.huggingface import HuggingFaceSource
from kultrun.api.contracts import ApiRequest, Method
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import Platform, build, config_schema
from kultrun.model.contracts import ModelCatalogEntry
from tests.architecture import scan


def _platform(tmp_path: Path) -> Platform:
    configuration = config_schema().load(
        {"platform": {"state_root": str(tmp_path / "state")}}
    )
    return build(configuration)


def _call(platform: Platform, path: str) -> dict[str, object]:
    response = platform.router.handle(
        ApiRequest(method=Method.GET, path=f"/v1{path}", query={})
    )
    assert response.status == 200, response.body
    payload = response.body["payload"]
    assert isinstance(payload, dict)
    return payload


class TestTheSourceIsBoundedAndHonest:
    def test_the_adapter_does_not_search_or_download(self) -> None:
        source = HuggingFaceSource()
        assert source.identity.value == "huggingface"
        entries = source.candidates()
        assert 4 <= len(entries) <= 8
        assert all(isinstance(entry, ModelCatalogEntry) for entry in entries)

    def test_quantized_variants_are_distinct_candidates(self) -> None:
        names = {
            entry.metadata.logical_name.value
            for entry in HuggingFaceSource().candidates()
        }
        assert "qwen2.5-7b-instruct-awq" in names
        assert "llama-3.1-8b-instruct-fp16" in names

    def test_a_requirement_never_names_a_host(self) -> None:
        for entry in HuggingFaceSource().candidates():
            assert not hasattr(entry.requirement, "host_id")
            encoded = entry.requirement.__dataclass_fields__
            assert "host_id" not in encoded

    def test_unknown_stays_unresolved(self) -> None:
        tiny = next(
            entry
            for entry in HuggingFaceSource().candidates()
            if entry.metadata.logical_name.value == "tinyllama-1.1b-chat-q4"
        )
        assert not is_resolved(tiny.requirement.vram_kv_bytes_per_token)
        assert not is_resolved(tiny.requirement.unified_memory_bytes)

    def test_deployed_size_is_not_parameter_count(self) -> None:
        for entry in HuggingFaceSource().candidates():
            meta = entry.metadata
            req = entry.requirement
            if is_resolved(meta.parameter_count) and is_resolved(
                req.estimated_vram_bytes
            ):
                assert req.estimated_vram_bytes != meta.parameter_count

    def test_every_candidate_carries_method_and_confidence(self) -> None:
        for entry in HuggingFaceSource().candidates():
            assert is_resolved(entry.requirement.estimation_method)
            assert entry.requirement.estimation_method == "curated-conservative-v0"
            assert entry.requirement.confidence.value in {
                "low",
                "medium",
                "high",
                "unknown",
            }
            assert entry.metadata.source_ref
            assert entry.metadata.source.value == "huggingface"


class TestTheApiIsReadOnly:
    def test_the_catalog_surface_does_not_rank(self, tmp_path: Path) -> None:
        payload = _call(_platform(tmp_path), "/models")
        assert payload["ranking"] is False
        assert payload["selection"] is False
        assert payload["download"] is False
        source = payload["source"]
        assert isinstance(source, dict)
        assert source["live_fetch"] is False
        candidates = payload["candidates"]
        assert isinstance(candidates, list)
        assert 4 <= len(candidates) <= 8
        first = candidates[0]
        assert isinstance(first, dict)
        assert "metadata" in first
        assert "requirement" in first
        assert "recommended" not in payload
        assert "primary" not in payload

    def test_get_does_not_acquire(self, tmp_path: Path) -> None:
        platform = _platform(tmp_path)
        _call(platform, "/models")
        _call(platform, "/models")
        assert platform.models.entries() == HuggingFaceSource().candidates()

    def test_post_is_not_a_catalog_mutation(self, tmp_path: Path) -> None:
        response = _platform(tmp_path).router.handle(
            ApiRequest(method=Method.POST, path="/v1/models", query={})
        )
        assert response.status in (404, 405)

    def test_the_cli_lists_candidates_without_recommending(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from kultrun.main import main

        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.delenv("KULTRUN_FIXTURE", raising=False)
        assert main(["models"]) == 0
        printed = capsys.readouterr().out
        assert "selection no" in printed
        assert "ranking no" in printed
        assert "tinyllama-1.1b-chat-q4" in printed
        assert "RECOMMENDED" not in printed


class TestArchitecture:
    def test_the_model_adapter_does_not_import_planning_or_capacity(self) -> None:
        edges = [
            edge
            for edge in scan(Path(__file__).resolve().parent.parent / "src")
            if edge.source_module.startswith("kultrun.adapters.model_source")
            and edge.target_package in {"planning", "capacity", "resource"}
        ]
        assert edges == []

    def test_the_huggingface_adapter_does_not_import_the_hub_client(self) -> None:
        source = (
            Path(__file__).resolve().parent.parent
            / "src/kultrun/adapters/model_source/huggingface.py"
        ).read_text(encoding="utf-8")
        assert "import huggingface_hub" not in source
        assert "from huggingface_hub" not in source


class TestConsoleHonesty:
    def test_unresolved_wire_values_are_recognised(self) -> None:
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "$unresolved" in script
        assert "isUnresolved" in script

    def test_the_catalog_panel_does_not_recommend(self) -> None:
        html = (asset_root() / "index.html").read_text(encoding="utf-8")
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "Model catalog" in html
        assert "not recommend" in html
        assert "rank or download" in html
        assert "RECOMMENDED" not in script
        assert "preferred band" not in script.lower()
