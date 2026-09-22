"""Stage, verify, and promote. A partial tree is not an artifact."""

from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from machi.adapters.model.hub import (
    credential_supplied,
    fetch_files,
    inspect_repository,
)
from machi.adapters.model.local import copy_files, list_local_files, sha256_file
from machi.adapters.model.warehouse import (
    cache_root,
    file_records,
    load_artifact,
    prepare_staging,
    promote,
    verify_stored,
)
from machi.capacity.contracts import CapacityEnvelope
from machi.kernel.errors import ValidationError
from machi.kernel.unresolved import NOT_PROVIDED, Maybe
from machi.model.access import access_failure
from machi.model.compat import RuntimeView, storage_fits
from machi.model.contracts import (
    ArtifactLifecycle,
    AvailableModelEntry,
    CompatibilityState,
    ModelArtifact,
    ModelFailure,
    ModelSourceKind,
)
from machi.model.evaluate import evaluate_source
from machi.model.files import plan_with_index_text
from machi.model.identity import artifact_id
from machi.model.metadata import variant_name
from machi.model.source import SourceFileInfo, SourceView


@dataclass(frozen=True, slots=True)
class StoreResult:
    """Acquire outcome. A missing artifact is not a stored model."""

    artifact: ModelArtifact | None
    failure: ModelFailure
    artifact_id: str | None


_BLOCKED = frozenset(
    {
        CompatibilityState.UNSUPPORTED,
        CompatibilityState.BLOCKED_BY_POLICY,
        CompatibilityState.INSUFFICIENT_CAPACITY,
        CompatibilityState.UNRESOLVED,
    }
)


def view_local(root: Path, label: str) -> SourceView:
    """Inspect a local directory. The directory itself is not owned."""
    listed = list_local_files(root)
    digest = hashlib.sha256()
    for relative, _size in listed:
        digest.update(sha256_file(root / relative).encode())
    config_path = root / "config.json"
    index_path = root / "model.safetensors.index.json"
    config_text = (
        config_path.read_text(encoding="utf-8") if config_path.is_file() else None
    )
    index_text = (
        index_path.read_text(encoding="utf-8") if index_path.is_file() else None
    )
    return SourceView(
        repository=label,
        requested_revision="local",
        immutable_revision=digest.hexdigest(),
        files=tuple(SourceFileInfo(path, size) for path, size in listed),
        config_text=config_text,
        index_text=index_text,
        license_id=None,
        gated=False,
        private=False,
    )


def with_stored(state_root: Path, entry: AvailableModelEntry) -> AvailableModelEntry:
    """Cite a verified warehouse copy when this revision is already stored."""
    variant = variant_name(
        entry.definition.dtype,
        entry.definition.quantization,
        entry.definition.weight_format,
    )
    stored_id = artifact_id(
        entry.definition.model_id,
        entry.definition.immutable_revision,
        variant,
    )
    existing = load_artifact(state_root, stored_id)
    if existing is None or not verify_stored(state_root, existing):
        return entry
    return AvailableModelEntry(
        definition=entry.definition,
        compatibility=entry.compatibility,
        requirement=entry.requirement,
        artifact_id=existing.artifact_id,
        lifecycle=existing.lifecycle.value,
    )


def store_local(
    state_root: Path,
    source: Path,
    label: str,
    *,
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    accelerator_safe_bytes: int | None,
    observed_at: dt.datetime,
) -> StoreResult:
    """Copy a local source into the warehouse when the assessment allows it."""
    try:
        view = view_local(source, label)
    except ValidationError:
        return StoreResult(None, ModelFailure.LOCAL_IMPORT_INVALID, None)

    def _copy(destination: Path, relative_paths: tuple[str, ...]) -> None:
        copy_files(source, destination, relative_paths)

    return store_view(
        state_root,
        view,
        source_kind=ModelSourceKind.LOCAL,
        fetch=_copy,
        runtime=runtime,
        capacity=capacity,
        accelerator_safe_bytes=accelerator_safe_bytes,
        observed_at=observed_at,
    )


