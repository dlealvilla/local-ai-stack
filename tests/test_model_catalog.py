"""Stage 1.4A — curated catalog, normalized metadata, no selection.

The catalog describes candidates. It does not decide whether this host
can run them, download them, or rank them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kultrun.adapters.host import fixtures
from kultrun.adapters.http.console import asset_root
from kultrun.adapters.model_source.candidates import ORIGINAL_FIXTURES
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
        assert 18 <= len(entries) <= 30
        assert all(isinstance(entry, ModelCatalogEntry) for entry in entries)

    def test_the_original_six_remain_regression_fixtures(self) -> None:
        names = {
            entry.metadata.logical_name.value
            for entry in HuggingFaceSource().candidates()
        }
        assert set(ORIGINAL_FIXTURES) <= names

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
        names = {
            entry.metadata.logical_name.value: entry
            for entry in HuggingFaceSource().candidates()
        }
        for logical in ORIGINAL_FIXTURES:
            assert names[logical].requirement.estimation_method == "curated"
        for logical, entry in names.items():
            assert is_resolved(entry.requirement.estimation_method)
            if logical not in ORIGINAL_FIXTURES:
                assert entry.requirement.estimation_method == "formula_v0"
            assert entry.requirement.confidence.value in {
                "low",
                "medium",
                "high",
                "unknown",
            }
            assert entry.metadata.source_ref
            assert entry.metadata.source.value == "huggingface"
            assert entry.requirement.estimator_provider == "kultrun"

    def test_the_set_covers_size_bands_families_quant_and_moe(self) -> None:
        entries = HuggingFaceSource().candidates()
        params = [
            entry.metadata.parameter_count
            for entry in entries
            if is_resolved(entry.metadata.parameter_count)
        ]
        assert any(count < 2_000_000_000 for count in params)
        assert any(2_000_000_000 <= count < 4_000_000_000 for count in params)
        assert any(7_000_000_000 <= count < 10_000_000_000 for count in params)
        assert any(12_000_000_000 <= count < 16_000_000_000 for count in params)
        assert any(20_000_000_000 <= count < 35_000_000_000 for count in params)
        assert any(60_000_000_000 <= count < 80_000_000_000 for count in params)
        families = {entry.metadata.family for entry in entries}
        assert {"tinyllama", "qwen2.5", "llama-3.1", "mixtral"} <= families
        quants = {entry.metadata.quantization for entry in entries}
        assert {"q4_k", "awq", "fp16"} <= quants
        assert any(entry.metadata.is_moe is True for entry in entries)


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
        assert 18 <= len(candidates) <= 30
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


class TestSelectionSurface:
    def test_the_selection_api_exposes_only_the_active_estimator(
        self, tmp_path: Path
    ) -> None:
        configuration = config_schema().load(
            {
                "platform": {
                    "state_root": str(tmp_path / "state"),
                    "model_requirement_estimator": "kultrun",
                }
            }
        )
        platform = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
        payload = _call(platform, "/models/selection")
        assert payload["estimator_provider"] == "kultrun"
        assert "kultrun_estimate" not in payload
        assert "llmfit_estimate" not in payload
        assert "comparison" not in payload
        recommendation = payload["recommendation"]
        assert isinstance(recommendation, dict)
        assert recommendation["estimator_provider"] == "kultrun"
        assert "llmfit" not in recommendation.get("rationale", [""])[0].lower()
        encoded = str(payload)
        assert "RequirementEvidenceReconciler" not in encoded

    def test_auto_mode_api_uses_llmfit_when_the_plan_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kultrun.adapters.estimators.llmfit import fixture_plan

        fixture_root = (
            Path(__file__).resolve().parent / "fixtures" / "estimators" / "llmfit"
        )
        monkeypatch.delenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", raising=False)
        monkeypatch.setattr(
            "kultrun.adapters.estimators.llmfit._subprocess_plan",
            fixture_plan(fixture_root),
        )
        configuration = config_schema().load(
            {"platform": {"state_root": str(tmp_path / "state")}}
        )
        platform = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
        payload = _call(platform, "/models/selection")
        assert payload["estimator_mode"] == "auto"
        assert payload["estimator_provider"] == "llmfit"
        assert payload["requested_primary"] == "llmfit"
        assert payload["fallback_used"] is False
        assert "kultrun_estimate" not in payload
        assert "llmfit_estimate" not in payload
        assert "comparison" not in payload

    def test_auto_mode_api_falls_back_when_llmfit_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", raising=False)
        monkeypatch.setenv("PATH", "/nonexistent")
        configuration = config_schema().load(
            {"platform": {"state_root": str(tmp_path / "state")}}
        )
        platform = build(configuration, fixture=fixtures.DEFAULT_SHAPE)
        payload = _call(platform, "/models/selection")
        assert payload["estimator_mode"] == "auto"
        assert payload["estimator_provider"] == "kultrun"
        assert payload["fallback_used"] is True
        assert payload["fallback_reason"] == "provider_unavailable"
        assert "kultrun_estimate" not in payload
        assert "llmfit_estimate" not in payload

    def test_the_cli_recommend_subcommand_uses_the_configured_estimator(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from kultrun.main import main

        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
        monkeypatch.setenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", "kultrun")
        assert main(["models", "recommend"]) == 0
        printed = capsys.readouterr().out
        assert "mode kultrun" in printed
        assert "effective kultrun" in printed
        assert "fallback no" in printed
        assert "outcome" in printed
        assert "llmfit" not in printed

    def test_the_cli_auto_default_reports_fallback_when_llmfit_is_absent(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from kultrun.main import main

        monkeypatch.delenv("KULTRUN_MODEL_REQUIREMENT_ESTIMATOR", raising=False)
        monkeypatch.setenv("KULTRUN_STATE_ROOT", str(tmp_path / "state"))
        monkeypatch.setenv("KULTRUN_FIXTURE", fixtures.DEFAULT_SHAPE)
        monkeypatch.setenv("PATH", "/nonexistent")
        assert main(["models", "recommend"]) == 0
        printed = capsys.readouterr().out
        assert "mode auto" in printed
        assert "effective kultrun" in printed
        assert "fallback provider_unavailable" in printed


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
        catalog = html.split('id="catalog-panel"')[1].split('id="')[1]
        assert "Model catalog" in html
        assert "not recommend" in html
        assert "rank or download" in html
        assert "renderCatalog" in script
        assert catalog  # panel is present; selection is a different panel

    def test_the_selection_panel_shows_the_active_estimator_only(self) -> None:
        html = (asset_root() / "index.html").read_text(encoding="utf-8")
        script = (asset_root() / "app.js").read_text(encoding="utf-8")
        assert "Model selection" in html
        assert "/models/selection" in script
        assert "kultrun vs llmfit" not in script.lower()
        assert "dual estimate" not in script.lower()
        assert "RequirementEvidenceReconciler" not in script
        assert "llmfit unavailable" in script
        assert "fallbackLabel" in script
