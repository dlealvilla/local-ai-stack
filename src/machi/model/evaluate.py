"""Turn a source view into a definition and an assessment. No downloads."""

from __future__ import annotations

import datetime as dt

from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_PROVIDED, is_resolved
from machi.model.compat import RuntimeView, assess, requirement_for, weights_exceed
from machi.model.contracts import (
    AvailableModelEntry,
    AvailableModels,
    ModelDefinition,
    ModelSelection,
    ModelSourceKind,
    SelectionProvenance,
)
from machi.model.files import plan_with_index_text
from machi.model.identity import input_token, model_id
from machi.model.metadata import commercial_use, normalize_config
from machi.model.qualification import DeployableModels, select_id
from machi.model.source import SourceView


def evaluate_source(
    view: SourceView,
    *,
    source_kind: ModelSourceKind,
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    accelerator_safe_bytes: int | None,
    observed_at: dt.datetime,
    license_blocks: bool = False,
) -> AvailableModelEntry:
    """Normalize metadata and assess compatibility for one explicit reference."""
    meta = normalize_config(view.config_text)
    plan = plan_with_index_text(
        tuple((item.relative_path, item.size_bytes) for item in view.files),
        view.index_text,
    )
    sizes = tuple(item.size_bytes for item in plan.files)
    requirement = requirement_for(sizes)
    static = requirement.static_weight_bytes
    exceed = weights_exceed(
        int(static) if is_resolved(static) else None,
        accelerator_safe_bytes,
    )
    architecture = meta.architecture if isinstance(meta.architecture, str) else None
    compatibility = assess(
        architecture=architecture,
        quantization=meta.quantization,
        weight_format=plan.weight_format,
        requires_remote_code=meta.requires_remote_code,
        runtime=runtime,
        capacity=capacity,
        requirement=requirement,
        weights_exceed_accelerator=exceed,
        license_blocks=license_blocks,
        metadata=meta,
    )
    logical = model_id(source_kind, view.repository)
    definition = ModelDefinition(
        model_id=logical,
        source_kind=source_kind,
        repository=view.repository,
        requested_revision=view.requested_revision,
        immutable_revision=view.immutable_revision,
        display_name=view.repository.split("/")[-1][:240] or view.repository,
        architecture=meta.architecture,
        dtype=meta.dtype,
        quantization=meta.quantization,
        weight_format=plan.weight_format,
        context_length=meta.context_length,
        parameter_count=meta.parameter_count,
        license_id=view.license_id if view.license_id else NOT_PROVIDED,
        commercial_use=commercial_use(view.license_id),
        gated=view.gated,
        requires_remote_code=meta.requires_remote_code,
        derivation=meta.derivation,
        base_model=meta.base_model,
    )
    return AvailableModelEntry(
        definition=definition,
        compatibility=compatibility,
        requirement=requirement,
        artifact_id=NOT_PROVIDED,
        lifecycle=NOT_PROVIDED,
    )


def snapshot_for(
    entries: tuple[AvailableModelEntry, ...],
    *,
    foundation_id: str,
    capacity_evidence_id: str,
    policy_token: str,
    observed_at: dt.datetime,
) -> AvailableModels:
    parts = [
        foundation_id,
        capacity_evidence_id,
        policy_token,
        *(
            f"{item.definition.model_id}:{item.definition.immutable_revision}"
            for item in entries
        ),
    ]
    token = input_token(*parts)
    return AvailableModels(
        snapshot_id=f"mav_{token[:16]}",
        input_token=token,
        foundation_id=foundation_id,
        capacity_evidence_id=capacity_evidence_id,
        entries=entries,
        observed_at=observed_at,
    )


def select_entry(
    entry: AvailableModelEntry,
    deployable: DeployableModels,
    *,
    foundation_id: str,
    capacity_evidence_id: str,
    provenance: SelectionProvenance = SelectionProvenance.ADMINISTRATOR_SELECTED,
) -> ModelSelection:
    """Record a choice that is already in the current deployable set.

    Administrator, product, curated, and forced provenance all use this
    gate. The choice does not acquire or start anything.
    """
    member = select_id(deployable, entry.definition.model_id)
    if (
        member is None
        or member.immutable_revision != entry.definition.immutable_revision
    ):
        raise ValidationError("selection is outside current deployable models")
    return ModelSelection(
        selection_id=f"msel_{entry.definition.model_id[-8:]}",
        model_id=entry.definition.model_id,
        artifact_id=entry.artifact_id,
        immutable_revision=entry.definition.immutable_revision,
        provenance=provenance,
        compatibility_state=entry.compatibility.state,
        foundation_id=foundation_id,
        capacity_evidence_id=capacity_evidence_id,
        reason=entry.compatibility.reason,
    )
