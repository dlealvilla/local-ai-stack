"""Safetensors metadata weight evidence. Never downloads weight tensors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED
from kultrun.model.contracts import (
    ModelCatalogEntry,
    WeightEvidenceSource,
    WeightFootprintEvidence,
)

FetchFn = Callable[[str], dict[str, Any] | None]


class SafetensorsWeightEvidenceProvider:
    """Factual stored-tensor lower bound from Safetensors metadata JSON."""

    def __init__(self, *, fetch: FetchFn | None = None) -> None:
        self._fetch = fetch if fetch is not None else _no_metadata

    @property
    def identity(self) -> Name:
        return Name("huggingface_safetensors")

    def footprint(self, entry: ModelCatalogEntry) -> WeightFootprintEvidence:
        ident = entry.metadata.model_id
        ref = entry.metadata.source_ref
        try:
            payload = self._fetch(ref)
        except Exception as error:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.UNAVAILABLE,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("safetensors metadata fetch failed",),
                source_revision=entry.metadata.source_revision,
                provider_failure=type(error).__name__,
            )
        if payload is None:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.UNAVAILABLE,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("safetensors metadata not available",),
                source_revision=entry.metadata.source_revision,
                provider_failure="metadata_unavailable",
            )
        try:
            total, shards = serialized_tensor_bytes(payload)
        except ValueError as error:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.HUGGINGFACE_SAFETENSORS,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("malformed safetensors metadata",),
                source_revision=entry.metadata.source_revision,
                provider_failure=str(error),
            )
        return WeightFootprintEvidence(
            model_id=ident,
            source_ref=ref,
            evidence_source=WeightEvidenceSource.HUGGINGFACE_SAFETENSORS,
            serialized_weight_tensor_bytes=total,
            confidence=Confidence.HIGH,
            provenance=(
                "huggingface_safetensors",
                "factual_storage_lower_bound",
                "does_not_include_kv_or_runtime",
                "full_weights_not_downloaded",
            ),
            source_revision=entry.metadata.source_revision,
            shard_count=shards,
        )


def serialized_tensor_bytes(payload: dict[str, Any]) -> tuple[int, int]:
    """Sum stored tensor extents. Offsets are authoritative over dtype guesses."""
    files = _files(payload)
    if not files:
        raise ValueError("malformed_safetensors_metadata")
    total = 0
    shards = 0
    for _name, body in files.items():
        tensors = _tensors(body)
        if not tensors:
            continue
        shards += 1
        for info in tensors.values():
            total += _extent(info)
    if shards == 0:
        raise ValueError("malformed_safetensors_metadata")
    return total, shards


def _files(payload: dict[str, Any]) -> dict[str, Any]:
    files = payload.get("files")
    if isinstance(files, dict) and files:
        return files
    tensors = payload.get("tensors")
    if isinstance(tensors, dict) and tensors:
        return {"model.safetensors": {"tensors": tensors}}
    return {}


def _tensors(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    tensors = body.get("tensors")
    if isinstance(tensors, dict):
        return tensors
    return {}


def _extent(info: object) -> int:
    if not isinstance(info, dict):
        raise ValueError("malformed_safetensors_metadata")
    offsets = info.get("data_offsets")
    if (
        isinstance(offsets, (list, tuple))
        and len(offsets) == 2
        and isinstance(offsets[0], int)
        and isinstance(offsets[1], int)
        and offsets[1] >= offsets[0]
    ):
        return offsets[1] - offsets[0]
    raise ValueError("malformed_safetensors_metadata")


def _no_metadata(_source_ref: str) -> dict[str, Any] | None:
    return None


def build(*, fetch: FetchFn | None = None) -> SafetensorsWeightEvidenceProvider:
    return SafetensorsWeightEvidenceProvider(fetch=fetch)