def store_view(
    state_root: Path,
    view: SourceView,
    *,
    source_kind: ModelSourceKind,
    fetch: Callable[[Path, tuple[str, ...]], None],
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    accelerator_safe_bytes: int | None,
    observed_at: dt.datetime,
    credential_present: bool = False,
    license_blocks: bool = False,
) -> StoreResult:
    """Fetch only after revision, compatibility, and capacity are known."""
    denied = access_failure(
        gated=view.gated,
        private=view.private,
        credential_present=credential_present,
    )
    if denied is not None:
        return StoreResult(None, denied, None)
    entry = evaluate_source(
        view,
        source_kind=source_kind,
        runtime=runtime,
        capacity=capacity,
        accelerator_safe_bytes=accelerator_safe_bytes,
        observed_at=observed_at,
        license_blocks=license_blocks,
    )
    if entry.compatibility.state in _BLOCKED:
        return StoreResult(None, entry.compatibility.failure, None)
    if storage_fits(capacity, entry.requirement) is not True:
        return StoreResult(None, ModelFailure.INSUFFICIENT_STORAGE, None)
    plan = plan_with_index_text(
        tuple((item.relative_path, item.size_bytes) for item in view.files),
        view.index_text,
    )
    if plan.failure is not ModelFailure.NONE:
        return StoreResult(None, plan.failure, None)
    variant = variant_name(
        entry.definition.dtype,
        entry.definition.quantization,
        plan.weight_format,
    )
    stored_id = artifact_id(
        entry.definition.model_id,
        view.immutable_revision,
        variant,
    )
    existing = load_artifact(state_root, stored_id)
    if existing is not None:
        if verify_stored(state_root, existing):
            return StoreResult(existing, ModelFailure.NONE, stored_id)
        return StoreResult(None, ModelFailure.INTEGRITY_FAILED, stored_id)
    staging = prepare_staging(state_root, stored_id)
    relative = tuple(item.relative_path for item in plan.files)
    try:
        fetch(staging, relative)
    except (OSError, ValidationError):
        return StoreResult(None, ModelFailure.INTERRUPTED, stored_id)
    records = file_records(staging, relative)
    config_hash: Maybe[str] = NOT_PROVIDED
    if (staging / "config.json").is_file():
        config_hash = sha256_file(staging / "config.json")
    artifact = ModelArtifact(
        artifact_id=stored_id,
        model_id=entry.definition.model_id,
        source_kind=source_kind,
        repository=view.repository,
        immutable_revision=view.immutable_revision,
        variant=variant,
        lifecycle=ArtifactLifecycle.STORED,
        total_bytes=sum(item.size_bytes for item in records),
        files=records,
        config_sha256=config_hash,
        derivation=entry.definition.derivation,
        base_model=entry.definition.base_model,
        parent_artifact_id=NOT_PROVIDED,
        acquired_at=observed_at,
    )
    promote(state_root, artifact, staging)
    return StoreResult(artifact, ModelFailure.NONE, stored_id)


def store_hub(
    state_root: Path,
    repository: str,
    revision: str,
    *,
    runtime: RuntimeView,
    capacity: CapacityEnvelope | None,
    accelerator_safe_bytes: int | None,
    observed_at: dt.datetime,
    timeout_seconds: int,
) -> StoreResult:
    """Resolve one hub revision, then acquire that exact commit."""
    cache = cache_root(state_root)
    try:
        view = inspect_repository(repository, revision, cache=cache)
    except ValidationError as exc:
        try:
            failure = ModelFailure(exc.message)
        except ValueError:
            failure = ModelFailure.SOURCE_UNAVAILABLE
        return StoreResult(None, failure, None)

    def _fetch(destination: Path, relative_paths: tuple[str, ...]) -> None:
        fetch_files(
            view,
            destination,
            relative_paths,
            cache=cache,
            timeout_seconds=timeout_seconds,
        )

    return store_view(
        state_root,
        view,
        source_kind=ModelSourceKind.HUB,
        fetch=_fetch,
        runtime=runtime,
        capacity=capacity,
        accelerator_safe_bytes=accelerator_safe_bytes,
        observed_at=observed_at,
        credential_present=credential_supplied(),
        license_blocks=False,
    )
