"""Kultrun packaged/formula requirement estimator."""

from __future__ import annotations

from kultrun.adapters.estimators.common import unavailable_requirement
from kultrun.adapters.model_source.candidates import (
    PROVIDER_VERSION,
    packaged_candidates,
)
from kultrun.kernel.ids import Name
from kultrun.kernel.unresolved import is_resolved
from kultrun.model.contracts import (
    ModelCatalogEntry,
    ModelEstimationRequest,
    ModelRequirement,
)

IDENTITY = Name("kultrun")


class KultrunRequirementEstimator:
    """Looks up the packaged candidate. Does not invent a host fit."""

    def __init__(
        self, entries: tuple[ModelCatalogEntry, ...] | None = None
    ) -> None:
        self._entries = entries if entries is not None else packaged_candidates()
        self._by_id = {entry.metadata.model_id.value: entry for entry in self._entries}

    @property
    def identity(self) -> Name:
        return IDENTITY

    @property
    def version(self) -> str:
        return PROVIDER_VERSION

    def estimate(self, request: ModelEstimationRequest) -> ModelRequirement:
        if request.tensor_parallel != 1 or request.batch_size != 1:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="v0 estimates are single-device batch-1 only",
            )
        if request.offload_allowed:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="cpu offload is not assumed by the Kultrun estimator",
            )
        entry = self._by_id.get(request.model_id.value)
        if entry is None:
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="candidate is not in the Kultrun packaged set",
            )
        meta = entry.metadata
        if (
            is_resolved(request.quantization)
            and is_resolved(meta.quantization)
            and _norm(request.quantization) != _norm(meta.quantization)
        ):
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="quantization does not match the packaged variant",
            )
        if (
            is_resolved(request.context_tokens)
            and is_resolved(entry.requirement.assumed_context_tokens)
            and request.context_tokens != entry.requirement.assumed_context_tokens
        ):
            return unavailable_requirement(
                request,
                provider=IDENTITY.value,
                version=self.version,
                method="unsupported",
                reason="context does not match the packaged assumption",
            )
        return entry.requirement


def build(
    entries: tuple[ModelCatalogEntry, ...] | None = None,
) -> KultrunRequirementEstimator:
    return KultrunRequirementEstimator(entries)


def _norm(value: object) -> str:
    return str(value).lower().replace("-", "_")
