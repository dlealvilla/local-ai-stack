"""Hugging Face identity with a packaged curated candidate set.

The source_ref values are Hub ids. v0 does not call huggingface_hub, does
not search the Hub, and does not download. Live fetch is `docs/DEBT.md`
K-35. Estimates are coarse and conservative (K-36).
"""

from __future__ import annotations

import hashlib

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, Maybe
from kultrun.model.contracts import (
    ModelCatalogEntry,
    ModelId,
    ModelMetadata,
    ModelRequirement,
)

IDENTITY = Name("huggingface")
METHOD = "curated-conservative-v0"

GiB = 1024**3


def _id(logical: str) -> ModelId:
    token = hashlib.sha256(logical.encode("utf-8")).hexdigest()[:16]
    return ModelId(f"model_{token}")


def _gib(value: float) -> int:
    return int(value * GiB)


def _entry(
    *,
    logical: str,
    source_ref: str,
    display_name: str,
    family: str,
    parameters: int,
    quantization: str,
    context: int,
    architecture: str,
    license_id: str,
    commercial: Maybe[bool],
    runtimes: tuple[str, ...],
    storage_gib: float,
    peak_gib: float,
    ram_gib: float,
    vram_weights_gib: float,
    vram_overhead_gib: float,
    estimated_vram_gib: float,
    assumed_context: int,
    kv_per_token: Maybe[int],
    confidence: Confidence,
    revision: Maybe[str] = NOT_PROVIDED,
    unified_gib: Maybe[int] = NOT_PROVIDED,
    activation_gib: float | None = None,
) -> ModelCatalogEntry:
    model_id = _id(logical)
    metadata = ModelMetadata(
        model_id=model_id,
        logical_name=Name(logical),
        source=IDENTITY,
        source_ref=source_ref,
        source_revision=revision,
        family=family,
        parameter_count=parameters,
        context_length_tokens=context,
        quantization=quantization,
        license_id=license_id,
        commercial_use_restricted=commercial,
        architecture=architecture,
        display_name=display_name,
        supported_runtimes=runtimes,
    )
    activations: Maybe[int] = (
        _gib(activation_gib) if activation_gib is not None else NOT_PROVIDED
    )
    requirement = ModelRequirement(
        model_id=model_id,
        confidence=confidence,
        storage_bytes=_gib(storage_gib),
        peak_additional_bytes=_gib(peak_gib),
        vram_weights_bytes=_gib(vram_weights_gib),
        vram_kv_bytes_per_token=kv_per_token,
        vram_overhead_bytes=_gib(vram_overhead_gib),
        ram_bytes=_gib(ram_gib),
        unified_memory_bytes=unified_gib,
        activation_bytes=activations,
        estimated_vram_bytes=_gib(estimated_vram_gib),
        assumed_context_tokens=assumed_context,
        supported_runtimes=runtimes,
        estimation_method=METHOD,
    )
    return ModelCatalogEntry(metadata=metadata, requirement=requirement)


