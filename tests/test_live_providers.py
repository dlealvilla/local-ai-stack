"""Optional live Hub / Safetensors / Accelerate provider wiring."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from kultrun.adapters.model_source import hub_client
from kultrun.adapters.model_source.accelerate_fit import AccelerateStructuralProvider
from kultrun.adapters.model_source.candidates import packaged_candidates
from kultrun.adapters.model_source.huggingface import (
    HuggingFaceSource,
    hub_list_models,
)
from kultrun.adapters.model_source.safetensors import (
    SafetensorsWeightEvidenceProvider,
    huggingface_safetensors_payload,
    serialized_tensor_bytes,
)
from kultrun.kernel.unresolved import is_resolved
from kultrun.main import (
    SOURCE_MODE_VARIABLE,
    resolve_configuration,
    resolve_model_source,
)
from kultrun.model.discovery import DiscoveryQuery
from kultrun.platform.contracts import PlatformSettings

SOURCE = Path(__file__).resolve().parent.parent / "src" / "kultrun" / "adapters"


class TestSourceMode:
    def test_default_is_offline(self) -> None:
        settings = resolve_configuration({}).section(PlatformSettings)
        assert settings.model_source_mode == "offline"
        source, _weights, structural = resolve_model_source("offline")
        assert source._list_models is None
        assert structural._enabled is False

    def test_live_env_selects_hub_functions(self) -> None:
        loaded = resolve_configuration({SOURCE_MODE_VARIABLE: "live"}).section(
            PlatformSettings
        )
        assert loaded.model_source_mode == "live"
        source, weights, structural = resolve_model_source("live")
        assert source._list_models is hub_list_models
        assert weights._fetch is huggingface_safetensors_payload
        assert structural._enabled is True


class TestLiveListingSeam:
    def test_normalized_filters_are_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, object] = {}

        def fake(kwargs: dict[str, object]) -> tuple[object, ...]:
            seen.update(kwargs)
            return (
                SimpleNamespace(
                    id="org/demo",
                    pipeline_tag="text-generation",
                    gated=False,
                    tags=["vllm"],
                ),
            )

        monkeypatch.setattr(
            "kultrun.adapters.model_source.huggingface.list_model_infos",
            fake,
        )
        query = DiscoveryQuery(
            pipeline_tag="text-generation",
            gated=False,
            apps=("vllm",),
            search="qwen",
            limit=12,
        )
        hits = hub_list_models(query)
        assert seen["pipeline_tag"] == "text-generation"
        assert seen["gated"] is False
        assert seen["apps"] == ["vllm"]
        assert seen["search"] == "qwen"
        assert seen["limit"] == 12
        assert hits[0].source_ref == "org/demo"
        result = HuggingFaceSource(list_models=hub_list_models).discover(query)
        assert result.live is True
        assert result.payload()["compatibility"] is False

    def test_hub_error_keeps_catalog(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail(_kwargs: dict[str, object]) -> tuple[object, ...]:
            raise ConnectionError("hub down")

        monkeypatch.setattr(
            "kultrun.adapters.model_source.huggingface.list_model_infos",
            fail,
        )
        result = HuggingFaceSource(list_models=hub_list_models).discover(
            DiscoveryQuery()
        )
        assert result.live is False
        assert result.source_failure == "ConnectionError"
        assert len(result.catalog_entries) == len(packaged_candidates())

    def test_unsupported_apps_kwarg_falls_back_to_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: list[dict[str, object]] = []

        class Hub:
            class HfApi:
                def __init__(self, token: str | None = None) -> None:
                    pass

                def list_models(
                    self,
                    *,
                    pipeline_tag: str | None = None,
                    gated: bool | None = None,
                    filter: object = None,  # noqa: A002
                    limit: int | None = None,
                    tags: object = None,
                    search: str | None = None,
                ) -> list[object]:
                    recorded.append(
                        {
                            "pipeline_tag": pipeline_tag,
                            "filter": filter,
                            "limit": limit,
                        }
                    )
                    return []

        monkeypatch.setattr(hub_client, "import_hub", lambda: Hub)
        monkeypatch.setattr(hub_client, "hub_token", lambda: None)
        hub_client.list_model_infos(
            {
                "pipeline_tag": "text-generation",
                "gated": False,
                "apps": ["vllm"],
                "limit": 5,
            }
        )
        assert recorded[0]["filter"] == ["vllm"]
        assert recorded[0]["pipeline_tag"] == "text-generation"


class TestSafetensorsLiveSeam:
    def test_get_safetensors_metadata_is_the_api(self) -> None:
        text = (SOURCE / "model_source" / "hub_client.py").read_text(encoding="utf-8")
        assert "get_safetensors_metadata" in text
        assert "snapshot_download(" not in text
        assert "hf_hub_download(" not in text
        adapter = (SOURCE / "model_source" / "safetensors.py").read_text(
            encoding="utf-8"
        )
        assert "snapshot_download(" not in adapter
        assert "hf_hub_download(" not in adapter

    def test_index_total_size_is_preferred(self) -> None:
        total, shards = serialized_tensor_bytes(
            {
                "metadata": {"total_size": 900},
                "sharded": True,
                "files": {
                    "a.safetensors": {"tensors": {"w": {"data_offsets": [0, 40]}}},
                    "b.safetensors": {"tensors": {"w": {"data_offsets": [0, 60]}}},
                },
            }
        )
        assert total == 900
        assert shards == 2

    def test_payload_uses_revision_and_offsets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = packaged_candidates()[2]
        seen: dict[str, object] = {}

        def fake(
            repo_id: str, *, revision: str | None = None, timeout: int = 30
        ) -> object:
            seen["repo_id"] = repo_id
            seen["revision"] = revision
            return SimpleNamespace(
                metadata={"total_size": 128},
                sharded=False,
                files_metadata={
                    "model.safetensors": SimpleNamespace(
                        tensors={
                            "w": SimpleNamespace(
                                dtype="F16", shape=[8], data_offsets=(0, 128)
                            )
                        }
                    )
                },
                parameter_count={"F16": 64},
            )

        monkeypatch.setattr(
            "kultrun.adapters.model_source.safetensors.safetensors_metadata",
            fake,
        )
        payload = huggingface_safetensors_payload(entry)
        assert payload is not None
        assert payload["full_weight_download"] is False
        evidence = SafetensorsWeightEvidenceProvider(
            fetch=huggingface_safetensors_payload
        ).footprint(entry)
        assert seen["repo_id"] == entry.metadata.source_ref
        assert evidence.serialized_weight_tensor_bytes == 128
        assert "full_weights_not_downloaded" in evidence.provenance
        assert "factual_storage_lower_bound" in evidence.provenance


class TestAccelerateLiveSeam:
    def test_source_uses_empty_weights_and_never_loads_checkpoint(self) -> None:
        text = (SOURCE / "model_source" / "accelerate_fit.py").read_text(
            encoding="utf-8"
        )
        assert "init_empty_weights" in text
        assert "infer_auto_device_map" in text
        assert "load_checkpoint_and_dispatch" not in text
        assert "trust_remote_code=True" not in text
        assert "REMOTE_CODE_FLAG = False" in text

    def test_missing_extra_is_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_entry: object, *, max_memory: object = None) -> dict[str, object]:
            raise ImportError("accelerate")

        monkeypatch.setattr(
            "kultrun.adapters.model_source.accelerate_fit.live_structural_analyze",
            boom,
        )
        evidence = AccelerateStructuralProvider(enabled=True).footprint(
            packaged_candidates()[0]
        )
        assert not is_resolved(evidence.serialized_weight_tensor_bytes)
        assert evidence.provider_failure == "structural_check_not_available"

    def test_for_placement_does_not_mark_available(self) -> None:
        def analyze(_entry: object) -> dict[str, object]:
            return {"weight_bytes": 2048, "trust_remote_code": False}

        provider = AccelerateStructuralProvider(analyze=analyze, enabled=True)
        bound = provider.for_placement(24 * 1024**3)
        evidence = bound.footprint(packaged_candidates()[0])
        assert evidence.serialized_weight_tensor_bytes == 2048
        assert "structural_evidence_only" in evidence.provenance
        assert "not_vllm_serving_authority" in evidence.provenance
