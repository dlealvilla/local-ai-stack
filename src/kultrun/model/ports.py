"""The model-source and requirement-estimator seams.

`docs/ARCHITECTURE.md` Part IV: Kultrun owns normalized metadata and
requirements. Hugging Face, a local file, llmfit, or a later registry is
an adapter behind these ports. The ports do not rank, download or admit.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.model.contracts import (
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)


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


@runtime_checkable
class ModelRequirementEstimator(Protocol):
    """One replaceable producer of host-independent ModelRequirement.

    Product execution may wrap implementations in a router (auto: llmfit
    then Kultrun). Planning consumes this port and never a concrete
    provider, and never compares two estimates.
    """

    @property
    def identity(self) -> Name:
        """Stable provider name, e.g. kultrun or llmfit."""
        ...

    @property
    def version(self) -> str:
        """Provider version recorded on every estimate."""
        ...

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        """Evaluate this request. Must not silently change its assumptions."""
        ...
