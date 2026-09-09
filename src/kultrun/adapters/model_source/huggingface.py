"""Hugging Face identity with a packaged curated candidate set.

The source_ref values are Hub ids. Live Hub listing is optional Stage A
discovery and is never compatibility or capacity authority. Curated catalog
members are always retained, including when they lack a vLLM app tag.
"""

from __future__ import annotations

from collections.abc import Callable

from kultrun.adapters.model_source.candidates import IDENTITY, packaged_candidates
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
            notes=tuple(notes),
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


def build(*, list_models: ListModelsFn | None = None) -> HuggingFaceSource:
    """The composition root's constructor."""
    return HuggingFaceSource(list_models=list_models)
