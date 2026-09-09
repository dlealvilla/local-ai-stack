"""Hugging Face identity with a packaged curated candidate set.

The source_ref values are Hub ids. Live Hub listing is optional Stage A
discovery and is never compatibility or capacity authority. Curated catalog
members are always retained, including when they lack a vLLM app tag.
"""

from __future__ import annotations

from collections.abc import Callable

from kultrun.adapters.model_source.candidates import IDENTITY, packaged_candidates
from kultrun.adapters.model_source.hub_client import (
    LIST_TIMEOUT_NOTE,
    list_model_infos,
)
from kultrun.kernel.ids import Name
from kultrun.model.contracts import ModelCatalogEntry
from kultrun.model.discovery import (
    DiscoveryQuery,
    DiscoveryResult,
    RemoteDiscoveryHit,
)

ListModelsFn = Callable[[DiscoveryQuery], tuple[RemoteDiscoveryHit, ...]]


class HuggingFaceSource:
    """Hub identity, curated set, optional remote listing."""

    def __init__(self, *, list_models: ListModelsFn | None = None) -> None:
        self._list_models = list_models

    @property
    def identity(self) -> Name:
        return IDENTITY

    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        return packaged_candidates()

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        """Remote filters reduce *new* discovery. Curated entries stay."""
        catalog = packaged_candidates()
        catalog_refs = {entry.metadata.source_ref for entry in catalog}
        notes = [
            "remote filters are discovery hints, not Kultrun compatibility",
            "absence of a vllm app tag does not drop a curated catalog model",
        ]
        if self._list_models is None:
            return DiscoveryResult(
                universe_count=len(catalog),
                discovered_count=len(catalog),
                criteria=query,
                catalog_entries=catalog,
                live=False,
                notes=(*notes, "huggingface_hub listing not configured"),
            )
        try:
            hits = self._list_models(query)
        except Exception as error:
            return DiscoveryResult(
                universe_count=len(catalog),
                discovered_count=len(catalog),
                criteria=query,
                catalog_entries=catalog,
                live=False,
                source_failure=type(error).__name__,
                notes=(*notes, "source listing failed; curated catalog retained"),
            )
        remote = tuple(hits)
        return DiscoveryResult(
            universe_count=_universe_count(self._list_models, remote, catalog),
            discovered_count=len(catalog)
            + sum(1 for item in remote if item.source_ref not in catalog_refs),
            criteria=query,
            catalog_entries=catalog,
            remote_hits=remote,
            live=True,
            notes=(*notes, LIST_TIMEOUT_NOTE),
        )


def _universe_count(
    lister: ListModelsFn,
    remote: tuple[RemoteDiscoveryHit, ...],
    catalog: tuple[ModelCatalogEntry, ...],
) -> int:
    declared = getattr(lister, "universe_count", None)
    if isinstance(declared, int) and declared >= 0:
        return declared
    return max(len(remote), len(catalog))


def hub_list_models(query: DiscoveryQuery) -> tuple[RemoteDiscoveryHit, ...]:
    """Live Hub listing through the installed huggingface_hub signature.

    Remote filters are discovery hints. Absence of a vLLM app/tag never
    drops a curated catalog member — that policy lives in discover().
    """
    kwargs = _listing_kwargs(query)
    infos = list_model_infos(kwargs)
    hits = tuple(_hit(item) for item in infos)
    hub_list_models.universe_count = max(query.limit, len(hits))  # type: ignore[attr-defined]
    return hits


def _listing_kwargs(query: DiscoveryQuery) -> dict[str, object]:
    apps = list(query.apps) if query.apps else ["vllm"]
    kwargs: dict[str, object] = {
        "pipeline_tag": query.pipeline_tag,
        "gated": query.gated,
        "search": query.search,
        "limit": query.limit,
        "apps": apps,
        "tags": list(query.tags) if query.tags else None,
        "filter": None,
        "num_parameters": _num_parameters(query),
    }
    return kwargs


def _num_parameters(query: DiscoveryQuery) -> str | None:
    if query.parameter_min is None and query.parameter_max is None:
        return None
    parts: list[str] = []
    if query.parameter_min is not None:
        parts.append(f"min:{query.parameter_min}")
    if query.parameter_max is not None:
        parts.append(f"max:{query.parameter_max}")
    return ",".join(parts)


def _hit(info: object) -> RemoteDiscoveryHit:
    ident = str(getattr(info, "id", "") or getattr(info, "modelId", "") or "")
    tags = getattr(info, "tags", None)
    tag_values = (
        tuple(str(item) for item in tags) if isinstance(tags, (list, tuple)) else ()
    )
    gated = getattr(info, "gated", None)
    gated_flag = None if gated is None else bool(gated)
    return RemoteDiscoveryHit(
        source_ref=ident,
        pipeline_tag=getattr(info, "pipeline_tag", None),
        gated=gated_flag,
        tags=tag_values,
        parameter_count=_parameter_total(info),
    )


def _parameter_total(info: object) -> int | None:
    safetensors = getattr(info, "safetensors", None)
    counts = (
        getattr(safetensors, "parameters", None) if safetensors is not None else None
    )
    if isinstance(counts, dict) and counts:
        total = 0
        for value in counts.values():
            if isinstance(value, int):
                total += value
        return total or None
    return None


def build(*, list_models: ListModelsFn | None = None) -> HuggingFaceSource:
    """The composition root's constructor."""
    return HuggingFaceSource(list_models=list_models)
