"""The model-source seam.

`docs/ARCHITECTURE.md` Part IV: Kultrun owns normalized metadata and
requirements. Hugging Face, a local file, or a later registry is an
adapter behind this port. The port does not rank, download or admit.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.model.contracts import ModelCatalogEntry


@runtime_checkable
class ModelSource(Protocol):
    """A replaceable origin of candidate models."""

    @property
    def identity(self) -> Name:
        """Stable source name, e.g. huggingface."""
        ...

    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        """The current candidate set. Does not fetch the whole Hub."""
        ...
