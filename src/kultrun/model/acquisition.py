"""Acquire, verify, promote and delete ModelArtifacts.

Kultrun owns lifecycle truth. The provider only writes into staging.
Stored is not running. This is not ResourceManager reservation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from kultrun.capacity.contracts import CapacityEnvelope
from kultrun.host.contracts import HostId
from kultrun.kernel.clock import Clock
from kultrun.kernel.errors import (
    NotFoundError,
    PreconditionFailedError,
    ValidationError,
)
from kultrun.kernel.schema import to_dict
from kultrun.kernel.unresolved import NOT_PROVIDED, is_resolved
from kultrun.model.contracts import (
    AcquisitionFailureReason,
    AcquisitionId,
    AcquisitionReceipt,
    ArtifactId,
    ArtifactManifest,
    ArtifactState,
    ModelAcquisitionRequest,
    ModelArtifact,
    ModelCatalogEntry,
    VerificationState,
)
from kultrun.model.inventory import ModelInventory
from kultrun.model.ports import (
    AcquisitionProviderError,
    ModelAcquisitionProvider,
    ProviderFetchResult,
)
from kultrun.model.store import MANIFEST_NAME, ModelArtifactStore

_WEIGHT_SUFFIXES = {".bin", ".safetensors", ".gguf", ".pt"}
_SAFETENSORS_HEADER_LIMIT = 10_000_000


def request_from_entry(entry: ModelCatalogEntry) -> ModelAcquisitionRequest:
    """Build a request from a known candidate. No caller destination path."""
    meta = entry.metadata
    req = entry.requirement
    return ModelAcquisitionRequest(
        request_id=AcquisitionId.generate(),
        model_id=meta.model_id,
        logical_name=meta.logical_name,
        source=meta.source,
        source_ref=meta.source_ref,
        requested_revision=meta.source_revision,
        artifact_format=NOT_PROVIDED,
        quantization=meta.quantization,
        expected_storage_bytes=req.storage_bytes,
        expected_peak_bytes=req.peak_additional_bytes,
        license_id=meta.license_id,
    )


def identity_key(
    *,
    model_id: str,
    revision: str,
    quantization: str,
    artifact_format: str,
) -> str:
    raw = f"{model_id}|{revision}|{quantization}|{artifact_format}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def needed_bytes(request: ModelAcquisitionRequest) -> int | None:
    """Peak if known, else stored size. Unresolved is not zero."""
    if is_resolved(request.expected_peak_bytes):
        return request.expected_peak_bytes
    if is_resolved(request.expected_storage_bytes):
        return request.expected_storage_bytes
    return None


def safe_storage(
    envelope: CapacityEnvelope, mount: str | None = None
) -> tuple[str | None, object]:
    """SAFE layer only. Reported and effective never authorize."""
    if mount:
        pool = next(
            (item for item in envelope.pools if item.mount_point == mount),
            None,
        )
        if pool is None:
            raise ValidationError(
                "unknown storage pool",
                mount_point=mount,
                known=[item.mount_point for item in envelope.pools],
            )
        return mount, pool.space.safe_bytes
    for pool in envelope.pools:
        if is_resolved(pool.space.safe_bytes):
            return pool.mount_point, pool.space.safe_bytes
    return None, NOT_PROVIDED


class AcquisitionService:
    """Staging, verification, promotion and inventory. Not a download engine."""

    def __init__(
        self,
        provider: ModelAcquisitionProvider,
        inventory: ModelInventory,
        artifacts: ModelArtifactStore,
        clock: Clock,
    ) -> None:
        self._provider = provider
        self._inventory = inventory
        self._artifacts = artifacts
        self._clock = clock

    @property
    def provider_identity(self) -> str:
        return self._provider.identity.value

    @property
    def provider_version(self) -> str:
        return self._provider.version

    def acquire(
        self,
        request: ModelAcquisitionRequest,
        envelope: CapacityEnvelope,
        host_id: HostId,
    ) -> AcquisitionReceipt:
        """Preflight SAFE storage, fetch into staging, verify, then STORED."""
        now = self._clock.now()
        needed = needed_bytes(request)
        if needed is None:
            raise PreconditionFailedError(
                "storage requirement is unresolved; unknown is not zero",
                reason=AcquisitionFailureReason.UNRESOLVED_STORAGE_REQUIREMENT.value,
            )
        mount, safe = safe_storage(envelope)
        if not is_resolved(safe) or not isinstance(safe, int):
            raise PreconditionFailedError(
                "SAFE storage is unresolved; reported capacity authorizes nothing",
                reason=AcquisitionFailureReason.UNRESOLVED_STORAGE_REQUIREMENT.value,
            )
        if needed > safe:
            raise PreconditionFailedError(
                "SAFE storage is insufficient for this acquisition",
                reason=AcquisitionFailureReason.INSUFFICIENT_SAFE_STORAGE.value,
                needed_bytes=needed,
                safe_bytes=safe,
            )

        quant = _opt(request.quantization)
        fmt = _opt(request.artifact_format)
        try:
            resolved = self._provider.pin_revision(request)
        except AcquisitionProviderError as error:
            return self._failed(request, ArtifactId.generate(), error.reason, now)
        lock_key = identity_key(
            model_id=request.model_id.value,
            revision=resolved,
            quantization=quant,
            artifact_format=fmt,
        )
        with self._artifacts.lock(lock_key):
            existing = self._inventory.find_stored(
                model_id=request.model_id,
                revision=resolved,
                quantization=quant or None,
                artifact_format=fmt or None,
            )
            if existing is not None and existing.state is ArtifactState.STORED:
                return AcquisitionReceipt(
                    request_id=request.request_id,
                    artifact_id=existing.artifact_id,
                    outcome="reused",
                    state=ArtifactState.STORED,
                    resolved_revision=resolved,
                    stored_bytes=existing.installed_bytes,
                    file_count=existing.file_count,
                    verification_state=existing.verification_state,
                    reused=True,
                    serving=False,
                    acquired_at=now,
                )

            artifact_id = ArtifactId.generate()
            staging = self._artifacts.staging_dir(lock_key)
            self._record(
                request,
                artifact_id,
                ArtifactState.ACQUIRING,
                host_id,
                mount=mount,
                revision=resolved,
                now=now,
            )
            try:
                staging.mkdir(parents=True, exist_ok=True)
                fetched = self._provider.fetch(request, staging)
                if fetched.resolved_revision != resolved:
                    raise AcquisitionProviderError(
                        AcquisitionFailureReason.VARIANT_MISMATCH.value,
                        "provider resolved a different revision than pinned",
                    )
                if _opt(request.quantization) and _opt(request.quantization) != quant:
                    raise AcquisitionProviderError(
                        AcquisitionFailureReason.VARIANT_MISMATCH.value,
                        "provider must not substitute quantization",
                    )
                verified = verify_staging(staging, resolved)
                manifest = self._manifest(
                    request, artifact_id, fetched, verified, now
                )
                self._promote(artifact_id, staging, manifest)
            except AcquisitionProviderError as error:
                self._cleanup(staging)
                self._record(
                    request,
                    artifact_id,
                    ArtifactState.INVALID,
                    host_id,
                    mount=mount,
                    revision=resolved,
                    now=now,
                    failure=error.reason,
                )
                return self._failed(request, artifact_id, error.reason, now)
            except Exception as error:
                self._cleanup(staging)
                reason = AcquisitionFailureReason.PROVIDER_EXECUTION_ERROR.value
                self._record(
                    request,
                    artifact_id,
                    ArtifactState.INVALID,
                    host_id,
                    mount=mount,
                    revision=resolved,
                    now=now,
                    failure=reason,
                )
                return self._failed(request, artifact_id, reason, now, hidden=error)

            stored = ModelArtifact(
                artifact_id=artifact_id,
                model_id=request.model_id,
                revision=resolved,
                logical_name=request.logical_name.value,
                source=request.source.value,
                source_ref=request.source_ref,
                requested_revision=request.requested_revision,
                artifact_format=request.artifact_format,
                quantization=request.quantization,
                state=ArtifactState.STORED,
                created_at=now,
                acquired_at=now,
                updated_at=now,
                location=self._artifacts.relative_location(artifact_id),
                installed_bytes=verified.total_bytes,
                file_count=len(verified.files),
                download_bytes=fetched.bytes_written,
                checksum=verified.digest,
                manifest_digest=verified.digest,
                acquisition_provider=self._provider.identity.value,
                acquisition_provider_version=self._provider.version,
                license_id=request.license_id,
                verification_state=VerificationState.PASSED,
                verification_method=verified.method,
                integrity_evidence=verified.evidence,
                storage_mount=mount if mount is not None else NOT_PROVIDED,
            )
            self._inventory.put(stored, host_id)
            return AcquisitionReceipt(
                request_id=request.request_id,
                artifact_id=artifact_id,
                outcome="stored",
                state=ArtifactState.STORED,
                resolved_revision=resolved,
                stored_bytes=verified.total_bytes,
                file_count=len(verified.files),
                verification_state=VerificationState.PASSED,
                reused=False,
                serving=False,
                acquired_at=now,
            )

    def delete(self, artifact_id: ArtifactId, host_id: HostId) -> ModelArtifact:
        """Remove one managed artifact. Not stop/unload. Not an arbitrary path."""
        parsed = ArtifactId.parse(artifact_id.value)
        found = self._inventory.get(parsed)
        if found is None:
            raise NotFoundError("no such model artifact", artifact_id=parsed.value)
        if found.state is ArtifactState.DELETED:
            return found
        path = self._artifacts.artifact_dir(parsed)
        if not self._artifacts.contains(path):
            raise ValidationError("deletion path escapes the model store")
        if path.exists():
            shutil.rmtree(path)
        now = self._clock.now()
        tombstone = ModelArtifact(
            artifact_id=found.artifact_id,
            model_id=found.model_id,
            revision=found.revision,
            pool_id=found.pool_id,
            download_bytes=found.download_bytes,
            installed_bytes=found.installed_bytes,
            checksum=found.checksum,
            logical_name=found.logical_name,
            source=found.source,
            source_ref=found.source_ref,
            requested_revision=found.requested_revision,
            artifact_format=found.artifact_format,
            quantization=found.quantization,
            state=ArtifactState.DELETED,
            created_at=found.created_at,
            acquired_at=found.acquired_at,
            updated_at=now,
            location=found.location,
            file_count=found.file_count,
            manifest_digest=found.manifest_digest,
            acquisition_provider=found.acquisition_provider,
            acquisition_provider_version=found.acquisition_provider_version,
            license_id=found.license_id,
            verification_state=found.verification_state,
            verification_method=found.verification_method,
            integrity_evidence=found.integrity_evidence,
            failure_reason="deleted",
            storage_mount=found.storage_mount,
        )
        self._inventory.put(tombstone, host_id)
        return tombstone

    def _promote(
        self, artifact_id: ArtifactId, staging: Path, manifest: ArtifactManifest
    ) -> None:
        final = self._artifacts.artifact_dir(artifact_id)
        if final.exists():
            raise AcquisitionProviderError(
                AcquisitionFailureReason.CONCURRENT_ACQUISITION.value,
                "final artifact location already exists",
            )
        (staging / MANIFEST_NAME).write_text(
            json.dumps(to_dict(manifest), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        final.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(final)
        if not (final / MANIFEST_NAME).is_file():
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "promotion did not persist the manifest",
            )

    def _manifest(
        self,
        request: ModelAcquisitionRequest,
        artifact_id: ArtifactId,
        fetched: ProviderFetchResult,
        verified: _Verified,
        now: object,
    ) -> ArtifactManifest:
        return ArtifactManifest(
            artifact_id=artifact_id,
            model_id=request.model_id,
            logical_name=request.logical_name,
            source=request.source,
            source_ref=request.source_ref,
            requested_revision=request.requested_revision,
            resolved_revision=fetched.resolved_revision,
            artifact_format=request.artifact_format,
            quantization=request.quantization,
            acquisition_provider=self._provider.identity.value,
            acquisition_provider_version=self._provider.version,
            files=verified.files,
            sizes_bytes=verified.sizes,
            total_bytes=verified.total_bytes,
            integrity_evidence=verified.evidence,
            verification_state=VerificationState.PASSED,
            verification_method=verified.method,
            acquired_at=now,  # type: ignore[arg-type]
            license_id=request.license_id,
        )

    def _record(
        self,
        request: ModelAcquisitionRequest,
        artifact_id: ArtifactId,
        state: ArtifactState,
        host_id: HostId,
        *,
        mount: str | None,
        revision: str,
        now: object,
        failure: str | None = None,
    ) -> None:
        self._inventory.put(
            ModelArtifact(
                artifact_id=artifact_id,
                model_id=request.model_id,
                revision=revision,
                logical_name=request.logical_name.value,
                source=request.source.value,
                source_ref=request.source_ref,
                requested_revision=request.requested_revision,
                artifact_format=request.artifact_format,
                quantization=request.quantization,
                state=state,
                created_at=now,  # type: ignore[arg-type]
                updated_at=now,  # type: ignore[arg-type]
                location=self._artifacts.relative_location(artifact_id),
                acquisition_provider=self._provider.identity.value,
                acquisition_provider_version=self._provider.version,
                license_id=request.license_id,
                verification_state=(
                    VerificationState.FAILED
                    if state is ArtifactState.INVALID
                    else VerificationState.NOT_VERIFIED
                ),
                failure_reason=failure if failure is not None else NOT_PROVIDED,
                storage_mount=mount if mount is not None else NOT_PROVIDED,
            ),
            host_id,
        )

    def _failed(
        self,
        request: ModelAcquisitionRequest,
        artifact_id: ArtifactId,
        reason: str,
        now: object,
        hidden: Exception | None = None,
    ) -> AcquisitionReceipt:
        del hidden
        return AcquisitionReceipt(
            request_id=request.request_id,
            artifact_id=artifact_id,
            outcome="failed",
            state=ArtifactState.INVALID,
            verification_state=VerificationState.FAILED,
            failure_reason=reason,
            reused=False,
            serving=False,
            acquired_at=now,  # type: ignore[arg-type]
        )

    def _cleanup(self, staging: Path) -> None:
        if staging.exists() and self._artifacts.contains(staging):
            shutil.rmtree(staging, ignore_errors=True)


class _Verified:
    def __init__(
        self,
        files: tuple[str, ...],
        sizes: tuple[int, ...],
        total_bytes: int,
        method: str,
        evidence: tuple[str, ...],
        digest: str,
    ) -> None:
        self.files = files
        self.sizes = sizes
        self.total_bytes = total_bytes
        self.method = method
        self.evidence = evidence
        self.digest = digest


def verify_staging(staging: Path, resolved_revision: str) -> _Verified:
    """Required files exist, are regular, and are not obviously truncated."""
    if not resolved_revision or resolved_revision in {"latest", "HEAD"}:
        raise AcquisitionProviderError(
            AcquisitionFailureReason.VERIFICATION_FAILED.value,
            "artifact revision is not immutable",
        )
    root = staging.resolve()
    names: list[str] = []
    sizes: list[int] = []
    methods = ["required_files", "regular_readable", "revision_pinned"]
    evidence = [f"revision:{resolved_revision}"]
    for path in sorted(root.rglob("*")):
        if path.name == MANIFEST_NAME:
            continue
        if path.is_symlink():
            resolved = path.resolve()
            if root not in resolved.parents and resolved != root:
                raise AcquisitionProviderError(
                    AcquisitionFailureReason.VERIFICATION_FAILED.value,
                    "symlink escapes staging",
                )
        if not path.is_file():
            continue
        if not path.is_relative_to(root):
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "file escapes staging",
            )
        size = path.stat().st_size
        if size <= 0 and path.suffix in _WEIGHT_SUFFIXES:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "weight file is empty or truncated",
            )
        if path.suffix == ".safetensors":
            _check_safetensors_header(path)
            methods.append("safetensors_header")
        names.append(str(path.relative_to(root)))
        sizes.append(size)
    if not names:
        raise AcquisitionProviderError(
            AcquisitionFailureReason.VERIFICATION_FAILED.value,
            "staging contains no regular files",
        )
    total = sum(sizes)
    if total <= 0:
        raise AcquisitionProviderError(
            AcquisitionFailureReason.VERIFICATION_FAILED.value,
            "artifact bytes are empty",
        )
    digest = hashlib.sha256(
        "\n".join(f"{name}:{size}" for name, size in zip(names, sizes, strict=True))
        .encode("utf-8")
    ).hexdigest()
    evidence.append(f"manifest_sha256:{digest}")
    evidence.append(f"files:{len(names)}")
    return _Verified(
        files=tuple(names),
        sizes=tuple(sizes),
        total_bytes=total,
        method="+".join(dict.fromkeys(methods)),
        evidence=tuple(evidence),
        digest=digest,
    )


def _check_safetensors_header(path: Path) -> None:
    with path.open("rb") as handle:
        raw = handle.read(8)
        if len(raw) < 8:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "safetensors header is truncated",
            )
        length = int.from_bytes(raw, "little")
        if length < 2 or length > _SAFETENSORS_HEADER_LIMIT:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "safetensors header is implausible",
            )
        header = handle.read(length)
        if len(header) < length:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "safetensors header is truncated",
            )
        try:
            json.loads(header.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AcquisitionProviderError(
                AcquisitionFailureReason.VERIFICATION_FAILED.value,
                "safetensors header is not JSON",
            ) from error


def _opt(value: object) -> str:
    if not is_resolved(value) or value is None:
        return ""
    return str(value)
