"""T2-B connected-provider probe. Imports installed kultrun, not src/."""

from __future__ import annotations

import json
import os
from importlib import metadata
from pathlib import Path

from kultrun.adapters.estimators.llmfit import LlmfitRequirementEstimator
from kultrun.adapters.model_source.accelerate_fit import live_structural_analyze
from kultrun.adapters.model_source.candidates import (
    acceptance_candidate,
    packaged_candidates,
)
from kultrun.adapters.model_source.huggingface import HuggingFaceSource, hub_list_models
from kultrun.adapters.model_source.safetensors import (
    SafetensorsWeightEvidenceProvider,
    huggingface_safetensors_payload,
)
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import MemoryPlacement, ModelEstimationRequest
from kultrun.model.discovery import DiscoveryQuery

WEIGHT_SUFFIXES = {".safetensors", ".bin", ".gguf", ".pt", ".pth"}


def _weight_files(root: Path) -> list[str]:
    if not root.exists():
        return []
    found: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in WEIGHT_SUFFIXES:
            found.append(str(path))
    return found


def main() -> int:
    qwen = next(
        item
        for item in packaged_candidates()
        if item.metadata.logical_name.value == "qwen2.5-7b-instruct-awq"
    )
    listing = HuggingFaceSource(list_models=hub_list_models).discover(
        DiscoveryQuery(limit=8)
    )
    payload = huggingface_safetensors_payload(qwen)
    evidence = SafetensorsWeightEvidenceProvider(
        fetch=huggingface_safetensors_payload
    ).footprint(qwen)
    tiny = acceptance_candidate()
    analysis = live_structural_analyze(tiny, max_memory={"cpu": "1GiB"})
    estimator = LlmfitRequirementEstimator()
    raw = estimator.invoke_plan(qwen.metadata.source_ref, 8192, "AWQ-4bit")
    meta = qwen.metadata
    serving = estimator.estimate(
        ModelEstimationRequest(
            model_id=meta.model_id,
            source_ref=meta.source_ref,
            source_revision=meta.source_revision,
            artifact_format=NOT_PROVIDED,
            quantization=meta.quantization,
            context_tokens=8192,
            runtime="vllm",
            placement=MemoryPlacement.DISCRETE_GPU,
            offload_allowed=False,
            tensor_parallel=1,
            batch_size=1,
            runtime_version="0.28.0",
        )
    )
    cache = Path(os.environ.get("HF_HOME") or (Path.home() / ".cache" / "huggingface"))
    weights = _weight_files(cache)
    print(
        json.dumps(
            {
                "hf_discovery_live": listing.live,
                "hf_discovery_failure": listing.source_failure,
                "hf_discovery_hits": len(listing.remote_hits),
                "hf_catalog_retained": len(listing.catalog_entries),
                "hf_model": meta.source_ref,
                "hf_revision": (
                    meta.source_revision
                    if isinstance(meta.source_revision, str)
                    else None
                ),
                "safetensors_status": "ok" if payload else "missing",
                "sharded": (
                    bool(payload.get("sharded")) if isinstance(payload, dict) else None
                ),
                "parameter_counts": (
                    payload.get("parameter_count")
                    if isinstance(payload, dict)
                    else None
                ),
                "serialized_tensor_bytes": (
                    evidence.serialized_weight_tensor_bytes
                    if is_resolved(evidence.serialized_weight_tensor_bytes)
                    else None
                ),
                "full_weight_download": bool(weights),
                "weight_cache_files": weights,
                "accelerate_model": tiny.metadata.source_ref,
                "accelerate_revision": tiny.metadata.source_revision,
                "config_retrieved": bool(analysis.get("config")),
                "meta_device": bool(analysis.get("meta_device")),
                "actual_weights_loaded": bool(analysis.get("weights_loaded")),
                "max_memory": analysis.get("max_memory"),
                "device_map_keys": list(analysis.get("device_map_keys") or ()),
                "authority": "STRUCTURAL_EVIDENCE_ONLY",
                "llmfit_version": estimator.version,
                "llmfit_pkg": metadata.version("llmfit"),
                "raw_minimum_vram_gb": (raw.get("minimum") or {}).get("vram_gb"),
                "raw_recommended_vram_gb": (raw.get("recommended") or {}).get(
                    "vram_gb"
                ),
                "raw_context": raw.get("context"),
                "raw_quantization": raw.get("quantization"),
                "kv_alternatives": raw.get("kv_alternatives"),
                "estimator_provider": serving.estimator_provider,
                "estimation_method": serving.estimation_method,
                "refined_vram_bytes": (
                    serving.estimated_vram_bytes
                    if is_resolved(serving.estimated_vram_bytes)
                    else None
                ),
                "vram_weights_bytes": (
                    serving.vram_weights_bytes
                    if is_resolved(serving.vram_weights_bytes)
                    else None
                ),
                "vram_kv_cache_bytes": (
                    serving.vram_kv_cache_bytes
                    if is_resolved(serving.vram_kv_cache_bytes)
                    else None
                ),
                "refinement": [
                    item
                    for item in serving.assumptions
                    if "vLLM serving refinement" in item
                ],
                "assumptions": list(serving.assumptions),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
