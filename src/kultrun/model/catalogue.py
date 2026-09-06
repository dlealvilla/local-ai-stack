"""The curated candidate list. Does not rank and does not acquire."""

from __future__ import annotations

from kultrun.kernel.ids import Name
from kultrun.model.contracts import ModelCatalogEntry
from kultrun.model.ports import ModelSource


class ModelCatalogue:
    """Every candidate from the configured source. Plural from v1."""

    def __init__(self, source: ModelSource) -> None:
        self._source = source

    @property
    def source_identity(self) -> Name:
        """Which adapter produced these candidates."""
        return self._source.identity

    def entries(self) -> tuple[ModelCatalogEntry, ...]:
        """The bounded candidate set. Order is the source's order."""
        return self._source.candidates()
