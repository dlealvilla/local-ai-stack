"""Copy catalog metadata into runtime eligibility facts.

Composition-owned. Runtime evaluates; model remains the catalog owner.
Planning consumes CompatibilityVerdict tokens copied from the view.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from kultrun.model.catalogue import ModelCatalogue
from kultrun.planning.contracts import CompatibilityVerdict
from kultrun.runtime.contracts import EligibleModelView
from kultrun.runtime.eligibility import (
    ModelEligibilityFacts,
    planning_compatibility,
)


def catalog_facts(models: ModelCatalogue) -> tuple[ModelEligibilityFacts, ...]:
    """Global catalog plus known extras. Does not stamp eligibility on metadata."""
    rows: list[ModelEligibilityFacts] = []
    seen: set[str] = set()
    for entry in (*models.entries(), *models.extras()):
        ident = entry.metadata.model_id.value
        if ident in seen:
            continue
        seen.add(ident)
        meta = entry.metadata
        rows.append(
            ModelEligibilityFacts(
                model_id=ident,
                logical_name=meta.logical_name.value,
                architecture=meta.architecture,
                family=meta.family,
                quantization=meta.quantization,
                supported_runtimes=meta.supported_runtimes,
            )
        )
    return tuple(rows)


def runtime_compatibility(
    view: EligibleModelView, model_ids: Sequence[str]
) -> dict[str, CompatibilityVerdict]:
    """Authoritative runtime compatibility for planning. Not capacity fit."""
    tokens: Mapping[str, str] = planning_compatibility(view, model_ids)
    return {ident: CompatibilityVerdict(token) for ident, token in tokens.items()}
