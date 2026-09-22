"""Choose which repository files belong in one artifact."""

from __future__ import annotations

import json
from dataclasses import dataclass

from machi.model.contracts import ModelFailure, WeightFormat

_METADATA = frozenset(
    {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "generation_config.json",
        "tokenizer.model",
        "vocab.json",
        "merges.txt",
    }
)


@dataclass(frozen=True, slots=True)
class PlannedFile:
    relative_path: str
    size_bytes: int | None


@dataclass(frozen=True, slots=True)
class AcquisitionPlan:
    files: tuple[PlannedFile, ...]
    weight_format: WeightFormat
    failure: ModelFailure
    reason: str


def plan_acquisition(
    files: tuple[tuple[str, int | None], ...],
) -> AcquisitionPlan:
    """Prefer one safetensors variant. Skip code, gguf, and extra quants."""
    names = dict(files)
    if "model.safetensors.index.json" in names:
        return _bad(
            ModelFailure.METADATA_INVALID,
            "safetensors index text is required to choose shards",
        )
    weights = [
        path
        for path in names
        if path.endswith(".safetensors") and "/" not in path and "\\" not in path
    ]
    if weights:
        chosen = [*_metadata(names), *sorted(weights)]
        return _ok([(path, names[path]) for path in chosen], WeightFormat.SAFETENSORS)
    if any(path.endswith(".gguf") for path in names):
        return _bad(
            ModelFailure.UNSUPPORTED_WEIGHT_FORMAT,
            "gguf is not an artifact for this runtime path",
        )
    bins = [path for path in names if path.endswith(".bin") and "/" not in path]
    if bins:
        return _bad(
            ModelFailure.UNSUPPORTED_WEIGHT_FORMAT,
            "pytorch bin weights are not the selected format",
        )
    return _bad(ModelFailure.MODEL_CONFIG_MISSING, "no weight files were listed")


def plan_with_index_text(
    files: tuple[tuple[str, int | None], ...],
    index_text: str | None,
) -> AcquisitionPlan:
    """Use index JSON supplied by the source adapter. Do not fetch it here."""
    names = dict(files)
    if index_text:
        try:
            raw = json.loads(index_text)
        except json.JSONDecodeError:
            return _bad(ModelFailure.METADATA_INVALID, "safetensors index was not json")
        weight_map = raw.get("weight_map") if isinstance(raw, dict) else None
        if not isinstance(weight_map, dict):
            return _bad(ModelFailure.METADATA_INVALID, "safetensors index has no map")
        shards = sorted({str(name) for name in weight_map.values()})
        if not shards or any(name not in names for name in shards):
            return _bad(
                ModelFailure.METADATA_INVALID,
                "safetensors index names a missing file",
            )
        chosen = [*_metadata(names), "model.safetensors.index.json", *shards]
        return _ok([(path, names[path]) for path in chosen], WeightFormat.SAFETENSORS)
    return plan_acquisition(files)


def _metadata(names: dict[str, int | None]) -> list[str]:
    return sorted(path for path in names if path in _METADATA)


def _ok(
    selected: list[tuple[str, int | None]],
    weight_format: WeightFormat,
) -> AcquisitionPlan:
    unique: list[tuple[str, int | None]] = []
    seen: set[str] = set()
    for path, size in selected:
        if path in seen or path.endswith((".py", ".gguf")):
            continue
        seen.add(path)
        unique.append((path, size))
    return AcquisitionPlan(
        files=tuple(PlannedFile(path, size) for path, size in unique),
        weight_format=weight_format,
        failure=ModelFailure.NONE,
        reason="safetensors variant and tokenizer files",
    )


def _bad(failure: ModelFailure, reason: str) -> AcquisitionPlan:
    return AcquisitionPlan(
        files=(),
        weight_format=WeightFormat.UNKNOWN,
        failure=failure,
        reason=reason,
    )
