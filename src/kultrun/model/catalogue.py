"""The curated candidate list. Does not rank and does not acquire."""

from __future__ import annotations

from kultrun.kernel.ids import Name
from kultrun.model.contracts import ModelCatalogEntry
from kultrun.model.ports import ModelSource


class ModelCatalogue:
    """Every candidate from the configured source. Plural from v1."""

    def __init__(
        self,
        source: ModelSource,
        extras: tuple[ModelCatalogEntry, ...] = (),
    ) -> None:
        self._source = source
        self._extras = extras

    @property
    def source_identity(self) -> Name:
        """Which adapter produced these candidates."""
        return self._source.identity

    def entries(self) -> tuple[ModelCatalogEntry, ...]:
        """The bounded candidate set. Order is the source's order."""
        return self._source.candidates()

    @property
    def source(self) -> ModelSource:
        """The configured origin. Discovery, if any, is on this adapter."""
        return self._source

    def extras(self) -> tuple[ModelCatalogEntry, ...]:
        """Known non-catalog targets (bounded acceptance). Not recommendations."""
        return self._extras

    def acquirable(self, logical_name: str) -> ModelCatalogEntry | None:
        """A catalog candidate or a known extra. Not an arbitrary URL."""
        for entry in (*self.entries(), *self._extras):
            if entry.metadata.logical_name.value == logical_name:
                return entry
        return None

    def for_model(self, model_id: object) -> ModelCatalogEntry | None:
        """Resolve a catalog/extra entry by model identity."""
        token = getattr(model_id, "value", model_id)
        for entry in (*self.entries(), *self._extras):
            if entry.metadata.model_id.value == token:
                return entry
        return None
