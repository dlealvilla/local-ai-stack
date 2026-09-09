"""The model-source, estimator, and acquisition seams.

`docs/ARCHITECTURE.md` Part IV: Kultrun owns normalized metadata,
requirements, artifacts and inventory. Hugging Face, a local file, llmfit,
or a later registry is an adapter behind these ports. The ports do not
rank, reserve or serve.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kultrun.kernel.ids import Name
from kultrun.model.contracts import (
    ModelAcquisitionRequest,
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
    WeightFootprintEvidence,
)
from kultrun.model.discovery import DiscoveryQuery, DiscoveryResult


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
class ModelDiscoverySource(Protocol):
    """Optional Stage A listing. Remote filters are hints, not eligibility."""

    def discover(self, query: DiscoveryQuery) -> DiscoveryResult:
        """Reduce a source universe. Must not drop the curated catalog."""
        ...


@runtime_checkable
class WeightEvidenceProvider(Protocol):
    """Cheap factual weight footprint. Never downloads full weights."""

    @property
    def identity(self) -> Name:
        """Stable provider name."""
        ...

    def footprint(self, entry: ModelCatalogEntry) -> WeightFootprintEvidence:
        """Serialized tensor bytes or typed unknown. Not a VRAM requirement."""
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


@dataclass(frozen=True, slots=True)
class ProviderFetchResult:
    """Bytes written into a Kultrun staging directory. Not an inventory fact."""

    resolved_revision: str
    files: tuple[str, ...]
    bytes_written: int
    integrity_evidence: tuple[str, ...] = ()


class AcquisitionProviderError(Exception):
    """A typed provider failure. Never carries a credential."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@runtime_checkable
class ModelAcquisitionProvider(Protocol):
    """Obtain model files into a Kultrun-owned staging directory.

    Does not choose the permanent location, does not mark STORED, and does
    not own inventory. Hugging Face concepts stay in the adapter.
    """

    @property
    def identity(self) -> Name:
        """Stable provider name, e.g. huggingface or fixture."""
        ...

    @property
    def version(self) -> str:
        """Provider version recorded on the artifact."""
        ...

    def pin_revision(self, request: ModelAcquisitionRequest) -> str:
        """Resolve an immutable revision. Must not write artifact files."""
        ...

    def fetch(
        self, request: ModelAcquisitionRequest, staging_dir: Path
    ) -> ProviderFetchResult:
        """Write files under staging_dir only. Must not promote to STORED."""
        ...