#: Six variants: tiny, small, mid-AWQ, mid-FP16, large-AWQ, too-large.
#: Spread is the point; this is not a marketplace.
_CANDIDATES: tuple[ModelCatalogEntry, ...] = (
    _entry(
        logical="tinyllama-1.1b-chat-q4",
        source_ref="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
        display_name="TinyLlama 1.1B Chat Q4",
        family="tinyllama",
        parameters=1_100_000_000,
        quantization="q4_k",
        context=2048,
        architecture="llama",
        license_id="apache-2.0",
        commercial=False,
        runtimes=("llama.cpp", "vllm"),
        storage_gib=0.7,
        peak_gib=1.5,
        ram_gib=2.5,
        vram_weights_gib=0.8,
        vram_overhead_gib=0.4,
        estimated_vram_gib=1.2,
        assumed_context=2048,
        kv_per_token=NOT_PROVIDED,
        confidence=Confidence.LOW,
    ),
    _entry(
        logical="qwen2.5-3b-instruct-q4",
        source_ref="Qwen/Qwen2.5-3B-Instruct",
        display_name="Qwen2.5 3B Instruct Q4",
        family="qwen2.5",
        parameters=3_090_000_000,
        quantization="q4_k",
        context=32_768,
        architecture="qwen2",
        license_id="apache-2.0",
        commercial=False,
        runtimes=("llama.cpp", "vllm"),
        storage_gib=2.0,
        peak_gib=4.5,
        ram_gib=6.0,
        vram_weights_gib=2.2,
        vram_overhead_gib=0.6,
        estimated_vram_gib=3.2,
        assumed_context=8192,
        kv_per_token=32_768,
        confidence=Confidence.MEDIUM,
        activation_gib=0.4,
    ),
    _entry(
        logical="qwen2.5-7b-instruct-awq",
        source_ref="Qwen/Qwen2.5-7B-Instruct-AWQ",
        display_name="Qwen2.5 7B Instruct AWQ",
        family="qwen2.5",
        parameters=7_610_000_000,
        quantization="awq",
        context=32_768,
        architecture="qwen2",
        license_id="apache-2.0",
        commercial=False,
        runtimes=("vllm",),
        storage_gib=5.4,
        peak_gib=12.0,
        ram_gib=10.0,
        vram_weights_gib=5.4,
        vram_overhead_gib=1.2,
        estimated_vram_gib=8.0,
        assumed_context=8192,
        kv_per_token=65_536,
        confidence=Confidence.MEDIUM,
        activation_gib=0.8,
    ),
    _entry(
        logical="llama-3.1-8b-instruct-fp16",
        source_ref="meta-llama/Llama-3.1-8B-Instruct",
        display_name="Llama 3.1 8B Instruct FP16",
        family="llama-3.1",
        parameters=8_030_000_000,
        quantization="fp16",
        context=131_072,
        architecture="llama",
        license_id="llama-3.1",
        commercial=NOT_PROVIDED,
        runtimes=("vllm", "llama.cpp"),
        storage_gib=16.0,
        peak_gib=33.0,
        ram_gib=20.0,
        vram_weights_gib=16.1,
        vram_overhead_gib=1.5,
        estimated_vram_gib=19.5,
        assumed_context=8192,
        kv_per_token=131_072,
        confidence=Confidence.MEDIUM,
        activation_gib=1.0,
    ),
    _entry(
        logical="qwen2.5-14b-instruct-awq",
        source_ref="Qwen/Qwen2.5-14B-Instruct-AWQ",
        display_name="Qwen2.5 14B Instruct AWQ",
        family="qwen2.5",
        parameters=14_700_000_000,
        quantization="awq",
        context=32_768,
        architecture="qwen2",
        license_id="apache-2.0",
        commercial=False,
        runtimes=("vllm",),
        storage_gib=10.0,
        peak_gib=22.0,
        ram_gib=16.0,
        vram_weights_gib=10.0,
        vram_overhead_gib=1.8,
        estimated_vram_gib=14.5,
        assumed_context=8192,
        kv_per_token=98_304,
        confidence=Confidence.MEDIUM,
        activation_gib=1.2,
    ),
    _entry(
        logical="qwen2.5-72b-instruct-awq",
        source_ref="Qwen/Qwen2.5-72B-Instruct-AWQ",
        display_name="Qwen2.5 72B Instruct AWQ",
        family="qwen2.5",
        parameters=72_700_000_000,
        quantization="awq",
        context=32_768,
        architecture="qwen2",
        license_id="apache-2.0",
        commercial=False,
        runtimes=("vllm",),
        storage_gib=40.0,
        peak_gib=82.0,
        ram_gib=48.0,
        vram_weights_gib=40.0,
        vram_overhead_gib=3.0,
        estimated_vram_gib=48.0,
        assumed_context=4096,
        kv_per_token=262_144,
        confidence=Confidence.LOW,
        activation_gib=2.0,
    ),
)


class HuggingFaceSource:
    """Hub identity, curated set. Does not search or download."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        return _CANDIDATES


def build() -> HuggingFaceSource:
    """The composition root's constructor."""
    return HuggingFaceSource()
