"""Optional Accelerate structural weight evidence. Not vLLM feasibility."""

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

AnalyzeFn = Callable[[ModelCatalogEntry], dict[str, Any]]


class AccelerateStructuralProvider:
    """Empty-skeleton weight placement evidence. Never a serving authority."""

    def __init__(self, *, analyze: AnalyzeFn | None = None) -> None:
        self._analyze = analyze

    @property
    def identity(self) -> Name:
        return Name("accelerate_structural")

    def footprint(self, entry: ModelCatalogEntry) -> WeightFootprintEvidence:
        ident = entry.metadata.model_id
        ref = entry.metadata.source_ref
        if self._analyze is None:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=(
                    "structural_check_not_available",
                    (
                        "accelerate_installed"
                        if _accelerate_available()
                        else "accelerate_not_installed"
                    ),
                    "injected_analyzer_required",
                    "does_not_download_weights",
                ),
                source_revision=entry.metadata.source_revision,
                provider_failure="structural_check_not_available",
            )
        analyzer = self._analyze
        try:
            payload = analyzer(entry)
        except Exception as error:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("accelerate structural analysis failed",),
                source_revision=entry.metadata.source_revision,
                provider_failure=type(error).__name__,
            )
        if payload.get("trust_remote_code"):
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("trust_remote_code is not enabled",),
                source_revision=entry.metadata.source_revision,
                provider_failure="trust_remote_code_not_applicable",
            )
        if payload.get("applicable") is False:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("architecture not applicable to accelerate skeleton",),
                source_revision=entry.metadata.source_revision,
                provider_failure="not_applicable",
            )
        bytes_ = payload.get("weight_bytes")
        if not isinstance(bytes_, int) or bytes_ < 0:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=("accelerate produced no weight byte total",),
                source_revision=entry.metadata.source_revision,
                provider_failure="unresolved",
            )
        return WeightFootprintEvidence(
            model_id=ident,
            source_ref=ref,
            evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
            serialized_weight_tensor_bytes=bytes_,
            confidence=Confidence.MEDIUM,
            provenance=(
                "accelerate_structural",
                "init_empty_weights",
                "not_vllm_serving_authority",
                "full_weights_not_loaded",
            ),
            source_revision=entry.metadata.source_revision,
        )


def _accelerate_available() -> bool:
    try:
        import importlib

        importlib.import_module("accelerate")
    except ImportError:
        return False
    return True


def build(*, analyze: AnalyzeFn | None = None) -> AccelerateStructuralProvider:
    return AccelerateStructuralProvider(analyze=analyze)
