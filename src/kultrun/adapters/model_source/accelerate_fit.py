"""Optional Accelerate structural weight evidence. Not vLLM feasibility."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from kultrun.evidence.contracts import Confidence
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import (
    ModelCatalogEntry,
    WeightEvidenceSource,
    WeightFootprintEvidence,
)

AnalyzeFn = Callable[[ModelCatalogEntry], dict[str, Any]]
REMOTE_CODE_FLAG = False  # never inverted; trust_remote_code stays disabled


class AccelerateStructuralProvider:
    """Empty-skeleton weight placement evidence. Never a serving authority."""

    def __init__(
        self,
        *,
        analyze: AnalyzeFn | None = None,
        enabled: bool = False,
        max_memory: Mapping[str, int | str] | None = None,
    ) -> None:
        self._analyze = analyze
        self._enabled = enabled
        self._max_memory = None if max_memory is None else dict(max_memory)

    @property
    def identity(self) -> Name:
        return Name("accelerate_structural")

    def for_placement(
        self, available_vram_bytes: object
    ) -> AccelerateStructuralProvider:
        """Copy with current placement limits. Does not import planning."""
        max_memory: dict[str, int | str] | None = None
        if isinstance(available_vram_bytes, int) and available_vram_bytes > 0:
            max_memory = {"cuda:0": available_vram_bytes, "cpu": 0}
        return AccelerateStructuralProvider(
            analyze=self._analyze,
            enabled=self._enabled,
            max_memory=max_memory,
        )

    def footprint(self, entry: ModelCatalogEntry) -> WeightFootprintEvidence:
        ident = entry.metadata.model_id
        ref = entry.metadata.source_ref
        if self._analyze is None and not self._enabled:
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
                    "does_not_download_weights",
                ),
                source_revision=entry.metadata.source_revision,
                provider_failure="structural_check_not_available",
            )
        try:
            payload = (
                self._analyze(entry)
                if self._analyze is not None
                else live_structural_analyze(entry, max_memory=self._max_memory)
            )
        except ImportError as error:
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=(
                    "structural_check_not_available",
                    "optional analysis extra missing",
                    str(error.__class__.__name__),
                ),
                source_revision=entry.metadata.source_revision,
                provider_failure="structural_check_not_available",
            )
        except Exception as error:
            if _remote_code_required(error):
                return _not_applicable(
                    entry,
                    "trust_remote_code is not enabled",
                    "trust_remote_code_not_applicable",
                )
            return WeightFootprintEvidence(
                model_id=ident,
                source_ref=ref,
                evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
                serialized_weight_tensor_bytes=NOT_PROVIDED,
                confidence=Confidence.UNKNOWN,
                provenance=(
                    "accelerate structural analysis failed",
                    type(error).__name__,
                ),
                source_revision=entry.metadata.source_revision,
                provider_failure=type(error).__name__,
            )
        if payload.get("trust_remote_code"):
            return _not_applicable(
                entry,
                "trust_remote_code is not enabled",
                "trust_remote_code_not_applicable",
            )
        if payload.get("applicable") is False:
            reason = payload.get("reason") or (
                "architecture not applicable to accelerate skeleton"
            )
            return _not_applicable(
                entry,
                str(reason),
                "not_applicable",
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
                "infer_auto_device_map",
                "not_vllm_serving_authority",
                "structural_evidence_only",
                "full_weights_not_loaded",
            ),
            source_revision=entry.metadata.source_revision,
        )


def live_structural_analyze(
    entry: ModelCatalogEntry,
    *,
    max_memory: Mapping[str, int | str] | None = None,
) -> dict[str, Any]:
    """Config + meta skeleton. Does not load checkpoints or allocate a GPU."""
    import importlib

    importlib.import_module("accelerate")
    importlib.import_module("transformers")
    from accelerate import (  # type: ignore[import-not-found]
        infer_auto_device_map,
        init_empty_weights,
    )
    from transformers import (  # type: ignore[import-not-found]
        AutoConfig,
        AutoModelForCausalLM,
    )

    ref = entry.metadata.source_ref
    revision = entry.metadata.source_revision
    revision_kw = (
        {"revision": revision}
        if is_resolved(revision) and isinstance(revision, str)
        else {}
    )
    config = AutoConfig.from_pretrained(
        ref,
        trust_remote_code=REMOTE_CODE_FLAG,
        **revision_kw,
    )
    with init_empty_weights():
        model = AutoModelForCausalLM.from_config(
            config,
            trust_remote_code=REMOTE_CODE_FLAG,
        )
    limits: dict[str, int | str] = dict(max_memory) if max_memory else {"cpu": "1GiB"}
    device_map = infer_auto_device_map(model, max_memory=limits, dtype="float16")
    weight_bytes = _skeleton_bytes(model)
    return {
        "applicable": True,
        "trust_remote_code": REMOTE_CODE_FLAG,
        "weight_bytes": weight_bytes,
        "config": True,
        "meta_device": True,
        "weights_loaded": False,
        "max_memory": {str(key): str(value) for key, value in limits.items()},
        "device_map_keys": tuple(str(key) for key in dict(device_map)),
    }


def _skeleton_bytes(model: object) -> int:
    total = 0
    parameters = getattr(model, "parameters", lambda: ())()
    buffers = getattr(model, "buffers", lambda: ())()
    for tensor in (*parameters, *buffers):
        numel = int(tensor.numel())
        size = int(tensor.element_size())
        total += numel * size
    return total


def _not_applicable(
    entry: ModelCatalogEntry, note: str, failure: str
) -> WeightFootprintEvidence:
    return WeightFootprintEvidence(
        model_id=entry.metadata.model_id,
        source_ref=entry.metadata.source_ref,
        evidence_source=WeightEvidenceSource.ACCELERATE_STRUCTURAL,
        serialized_weight_tensor_bytes=NOT_PROVIDED,
        confidence=Confidence.UNKNOWN,
        provenance=(note,),
        source_revision=entry.metadata.source_revision,
        provider_failure=failure,
    )


def _remote_code_required(error: Exception) -> bool:
    text = str(error).lower()
    return "trust_remote_code" in text or "requires you to execute" in text


def _accelerate_available() -> bool:
    try:
        import importlib

        importlib.import_module("accelerate")
    except ImportError:
        return False
    return True


def build(
    *,
    analyze: AnalyzeFn | None = None,
    enabled: bool = False,
) -> AccelerateStructuralProvider:
    return AccelerateStructuralProvider(analyze=analyze, enabled=enabled)
