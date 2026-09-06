"""Hugging Face identity with a packaged curated candidate set.

The source_ref values are Hub ids. v0 does not call huggingface_hub, does
not search the Hub, and does not download. Live fetch is `docs/DEBT.md`
K-35. Estimates are adapter data consumed by KultrunRequirementEstimator.
"""

from __future__ import annotations

from kultrun.adapters.model_source.candidates import IDENTITY, packaged_candidates
from kultrun.kernel.ids import Name
from kultrun.model.contracts import ModelCatalogEntry


class HuggingFaceSource:
    """Hub identity, curated set. Does not search or download."""

    @property
    def identity(self) -> Name:
        return IDENTITY

    def candidates(self) -> tuple[ModelCatalogEntry, ...]:
        return packaged_candidates()


def build() -> HuggingFaceSource:
    """The composition root's constructor."""
    return HuggingFaceSource()
