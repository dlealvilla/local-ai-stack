"""InstallIdentity (MACHI 1.1.1).

Persist and validate the stable InstallRecord for a coherent local
ownership identity. This is installation identity, not an InstallRun,
not a host fingerprint, and not destruction authority.

The Store is injected. This component does not choose a filesystem
location, does not write a local marker, does not seed the registry,
and does not read process environment configuration.

Build identity is recorded as creation provenance. A later compatible
build may re-enter the same InstallId without rewriting that provenance.
"""

from __future__ import annotations

from machi.install.contracts import (
    InstallRecord,
    InstallRecordEstablishment,
    InstallRecordStatus,
    LocalOwnershipEstablishment,
    LocalOwnershipRegistryEstablishment,
    LocalOwnershipStatus,
    RegistrySeedStatus,
    StateRootBinding,
)
from machi.install.defaults import PRODUCT_NAMESPACE
from machi.install.events import root_fingerprint
from machi.kernel.build import BuildIdentity
from machi.kernel.clock import Clock, SystemClock
from machi.kernel.errors import ConflictError, NotFoundError, ValidationError
from machi.kernel.ids import InstallId, LocalOwnershipId
from machi.kernel.store import Store


class InstallIdentity:
    """Stable installation identity. Never scans, never deletes, never runs."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def establish(
        self,
        binding: StateRootBinding,
        establishment: LocalOwnershipEstablishment,
        registry: LocalOwnershipRegistryEstablishment,
        store: Store,
        build: BuildIdentity,
    ) -> InstallRecordEstablishment:
        """Create or return the InstallRecord for this coherent evidence.

        Consumes binding, local marker, and registry seed results. Does
        not resolve a root, write a marker, or seed the registry.
        """
        self._require_local_evidence(establishment)
        self._require_registry_evidence(registry)
        marker = establishment.marker
        record = registry.record
        expected = root_fingerprint(binding.root)
        if marker.root_fingerprint != expected:
            raise ConflictError(
                "state-root binding and local ownership evidence do not agree; "
                "refusing to mint an InstallId for conflicting evidence",
            )
        if record.root_fingerprint != expected:
            raise ConflictError(
                "state-root binding and control-plane registry evidence do "
                "not agree; refusing to mint an InstallId for conflicting evidence",
            )
        if record.marker_id != marker.marker_id:
            raise ConflictError(
                "local marker identity and registry identity do not agree; "
                "refusing to mint an InstallId for conflicting evidence",
            )
        if marker.product != PRODUCT_NAMESPACE or record.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "ownership evidence belongs to a different product; "
                "refusing to mint an InstallId",
            )
        key = marker.marker_id.value
        try:
            existing = store.get(InstallRecord, key)
        except NotFoundError:
            created = InstallRecord(
                install_id=InstallId.generate(),
                product=PRODUCT_NAMESPACE,
                marker_id=marker.marker_id,
                root_fingerprint=expected,
                created_at=self._clock.now(),
                created_by_version=build.version,
                created_by_origin=build.origin.value,
                created_by_build_id=build.build_id,
                created_by_source_commit=build.source_commit,
                created_by_clean_source=build.clean_source,
            )
            result = store.create(key, created)
            persisted = store.get(InstallRecord, key)
            return self._result(
                persisted, created=result.created, existed=result.existed
            )
        return self._existing(existing, marker.marker_id, expected)

    def _existing(
        self,
        existing: InstallRecord,
        marker_id: LocalOwnershipId,
        expected_fingerprint: str,
    ) -> InstallRecordEstablishment:
        if existing.marker_id != marker_id:
            raise ConflictError(
                "install record identity does not match the local marker; "
                "refusing to overwrite",
            )
        if existing.root_fingerprint != expected_fingerprint:
            raise ConflictError(
                "install record already exists and does not match this "
                "ownership evidence; refusing to overwrite",
            )
        if existing.product != PRODUCT_NAMESPACE:
            raise ConflictError(
                "install record belongs to a different product; refusing to overwrite",
                product=existing.product,
            )
        return self._result(existing, created=False, existed=True)

    def _require_local_evidence(
        self, establishment: LocalOwnershipEstablishment
    ) -> None:
        if establishment.status is not LocalOwnershipStatus.LOCAL_MARKER_PRESENT:
            raise ValidationError(
                "install record requires local_marker_present evidence",
                status=establishment.status.value,
            )
        if establishment.dual_ownership or establishment.destructive_authorization:
            raise ValidationError(
                "install record refuses synthetic dual-proof or delete authority",
            )

    def _require_registry_evidence(
        self, registry: LocalOwnershipRegistryEstablishment
    ) -> None:
        if registry.status is not RegistrySeedStatus.REGISTRY_SEED_PRESENT:
            raise ValidationError(
                "install record requires registry_seed_present evidence",
                status=registry.status.value,
            )
        if registry.dual_ownership or registry.destructive_authorization:
            raise ValidationError(
                "install record refuses synthetic dual-proof or delete authority",
            )

    def _result(
        self,
        record: InstallRecord,
        *,
        existed: bool,
        created: bool,
    ) -> InstallRecordEstablishment:
        return InstallRecordEstablishment(
            record=record,
            status=InstallRecordStatus.INSTALL_RECORD_PRESENT,
            dual_ownership=False,
            destructive_authorization=False,
            existed=existed,
            created=created,
        )
