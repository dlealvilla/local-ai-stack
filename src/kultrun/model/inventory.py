"""Plural stored-model inventory. Stored is not running."""

from __future__ import annotations

from kultrun.host.contracts import HostId
from kultrun.kernel.persistence import Store
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import (
    ArtifactId,
    ArtifactState,
    InventoryState,
    ModelArtifact,
    ModelId,
    ModelInventoryRecord,
)
from kultrun.model.store import ModelArtifactStore


class ModelInventory:
    """Every artifact this installation knows about. Never ``current_model``."""

    def __init__(self, store: Store, artifacts: ModelArtifactStore) -> None:
        self._store = store
        self._artifacts = artifacts

    def artifacts(self, *, include_deleted: bool = False) -> tuple[ModelArtifact, ...]:
        visible = []
        for artifact in self._store.records(ModelArtifact):
            if artifact.state is ArtifactState.DELETED and not include_deleted:
                continue
            visible.append(self.observe(artifact))
        return tuple(visible)

    def get(self, artifact_id: ArtifactId) -> ModelArtifact | None:
        found = self._store.get(ModelArtifact, artifact_id.value)
        if found is None:
            return None
        return self.observe(found)

    def find_stored(
        self,
        *,
        model_id: ModelId,
        revision: str,
        quantization: str | None,
        artifact_format: str | None,
    ) -> ModelArtifact | None:
        """Exact identity match among STORED artifacts. Not filename matching."""
        for artifact in self.artifacts():
            if artifact.state is not ArtifactState.STORED:
                continue
            if artifact.model_id != model_id:
                continue
            if not is_resolved(artifact.revision) or artifact.revision != revision:
                continue
            if _opt(artifact.quantization) != (quantization or ""):
                continue
            if _opt(artifact.artifact_format) != (artifact_format or ""):
                continue
            return artifact
        return None

    def observe(self, artifact: ModelArtifact) -> ModelArtifact:
        """Do not treat a STORED record as healthy if the files are gone."""
        if artifact.state is not ArtifactState.STORED:
            return artifact
        present = self._artifacts.manifest_path(artifact.artifact_id).is_file()
        if present:
            return artifact
        return ModelArtifact(
            artifact_id=artifact.artifact_id,
            model_id=artifact.model_id,
            revision=artifact.revision,
            pool_id=artifact.pool_id,
            download_bytes=artifact.download_bytes,
            installed_bytes=artifact.installed_bytes,
            checksum=artifact.checksum,
            logical_name=artifact.logical_name,
            source=artifact.source,
            source_ref=artifact.source_ref,
            requested_revision=artifact.requested_revision,
            artifact_format=artifact.artifact_format,
            quantization=artifact.quantization,
            state=ArtifactState.INVALID,
            created_at=artifact.created_at,
            acquired_at=artifact.acquired_at,
            updated_at=artifact.updated_at,
            location=artifact.location,
            file_count=artifact.file_count,
            manifest_digest=artifact.manifest_digest,
            acquisition_provider=artifact.acquisition_provider,
            acquisition_provider_version=artifact.acquisition_provider_version,
            license_id=artifact.license_id,
            verification_state=artifact.verification_state,
            verification_method=artifact.verification_method,
            integrity_evidence=artifact.integrity_evidence,
            failure_reason="stored record missing manifest",
            storage_mount=artifact.storage_mount,
        )

    def put(self, artifact: ModelArtifact, host_id: HostId) -> None:
        self._store.put(artifact.artifact_id.value, artifact)
        record = ModelInventoryRecord(
            model_id=artifact.model_id,
            host_id=host_id,
            state=_inventory_state(artifact.state),
            artifact_id=artifact.artifact_id,
            pool_id=artifact.pool_id,
            managed_bytes=(
                artifact.installed_bytes
                if is_resolved(artifact.installed_bytes)
                else NOT_PROVIDED
            ),
        )
        self._store.put(artifact.artifact_id.value, record)

    def record(self, artifact_id: ArtifactId) -> ModelInventoryRecord | None:
        return self._store.get(ModelInventoryRecord, artifact_id.value)


def _inventory_state(state: ArtifactState) -> InventoryState:
    return InventoryState(state.value)


def _opt(value: object) -> str:
    if not is_resolved(value) or value is None:
        return ""
    return str(value)
