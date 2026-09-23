"""Normalize config text. Does not execute repository code."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from machi.kernel.unresolved import NOT_PROVIDED, Maybe
from machi.model.contracts import (
    CommercialUse,
    DerivationKind,
    QuantizationKind,
    WeightFormat,
)


@dataclass(frozen=True, slots=True)
class NormalizedMetadata:
    architecture: Maybe[str]
    dtype: Maybe[str]
    quantization: QuantizationKind
    context_length: Maybe[int]
    parameter_count: Maybe[int]
    requires_remote_code: bool
    base_model: Maybe[str]
    derivation: DerivationKind
    config_sha256: Maybe[str]
    hidden_size: Maybe[int]
    attention_heads: Maybe[int]
    key_value_heads: Maybe[int]
    explicit_head_dim: Maybe[int]
    derived_head_dim: Maybe[int]
    layer_count: Maybe[int]
    sliding_window: bool


_ALLOWED = frozenset({"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause"})
_RESTRICTED_MARKERS = ("non-commercial", "cc-by-nc", "-nc")


def commercial_use(license_id: str | None) -> CommercialUse:
    """Classify a declared identifier. Absence is unknown, not approval."""
    if license_id is None or not license_id.strip():
        return CommercialUse.UNKNOWN
    token = license_id.strip().lower()
    if any(marker in token for marker in _RESTRICTED_MARKERS):
        return CommercialUse.DECLARED_RESTRICTED
    if token in _ALLOWED:
        return CommercialUse.DECLARED_ALLOWED
    return CommercialUse.REQUIRES_REVIEW


def normalize_config(text: str | None) -> NormalizedMetadata:
    """Read structured config fields. Unknown stays unresolved."""
    if text is None or not text.strip():
        return NormalizedMetadata(
            architecture=NOT_PROVIDED,
            dtype=NOT_PROVIDED,
            quantization=QuantizationKind.UNKNOWN,
            context_length=NOT_PROVIDED,
            parameter_count=NOT_PROVIDED,
            requires_remote_code=False,
            base_model=NOT_PROVIDED,
            derivation=DerivationKind.UNKNOWN,
            config_sha256=NOT_PROVIDED,
            hidden_size=NOT_PROVIDED,
            attention_heads=NOT_PROVIDED,
            key_value_heads=NOT_PROVIDED,
            explicit_head_dim=NOT_PROVIDED,
            derived_head_dim=NOT_PROVIDED,
            layer_count=NOT_PROVIDED,
            sliding_window=False,
        )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return _empty(digest, remote=False)
    if not isinstance(raw, dict):
        return _empty(digest, remote=False)
    architecture = _architecture(raw)
    dtype = raw.get("torch_dtype")
    quant, derivation = _quantization(raw)
    context = _positive_int(raw.get("max_position_embeddings"))
    if context is None:
        context = _positive_int(raw.get("max_sequence_length"))
    parameters = _positive_int(raw.get("num_parameters"))
    base = raw.get("_name_or_path")
    remote = "auto_map" in raw
    hidden = _positive_int(raw.get("hidden_size"))
    heads = _positive_int(raw.get("num_attention_heads"))
    explicit = _positive_int(raw.get("head_dim"))
    derived = _derived_head(hidden, heads, explicit)
    return NormalizedMetadata(
        architecture=architecture if architecture else NOT_PROVIDED,
        dtype=dtype if isinstance(dtype, str) and dtype else NOT_PROVIDED,
        quantization=quant,
        context_length=context if context is not None else NOT_PROVIDED,
        parameter_count=parameters if parameters is not None else NOT_PROVIDED,
        requires_remote_code=remote,
        base_model=base if isinstance(base, str) and base else NOT_PROVIDED,
        derivation=derivation,
        config_sha256=digest,
        hidden_size=hidden if hidden is not None else NOT_PROVIDED,
        attention_heads=heads if heads is not None else NOT_PROVIDED,
        key_value_heads=_kv_heads(raw, heads),
        explicit_head_dim=explicit if explicit is not None else NOT_PROVIDED,
        derived_head_dim=derived if derived is not None else NOT_PROVIDED,
        layer_count=_layers(raw),
        sliding_window=_positive_int(raw.get("sliding_window")) is not None,
    )


def _empty(digest: str, *, remote: bool) -> NormalizedMetadata:
    return NormalizedMetadata(
        architecture=NOT_PROVIDED,
        dtype=NOT_PROVIDED,
        quantization=QuantizationKind.UNKNOWN,
        context_length=NOT_PROVIDED,
        parameter_count=NOT_PROVIDED,
        requires_remote_code=remote,
        base_model=NOT_PROVIDED,
        derivation=DerivationKind.UNKNOWN,
        config_sha256=digest,
        hidden_size=NOT_PROVIDED,
        attention_heads=NOT_PROVIDED,
        key_value_heads=NOT_PROVIDED,
        explicit_head_dim=NOT_PROVIDED,
        derived_head_dim=NOT_PROVIDED,
        layer_count=NOT_PROVIDED,
        sliding_window=False,
    )


def _architecture(raw: dict[str, object]) -> str | None:
    values = raw.get("architectures")
    if isinstance(values, list) and values and isinstance(values[0], str):
        return values[0][:80]
    model_type = raw.get("model_type")
    if isinstance(model_type, str) and model_type:
        return model_type[:80]
    return None


def _quantization(raw: dict[str, object]) -> tuple[QuantizationKind, DerivationKind]:
    block = raw.get("quantization_config")
    if not isinstance(block, dict):
        return QuantizationKind.NONE, DerivationKind.ORIGINAL
    method = str(block.get("quant_method", "")).lower()
    if method == "awq":
        return QuantizationKind.AWQ, DerivationKind.QUANTIZED
    if method == "gptq":
        return QuantizationKind.GPTQ, DerivationKind.QUANTIZED
    if method in {"fp8", "fbgemm_fp8"}:
        return QuantizationKind.FP8, DerivationKind.QUANTIZED
    if method:
        return QuantizationKind.OTHER, DerivationKind.QUANTIZED
    return QuantizationKind.UNKNOWN, DerivationKind.UNKNOWN


def _derived_head(
    hidden: int | None, heads: int | None, explicit: int | None
) -> int | None:
    if explicit is not None:
        return explicit
    if hidden is None or heads is None or hidden % heads != 0:
        return None
    return hidden // heads


def _kv_heads(raw: dict[str, object], heads: int | None) -> Maybe[int]:
    declared = _positive_int(raw.get("num_key_value_heads"))
    if declared is not None:
        return declared
    if heads is not None:
        return heads
    return NOT_PROVIDED


def _layers(raw: dict[str, object]) -> Maybe[int]:
    count = _positive_int(raw.get("num_hidden_layers"))
    if count is None:
        count = _positive_int(raw.get("n_layer"))
    return count if count is not None else NOT_PROVIDED


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    return value


def variant_name(
    dtype: Maybe[str],
    quantization: QuantizationKind,
    weight_format: WeightFormat,
) -> str:
    """Distinguish published variants. Names are not evidence of size."""
    dtype_text = dtype if isinstance(dtype, str) else "undetermined"
    return f"{dtype_text}-{quantization.value}-{weight_format.value}"[:80]
